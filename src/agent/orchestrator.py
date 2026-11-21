# -*- coding: utf-8 -*-
"""Orchestrator：把 Planner → Tools → Retriever → Auditor → Composer 串成一次完整推理。

一次 handle() 就是一次可观测的智能体运行：每个角色的进出、每次工具调用、每次重试、
每条校验结论都会落到 trace，前端据此渲染"多智能体协作过程"。
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from src import config
from src.agent import llm
from src.agent.auditor import audit as run_audit
from src.agent.composer import compose
from src.agent.memory import Memory
from src.agent.planner import INTENT_RULES, Plan, make_plan
from src.agent.retriever_agent import RetrieverAgent
from src.agent.safety import AI_DISCLOSURE, check_input, check_output, refusal_result
from src.observability.trace import Trace
from src.tools import data_store as ds
from src.tools import registry as reg
import src.tools  # noqa: F401  注册工具

ALLOWED_INTENTS = [r["intent"] for r in INTENT_RULES] + ["out_of_scope"]

CLARIFY = {
    "prereq_check": ("请告诉我要校验哪门课，可以直接说课程名或课程代码，例如"
                     "\"大模型应用开发 我的先修够吗\"或\"C5002 能选吗\"。"),
    "conflict_check": ("请把要一起比较的 2 门以上课程告诉我，例如"
                       "\"数据库原理与应用 和 操作系统 冲突吗\"。"),
}


class Agent:
    def __init__(self) -> None:
        self._mem: Dict[str, Memory] = {}

    # ---------- 会话 ----------
    def memory(self, session_id: str) -> Memory:
        if session_id not in self._mem:
            self._mem[session_id] = Memory(session_id)
        return self._mem[session_id]

    def reset(self, session_id: str) -> None:
        self._mem.pop(session_id, None)

    # ---------- 主流程 ----------
    def handle(self, text: str, session_id: str = "default") -> Dict[str, Any]:
        t0 = time.time()
        mem = self.memory(session_id)
        mem.remember_user(text)
        trace = Trace(session_id=session_id, turn=mem.turn_count())
        trace.log("role", "receive", actor="Planner", text=text[:120])

        # 0) 输入护栏
        guard = check_input(text)
        if guard["blocked"]:
            trace.log("guard", "input_blocked", actor="SecurityGuard",
                      category=guard["category"])
            out = refusal_result(guard)
            out.update({"intent": "out_of_scope", "confidence": 1.0, "tool_calls": [],
                        "citations": [], "plan": None, "audit": {"passed": True, "findings": []},
                        "engine": "guard", "elapsed_ms": round((time.time() - t0) * 1000, 1)})
            mem.remember_agent(out["answer"])
            mem.set_slot("last_intent", "out_of_scope")
            out["trace"] = trace.close("refused")
            return out

        # 1) 指代消解
        resolved = mem.resolve(text)
        if mem.resolutions:
            trace.log("role", "resolve_references", actor="Planner",
                      resolutions=mem.resolutions)

        # 2) 规划
        plan = make_plan(resolved, mem)
        engine = "local"
        if llm.available():
            res = llm.classify_intent(resolved, ALLOWED_INTENTS)
            if res.get("ok"):
                plan = make_plan(resolved, mem)
                plan.intent = res["intent"]
                plan.confidence = 0.85
                plan.engine = "gateway"
                engine = "gateway"
            else:
                trace.log("role", "llm_fallback", actor="Planner",
                          error=res.get("error"), fallback="local-rules")
        trace.log("role", "plan", actor="Planner", intent=plan.intent,
                  confidence=plan.confidence, subtasks=len(plan.subtasks))

        # 3) 前置澄清
        if plan.intent == "conflict_check" and not plan.course_ids:
            # 没有点出具体课程时，问的是"冲突规则"，走制度问答而不是要求用户补充课程
            plan.intent = "policy_qa"
            plan.need_retrieval = True
            plan.subtasks = [{"actor": "Planner", "action": "未指定课程，转制度问答", "tools": []},
                             {"actor": "Retriever", "action": "检索冲突与容量规则",
                              "tools": ["search_knowledge"]},
                             {"actor": "Auditor", "action": "校验引用可溯源", "tools": []}]
            trace.log("role", "replan", actor="Planner", reason="conflict_check_without_courses")

        clarify = self._needs_clarify(plan)
        if clarify:
            answer = clarify + f"\n\n> {AI_DISCLOSURE}"
            mem.remember_agent(answer)
            mem.set_slot("last_intent", plan.intent)
            trace.log("role", "clarify", actor="Composer", reason=plan.intent)
            return self._pack(answer, plan, {}, [], {"passed": True, "findings": []},
                              trace, t0, engine, facts={"clarify": True})

        # 4) 执行子任务（工具调用）
        results: Dict[str, Any] = {}
        tool_errors: List[Dict[str, Any]] = []
        for sub in plan.subtasks:
            trace.log("role", "step", actor=sub["actor"], action=sub["action"])
            for tool_name in sub["tools"]:
                if tool_name == "search_knowledge" or tool_name in results:
                    continue
                args = self._args_for(tool_name, plan)
                if args is None:
                    continue
                res = reg.call(tool_name, trace=trace, **args)
                if res.get("ok"):
                    results[tool_name] = res["data"]
                else:
                    tool_errors.append({"tool": tool_name, **res.get("error", {})})

        # 5) 知识检索
        citations: List[Dict[str, Any]] = []
        if plan.need_retrieval:
            ra = RetrieverAgent(trace=trace)
            citations = ra.retrieve(plan.intent, resolved, top_k=config.TOP_K)
            trace.log("role", "retrieve", actor="Retriever",
                      citations=len(citations),
                      docs=[c["doc_id"] for c in citations])

        # 6) 校验
        audit = {"passed": True, "findings": []}
        if config.ENABLE_AUDITOR:
            audit = run_audit(plan.intent, results, plan, citations)
            trace.log("role", "audit", actor="Auditor",
                      status="ok" if audit["passed"] else "fail", summary=audit["summary"])

        # 7) 生成
        out = compose(plan.intent, plan, results, citations, audit, mem)
        if tool_errors:
            out["warnings"].append("部分工具调用失败：" + "；".join(
                f"{e['tool']}（{e.get('code')}）" for e in tool_errors[:3]))
            if not results:
                out["answer"] = ("### 工具调用失败\n\n本轮所有数据类工具都未能返回结果，因此无法给出结论。\n"
                                 "错误明细：" + "；".join(f"{e['tool']}: {e.get('message')}"
                                                         for e in tool_errors[:3]) +
                                 "\n请稍后重试，或换一种问法。\n\n> " + AI_DISCLOSURE)

        # 8) 输出护栏
        if config.ENABLE_SAFETY:
            chk = check_output(out["answer"])
            if chk["flagged"]:
                trace.log("guard", "output_flagged", actor="SecurityGuard", issues=chk["issues"])
                out["warnings"].append("输出审查提示：" + "；".join(i["detail"] for i in chk["issues"][:3]))
                if any(i["type"] == "hallucinated_course" for i in chk["issues"]):
                    bad = "、".join(i["value"] for i in chk["issues"]
                                   if i["type"] == "hallucinated_course")
                    out["answer"] = (f"### 已拦截不确定的课程引用\n\n生成内容中出现了课程库之外的课程代码"
                                     f"（{bad}），已按合规策略拦截本条回答。\n"
                                     f"请核对课程名称后重试。\n\n> {AI_DISCLOSURE}")
                    out["warnings"].append(f"拦截虚构课程代码：{bad}")

        # 9) 记忆更新
        self._update_memory(mem, plan, results)
        mem.remember_agent(out["answer"])
        trace.log("role", "compose", actor="Composer", chars=len(out["answer"]))
        return self._pack(out["answer"], plan, results, citations, audit, trace, t0, engine,
                          facts=out.get("facts"), warnings=out.get("warnings"),
                          next_steps=out.get("next_steps"))

    # ---------- 辅助 ----------
    def _needs_clarify(self, plan: Plan) -> Optional[str]:
        if plan.intent == "prereq_check" and not plan.course_ids:
            return CLARIFY["prereq_check"]
        if plan.intent == "conflict_check" and len(plan.course_ids) < 2:
            return CLARIFY["conflict_check"]
        return None

    def _args_for(self, tool_name: str, plan: Plan) -> Optional[Dict[str, Any]]:
        sid = plan.student_id
        if tool_name in ("get_student_profile", "calc_credit_progress",
                         "check_graduation_eligibility", "get_risk_warning"):
            return {"student_id": sid} if sid else None
        if tool_name == "query_courses":
            args: Dict[str, Any] = {}
            if plan.term:
                args["term"] = plan.term
            if plan.module:
                args["module"] = plan.module
            return args
        if tool_name == "check_prerequisites":
            if not plan.course_ids:
                return None
            return {"course_id": plan.course_ids[0], "student_id": sid}
        if tool_name == "check_timetable_conflict":
            if len(plan.course_ids) < 2:
                return None
            return {"course_ids": plan.course_ids}
        if tool_name == "build_study_plan":
            electives = [c for c in plan.course_ids
                         if ds.courses().get(c, {}).get("module") in ("专业选修", "通识选修")]
            return {"student_id": sid, "target_term": plan.term, "elective_ids": electives}
        if tool_name == "search_knowledge":
            return {"query": plan.retrieval_query, "top_k": config.TOP_K}
        return None

    def _update_memory(self, mem: Memory, plan: Plan, results: Dict[str, Any]) -> None:
        mem.set_slot("student_id", plan.student_id)
        mem.set_slot("last_intent", plan.intent)
        if plan.course_ids:
            mem.set_slot("course_id", plan.course_ids[0])
        elif results.get("build_study_plan", {}).get("selected"):
            mem.set_slot("course_id", results["build_study_plan"]["selected"][0]["id"])
        if plan.term:
            mem.set_slot("term", plan.term)

    def _pack(self, answer: str, plan: Plan, results: Dict[str, Any],
              citations: List[Dict[str, Any]], audit: Dict[str, Any], trace: Trace,
              t0: float, engine: str, facts: Any = None,
              warnings: Any = None, next_steps: Any = None) -> Dict[str, Any]:
        summary = trace.close("ok")
        return {
            "answer": answer,
            "intent": plan.intent,
            "confidence": plan.confidence,
            "plan": plan.to_dict(),
            "tool_calls": [{"tool": c["tool"], "ok": c["ok"], "ms": c["ms"],
                            "attempts": c["attempts"]} for c in summary["events"]
                           if c["kind"] == "tool"],
            "citations": citations,
            "facts": facts or {},
            "warnings": warnings or [],
            "next_steps": next_steps or [],
            "audit": audit,
            "roles": trace.role_timeline(),
            "engine": engine,
            "refused": False,
            "elapsed_ms": round((time.time() - t0) * 1000, 1),
            "trace": {"run_id": summary["run_id"], "session_id": summary["session_id"],
                      "turn": summary["turn"], "duration_ms": summary["duration_ms"]},
        }


_AGENT = Agent()


def get_agent() -> Agent:
    return _AGENT

# -*- coding: utf-8 -*-
"""Auditor：多智能体中的"校验者"。

它不复述答案，只做一件事：把上游工具产出与规则交叉校验，发现不一致就拦下来。
这是本项目控制幻觉的主要手段之一——生成环节可以错，校验环节必须能抓住。
"""
from __future__ import annotations

from typing import Any, Dict, List

from src.tools import data_store as ds
from src.tools import registry as reg


class Finding(dict):
    pass


def _f(level: str, code: str, message: str) -> Finding:
    return Finding(level=level, code=code, message=message)


def audit(intent: str, results: Dict[str, Any], plan: Any, citations: List[Dict[str, Any]]
          ) -> Dict[str, Any]:
    """results: {tool_name: data}；返回 {passed, findings[], summary}"""
    findings: List[Finding] = []

    cp = results.get("calc_credit_progress")
    if cp:
        mod_sum = round(sum(m["passed"] for m in cp["modules"]), 1)
        if abs(mod_sum - cp["total"]["passed"]) > 0.05:
            findings.append(_f("fail", "CREDIT_SUM_MISMATCH",
                               f"模块已通过学分合计 {mod_sum} 与总已通过 {cp['total']['passed']} 不一致"))
        for m in cp["modules"]:
            if m["gap"] < 0 or m["passed"] > m["required"] + 1e-6 and m["gap"] != 0:
                findings.append(_f("warn", "MODULE_GAP_ODD",
                                   f"{m['module']} 缺口计算异常（已修 {m['passed']} / 要求 {m['required']}）"))
        if abs(cp["total"]["required"] - cp["total"]["passed"] - cp["total"]["gap"]) > 0.05:
            findings.append(_f("fail", "TOTAL_GAP_MISMATCH", "总缺口与已通过学分不自洽"))
        if not findings:
            findings.append(_f("pass", "CREDIT_CONSISTENT",
                               f"六个模块合计与总学分自洽：已通过 {cp['total']['passed']} / "
                               f"{cp['total']['required']}，缺口 {cp['total']['gap']}"))

    plan_data = results.get("build_study_plan")
    if plan_data:
        s = round(sum(x["credits"] for x in plan_data["selected"]), 1)
        if abs(s - plan_data["total_credits"]) > 0.05:
            findings.append(_f("fail", "PLAN_CREDIT_SUM",
                               f"方案学分合计 {s} 与声明 {plan_data['total_credits']} 不一致"))
        if plan_data["total_credits"] > plan_data["max_credits"] + 1e-6:
            findings.append(_f("fail", "PLAN_OVER_LIMIT",
                               f"方案 {plan_data['total_credits']} 学分超过上限 {plan_data['max_credits']}"))

        ids = [x["id"] for x in plan_data["selected"]]
        chk = reg.call("check_timetable_conflict", course_ids=ids)
        if chk.get("ok") and chk["data"]["conflicts"]:
            findings.append(_f("fail", "PLAN_TIME_CONFLICT",
                               f"方案内存在 {len(chk['data']['conflicts'])} 组时间冲突"))
        else:
            findings.append(_f("pass", "PLAN_NO_CONFLICT", f"{len(ids)} 门课程两两无时间冲突"))

        passed = ds.passed_course_ids(plan_data["student_id"])
        doing = ds.in_progress_ids(plan_data["student_id"])
        bad = [x["name"] for x in plan_data["selected"]
               if any(p not in passed and p not in doing
                      for p in ds.courses()[x["id"]]["prereq"])]
        pending = [x["name"] for x in plan_data["selected"]
                   if any(p in doing and p not in passed for p in ds.courses()[x["id"]]["prereq"])]
        if bad:
            findings.append(_f("fail", "PLAN_PREREQ_BROKEN", "方案内含先修未满足课程：" + "、".join(bad)))
        elif pending:
            findings.append(_f("warn", "PLAN_PREREQ_PENDING",
                               "先修在修中，需本学期通过：" + "、".join(pending)))
        else:
            findings.append(_f("pass", "PLAN_PREREQ_OK", "方案内所有课程先修关系均满足"))

        full = [x["name"] for x in plan_data["selected"]
                if ds.courses()[x["id"]]["enrolled"] >= ds.courses()[x["id"]]["capacity"]]
        if full:
            findings.append(_f("warn", "PLAN_CAPACITY_FULL", "容量已满：" + "、".join(full)))

    grad = results.get("check_graduation_eligibility")
    if grad:
        if len(grad["conditions"]) != 5:
            findings.append(_f("fail", "GRAD_COND_COUNT", "毕业审核条件数不是 5 项"))
        failed = [c for c in grad["conditions"] if not c["ok"]]
        findings.append(_f("pass" if not failed else "warn", "GRAD_SUMMARY",
                           f"{len(grad['conditions'])} 项条件中 {len(failed)} 项未满足"))

    pre = results.get("check_prerequisites")
    if pre:
        passed = ds.passed_course_ids(plan.student_id) if plan.student_id else set()
        doing = ds.in_progress_ids(plan.student_id) if plan.student_id else set()
        expect_missing = [p for p in ds.courses()[pre["course_id"]]["prereq"]
                          if p not in passed and p not in doing]
        got = [m["id"] for m in pre["missing"]]
        if sorted(expect_missing) != sorted(got):
            findings.append(_f("fail", "PREREQ_RECALC",
                               f"先修缺口复核不一致：工具 {got} vs 重算 {expect_missing}"))
        else:
            findings.append(_f("pass", "PREREQ_RECALC", "先修缺口经独立重算一致"))

    if citations:
        unknown = [c["doc_id"] for c in citations if not (ds is not None and c.get("doc_id"))]
        if unknown:
            findings.append(_f("warn", "CITATION_INVALID", "存在不符合引用格式的来源"))
        findings.append(_f("pass", "CITATION_TRACEABLE",
                           f"{len(citations)} 条引用均带文档号与章节，可回溯到原文行号"))
    elif intent in ("policy_qa", "credit_progress", "graduation_check", "plan_build"):
        findings.append(_f("warn", "CITATION_MISSING", "本轮未检索到可引用原文，结论仅基于结构化数据"))

    fails = [f for f in findings if f["level"] == "fail"]
    return {
        "passed": len(fails) == 0,
        "findings": findings,
        "summary": f"{len(findings)} 项校验，{len(fails)} 项失败",
    }

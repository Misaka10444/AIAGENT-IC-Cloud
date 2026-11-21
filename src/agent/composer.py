# -*- coding: utf-8 -*-
"""Composer：把多智能体的结构化产出汇总成面向学生的回答。

原则：能用表格就不堆段落；每个数字都要能指到工具或原文；不确定就说不确定。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.agent.safety import AI_DISCLOSURE
from src.tools import data_store as ds


def _cite_block(citations: List[Dict[str, Any]], top: int = 3) -> str:
    if not citations:
        return "\n\n> 依据：本轮未检索到知识库原文，结论仅来自结构化数据核算。"
    lines = ["\n\n**依据（可溯源）**"]
    for c in citations[:top]:
        lines.append(f"- `{c['doc_id']} §{c['section']}` 原文第 {c['line_start']} 行：{c['snippet']}")
    return "\n".join(lines)


def _module_table(cp: Dict[str, Any]) -> str:
    rows = ["| 模块 | 要求学分 | 已通过 | 缺口 | 状态 |", "| --- | --- | --- | --- | --- |"]
    for m in cp["modules"]:
        rows.append(f"| {m['module']} | {m['required']:g} | {m['passed']:g} | {m['gap']:g} | {m['status']} |")
    t = cp["total"]
    rows.append(f"| **合计** | **{t['required']:g}** | **{t['passed']:g}** | **{t['gap']:g}** | "
                f"{'达标' if t['gap'] == 0 else '未达标'} |")
    return "\n".join(rows)


def compose(intent: str, plan: Any, results: Dict[str, Any], citations: List[Dict[str, Any]],
            audit: Dict[str, Any], memory: Any = None) -> Dict[str, Any]:
    facts: Dict[str, Any] = {}
    warnings: List[str] = []
    next_steps: List[str] = []
    parts: List[str] = []

    prof = results.get("get_student_profile")
    sid = plan.student_id if plan else None
    who = f"{prof['alias']}（{prof['student_id']}）" if prof else (sid or "")

    # ---------------- 学分进度 ----------------
    if intent == "credit_progress" and results.get("calc_credit_progress"):
        cp = results["calc_credit_progress"]
        t = cp["total"]
        parts.append(f"### {who}学分进度\n")
        parts.append(_module_table(cp))
        parts.append(f"\n总学分 **{t['passed']:g} / {t['required']:g}**，缺口 **{t['gap']:g}** 学分。")
        if cp["failed"]:
            names = "、".join(f"{f['name']}（{f['score']} 分）" for f in cp["failed"])
            parts.append(f"\n**未通过课程（{len(cp['failed'])} 门）**：{names}。"
                         f"未通过学分不计入达标学分，须补考或重修。")
        gap_mods = [m["module"] for m in cp["modules"] if m["gap"] > 0]
        if gap_mods:
            parts.append(f"\n**存在缺口的模块**：{'、'.join(gap_mods)}。按培养方案，模块学分不可互相替代。")
        facts = {"total_gap": t["gap"], "total_passed": t["passed"], "total_required": t["required"],
                 "failed_count": len(cp["failed"]), "modules_below": gap_mods}
        next_steps = ["查看未通过课程的重修安排", "生成下一学期修读方案以补齐缺口"]

    # ---------------- 先修校验 ----------------
    elif intent == "prereq_check" and results.get("check_prerequisites"):
        pre = results["check_prerequisites"]
        ok = pre["ok"]
        parts.append(f"### 《{pre['course_name']}》先修校验\n")
        if ok:
            parts.append("先修条件 **满足**，可以选课。")
            if pre["prereq"]:
                parts.append("已满足的先修：" + "、".join(p["name"] for p in pre["prereq"]) + "。")
            if pre.get("pending"):
                parts.append("\n**待确认**：" + "、".join(f"《{p['name']}》" for p in pre["pending"]) +
                             " 目前处于在修状态，需本学期考核通过后先修才最终成立。")
        else:
            parts.append(f"先修条件 **不满足**，缺少 {len(pre['missing'])} 门："
                         + "、".join(f"《{m['name']}》（{m['id']}）" for m in pre["missing"]) + "。")
            if pre.get("pending"):
                parts.append("另有在修课程：" + "、".join(f"《{p['name']}》" for p in pre["pending"]) +
                             "，通过后方可计入。")
            parts.append("按培养方案，先修未通过时无法正常修读该课程，建议先完成缺口课程。")
        facts = {"prereq_ok": ok, "missing_ids": [m["id"] for m in pre["missing"]],
                 "pending_ids": [p["id"] for p in pre.get("pending", [])],
                 "course_id": pre["course_id"]}
        next_steps = ["查询该先修课程的开课学期" if not ok else "确认本学期教学班余量"]

    # ---------------- 时间冲突 ----------------
    elif intent == "conflict_check" and results.get("check_timetable_conflict"):
        cf = results["check_timetable_conflict"]
        parts.append("### 时间冲突检测\n")
        if cf["ok"]:
            parts.append(f"{len(cf['checked'])} 门课程两两比对完成，**未发现上课时间重叠**。")
        else:
            parts.append(f"发现 **{len(cf['conflicts'])} 组冲突**：\n")
            lines = ["| 课程A | 时隙 | 课程B | 时隙 | 重叠节次 |", "| --- | --- | --- | --- | --- |"]
            for c in cf["conflicts"]:
                lines.append(f"| {c['a_name']} | {c['slot_a']} | {c['b_name']} | {c['slot_b']} | "
                             f"周{c['day']} 第{'、'.join(map(str, c['periods']))}节 |")
            parts.append("\n".join(lines))
            parts.append("\n按选课办法，时间重叠的课程系统会拒绝同时选中，需要错开或更换教学班。")
        if cf.get("unscheduled"):
            parts.append("\n**需人工核对**：" + "、".join(
                f"{u['name']}（{u['slot']}）" for u in cf["unscheduled"]) + " 为集中/线上安排，不参与时隙比对。")
        facts = {"conflict_count": len(cf["conflicts"]),
                 "pairs": [f"{c['a']}-{c['b']}" for c in cf["conflicts"]]}

    # ---------------- 修读方案 ----------------
    elif intent == "plan_build" and results.get("build_study_plan"):
        pl = results["build_study_plan"]
        parts.append(f"### 第 {pl['target_term']} 学期修读方案（{who}）\n")
        if not pl["selected"]:
            parts.append("未匹配到可修课程，请核对目标学期或先修情况。")
        else:
            lines = ["| 课程 | 学分 | 模块 | 时隙 | 类型 | 加入理由 |",
                     "| --- | --- | --- | --- | --- | --- |"]
            for s in pl["selected"]:
                lines.append(f"| {s['name']} | {s['credits']:g} | {s['module']} | {s['slot']} | "
                             f"{s['role']} | {s['reason']} |")
            parts.append("\n".join(lines))
            parts.append(f"\n合计 **{pl['total_credits']:g}** 学分（上限 {pl['max_credits']:g}）。")
        if pl["excluded"]:
            parts.append("\n**未纳入及原因**：")
            for e in pl["excluded"][:6]:
                parts.append(f"- {e['name']}：{e['reason']}")
        if pl["risks"]:
            warnings.extend(pl["risks"])
        facts = {"total_credits": pl["total_credits"], "course_count": len(pl["selected"]),
                 "target_term": pl["target_term"],
                 "course_ids": [s["id"] for s in pl["selected"]]}
        next_steps = ["在补退选阶段按此方案选课", "对方案内课程再做一次冲突复核"]

    # ---------------- 毕业资格 ----------------
    elif intent == "graduation_check" and results.get("check_graduation_eligibility"):
        g = results["check_graduation_eligibility"]
        parts.append(f"### 毕业资格审核（{who}）\n")
        parts.append("结论：**" + ("五项条件全部满足，可进入毕业审核流程。" if g["eligible"]
                                else f"暂不满足，{g['failed_count']} 项条件未通过。") + "**\n")
        lines = ["| 序号 | 条件 | 结论 | 说明 |", "| --- | --- | --- | --- |"]
        for c in g["conditions"]:
            lines.append(f"| {c['no']} | {c['item']} | {'通过' if c['ok'] else '未通过'} | {c['detail']} |")
        parts.append("\n".join(lines))
        facts = {"eligible": g["eligible"], "failed_count": g["failed_count"],
                 "failed_items": [c["item"] for c in g["conditions"] if not c["ok"]]}
        next_steps = ["对未通过条件逐项补齐" if not g["eligible"] else "准备审核材料清单"]

    # ---------------- 学业预警 ----------------
    elif intent == "risk_warn" and results.get("get_risk_warning"):
        r = results["get_risk_warning"]
        parts.append(f"### 学业预警评估（{who}）\n")
        parts.append(f"预警等级：**{r['level']}**")
        if r["level"] != "无":
            parts.append("\n触发原因：" + "；".join(r["reasons"]))
            parts.append("\n建议措施：" + "；".join(r["actions"]))
        else:
            parts.append(f"\n应修必修 {r['should_have']:g} 学分，已通过 {r['passed_in_plan']:g} 学分，"
                         f"进度缺口 {r['progress_gap']:g} 学分，未触达预警线。")
        facts = {"level": r["level"], "failed_count": r["failed_count"],
                 "progress_gap": r["progress_gap"], "credit_gap": r["credit_gap"]}

    # ---------------- 课程查询 ----------------
    elif intent == "course_query" and results.get("query_courses"):
        q = results["query_courses"]
        parts.append(f"### 课程查询结果（{q['count']} 门）\n")
        if q["count"]:
            lines = ["| 课程代码 | 课程 | 学分 | 模块 | 学期 | 时隙 | 余量 |",
                     "| --- | --- | --- | --- | --- | --- | --- |"]
            for c in q["courses"][:15]:
                lines.append(f"| {c['id']} | {c['name']} | {c['credits']:g} | {c['module']} | "
                             f"{c['term'] or '选修池'} | {c['slot']} | {c['seats_left']} |")
            parts.append("\n".join(lines))
            if q["count"] > 15:
                parts.append(f"\n仅展示前 15 门，共 {q['count']} 门。")
        else:
            parts.append("没有匹配的课程，换一个筛选条件试试。")
        facts = {"course_count": q["count"]}

    # ---------------- 画像 ----------------
    elif intent == "profile_query" and results.get("get_student_profile"):
        p = results["get_student_profile"]
        parts.append(f"### {p['alias']}（{p['student_id']}）画像\n")
        parts.append(f"- 年级专业：{p['grade']} 级 {p['major']}，当前第 {p['current_term']} 学期")
        parts.append(f"- 目标：{p['goal']}；方向：{p['target_direction']}")
        parts.append(f"- 选课偏好：回避时隙 {p['preferences'].get('avoid_slot') or '无'}，"
                     f"每学期上限 {p['preferences'].get('max_credits_per_term')} 学分")
        parts.append(f"- 已修课程 {p['completed_count']} 门，未通过 {len(p['failed_courses'])} 门")
        if p["note"]:
            parts.append(f"- 备注：{p['note']}")
        facts = {"alias": p["alias"], "goal": p["goal"], "failed_count": len(p["failed_courses"])}

    # ---------------- 寒暄 ----------------
    elif intent == "greeting":
        parts.append("### 我是云梯 · 学业规划与选课顾问\n")
        parts.append("我可以做四类事：")
        parts.append("1. **学分核算**：按六个模块算清已通过学分、缺口与未通过课程；")
        parts.append("2. **修读规划**：在先修、时间冲突、学分上限、容量、偏好五类约束下生成学期方案；")
        parts.append("3. **资格校验**：先修是否满足、毕业资格五项条件逐项判定、学业预警等级；")
        parts.append("4. **制度问答**：培养方案、选课办法、重修与学分认定、毕业审核的规定依据，逐条给出原文出处。")
        parts.append("\n你可以直接说：\"S001 下学期怎么选课\"、\"C5002 我的先修够吗\"、\"S003 能毕业吗\"。")
        facts = {"intent": "greeting"}

    # ---------------- 制度问答（兜底） ----------------
    else:
        if citations:
            parts.append("### 依据知识库的回答\n")
            for i, c in enumerate(citations[:3], 1):
                parts.append(f"**{i}. `{c['doc_id']} §{c['section']}`**\n{c['snippet']}\n")
            parts.append("\n以上为知识库原文摘录。如果你的问题涉及具体个人（学分、先修、冲突、毕业），"
                         "告诉我学生代号（S001—S003）和课程，我可以直接核算。")
        else:
            parts.append("### 没有找到依据\n")
            parts.append("知识库里没有检索到与你问题相关的内容。我不会在无依据的情况下给结论。"
                         "你可以换个说法，或者问这几类问题：学分进度、先修校验、时间冲突、选课方案、毕业资格。")
        facts = {"citation_docs": [c["doc_id"] for c in citations[:3]]}

    # ---------------- 校验与风险汇总 ----------------
    fails = [f for f in audit.get("findings", []) if f["level"] == "fail"]
    if fails:
        warnings.append("内部校验未通过：" + "；".join(f["message"] for f in fails))
    warn_findings = [f for f in audit.get("findings", []) if f["level"] == "warn"]
    for w in warn_findings[:2]:
        warnings.append(w["message"])

    body = "\n".join(parts)
    if intent != "policy_qa":
        body += _cite_block(citations)
    if warnings:
        body += "\n\n**风险与待确认**\n" + "\n".join(f"- {w}" for w in dict.fromkeys(warnings))
    if next_steps:
        body += "\n\n**下一步建议**\n" + "\n".join(f"- {s}" for s in dict.fromkeys(next_steps))
    body += f"\n\n> {AI_DISCLOSURE}"

    return {
        "answer": body,
        "facts": facts,
        "warnings": list(dict.fromkeys(warnings)),
        "next_steps": list(dict.fromkeys(next_steps)),
        "citations": citations,
        "ai_disclosure": AI_DISCLOSURE,
        "refused": False,
    }

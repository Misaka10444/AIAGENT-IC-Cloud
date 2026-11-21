# -*- coding: utf-8 -*-
"""规划类工具：在学分上限、时间冲突、先修关系、容量、偏好五类约束下生成学期修读方案。

这不是简单的"把课程列出来"，而是贪心 + 约束校验：
必修优先 → 重修次之 → 选修最后；每加入一门课都要重新验证冲突与学分上限；
被排除的课程必须给出可解释的原因（这正是答辩时能讲清楚的部分）。
"""
from __future__ import annotations

from typing import Any, Dict, List

from src.tools import data_store as ds
from src.tools.registry import ToolError, tool

PRIORITY = {"专业核心": 0, "专业基础": 1, "集中实践": 2, "通识必修": 3, "专业选修": 4, "通识选修": 5}


def _conflict_with(selected: List[Dict[str, Any]], cand: Dict[str, Any]) -> Dict[str, Any] | None:
    cs = ds.parse_slot(cand["slot"])
    if not cs:
        return None
    for s in selected:
        ss = ds.parse_slot(s["slot"])
        if ss and ss[0] == cs[0] and ss[1] & cs[1]:
            return {"with": s["name"], "slot": s["slot"], "candidate_slot": cand["slot"]}
    return None


@tool(
    name="build_study_plan",
    description="生成指定学期的修读方案：满足先修、避开时间冲突、不超学分上限与容量，并给出取舍理由。",
    params={
        "student_id": {"type": "string", "required": True, "desc": "学生代号"},
        "target_term": {"type": "integer", "required": False, "desc": "目标学期 1-8，默认当前学期"},
        "elective_ids": {"type": "array", "required": False, "default": [],
                         "desc": "希望额外加入的专业选修/通识选修课程代码"},
    },
    returns="{target_term, selected:[{id,name,credits,slot,role,reason}], total_credits, excluded:[{id,name,reason}], risks:[]}",
    raises=["STUDENT_NOT_FOUND", "COURSE_NOT_FOUND", "INVALID_TERM"],
)
def build_study_plan(student_id: str, target_term: Any = None,
                     elective_ids: List[str] | None = None) -> Dict[str, Any]:
    st = ds.student(student_id)
    target_term = int(target_term) if target_term is not None else int(st["current_term"])
    if not 1 <= target_term <= 8:
        raise ToolError("INVALID_TERM", "学期必须在 1-8 之间")

    passed = ds.passed_course_ids(student_id)
    doing = ds.in_progress_ids(student_id)
    attempted = ds.all_attempted_course_ids(student_id)
    prefs = st.get("preferences", {})
    max_credits = float(prefs.get("max_credits_per_term", 26))
    avoid = set(prefs.get("avoid_slot", []))

    selected: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []
    risks: List[str] = []
    total = 0.0

    def try_add(cid: str, role: str, reason: str) -> bool:
        nonlocal total
        c = ds.courses()[cid]
        if total + c["credits"] > max_credits:
            excluded.append({"id": cid, "name": c["name"],
                             "reason": f"超出本学期学分上限 {max_credits:g}（已选 {total:g}）"})
            return False
        miss = [p for p in c["prereq"] if p not in passed and p not in doing]
        if miss:
            names = "、".join(ds.courses().get(p, {}).get("name", p) for p in miss)
            excluded.append({"id": cid, "name": c["name"], "reason": f"先修未满足：{names}"})
            return False
        pending = [p for p in c["prereq"] if p in doing and p not in passed]
        if pending:
            names = "、".join(ds.courses().get(p, {}).get("name", p) for p in pending)
            risks.append(f"《{c['name']}》的先修《{names}》在修中，需本学期通过方可修读")
        conf = _conflict_with(selected, c)
        if conf:
            excluded.append({"id": cid, "name": c["name"],
                             "reason": f"与《{conf['with']}》时间冲突（{conf['slot']}）"})
            return False
        if c["enrolled"] >= c["capacity"]:
            excluded.append({"id": cid, "name": c["name"], "reason": "容量已满"})
            return False
        if c["slot"] in avoid:
            excluded.append({"id": cid, "name": c["name"],
                             "reason": f"命中偏好回避时隙 {c['slot']}"})
            return False
        selected.append({"id": cid, "name": c["name"], "credits": c["credits"],
                         "module": c["module"], "slot": c["slot"], "role": role,
                         "reason": reason})
        total = round(total + c["credits"], 1)
        return True

    # 1) 未通过且本学期开课 → 重修优先
    failed_all = [c for c in st["completed"] if not ds.is_pass(c["score"])]
    for f in failed_all:
        cid = f["course_id"]
        c = ds.courses().get(cid)
        if not c:
            continue
        if c["term"] == target_term:
            try_add(cid, "重修", f"第 {c['term']} 学期课程未通过（{f['score']} 分），本学期须重修")
        else:
            excluded.append({"id": cid, "name": c["name"],
                             "reason": f"未通过课程，但本学期（第 {target_term} 学期）未开课"
                                       f"（原开课学期为第 {c['term']} 学期），需等待开课学期重修"})

    # 2) 本学期必修（含集中实践；已在修的课程不重复加入）
    required = [c for c in ds.courses().values()
                if c["term"] == target_term and c["id"] not in passed
                and c["id"] not in doing]
    required.sort(key=lambda c: (PRIORITY.get(c["module"], 9), c["id"]))
    for c in required:
        try_add(c["id"], "必修", f"第 {target_term} 学期培养方案内必修课程（{c['module']}）")

    # 3) 用户指定的选修
    for cid in (elective_ids or []):
        if cid not in ds.courses():
            raise ToolError("COURSE_NOT_FOUND", f"课程库中没有 {cid}")
        if cid in passed:
            excluded.append({"id": cid, "name": ds.courses()[cid]["name"], "reason": "已通过，无需重复修读"})
            continue
        try_add(cid, "选修", "学生指定的选修课程")

    # 4) 补足专业选修缺口（每学期自动加入不超过 2 门，避免把选修堆在一个学期）
    gap_elective = calc_module_gap(student_id).get("专业选修", 0.0)
    chosen_elective = sum(s["credits"] for s in selected if s["module"] == "专业选修")
    remaining = round(gap_elective - chosen_elective, 1)
    auto_added = 0
    if remaining > 0:
        pool = [c for c in ds.courses().values()
                if c["module"] == "专业选修" and c["id"] not in passed and c["id"] not in attempted]
        pool.sort(key=lambda c: (-c["credits"], c["id"]))
        for c in pool:
            if remaining <= 0 or auto_added >= 2:
                break
            if try_add(c["id"], "选修", f"补足专业选修模块学分缺口（尚缺 {remaining:g} 学分）"):
                remaining = round(remaining - c["credits"], 1)
                auto_added += 1
        if remaining > 0:
            risks.append(f"专业选修模块仍缺 {remaining:g} 学分，建议分摊到后续 2—3 个学期完成，"
                         f"避免在单学期堆叠选修课")

    selected.sort(key=lambda s: (PRIORITY.get(s["module"], 9), s["id"]))

    if total > 24:
        risks.append(f"本学期修读 {total:g} 学分，高于建议区间 20—26 的偏上位置，注意时间投入")
    if not selected:
        risks.append("当前学期未匹配到可修课程，请核对目标学期或先修情况")
    if any(s["role"] == "重修" for s in selected):
        risks.append("含重修课程，重修与正常课程共用 26 学分上限")
    if any(s["module"] == "集中实践" for s in selected):
        risks.append("含集中实践类课程，需自行核对集中周次是否与其它课程重叠")

    return {
        "student_id": student_id,
        "target_term": target_term,
        "selected": selected,
        "total_credits": total,
        "max_credits": max_credits,
        "excluded": excluded,
        "risks": risks,
        "preferences": prefs,
    }


def calc_module_gap(student_id: str, extra: float = 0.0, module: str | None = None) -> Any:
    """轻量模块缺口查询（避免与 academic 模块循环导入）。"""
    req = ds.program()["requirements"]["modules"]
    passed = ds.passed_course_ids(student_id)
    per = {m: 0.0 for m in req}
    for cid in passed:
        mod = ds.module_of(cid)
        if mod in per:
            per[mod] += ds.credit_of(cid)
    if module:
        return round(max(0.0, req[module] - per.get(module, 0.0) - extra), 1)
    return {m: round(max(0.0, req[m] - per.get(m, 0.0)), 1) for m in req}

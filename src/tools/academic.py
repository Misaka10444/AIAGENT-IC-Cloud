# -*- coding: utf-8 -*-
"""教务类专业工具：画像查询、学分核算、先修校验、冲突检测、课程检索、毕业资格。"""
from __future__ import annotations

from typing import Any, Dict, List

from src.tools import data_store as ds
from src.tools.registry import ToolError, tool


def _fmt(course_id: str) -> Dict[str, Any]:
    c = ds.courses().get(course_id)
    if not c:
        return {"id": course_id, "name": "未知课程", "credits": 0.0}
    return {"id": c["id"], "name": c["name"], "credits": c["credits"],
            "module": c["module"], "slot": c["slot"], "term": c["term"]}


@tool(
    name="get_student_profile",
    description="读取学生脱敏画像：年级、专业、目标方向、选课偏好、已修课程与成绩。",
    params={
        "student_id": {"type": "string", "required": True,
                       "desc": "学生代号，如 S001"},
    },
    returns="{student_id, alias, grade, goal, target_direction, preferences, completed_count, failed_courses}",
    raises=["STUDENT_NOT_FOUND"],
)
def get_student_profile(student_id: str) -> Dict[str, Any]:
    st = ds.student(student_id)
    failed = [{"id": c["course_id"], "name": ds.courses().get(c["course_id"], {}).get("name", "?"),
               "score": c["score"]} for c in st["completed"] if not ds.is_pass(c["score"])]
    return {
        "student_id": st["student_id"],
        "alias": st["alias"],
        "grade": st["grade"],
        "major": st["major"],
        "current_term": st["current_term"],
        "goal": st["goal"],
        "target_direction": st["target_direction"],
        "preferences": st["preferences"],
        "completed_count": len(st["completed"]),
        "failed_courses": failed,
        "note": st.get("note", ""),
    }


@tool(
    name="calc_credit_progress",
    description="按培养方案六个模块核算已通过学分、缺口与未通过课程，输出可解释的学分进度。",
    params={
        "student_id": {"type": "string", "required": True, "desc": "学生代号"},
    },
    returns="{modules:[{module,required,passed,gap,status}], total:{required,passed,gap}, failed:[], unattempted_core:[]}",
    raises=["STUDENT_NOT_FOUND"],
)
def calc_credit_progress(student_id: str) -> Dict[str, Any]:
    st = ds.student(student_id)
    req = ds.program()["requirements"]["modules"]
    passed_ids = ds.passed_course_ids(student_id)

    per_module: Dict[str, float] = {m: 0.0 for m in req}
    for cid in passed_ids:
        mod = ds.module_of(cid)
        if mod in per_module:
            per_module[mod] += ds.credit_of(cid)

    modules = []
    for mod, required in req.items():
        passed = round(per_module.get(mod, 0.0), 1)
        gap = round(max(0.0, required - passed), 1)
        modules.append({
            "module": mod,
            "required": required,
            "passed": passed,
            "gap": gap,
            "status": "达标" if gap == 0 else "缺口",
        })

    failed = [{"id": c["course_id"],
               "name": ds.courses().get(c["course_id"], {}).get("name", "?"),
               "module": ds.module_of(c["course_id"]),
               "credits": ds.credit_of(c["course_id"]),
               "score": c["score"]}
              for c in st["completed"] if not ds.is_pass(c["score"])]

    # 尚未修读的专业核心课：后续规划的硬约束
    core_all = [cid for cid, c in ds.courses().items() if c["module"] == "专业核心"]
    unattempted_core = [dict(id=cid, name=ds.courses()[cid]["name"],
                             term=ds.courses()[cid]["term"],
                             credits=ds.courses()[cid]["credits"])
                        for cid in sorted(core_all, key=lambda x: ds.courses()[x]["term"])
                        if cid not in ds.all_attempted_course_ids(student_id)]

    total_required = float(ds.program()["requirements"]["total_credits"])
    total_passed = round(sum(ds.credit_of(c) for c in passed_ids), 1)
    return {
        "student_id": student_id,
        "program_id": st["program_id"],
        "modules": modules,
        "total": {
            "required": total_required,
            "passed": total_passed,
            "gap": round(max(0.0, total_required - total_passed), 1),
        },
        "failed": failed,
        "unattempted_core": unattempted_core,
    }


@tool(
    name="query_courses",
    description="按学期、模块、关键字检索课程库，返回学分、先修、上课时间与容量余量。",
    params={
        "term": {"type": "integer", "required": False, "desc": "开课学期 1-8；0 表示选修池"},
        "module": {"type": "string", "required": False,
                   "enum": ["通识必修", "通识选修", "专业基础", "专业核心", "专业选修", "集中实践"]},
        "keyword": {"type": "string", "required": False, "desc": "课程名或描述关键字"},
        "only_with_capacity": {"type": "boolean", "required": False, "default": False,
                               "desc": "仅返回仍有容量的课程"},
    },
    returns="{count, courses:[{id,name,credits,module,term,prereq,slot,capacity,enrolled,seats_left}]}",
    raises=["ENUM_MISMATCH"],
)
def query_courses(term: Any = None, module: Any = None, keyword: Any = None,
                  only_with_capacity: bool = False) -> Dict[str, Any]:
    items = list(ds.courses().values())
    if term is not None:
        items = [c for c in items if c["term"] == int(term)]
    if module:
        items = [c for c in items if c["module"] == module]
    if keyword:
        kw = str(keyword)
        items = [c for c in items if kw in c["name"] or kw in c["desc"]]
    if only_with_capacity:
        items = [c for c in items if c["enrolled"] < c["capacity"]]
    items.sort(key=lambda c: (c["term"], c["module"], c["id"]))
    return {
        "count": len(items),
        "courses": [{
            "id": c["id"], "name": c["name"], "credits": c["credits"],
            "module": c["module"], "term": c["term"], "prereq": c["prereq"],
            "slot": c["slot"], "capacity": c["capacity"], "enrolled": c["enrolled"],
            "seats_left": max(0, c["capacity"] - c["enrolled"]),
        } for c in items],
    }


@tool(
    name="check_prerequisites",
    description="校验某门课程的先修要求是否满足。已通过=满足；在修=待确认（不计入缺失）；未修/未通过=缺失。",
    params={
        "course_id": {"type": "string", "required": True, "desc": "课程代码，如 C5002"},
        "student_id": {"type": "string", "required": True, "desc": "学生代号"},
    },
    returns="{course_id, course_name, ok, prereq:[], missing:[], pending:[]}",
    raises=["COURSE_NOT_FOUND", "STUDENT_NOT_FOUND"],
)
def check_prerequisites(course_id: str, student_id: str) -> Dict[str, Any]:
    c = ds.courses().get(course_id)
    if not c:
        raise ToolError("COURSE_NOT_FOUND", f"课程库中没有课程 {course_id}")
    passed = ds.passed_course_ids(student_id)
    doing = ds.in_progress_ids(student_id)
    missing, pending = [], []
    for p in c["prereq"]:
        item = {"id": p, "name": ds.courses().get(p, {}).get("name", "?")}
        if p in passed:
            continue
        if p in doing:
            pending.append(item)
        else:
            missing.append(item)
    return {
        "course_id": course_id,
        "course_name": c["name"],
        "ok": len(missing) == 0,
        "prereq": [{"id": p, "name": ds.courses().get(p, {}).get("name", "?")}
                   for p in c["prereq"]],
        "missing": missing,
        "pending": pending,
    }


@tool(
    name="check_timetable_conflict",
    description="检测一组课程之间是否存在上课时间重叠，返回具体的冲突课程对与时隙。",
    params={
        "course_ids": {"type": "array", "required": True, "desc": "课程代码列表，如 [\"C4001\",\"C4002\"]"},
    },
    returns="{ok, conflicts:[{a,b,slot_a,slot_b,day,periods}], unscheduled:[]}",
    raises=["COURSE_NOT_FOUND"],
)
def check_timetable_conflict(course_ids: List[str]) -> Dict[str, Any]:
    unknown = [c for c in course_ids if c not in ds.courses()]
    if unknown:
        raise ToolError("COURSE_NOT_FOUND", f"课程库中没有：{', '.join(unknown)}")
    conflicts, unscheduled = [], []
    seen = []
    for cid in course_ids:
        if cid in seen:
            continue
        seen.append(cid)
        c = ds.courses()[cid]
        slot = ds.parse_slot(c["slot"])
        if slot is None:
            unscheduled.append({"id": cid, "name": c["name"], "slot": c["slot"]})
    for i in range(len(seen)):
        for j in range(i + 1, len(seen)):
            a, b = seen[i], seen[j]
            sa = ds.parse_slot(ds.courses()[a]["slot"])
            sb = ds.parse_slot(ds.courses()[b]["slot"])
            if not sa or not sb:
                continue
            if sa[0] == sb[0] and sa[1] & sb[1]:
                conflicts.append({
                    "a": a, "a_name": ds.courses()[a]["name"], "slot_a": ds.courses()[a]["slot"],
                    "b": b, "b_name": ds.courses()[b]["name"], "slot_b": ds.courses()[b]["slot"],
                    "day": sa[0], "periods": sorted(sa[1] & sb[1]),
                })
    return {"ok": len(conflicts) == 0, "conflicts": conflicts, "unscheduled": unscheduled,
            "checked": seen}


@tool(
    name="check_graduation_eligibility",
    description="按毕业审核五项必要条件逐项判定，输出不满足的条目与原因。",
    params={
        "student_id": {"type": "string", "required": True, "desc": "学生代号"},
    },
    returns="{eligible, conditions:[{no,item,ok,detail}], failed_count}",
    raises=["STUDENT_NOT_FOUND"],
)
def check_graduation_eligibility(student_id: str) -> Dict[str, Any]:
    st = ds.student(student_id)
    prog = ds.program()["requirements"]
    cp = calc_credit_progress(student_id)
    passed_ids = ds.passed_course_ids(student_id)

    conds = []
    total_ok = cp["total"]["passed"] >= cp["total"]["required"]
    conds.append({"no": 1, "item": f"总学分不低于 {cp['total']['required']:g}",
                  "ok": total_ok,
                  "detail": "已通过 %.1f 学分，缺口 %.1f" % (cp["total"]["passed"], cp["total"]["gap"])})

    gap_mods = [m for m in cp["modules"] if m["gap"] > 0]
    conds.append({"no": 2, "item": "六个模块学分分别达标", "ok": len(gap_mods) == 0,
                  "detail": "；".join("%s缺 %.1f" % (m["module"], m["gap"]) for m in gap_mods)
                  or "全部模块达标"})

    failed_core = [f for f in cp["failed"] if f["module"] == "专业核心"]
    unattempted_core = cp["unattempted_core"]
    core_ok = len(failed_core) == 0 and len(unattempted_core) == 0
    core_detail = ""
    if failed_core:
        core_detail = "未通过：" + "；".join("%s（%s 分）" % (f["name"], f["score"]) for f in failed_core)
    elif unattempted_core:
        names = "、".join(c["name"] for c in unattempted_core[:5])
        more = f" 等 {len(unattempted_core)} 门" if len(unattempted_core) > 5 else ""
        core_detail = f"尚有 {len(unattempted_core)} 门专业核心课未修读：{names}{more}"
    else:
        core_detail = "专业核心课程全部通过"
    conds.append({"no": 3, "item": "专业核心课程全部通过", "ok": core_ok, "detail": core_detail})

    thesis = "C8001"
    thesis_score = next((c["score"] for c in st["completed"] if c["course_id"] == thesis), None)
    thesis_ok = thesis in passed_ids
    conds.append({"no": 4, "item": "毕业设计（论文）通过答辩", "ok": thesis_ok,
                  "detail": "成绩 %s" % thesis_score if thesis_score is not None else "尚未完成"})

    intern = "C8002"
    intern_ok = intern in passed_ids
    conds.append({"no": 5, "item": "顶岗实习合格且取得职业技能等级证书", "ok": intern_ok,
                  "detail": "顶岗实习待完成" if not intern_ok else "实习合格；证书由学院统一核验"})

    failed_n = sum(1 for c in conds if not c["ok"])
    return {"eligible": failed_n == 0, "conditions": conds, "failed_count": failed_n,
            "student_id": student_id}


@tool(
    name="get_risk_warning",
    description="按学业预警办法判定预警等级（黄/橙/红/无）。进度缺口=应修必修学分(当前学期及之前)−已通过必修学分，避免低年级被误判。",
    params={
        "student_id": {"type": "string", "required": True, "desc": "学生代号"},
    },
    returns="{level, reasons:[], actions:[], failed_count, progress_gap, should_have, passed_in_plan}",
    raises=["STUDENT_NOT_FOUND"],
)
def get_risk_warning(student_id: str) -> Dict[str, Any]:
    st = ds.student(student_id)
    cp = calc_credit_progress(student_id)
    term_now = int(st["current_term"])
    failed_count = len(cp["failed"])

    # 应修：当前学期及之前的必修类课程（不含需要自主选择的通识选修/专业选修）
    scheduled = [c for c in ds.courses().values()
                 if c["term"] and c["term"] <= term_now
                 and c["module"] not in ("通识选修", "专业选修")]
    should_have = round(sum(c["credits"] for c in scheduled), 1)
    passed_ids = ds.passed_course_ids(student_id)
    passed_in_plan = round(sum(c["credits"] for c in scheduled if c["id"] in passed_ids), 1)
    progress_gap = round(max(0.0, should_have - passed_in_plan), 1)

    level, reasons = "无", []
    if failed_count >= 3 or progress_gap > 20:
        level = "橙色"
    elif failed_count >= 1 or progress_gap > 10:
        level = "黄色"
    if failed_count >= 3:
        reasons.append(f"未通过课程 {failed_count} 门")
    elif failed_count:
        reasons.append(f"未通过课程 {failed_count} 门")
    if progress_gap > 0:
        reasons.append(f"学业进度缺口 {progress_gap:g} 学分"
                       f"（应修 {should_have:g}，已通过 {passed_in_plan:g}）")

    actions = {
        "无": ["按培养方案正常修读，每学期做一次学分自查"],
        "黄色": ["联系辅导员制定补修计划", "补退选阶段优先选取重修教学班"],
        "橙色": ["学院约谈并安排学业导师", "使用重修优先选课权", "每学期至少 3 次导师面谈"],
        "红色": ["学院专项帮扶", "重新评估修读方案"],
    }[level]
    return {"level": level, "reasons": reasons or ["未触发预警条件"], "actions": actions,
            "failed_count": failed_count, "progress_gap": progress_gap,
            "should_have": should_have, "passed_in_plan": passed_in_plan,
            "credit_gap": cp["total"]["gap"]}

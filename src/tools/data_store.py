# -*- coding: utf-8 -*-
"""教务数据访问层：培养方案、课程库、学生画像。带进程内缓存。"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Dict, List, Optional

from src import config


@lru_cache(maxsize=1)
def courses() -> Dict[str, Dict[str, Any]]:
    raw = json.loads((config.DATA_DIR / "courses.json").read_text(encoding="utf-8"))
    return {c["id"]: c for c in raw["courses"]}


@lru_cache(maxsize=1)
def courses_meta() -> Dict[str, Any]:
    raw = json.loads((config.DATA_DIR / "courses.json").read_text(encoding="utf-8"))
    return raw["meta"]


@lru_cache(maxsize=1)
def program() -> Dict[str, Any]:
    return json.loads((config.DATA_DIR / "program_ai_2025.json").read_text(encoding="utf-8"))


def student(student_id: str) -> Dict[str, Any]:
    path = config.STUDENT_DIR / f"{student_id}.json"
    if not path.exists():
        from src.tools.registry import ToolError
        raise ToolError("STUDENT_NOT_FOUND",
                        f"未找到学生 {student_id}，可用样例：S001 / S002 / S003")
    return json.loads(path.read_text(encoding="utf-8"))


def list_students() -> List[str]:
    return sorted(p.stem for p in config.STUDENT_DIR.glob("*.json"))


def is_pass(score: Any) -> bool:
    """成绩是否通过：数字 >= 60，或"合格"/"优秀"等文本标签。"""
    if isinstance(score, (int, float)):
        return float(score) >= 60
    return str(score) in ("合格", "优秀", "良好", "通过")


def num_score(score: Any) -> Optional[float]:
    return float(score) if isinstance(score, (int, float)) else None


def passed_course_ids(student_id: str) -> set:
    st = student(student_id)
    return {c["course_id"] for c in st["completed"] if is_pass(c["score"])}


def all_attempted_course_ids(student_id: str) -> set:
    st = student(student_id)
    return {c["course_id"] for c in st["completed"]}


def in_progress_ids(student_id: str) -> set:
    """在修（已选课、成绩未出）课程。用于先修判定的"待确认"分支。"""
    st = student(student_id)
    return set(st.get("in_progress", []) or [])


def credit_of(course_id: str) -> float:
    c = courses().get(course_id)
    return float(c["credits"]) if c else 0.0


def module_of(course_id: str) -> str:
    c = courses().get(course_id)
    return c["module"] if c else "未知"


def parse_slot(slot: str) -> Optional[tuple]:
    """把 "周一 1-2" 解析成 (1, {1,2})；线上/集中类返回 None（不做时间冲突判定）。"""
    days = {"周一": 1, "周二": 2, "周三": 3, "周四": 4, "周五": 5, "周六": 6, "周日": 7}
    parts = str(slot).split()
    if len(parts) != 2 or parts[0] not in days:
        return None
    try:
        a, b = parts[1].split("-")
        periods = set(range(int(a), int(b) + 1))
    except (ValueError, IndexError):
        return None
    return days[parts[0]], periods

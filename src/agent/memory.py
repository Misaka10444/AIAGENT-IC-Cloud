# -*- coding: utf-8 -*-
"""会话记忆：轮次状态 + 实体槽位 + 指代消解。

多轮对话的难点不是"记住历史"，而是"知道这一轮的'那门课'指哪一门"。
这里用显式槽位（student_id / course_id / term）记录最近一次被提到的实体，
再按规则把代词替换回实体，替换过程写入 trace，便于答辩时展示消解依据。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from src.tools import data_store as ds

PRONOUN_COURSE = ["那门课", "这门课", "那门", "这门", "它", "该课程", "这门课程", "那门课程"]
PRONOUN_STUDENT = ["这个学生", "该生", "他", "她", "这个同学", "该同学"]
TERM_PATTERNS = [
    (r"下(?:个)?学期", None), (r"这(?:个)?学期", None), (r"本(?:个)?学期", None),
    (r"第\s*([1-8])\s*学期", "explicit"), (r"大([一二三四])", "grade"),
]
CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4}


class Memory:
    def __init__(self, session_id: str = "default"):
        self.session_id = session_id
        self.slots: Dict[str, Any] = {"student_id": None, "course_id": None, "term": None}
        self.history: List[Dict[str, str]] = []
        self.resolutions: List[Dict[str, str]] = []

    # ---------- 写 ----------
    def remember_user(self, text: str) -> None:
        self.history.append({"role": "user", "content": text})

    def remember_agent(self, text: str) -> None:
        self.history.append({"role": "assistant", "content": text})

    def set_slot(self, key: str, value: Any) -> None:
        if value is not None:
            self.slots[key] = value

    # ---------- 读 ----------
    def last_user(self) -> str:
        for h in reversed(self.history):
            if h["role"] == "user":
                return h["content"]
        return ""

    def turn_count(self) -> int:
        return sum(1 for h in self.history if h["role"] == "user")

    # ---------- 指代消解 ----------
    def resolve(self, text: str) -> str:
        """把代词替换为上一轮实体，返回消解后的文本（原文不改，仅用于理解）。"""
        out = text
        self.resolutions = []

        cid = self.slots.get("course_id")
        if cid and cid in ds.courses():
            name = ds.courses()[cid]["name"]
            for p in PRONOUN_COURSE:
                if p in out:
                    out = out.replace(p, f"《{name}》")
                    self.resolutions.append({"type": "course", "pronoun": p,
                                             "resolved_to": name, "evidence": f"上一轮提到课程 {cid}"})
                    break

        sid = self.slots.get("student_id")
        if sid:
            for p in PRONOUN_STUDENT:
                if p in out and sid not in out:
                    out = out.replace(p, f"学生{sid[-1]}")
                    self.resolutions.append({"type": "student", "pronoun": p,
                                             "resolved_to": sid, "evidence": "上一轮确定了学生代号"})
                    break
        return out

    def term_from_text(self, text: str, current_term: Optional[int] = None) -> Optional[int]:
        for pat, kind in TERM_PATTERNS:
            m = re.search(pat, text)
            if not m:
                continue
            if kind == "explicit":
                return int(m.group(1))
            if kind == "grade":
                return CN_NUM[m.group(1)] * 2
            if "下" in pat:
                return (current_term or 1) + 1
            return current_term
        return None


def detect_student(text: str, fallback: Optional[str] = None) -> Optional[str]:
    """从文本中识别学生代号：S001 / 学生A / 样例1。"""
    m = re.search(r"\bS00(\d)\b", text, re.I)
    if m:
        return f"S00{m.group(1)}"
    m = re.search(r"学生\s*([ABC])", text)
    if m:
        return {"A": "S001", "B": "S002", "C": "S003"}[m.group(1)]
    return fallback


def detect_courses(text: str) -> List[str]:
    """课程识别：先匹配课程代码，再匹配课程全名（取最长匹配，避免子串误判）。"""
    found: List[str] = []
    for cid in re.findall(r"\b[CE]\d{4}\b", text, re.I):
        cid = cid.upper()
        if cid in ds.courses() and cid not in found:
            found.append(cid)
    for cid, c in sorted(ds.courses().items(), key=lambda kv: -len(kv[1]["name"])):
        if c["name"] and c["name"] in text and cid not in found:
            found.append(cid)
    return found

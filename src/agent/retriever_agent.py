# -*- coding: utf-8 -*-
"""Retriever Agent：按意图改写检索式，召回知识库片段并做引用去重。"""
from __future__ import annotations

from typing import Any, Dict, List

from src.tools import registry as reg

INTENT_QUERY_HINT = {
    "credit_progress": "学分 模块 要求 学分结构 通识必修 专业核心 集中实践",
    "prereq_check": "先修 先修关系 课程 主线 程序设计基础 数据结构 机器学习基础",
    "conflict_check": "时间冲突 选课 容量 教学班 集中实践 周次",
    "plan_build": "学分上限 选课时间 补退选 修读建议 每学期",
    "graduation_check": "毕业资格 审核 条件 学分 毕业设计 顶岗实习 证书",
    "risk_warn": "学业预警 黄色 橙色 学分缺口 帮扶",
    "course_query": "课程简介 课程难度 岗位方向",
    "policy_qa": "",
    "profile_query": "",
}


class RetrieverAgent:
    def __init__(self, trace=None):
        self.trace = trace

    def retrieve(self, intent: str, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        hint = INTENT_QUERY_HINT.get(intent, "")
        q = f"{query} {hint}".strip() if hint else query
        res = reg.call("search_knowledge", trace=self.trace, query=q, top_k=top_k)
        if not res.get("ok"):
            return []
        chunks = res["data"]["chunks"]
        # 引用去重：同一文档同一章节只保留得分最高的一条
        seen, out = set(), []
        for c in chunks:
            key = (c["doc_id"], c["section"])
            if key in seen:
                continue
            seen.add(key)
            out.append(c)
        return out

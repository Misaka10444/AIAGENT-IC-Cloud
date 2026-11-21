# -*- coding: utf-8 -*-
"""知识检索工具：把 RAG 索引封装成标准工具，返回带出处的片段。"""
from __future__ import annotations

from typing import Any, Dict, List

from src.rag import index as kb_index
from src.tools.registry import tool


@tool(
    name="search_knowledge",
    description="在培养方案、选课办法、重修规定、毕业审核、学业预警、课程简介与AI使用规范中检索，返回带文档号与章节的原文片段。",
    params={
        "query": {"type": "string", "required": True, "desc": "自然语言问题或关键词"},
        "top_k": {"type": "integer", "required": False, "desc": "返回片段数，默认 5"},
    },
    returns="{count, chunks:[{doc_id,title,section,line_start,snippet,score}]}",
    raises=["EMPTY_QUERY"],
)
def search_knowledge(query: str, top_k: Any = None) -> Dict[str, Any]:
    from src.tools.registry import ToolError
    if not str(query).strip():
        raise ToolError("EMPTY_QUERY", "检索词不能为空")
    k = int(top_k) if top_k else None
    chunks = kb_index.index().search(str(query), top_k=k)
    return {"count": len(chunks), "chunks": chunks, "query": query,
            "index_stats": kb_index.index().stats()}


@tool(
    name="get_kb_stats",
    description="返回知识库规模统计（文档数、片段数、平均片段长度），用于答辩时说明索引构建结果。",
    params={},
    returns="{chunks, docs, avg_chunk_chars, vocab}",
    raises=[],
)
def get_kb_stats() -> Dict[str, Any]:
    return kb_index.index().stats()

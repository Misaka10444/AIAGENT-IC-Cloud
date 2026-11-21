# -*- coding: utf-8 -*-
"""知识库索引：切分 → BM25 召回 → 特征重排 → 引用溯源。

纯标准库实现，不依赖向量库，原因写在 docs/design.md：
本赛题的数据规模（7 篇文档、约 90 个片段）用 BM25 + 规则重排就能达到可测的召回，
而向量检索需要额外模型与密钥，会削弱"零密钥可复现"这一演示前提。
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

from src import config

STOP_TERMS = [
    "请问", "如何", "是否", "怎么", "什么", "哪些", "多少", "可以", "需要", "应该",
    "一下", "吗", "呢", "的", "了", "是", "和", "与", "在", "我", "他", "她", "它",
    "这个", "那个", "还有", "以及", "如果", "那么", "为什么", "能不能",
]


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    doc_title: str
    section: str
    line_start: int
    text: str
    char_len: int = 0
    tokens: List[str] = field(default_factory=list)

    def cite(self) -> Dict[str, Any]:
        snippet = re.sub(r"\s+", " ", self.text.strip())
        return {
            "doc_id": self.doc_id,
            "title": self.doc_title,
            "section": self.section,
            "line_start": self.line_start,
            "snippet": snippet[:160] + ("…" if len(snippet) > 160 else ""),
            "chunk_id": self.chunk_id,
        }


def _tokenize(text: str) -> List[str]:
    """中文用字二元组，英文/数字用单词，过滤停用词与标点。"""
    text = text.lower()
    for w in STOP_TERMS:
        text = text.replace(w, " ")
    tokens: List[str] = []
    for seg in re.findall(r"[\u4e00-\u9fff]+|[a-z0-9]+(?:\.[0-9]+)?", text):
        if re.match(r"[a-z0-9]", seg):
            tokens.append(seg)
            continue
        if len(seg) == 1:
            tokens.append(seg)
        else:
            tokens.extend(seg[i:i + 2] for i in range(len(seg) - 1))
    return tokens


def _parse_front_matter(raw: str) -> Tuple[Dict[str, str], List[str]]:
    lines = raw.splitlines()
    meta: Dict[str, str] = {}
    if lines and lines[0].strip() == "---":
        end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
        if end:
            for ln in lines[1:end]:
                if ":" in ln:
                    k, v = ln.split(":", 1)
                    meta[k.strip()] = v.strip()
            return meta, lines[end + 1:]
    return meta, lines


def _split_sections(lines: List[str]) -> List[Tuple[str, int, str]]:
    """返回 [(section_heading, line_start_1based, text)]"""
    sections: List[Tuple[str, int, str]] = []
    cur_head, cur_start, buf = "正文", 1, []
    for idx, ln in enumerate(lines, start=1):
        if ln.startswith("## "):
            if buf and "".join(buf).strip():
                sections.append((cur_head, cur_start, "\n".join(buf).strip()))
            cur_head, cur_start, buf = ln[3:].strip(), idx, []
            continue
        if ln.startswith("# "):
            continue
        buf.append(ln)
    if buf and "".join(buf).strip():
        sections.append((cur_head, cur_start, "\n".join(buf).strip()))
    return sections


def _chunk_text(text: str, size: int, overlap: int) -> List[Tuple[int, str]]:
    """按段落边界切分，超长段按字符窗口切，返回 [(相对行号偏移, 片段)]"""
    paras = [(i, p) for i, p in enumerate(text.split("\n")) if p.strip()]
    out: List[Tuple[int, str]] = []
    buf, buf_start = "", 0
    for i, p in paras:
        if not buf:
            buf_start = i
        if len(buf) + len(p) + 1 <= size:
            buf = (buf + "\n" + p).strip() if buf else p
            continue
        if buf:
            out.append((buf_start, buf))
        tail = buf[-overlap:] if len(buf) > overlap else ""
        buf = (tail + "\n" + p).strip() if tail else p
        buf_start = i
    if buf:
        out.append((buf_start, buf))
    return out


class KnowledgeIndex:
    def __init__(self, kb_dir=None):
        self.chunks: List[Chunk] = []
        self._df: Dict[str, int] = {}
        self._avgdl = 0.0
        self._build(kb_dir or config.KB_DIR)

    # ---------- 构建 ----------
    def _build(self, kb_dir) -> None:
        for path in sorted(kb_dir.glob("*.md")):
            raw = path.read_text(encoding="utf-8")
            meta, body = _parse_front_matter(raw)
            doc_id = meta.get("doc_id", path.stem)
            doc_title = meta.get("title", path.stem)
            for head, line_start, text in _split_sections(body):
                for off, piece in _chunk_text(text, config.CHUNK_SIZE, config.CHUNK_OVERLAP):
                    cid = f"{doc_id}#{len([c for c in self.chunks if c.doc_id == doc_id]) + 1}"
                    ch = Chunk(cid, doc_id, doc_title, head, line_start + off, piece,
                               char_len=len(piece))
                    ch.tokens = _tokenize(piece + " " + head + " " + doc_title)
                    self.chunks.append(ch)
        for ch in self.chunks:
            for t in set(ch.tokens):
                self._df[t] = self._df.get(t, 0) + 1
        self._avgdl = (sum(c.char_len for c in self.chunks) / len(self.chunks)) if self.chunks else 1.0
        self._N = max(1, len(self.chunks))

    # ---------- 检索 ----------
    def _bm25(self, q_tokens: List[str]) -> Dict[int, float]:
        scores: Dict[int, float] = {}
        qs = list(dict.fromkeys(q_tokens))
        for i, ch in enumerate(self.chunks):
            tf: Dict[str, int] = {}
            for t in ch.tokens:
                tf[t] = tf.get(t, 0) + 1
            s = 0.0
            for q in qs:
                f = tf.get(q, 0)
                if not f:
                    continue
                idf = math.log(1 + (self._N - self._df.get(q, 0) + 0.5) / (self._df.get(q, 0) + 0.5))
                norm = config.BM25_K1 * (1 - config.BM25_B + config.BM25_B * ch.char_len / self._avgdl)
                s += idf * (f * (config.BM25_K1 + 1)) / (f + norm)
            if s > 0:
                scores[i] = s
        return scores

    def _rerank(self, q_tokens: List[str], cand: List[Tuple[int, float]]) -> List[Tuple[int, float]]:
        qset = set(q_tokens)
        out = []
        for i, base in cand:
            ch = self.chunks[i]
            head_tokens = set(_tokenize(ch.section + " " + ch.doc_title))
            head_hit = len(qset & head_tokens) / max(1, len(qset))
            ctset = set(ch.tokens)
            coverage = len(qset & ctset) / max(1, len(qset))
            out.append((i, base + 0.8 * head_hit + 0.5 * coverage))
        out.sort(key=lambda x: -x[1])
        return out

    def search(self, query: str, top_k: int | None = None, rerank: bool | None = None
               ) -> List[Dict[str, Any]]:
        top_k = top_k or config.TOP_K
        rerank = config.ENABLE_RERANK if rerank is None else rerank
        q_tokens = _tokenize(query)
        if not q_tokens:
            return []
        scores = self._bm25(q_tokens)
        cand = sorted(scores.items(), key=lambda x: -x[1])[: max(top_k * 4, 12)]
        # 相关性阈值只看原始 BM25 分，避免被重排加分掩盖"其实没有依据"的情况
        cand = [(i, sc) for i, sc in cand if sc >= config.MIN_SCORE]
        if rerank:
            cand = self._rerank(q_tokens, cand)
        out = []
        for i, sc in cand[:top_k]:
            ch = self.chunks[i]
            item = ch.cite()
            item["score"] = round(sc, 4)
            out.append(item)
        return out

    def stats(self) -> Dict[str, Any]:
        return {"chunks": len(self.chunks),
                "docs": len({c.doc_id for c in self.chunks}),
                "avg_chunk_chars": round(self._avgdl, 1),
                "vocab": len(self._df)}


_INDEX: KnowledgeIndex | None = None


def index() -> KnowledgeIndex:
    global _INDEX
    if _INDEX is None:
        _INDEX = KnowledgeIndex()
    return _INDEX

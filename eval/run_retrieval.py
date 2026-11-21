# -*- coding: utf-8 -*-
"""检索排序评测：只测 RAG（切分 → BM25 → 重排），与生成和工具解耦。

指标：
- Top-1 文档命中率：第一位召回片段的文档号是否等于 gold_doc
- 章节命中率：前 K 条中存在文档号与章节名同时命中的片段
- MRR@K：正确文档首次出现位置的倒数均值
- Recall@K：正确文档是否出现在前 K 条

用法：
    python -m eval.run_retrieval           # 两种配置对比
    python -m eval.run_retrieval --out ... 
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from src import config
from src.rag.index import index

HERE = Path(__file__).resolve().parent
CASES = HERE / "retrieval_cases.json"


def evaluate(rerank: bool, top_k: int = 5) -> Dict[str, Any]:
    data = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    top1 = sec_hit = recall = 0
    mrr = 0.0
    rows: List[Dict[str, Any]] = []
    for c in data:
        res = index().search(c["query"], top_k=top_k, rerank=rerank)
        docs = [r["doc_id"] for r in res]
        first = next((i for i, d in enumerate(docs) if d == c["gold_doc"]), None)
        if first is not None:
            mrr += 1.0 / (first + 1)
            recall += 1
        if docs and docs[0] == c["gold_doc"]:
            top1 += 1
        if any(r["doc_id"] == c["gold_doc"] and r["section"] == c["gold_section"] for r in res):
            sec_hit += 1
        rows.append({"id": c["id"], "query": c["query"],
                     "rank": None if first is None else first + 1,
                     "top1": docs[0] if docs else None,
                     "gold": c["gold_doc"]})
    n = len(data)
    return {
        "rerank": rerank, "top_k": top_k, "cases": n,
        "top1_doc_rate": round(top1 / n * 100, 1),
        "section_hit_rate": round(sec_hit / n * 100, 1),
        "recall_at_k": round(recall / n * 100, 1),
        "mrr": round(mrr / n, 4),
        "rows": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "retrieval_report.md"))
    args = ap.parse_args()

    off = evaluate(False)
    on = evaluate(True)

    lines = ["# 检索排序评测", "",
             f"用例数：{off['cases']}　·　Top-K：{off['top_k']}　·　"
             f"知识库：{index().stats()['docs']} 篇 / {index().stats()['chunks']} 片段", "",
             "| 指标 | 仅 BM25 | BM25 + 特征重排 | 变化 |",
             "| --- | --- | --- | --- |"]
    for key, label, unit in [("top1_doc_rate", "Top-1 文档命中率", "pt"),
                             ("section_hit_rate", "章节命中率", "pt"),
                             ("recall_at_k", "Recall@K", "pt"),
                             ("mrr", "MRR@K", "")]:
        a, b = off[key], on[key]
        delta = f"{b - a:+.1f}{unit}" if unit else f"{b - a:+.4f}"
        lines.append(f"| {label} | {a}{'%' if unit else ''} | {b}{'%' if unit else ''} | {delta} |")

    lines += ["", "## 逐条明细（重排开启）", "",
              "| 用例 | 提问 | 正确文档 | 首次命中名次 | Top-1 文档 |",
              "| --- | --- | --- | --- | --- |"]
    for r in on["rows"]:
        lines.append(f"| {r['id']} | {r['query']} | {r['gold']} | "
                     f"{r['rank'] if r['rank'] else '未命中'} | {r['top1'] or '—'} |")

    miss = [r for r in on["rows"] if r["rank"] != 1]
    lines += ["", "## 未在第一位命中的用例（重排开启）", ""]
    if miss:
        lines.append("| 用例 | 提问 | 正确文档 | 名次 | Top-1 |")
        lines.append("| --- | --- | --- | --- | --- |")
        for r in miss:
            lines.append(f"| {r['id']} | {r['query']} | {r['gold']} | {r['rank']} | {r['top1']} |")
    else:
        lines.append("无，全部用例第一位即命中正确文档。")

    text = "\n".join(lines)
    Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

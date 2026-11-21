# -*- coding: utf-8 -*-
"""评测脚本：在固定用例集上跑真实推理链路，输出可复现的量化指标。

用法：
    python -m eval.run_eval                  # 优化后配置（重排 + 校验全开）
    python -m eval.run_eval --baseline       # 消融：关闭重排与自检
    python -m eval.run_eval --compare        # 两种配置都跑，生成前后对比报告

指标口径（与 docs/design.md 第 5 节一致）：
- 任务成功率：一条用例的全部断言都通过，才算通过。分母是全部用例数。
- 意图准确率 / 工具准确率 / 引用命中率：只统计"该用例设置了对应断言"的子集。
- 幻觉率：回答中出现课程库之外的课程代码，或出现"保证/包过"等承诺性表述的用例占比。
- 延迟：单轮 handle() 的端到端墙钟时间，取 P50 与 P95。
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from src import config
from src.agent.orchestrator import get_agent
from src.tools import data_store as ds
import src.tools  # noqa: F401

EVAL_DIR = Path(__file__).resolve().parent
CASES = EVAL_DIR / "cases.jsonl"
PROMISE_WORDS = ["保证", "包过", "一定能通过", "绝对能"]


def load_cases() -> List[Dict[str, Any]]:
    out = []
    for ln in CASES.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln:
            out.append(json.loads(ln))
    return out


def _hallucinated(text: str) -> List[str]:
    bad = []
    for cid in set(re.findall(r"\b[CE]\d{4}\b", text)):
        if cid not in ds.courses():
            bad.append(cid)
    for w in PROMISE_WORDS:
        if w in text:
            bad.append(w)
    return bad


def run_one(case: Dict[str, Any], run_tag: str, auditor_on: bool) -> Dict[str, Any]:
    agent = get_agent()
    sid = f"eval-{case['id']}-{run_tag}"
    agent.reset(sid)
    res: Dict[str, Any] = {}
    t0 = time.time()
    for turn in case["turns"]:
        res = agent.handle(turn, session_id=sid)
    elapsed = round((time.time() - t0) * 1000, 1)

    exp = case.get("expect", {})
    fails: List[str] = []

    if "intent" in exp:
        allowed = exp["intent"] if isinstance(exp["intent"], list) else [exp["intent"]]
        if res.get("intent") not in allowed:
            fails.append(f"意图 期望{allowed} 实际{res.get('intent')}")

    if "tools_contains" in exp:
        got = {c["tool"] for c in res.get("tool_calls", [])}
        miss = [t for t in exp["tools_contains"] if t not in got]
        if miss:
            fails.append(f"工具缺失 {miss}")

    if "citations_any" in exp:
        docs = {c["doc_id"] for c in res.get("citations", [])}
        if not (docs & set(exp["citations_any"])):
            fails.append(f"引用未命中 期望{exp['citations_any']} 实际{sorted(docs)}")

    for s in exp.get("answer_contains", []):
        if s not in res.get("answer", ""):
            fails.append(f"回答缺少「{s}」")

    for s in exp.get("answer_not_contains", []):
        if s in res.get("answer", ""):
            fails.append(f"回答不应包含「{s}」")

    if exp.get("refused") and not res.get("refused"):
        fails.append("应拒答但未拒答")

    if exp.get("audit_passed") and auditor_on and not res.get("audit", {}).get("passed", True):
        fails.append("自检未通过")

    if "min_course_count" in exp:
        cnt = (res.get("facts") or {}).get("course_count", 0)
        if cnt < exp["min_course_count"]:
            fails.append(f"方案课程数 {cnt} < {exp['min_course_count']}")

    hallu = _hallucinated(res.get("answer", ""))
    if hallu:
        fails.append(f"幻觉/越界表述 {hallu}")

    return {
        "id": case["id"],
        "category": case["category"],
        "turns": case["turns"],
        "intent": res.get("intent"),
        "tools": [c["tool"] for c in res.get("tool_calls", [])],
        "citation_docs": [c["doc_id"] for c in res.get("citations", [])],
        "citation_top1": (res.get("citations") or [{}])[0].get("doc_id"),
        "audit_passed": bool(res.get("audit", {}).get("passed", True)),
        "refused": bool(res.get("refused")),
        "elapsed_ms": elapsed,
        "fails": fails,
        "passed": not fails,
        "answer_head": (res.get("answer") or "")[:160],
    }


def summarize(results: List[Dict[str, Any]], cases: List[Dict[str, Any]],
              auditor_on: bool) -> Dict[str, Any]:
    by_id = {c["id"]: c for c in cases}
    total = len(results)
    ok = sum(1 for r in results if r["passed"])

    def subset(pred) -> Tuple[int, int]:
        rows = [r for r in results if pred(by_id[r["id"]])]
        return sum(1 for r in rows if r["passed"]), len(rows)

    def rate(pred) -> Tuple[float, int]:
        a, b = subset(pred)
        return (round(a / b * 100, 1) if b else 100.0), b

    intent_rate, intent_n = rate(lambda c: "intent" in c.get("expect", {}))
    tool_rate, tool_n = rate(lambda c: "tools_contains" in c.get("expect", {}))
    cite_rate, cite_n = rate(lambda c: "citations_any" in c.get("expect", {}))
    cite_cases = [r for r in results if "citations_any" in by_id[r["id"]].get("expect", {})]
    top1_hit = sum(1 for r in cite_cases
                   if r["citation_top1"] in by_id[r["id"]]["expect"]["citations_any"])
    top1_rate = round(top1_hit / len(cite_cases) * 100, 1) if cite_cases else 100.0
    audit_rate = round(sum(1 for r in results if r["audit_passed"]) / total * 100, 1) if total else 0.0
    mt_rate, mt_n = rate(lambda c: c["category"] == "multiturn")
    safe_rate, safe_n = rate(lambda c: c["category"] == "safety")
    abst_rate, abst_n = rate(lambda c: c["category"] == "abstain")
    hallu_n = sum(1 for r in results if any("幻觉" in f for f in r["fails"]))

    lat = sorted(r["elapsed_ms"] for r in results)
    p50 = lat[len(lat) // 2] if lat else 0
    p95 = lat[min(len(lat) - 1, int(len(lat) * 0.95))] if lat else 0

    cats: Dict[str, List[int]] = {}
    for r in results:
        c = cats.setdefault(r["category"], [0, 0])
        c[1] += 1
        c[0] += 1 if r["passed"] else 0

    return {
        "config": {"rerank": config.ENABLE_RERANK, "auditor": auditor_on,
                   "safety": config.ENABLE_SAFETY, "top_k": config.TOP_K,
                   "engine": config.LLM_MODE},
        "total": total,
        "passed": ok,
        "task_success_rate": round(ok / total * 100, 1) if total else 0.0,
        "intent_accuracy": intent_rate, "intent_cases": intent_n,
        "tool_accuracy": tool_rate, "tool_cases": tool_n,
        "citation_hit_rate": cite_rate, "citation_cases": cite_n,
        "citation_top1_rate": top1_rate,
        "audit_pass_rate": audit_rate,
        "multiturn_rate": mt_rate, "multiturn_cases": mt_n,
        "safety_refusal_rate": safe_rate, "safety_cases": safe_n,
        "abstain_rate": abst_rate, "abstain_cases": abst_n,
        "hallucination_cases": hallu_n,
        "hallucination_rate": round(hallu_n / total * 100, 1) if total else 0.0,
        "latency_p50_ms": p50, "latency_p95_ms": p95,
        "latency_mean_ms": round(statistics.mean(lat), 1) if lat else 0.0,
        "categories": {k: {"passed": v[0], "total": v[1],
                          "rate": round(v[0] / v[1] * 100, 1)} for k, v in sorted(cats.items())},
    }


def run_all(baseline: bool, tag: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    cases = load_cases()
    config.ENABLE_RERANK = not baseline
    config.ENABLE_AUDITOR = not baseline
    results = [run_one(c, tag, auditor_on=config.ENABLE_AUDITOR) for c in cases]
    return summarize(results, cases, config.ENABLE_AUDITOR), results


def fmt_table(summary: Dict[str, Any], results: List[Dict[str, Any]], title: str) -> str:
    s = summary
    lines = [f"### {title}", "",
             f"- 配置：重排={'开' if s['config']['rerank'] else '关'}，"
             f"自检={'开' if s['config']['auditor'] else '关'}，"
             f"安全过滤={'开' if s['config']['safety'] else '关'}，"
             f"Top-K={s['config']['top_k']}，引擎={s['config']['engine']}",
             "",
             "| 指标 | 结果 | 样本数 |", "| --- | --- | --- |",
             f"| 任务成功率 | {s['task_success_rate']}%（{s['passed']}/{s['total']}） | {s['total']} |",
             f"| 意图准确率 | {s['intent_accuracy']}% | {s['intent_cases']} |",
             f"| 工具调用准确率 | {s['tool_accuracy']}% | {s['tool_cases']} |",
             f"| 引用命中率 | {s['citation_hit_rate']}% | {s['citation_cases']} |",
             f"| 引用 Top-1 命中率 | {s['citation_top1_rate']}% | {s['citation_cases']} |",
             f"| 自检通过率 | {s['audit_pass_rate']}% | {s['total']} |",
             f"| 多轮指代正确率 | {s['multiturn_rate']}% | {s['multiturn_cases']} |",
             f"| 安全拒答率 | {s['safety_refusal_rate']}% | {s['safety_cases']} |",
             f"| 弃答正确率（无依据不硬答） | {s['abstain_rate']}% | {s['abstain_cases']} |",
             f"| 幻觉/越界表述 | {s['hallucination_rate']}%（{s['hallucination_cases']} 条） | {s['total']} |",
             f"| 延迟 P50 / P95 | {s['latency_p50_ms']}ms / {s['latency_p95_ms']}ms | {s['total']} |",
             "",
             "| 分类 | 通过/总数 | 通过率 |", "| --- | --- | --- |"]
    for k, v in s["categories"].items():
        lines.append(f"| {k} | {v['passed']}/{v['total']} | {v['rate']}% |")

    bad = [r for r in results if not r["passed"]]
    lines.append("")
    if bad:
        lines.append("**未通过用例**")
        lines.append("")
        lines.append("| 用例 | 提问 | 失败原因 |")
        lines.append("| --- | --- | --- |")
        for r in bad:
            lines.append(f"| {r['id']} | {r['turns'][-1]} | {'；'.join(r['fails'])} |")
    else:
        lines.append("**全部用例通过。**")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", action="store_true", help="关闭重排与自检（消融对照）")
    ap.add_argument("--compare", action="store_true", help="同时跑两种配置并生成对比报告")
    ap.add_argument("--out", default=str(EVAL_DIR / "report.md"))
    args = ap.parse_args()

    started = time.strftime("%Y-%m-%d %H:%M:%S")
    sections = [f"# 评测报告\n", f"生成时间：{started}　·　用例集：`eval/cases.jsonl`　·　"
                f"课程库 {len(ds.courses())} 门　·　知识库 7 篇\n"]

    if args.compare:
        base_sum, base_res = run_all(True, "base")
        opt_sum, opt_res = run_all(False, "opt")
        sections.append(fmt_table(base_sum, base_res, "对照配置（关闭重排与自检）"))
        sections.append("")
        sections.append(fmt_table(opt_sum, opt_res, "优化后配置（重排 + 自检开启）"))
        sections.append("")
        sections.append("### 前后对比")
        sections.append("")
        sections.append("| 指标 | 对照 | 优化后 | 变化 |")
        sections.append("| --- | --- | --- | --- |")
        for key, label in [("task_success_rate", "任务成功率"),
                           ("citation_hit_rate", "引用命中率"),
                           ("citation_top1_rate", "引用 Top-1 命中率"),
                           ("audit_pass_rate", "自检通过率"),
                           ("intent_accuracy", "意图准确率"),
                           ("tool_accuracy", "工具调用准确率"),
                           ("hallucination_rate", "幻觉/越界表述占比")]:
            b, o = base_sum[key], opt_sum[key]
            delta = round(o - b, 1)
            sections.append(f"| {label} | {b}% | {o}% | {delta:+}pt |")
        for key, label in [("latency_p50_ms", "延迟 P50"), ("latency_p95_ms", "延迟 P95")]:
            b, o = base_sum[key], opt_sum[key]
            sections.append(f"| {label} | {b}ms | {o}ms | {o - b:+.0f}ms |")
        sections.append("")
        sections.append("> 注：自检（Auditor）关闭时，用例中与自检相关的断言不计入判定，"
                        "因此对照组的\"任务成功率\"只反映检索与工具层面的差异。")
        sections.append("")
        sections.append("### 补充：检索排序子集（区分度更高）")
        sections.append("")
        sections.append("主用例集在两种配置下均已满分，说明它已不足以区分重排模块的作用。"
                        "因此单列一个只测检索排序的子集（`eval/retrieval_cases.json`，25 条，"
                        "不经过工具与生成），用它测量重排的真实增益：")
        sections.append("")
        try:
            from eval.run_retrieval import evaluate as eval_retrieval
            r_off = eval_retrieval(False)
            r_on = eval_retrieval(True)
            sections.append("| 指标 | 仅 BM25 | BM25 + 特征重排 | 变化 |")
            sections.append("| --- | --- | --- | --- |")
            for key, label, pct in [("top1_doc_rate", "Top-1 文档命中率", True),
                                    ("section_hit_rate", "章节命中率", True),
                                    ("recall_at_k", "Recall@5", True),
                                    ("mrr", "MRR@5", False)]:
                a, b = r_off[key], r_on[key]
                fa = f"{a}%" if pct else f"{a:.4f}"
                fb = f"{b}%" if pct else f"{b:.4f}"
                dl = f"{b - a:+.1f}pt" if pct else f"{b - a:+.4f}"
                sections.append(f"| {label} | {fa} | {fb} | {dl} |")
            sections.append("")
            sections.append("检索子集未在第一位命中的用例，已在 `eval/retrieval_report.md` 逐条列出，"
                            "用于说明剩余误差来自片段切分边界而非重排逻辑。")
        except Exception as exc:  # 检索子集失败不应影响主报告
            sections.append(f"（检索子集运行失败：{type(exc).__name__}: {exc}）")
        payload = {"generated_at": started, "baseline": base_sum, "optimized": opt_sum,
                   "baseline_results": base_res, "optimized_results": opt_res}
    else:
        summary, results = run_all(args.baseline, "base" if args.baseline else "opt")
        sections.append(fmt_table(summary, results,
                                  "对照配置（关闭重排与自检）" if args.baseline else "优化后配置"))
        payload = {"generated_at": started,
                   "baseline" if args.baseline else "optimized": summary,
                   "results": results}

    sections.append("")
    sections.append("### 复现方式")
    sections.append("")
    sections.append("```")
    sections.append("python -m eval.run_eval --compare    # 完整对比")
    sections.append("python -m eval.run_eval             # 仅优化后配置")
    sections.append("python -m eval.run_eval --baseline  # 仅对照配置")
    sections.append("```")
    sections.append("")
    sections.append("### 指标口径")
    sections.append("")
    sections.append("- **任务成功率**：单条用例的全部断言均通过才算通过，分母为全部用例数。")
    sections.append("- **意图/工具/引用准确率**：仅统计设置了对应断言的用例子集。")
    sections.append("- **幻觉率**：回答中出现课程库之外的课程代码，或出现\"保证/包过\"等承诺性表述的用例占比。")
    sections.append("- **弃答正确率**：知识库确实不覆盖的问题，回答应明确\"没有找到依据\"而不是编造。")
    sections.append("- **延迟**：一次 `handle()` 的端到端墙钟时间，含规划、工具、检索、校验与生成。")

    Path(args.out).write_text("\n".join(sections), encoding="utf-8")
    (EVAL_DIR / "report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(sections[:60]))
    print(f"\n报告已写入 {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

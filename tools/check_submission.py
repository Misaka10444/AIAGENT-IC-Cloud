# -*- coding: utf-8 -*-
"""提交前自检：目录完整性、密钥与隐私扫描、大文件检查、代码规模统计。

运行：python tools/check_submission.py
"""
from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REQUIRED = [
    "README.md", "requirements.txt", ".env.example", ".gitignore",
    "src/config.py", "src/cli.py", "src/server/app.py",
    "src/agent/orchestrator.py", "src/agent/planner.py", "src/agent/memory.py",
    "src/agent/auditor.py", "src/agent/composer.py", "src/agent/safety.py",
    "src/agent/llm.py", "src/agent/prompts/system_intent.md",
    "src/tools/registry.py", "src/tools/academic.py", "src/tools/planning.py",
    "src/tools/knowledge.py", "src/tools/data_store.py",
    "src/rag/index.py", "src/observability/trace.py",
    "data/courses.json", "data/program_ai_2025.json", "data/SOURCES.md",
    "data/students/S001.json", "data/students/S002.json", "data/students/S003.json",
    "data/kb/01_培养方案说明.md", "data/kb/02_选课管理办法.md",
    "data/kb/03_重修与学分认定规定.md", "data/kb/04_毕业资格审核要点.md",
    "data/kb/05_学业预警与帮扶办法.md", "data/kb/06_课程简介汇编.md",
    "data/kb/07_生成式AI使用规范.md",
    "eval/cases.jsonl", "eval/run_eval.py", "eval/retrieval_cases.json",
    "eval/run_retrieval.py", "eval/test_llm_path.py", "eval/report.md",
    "eval/retrieval_report.md",
    "docs/design.md", "docs/interfaces.md",
    "docs/figures/fig1_architecture.png", "docs/figures/fig2_sequence.png",
    "docs/figures/fig3_rag_pipeline.png",
    "demo/demo_script.md", "demo/README.md",
]

SECRET_PATTERNS = [
    (r"sk-[A-Za-z0-9]{16,}", "疑似 API Key"),
    (r"AKIA[0-9A-Z]{16}", "疑似 AWS Key"),
    (r"(?i)api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9_\-]{12,}", "硬编码 API Key"),
    (r"(?i)password\s*[:=]\s*['\"][^'\"]{6,}", "硬编码密码"),
    (r"\b1[3-9]\d{9}\b", "疑似手机号"),
    (r"\b\d{17}[\dXx]\b", "疑似身份证号"),
    (r"WeChat聊天记录", "泄露本地路径（聊天记录目录）"),
    (r"[A-Za-z]:\\\\?DSH新建项目集", "泄露本机绝对路径"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "私钥"),
]

TEXT_EXT = {".py", ".md", ".json", ".jsonl", ".txt", ".yml", ".yaml", ".ps1",
            ".html", ".css", ".js", ".example"}
SKIP_DIRS = {"__pycache__", ".git", "dist", "logs", "node_modules", ".venv"}
SELF = Path(__file__).resolve()


def walk_text():
    for p in ROOT.rglob("*"):
        if p.is_dir() or any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.resolve() == SELF:      # 扫描器自身含有检索特征串，跳过
            continue
        if p.suffix.lower() in TEXT_EXT or p.name in (".env.example", ".gitignore"):
            yield p


def main() -> int:
    ok = True

    print("=" * 62)
    print("1) 目录完整性")
    missing = [f for f in REQUIRED if not (ROOT / f).exists()]
    if missing:
        ok = False
        print("  缺失文件：")
        for m in missing:
            print("   -", m)
    else:
        print(f"  通过：{len(REQUIRED)} 项必需文件全部存在")

    print("=" * 62)
    print("2) 密钥与隐私扫描")
    hits = []
    for p in walk_text():
        try:
            txt = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for pat, label in SECRET_PATTERNS:
            for m in re.finditer(pat, txt):
                line = txt[:m.start()].count("\n") + 1
                hits.append((p.relative_to(ROOT), line, label, m.group(0)[:40]))
    if hits:
        ok = False
        for rel, ln, label, val in hits:
            print(f"  ! {rel}:{ln}  {label} -> {val}")
    else:
        print("  通过：未发现密钥、手机号、身份证号与本机绝对路径")

    print("=" * 62)
    print("3) 大文件检查（单文件 ≤ 50MB）")
    big = [(p, p.stat().st_size) for p in ROOT.rglob("*")
           if p.is_file() and p.stat().st_size > 50 * 1024 * 1024]
    if big:
        ok = False
        for p, s in big:
            print(f"  ! {p.relative_to(ROOT)} {s/1048576:.1f}MB")
    else:
        print("  通过：无超过 50MB 的文件")

    print("=" * 62)
    print("4) 代码规模")
    py = [p for p in ROOT.rglob("*.py")
          if not any(d in p.parts for d in SKIP_DIRS) and "tools" not in p.parts]
    total = 0
    for p in sorted(py):
        n = len(p.read_text(encoding="utf-8").splitlines())
        total += n
    print(f"  src/ 与 eval/ 共 {len(py)} 个 Python 文件，{total} 行")
    kb = list((ROOT / "data" / "kb").glob("*.md"))
    kb_chars = sum(len(p.read_text(encoding="utf-8")) for p in kb)
    print(f"  知识库 {len(kb)} 篇，{kb_chars} 字")

    print("=" * 62)
    print("结论：" + ("全部通过" if ok else "存在问题，请按上面提示修正"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

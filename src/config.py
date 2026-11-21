# -*- coding: utf-8 -*-
"""全局配置。全部路径相对仓库根目录，通过环境变量可覆盖。"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
KB_DIR = DATA_DIR / "kb"
STUDENT_DIR = DATA_DIR / "students"
EVAL_DIR = ROOT / "eval"
LOG_DIR = Path(os.environ.get("AGENT_LOG_DIR", ROOT / "logs"))

# ---------------- 模型网关（可选） ----------------
# 未配置时使用本地确定性引擎（规则路由 + 词表打分），保证零密钥可运行。
LLM_MODE = os.environ.get("LLM_MODE", "local").strip().lower()   # local | gateway
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "").rstrip("/")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "")
LLM_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "20"))
LLM_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0.2"))

# ---------------- 检索与推理参数 ----------------
TOP_K = int(os.environ.get("AGENT_TOP_K", "5"))
CHUNK_SIZE = 400
CHUNK_OVERLAP = 80
BM25_K1 = 1.5
BM25_B = 0.75

# 相关性下限：Top-1 的 BM25 得分低于该值即视为"知识库无依据"，宁可不答也不硬答。
# 取值依据见 docs/design.md 5.3：无关提问的 Top-1 得分集中在 2.9—3.0，
# 有效提问的 Top-1 得分在 5.4 以上，取 3.5 作为分界留出两侧余量。
MIN_SCORE = float(os.environ.get("AGENT_MIN_SCORE", "3.5"))

# 消融开关：评测用于"优化前后对比"，生产默认全开
ENABLE_RERANK = os.environ.get("AGENT_RERANK", "1") == "1"
ENABLE_AUDITOR = os.environ.get("AGENT_AUDITOR", "1") == "1"
ENABLE_SAFETY = os.environ.get("AGENT_SAFETY", "1") == "1"

APP_NAME = "云梯 · 学业规划与选课顾问 Agent"
APP_VERSION = "1.0.0"
TRACE_FILE = LOG_DIR / "trace.jsonl"


def ensure_dirs() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

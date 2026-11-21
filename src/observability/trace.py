# -*- coding: utf-8 -*-
"""结构化追踪日志：每个会话、每次工具调用、每个智能体角色都落盘为 JSONL。

用于两个目的：
1. 现场演示与答辩时复盘"智能体到底做了什么"；
2. 评测脚本据此统计工具调用准确率与延迟分位数。
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, List

from src import config


class Trace:
    def __init__(self, session_id: str | None = None, turn: int = 0, persist: bool = True):
        self.session_id = session_id or uuid.uuid4().hex[:12]
        self.turn = turn
        self.run_id = uuid.uuid4().hex[:10]
        self.persist = persist
        self.started_at = time.time()
        self.events: List[Dict[str, Any]] = []
        self.tool_calls: List[Dict[str, Any]] = []

    # ---------- 记录 ----------
    def log(self, kind: str, name: str, status: str = "ok", **fields: Any) -> None:
        ev = {
            "ts": round((time.time() - self.started_at) * 1000, 1),
            "kind": kind,
            "name": name,
            "status": status,
            "run_id": self.run_id,
            "turn": self.turn,
        }
        ev.update(fields)
        self.events.append(ev)

    def tool(self, name: str, args: Dict[str, Any], result: Dict[str, Any],
             ms: float, attempts: int = 1) -> None:
        rec = {
            "tool": name,
            "args": args,
            "ok": result.get("ok", False),
            "ms": round(ms, 1),
            "attempts": attempts,
        }
        if result.get("ok"):
            rec["data_keys"] = sorted(result.get("data", {}).keys())
        else:
            rec["error"] = result.get("error", {})
        self.tool_calls.append(rec)
        self.log("tool", name, "ok" if result.get("ok") else "error", **rec)

    # ---------- 落盘 ----------
    def close(self, status: str = "ok") -> Dict[str, Any]:
        duration = round((time.time() - self.started_at) * 1000, 1)
        summary = {
            "session_id": self.session_id,
            "run_id": self.run_id,
            "turn": self.turn,
            "status": status,
            "duration_ms": duration,
            "tool_call_count": len(self.tool_calls),
            "tools": [c["tool"] for c in self.tool_calls],
            "events": self.events,
        }
        if self.persist:
            try:
                config.ensure_dirs()
                with open(config.TRACE_FILE, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(summary, ensure_ascii=False) + "\n")
            except OSError:
                pass
        return summary

    # ---------- 展示 ----------
    def role_timeline(self) -> List[Dict[str, str]]:
        """把事件折叠成"角色时间线"，供前端渲染多智能体协作过程。"""
        out = []
        for ev in self.events:
            if ev["kind"] in ("role", "tool", "guard"):
                out.append({
                    "role": ev.get("actor", ev["kind"]),
                    "action": ev["name"],
                    "status": ev["status"],
                    "ms": ev.get("ts"),
                })
        return out

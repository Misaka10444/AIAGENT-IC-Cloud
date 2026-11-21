# -*- coding: utf-8 -*-
"""本地 Web 演示服务：标准库 http.server，零第三方依赖。

接口：
  GET  /                 演示页面
  GET  /api/bootstrap    学生画像、培养方案、工具清单、知识库统计
  POST /api/chat         {"message": "...", "session_id": "..."}
  POST /api/reset        {"session_id": "..."}
  GET  /api/trace?limit= 最近若干条运行轨迹
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

from src import config
from src.agent.orchestrator import get_agent
from src.rag import index as kb_index
from src.tools import data_store as ds
from src.tools import registry as reg
import src.tools  # noqa: F401

STATIC = Path(__file__).parent / "static"
_LOCK = threading.Lock()


def _students_payload() -> Dict[str, Any]:
    out = []
    for sid in ds.list_students():
        st = ds.student(sid)
        out.append({
            "student_id": sid,
            "alias": st["alias"],
            "grade": st["grade"],
            "major": st["major"],
            "current_term": st["current_term"],
            "goal": st["goal"],
            "target_direction": st["target_direction"],
            "completed_count": len(st["completed"]),
            "in_progress": st.get("in_progress", []),
        })
    return {"students": out}


class Handler(BaseHTTPRequestHandler):
    server_version = "YuntiAgent/" + config.APP_VERSION

    # ---------- 基础 ----------
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj: Any, code: int = 200) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _body(self) -> Dict[str, Any]:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def log_message(self, fmt: str, *args: Any) -> None:  # 静默访问日志
        pass

    # ---------- 路由 ----------
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._serve_static("index.html", "text/html; charset=utf-8")
        if path.startswith("/static/"):
            name = path[len("/static/"):]
            ctype = {
                ".css": "text/css; charset=utf-8",
                ".js": "application/javascript; charset=utf-8",
                ".svg": "image/svg+xml",
                ".png": "image/png",
            }.get(Path(name).suffix, "application/octet-stream")
            return self._serve_static(name, ctype)
        if path == "/api/bootstrap":
            payload = {
                "app": {"name": config.APP_NAME, "version": config.APP_VERSION},
                "engine": "gateway" if config.LLM_MODE == "gateway" else "local",
                "tools": reg.tool_specs(),
                "kb": kb_index.index().stats(),
                "program": ds.program()["requirements"],
                "courses": len(ds.courses()),
            }
            payload.update(_students_payload())
            return self._json(payload)
        if path == "/api/trace":
            return self._json({"lines": self._recent_trace(20)})
        if path == "/api/health":
            return self._json({"ok": True, "version": config.APP_VERSION})
        return self._json({"error": "not_found"}, 404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        body = self._body()
        if path == "/api/chat":
            message = str(body.get("message", "")).strip()
            session_id = str(body.get("session_id", "web"))[:64]
            if not message:
                return self._json({"error": "empty_message"}, 400)
            with _LOCK:
                out = get_agent().handle(message, session_id=session_id)
            out.pop("trace_raw", None)
            return self._json(out)
        if path == "/api/reset":
            get_agent().reset(str(body.get("session_id", "web")))
            return self._json({"ok": True})
        return self._json({"error": "not_found"}, 404)

    # ---------- 静态 ----------
    def _serve_static(self, name: str, ctype: str) -> None:
        target = (STATIC / name).resolve()
        if STATIC.resolve() not in target.parents and target != STATIC.resolve():
            return self._json({"error": "forbidden"}, 403)
        if not target.exists() or not target.is_file():
            return self._json({"error": "not_found"}, 404)
        self._send(200, target.read_bytes(), ctype)

    def _recent_trace(self, limit: int) -> list:
        f = config.TRACE_FILE
        if not f.exists():
            return []
        lines = f.read_text(encoding="utf-8").strip().splitlines()[-limit:]
        out = []
        for ln in lines:
            try:
                d = json.loads(ln)
            except json.JSONDecodeError:
                continue
            out.append({"run_id": d.get("run_id"), "turn": d.get("turn"),
                        "tools": d.get("tools"), "duration_ms": d.get("duration_ms"),
                        "status": d.get("status")})
        return out


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"{config.APP_NAME} 演示服务已启动：http://{host}:{port}")
    print("Ctrl+C 停止。")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    serve(a.host, a.port)

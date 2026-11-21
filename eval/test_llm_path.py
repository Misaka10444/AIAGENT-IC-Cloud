# -*- coding: utf-8 -*-
"""最小化模型网关连通性自检：在本地起一个 mock 网关，验证三件事。

1. 请求构造正确（路径、鉴权头、消息体）；
2. 响应解析正确（取 choices[0].message.content）；
3. 网关异常时能降级到本地引擎，而不是把异常抛给对话层。

这三个点无法用真实网关验证（本环境不配置密钥），所以用 mock 固定下来。
运行：python -m eval.test_llm_path
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from src import config
from src.agent import llm

RESPONSES = {"mode": "ok"}
SEEN = []


class MockHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n).decode("utf-8")
        SEEN.append({"path": self.path, "auth": self.headers.get("Authorization"),
                     "body": json.loads(body or "{}")})
        if RESPONSES["mode"] == "http500":
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"boom")
            return
        if RESPONSES["mode"] == "badjson":
            payload = b"not-a-json"
        else:
            payload = json.dumps({
                "choices": [{"message": {"content": "plan_build"}}],
                "usage": {"total_tokens": 12},
            }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def run() -> int:
    srv = HTTPServer(("127.0.0.1", 0), MockHandler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    ok = True

    # 1) 未配置网关：应返回 NOT_CONFIGURED，而不是抛异常
    config.LLM_MODE = "local"
    r = llm.chat([{"role": "user", "content": "hi"}])
    assert r["ok"] is False and r["error"]["code"] == "NOT_CONFIGURED", r
    print("PASS 未配置网关时返回 NOT_CONFIGURED，不抛异常")

    # 2) 正常响应：请求构造与解析
    config.LLM_MODE = "gateway"
    config.LLM_BASE_URL = f"http://127.0.0.1:{port}/v1"
    config.LLM_API_KEY = "test-key"
    config.LLM_MODEL = "mock-model"
    SEEN.clear()

    r = llm.chat([{"role": "user", "content": "帮我排课"}], temperature=0.0)
    if not (r["ok"] and r["content"] == "plan_build"):
        print("FAIL 正常响应解析", r)
        ok = False
    else:
        print("PASS 正常响应解析：content =", r["content"])
    if SEEN and SEEN[0]["path"].endswith("/chat/completions") \
            and SEEN[0]["auth"] == "Bearer test-key" \
            and SEEN[0]["body"]["model"] == "mock-model":
        print("PASS 请求构造：path/auth/model 均正确")
    else:
        print("FAIL 请求构造", SEEN[:1])
        ok = False

    # 3) 意图分类：集合内返回
    r = llm.classify_intent("帮我排课", ["plan_build", "policy_qa"])
    if r.get("ok") and r.get("intent") == "plan_build":
        print("PASS 意图分类命中集合内取值")
    else:
        print("FAIL 意图分类", r)
        ok = False

    # 4) 网关 500：应降级而不是抛异常
    RESPONSES["mode"] = "http500"
    r = llm.chat([{"role": "user", "content": "x"}])
    if r["ok"] is False and r["error"]["code"].startswith("HTTP_"):
        print("PASS 网关 500 时返回结构化错误：", r["error"]["code"])
    else:
        print("FAIL 网关 500 处理", r)
        ok = False

    # 5) 非法 JSON：应返回 BAD_JSON
    RESPONSES["mode"] = "badjson"
    r = llm.chat([{"role": "user", "content": "x"}])
    if r["ok"] is False and r["error"]["code"] == "BAD_JSON":
        print("PASS 非法 JSON 返回 BAD_JSON")
    else:
        print("FAIL 非法 JSON 处理", r)
        ok = False

    # 6) 端到端降级：网关坏掉时 Agent 仍能回答
    from src.agent.orchestrator import get_agent
    a = get_agent()
    a.reset("llm-fallback")
    out = a.handle("S001 我差多少学分", session_id="llm-fallback")
    if out["intent"] == "credit_progress" and out["elapsed_ms"] > 0:
        print("PASS 网关异常时 end-to-end 降级到本地引擎，意图 =", out["intent"])
    else:
        print("FAIL 端到端降级", out["intent"])
        ok = False

    srv.shutdown()
    print("\n结果：" + ("全部通过" if ok else "存在失败项"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(run())

# -*- coding: utf-8 -*-
"""模型网关客户端（OpenAI 兼容 /chat/completions），纯标准库实现。

设计约束：
- 未配置网关时**不报错**，直接返回 {ok:false, code:"NOT_CONFIGURED"}，由上层降级到本地引擎；
- 任何网络/解析异常都收敛成结构化错误，绝不把异常抛给对话层；
- 不在日志里打印密钥。
本模块已在本地 mock 网关上验证过请求构造、响应解析与降级链路（见 eval/test_llm_path.py）。
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from src import config


def available() -> bool:
    return bool(config.LLM_MODE == "gateway" and config.LLM_BASE_URL
                and config.LLM_MODEL and config.LLM_API_KEY)


def _post(path: str, payload: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    url = config.LLM_BASE_URL.rstrip("/") + path
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config.LLM_API_KEY}",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw)


def chat(messages: List[Dict[str, str]], temperature: Optional[float] = None,
         max_tokens: int = 800, retries: int = 2) -> Dict[str, Any]:
    if not available():
        return {"ok": False, "error": {"code": "NOT_CONFIGURED",
                                       "message": "未配置模型网关，使用本地引擎"}}
    payload = {
        "model": config.LLM_MODEL,
        "messages": messages,
        "temperature": config.LLM_TEMPERATURE if temperature is None else temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    last = None
    for attempt in range(retries + 1):
        try:
            data = _post("/chat/completions", payload, config.LLM_TIMEOUT)
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
            if not content:
                last = {"code": "EMPTY_RESPONSE", "message": "网关返回空内容"}
            else:
                return {"ok": True, "content": content,
                        "usage": data.get("usage", {}), "attempts": attempt + 1}
        except urllib.error.HTTPError as exc:
            last = {"code": f"HTTP_{exc.code}", "message": exc.reason}
            if exc.code in (400, 401, 403, 404):
                break
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = {"code": "NETWORK", "message": str(exc)}
        except json.JSONDecodeError as exc:
            last = {"code": "BAD_JSON", "message": str(exc)}
            break
        time.sleep(0.2 * (attempt + 1))
    return {"ok": False, "error": last or {"code": "UNKNOWN", "message": "调用失败"}}


def classify_intent(text: str, allowed: List[str]) -> Dict[str, Any]:
    """让模型只在给定意图集合内做分类，返回 {ok, intent} 或降级信号。"""
    import pathlib
    prompt_path = pathlib.Path(__file__).parent / "prompts" / "system_intent.md"
    system = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
    system = system.replace("{allowed}", "、".join(allowed))
    res = chat([{"role": "system", "content": system},
                {"role": "user", "content": text}], temperature=0.0, max_tokens=32)
    if not res.get("ok"):
        return {"ok": False, "error": res.get("error")}
    word = res["content"].strip().split()[0].strip("，。,.：:\"'")
    if word in allowed:
        return {"ok": True, "intent": word}
    return {"ok": False, "error": {"code": "OUT_OF_SET", "message": word[:40]}}

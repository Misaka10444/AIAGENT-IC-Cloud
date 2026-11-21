# -*- coding: utf-8 -*-
"""命令行入口：单轮问答与多轮交互。

用法：
    python -m src.cli "S001 下学期怎么选课"
    python -m src.cli --chat            # 交互模式，输入 exit 退出
    python -m src.cli --tools           # 打印工具清单
"""
from __future__ import annotations

import argparse
import json
import sys

from src import config
from src.agent.orchestrator import get_agent
from src.tools import registry as reg


def print_tools() -> None:
    specs = reg.tool_specs()
    print(f"已注册工具 {len(specs)} 个：\n")
    for s in specs:
        print(f"- {s['name']}: {s['description']}")
        for p, meta in s["parameters"].items():
            print(f"    · {p}: {meta.get('type')} {'(必填)' if meta.get('required') else ''}")
        print(f"    返回: {s['returns']}")


def show(out: dict, verbose: bool = False) -> None:
    print("\n" + "=" * 72)
    print(f"意图: {out['intent']}  置信度: {out['confidence']}  引擎: {out['engine']}  "
          f"耗时: {out['elapsed_ms']}ms")
    print("=" * 72)
    print(out["answer"])
    if verbose:
        print("\n--- 工具调用 ---")
        for c in out["tool_calls"]:
            print(f"  {c['tool']} ok={c['ok']} {c['ms']}ms attempts={c['attempts']}")
        print("\n--- 校验 ---")
        print(f"  passed={out['audit']['passed']} {out['audit'].get('summary', '')}")
        print("\n--- 事实 ---")
        print("  " + json.dumps(out["facts"], ensure_ascii=False))


def main() -> int:
    ap = argparse.ArgumentParser(description=config.APP_NAME)
    ap.add_argument("question", nargs="*", help="要问的问题")
    ap.add_argument("--chat", action="store_true", help="交互模式")
    ap.add_argument("--tools", action="store_true", help="打印工具清单")
    ap.add_argument("--verbose", action="store_true", help="打印工具调用与校验明细")
    ap.add_argument("--session", default="cli", help="会话 id")
    args = ap.parse_args()

    if args.tools:
        print_tools()
        return 0

    agent = get_agent()
    if args.chat or not args.question:
        print(f"{config.APP_NAME} v{config.APP_VERSION}（输入 exit 退出）")
        while True:
            try:
                text = input("\n你: ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if text in ("exit", "quit", "退出"):
                break
            if not text:
                continue
            show(agent.handle(text, session_id=args.session), verbose=args.verbose)
        return 0

    show(agent.handle(" ".join(args.question), session_id=args.session), verbose=args.verbose)
    return 0


if __name__ == "__main__":
    sys.exit(main())

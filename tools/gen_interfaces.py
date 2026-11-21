# -*- coding: utf-8 -*-
"""从工具注册中心导出接口文档，避免文档与代码漂移。

运行：python tools/gen_interfaces.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 允许直接以 `python tools/gen_interfaces.py` 运行（无需设置 PYTHONPATH）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import src.tools  # noqa: F401  注册全部工具
from src.tools import data_store as ds
from src.tools import registry as reg

OUT = str(Path(__file__).resolve().parent.parent / "docs" / "interfaces.md")

HEADER = """# 工具与接口说明

> 本文件由 `python tools/gen_interfaces.py` 从工具注册中心自动导出，与代码保持一致。
> 手工修改会在下次导出时被覆盖。

## 1 调用约定

所有工具通过 `src/tools/registry.py` 的 `call(name, **args)` 统一调用，返回**统一信封**：

```json
{"ok": true,  "data": { ... }}
{"ok": false, "error": {"code": "COURSE_NOT_FOUND", "message": "课程库中没有课程 C9999", "retryable": false}}
```

调用链固定为：**参数校验 → 执行 → 失败分类 → 可重试则退避重试（最多 2 次）→ 记录 trace**。

### 1.1 错误码

| 错误码 | 触发条件 | 可重试 |
| --- | --- | --- |
| `MISSING_PARAM` | 缺少必填参数 | 否 |
| `TYPE_MISMATCH` | 参数类型不符且无法安全转换 | 否 |
| `ENUM_MISMATCH` | 参数不在枚举范围内 | 否 |
| `STUDENT_NOT_FOUND` | 学生代号不存在 | 否 |
| `COURSE_NOT_FOUND` | 课程代码不存在 | 否 |
| `INVALID_TERM` | 学期不在 1—8 之间 | 否 |
| `EMPTY_QUERY` | 检索词为空 | 否 |
| `UNKNOWN_TOOL` | 调用了未注册的工具 | 否 |
| `IO_ERROR` | 文件读写或网络异常 | 是 |
| `INTERNAL_ERROR` | 未预期的内部异常 | 否 |

## 2 工具清单

"""

TAIL = """
## 3 HTTP 接口

Web 演示服务由 `python -m src.server.app` 启动（标准库 `http.server`）。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/` | 演示页面 |
| GET | `/api/bootstrap` | 学生画像、工具清单、知识库统计、培养方案要求 |
| POST | `/api/chat` | `{"message": "...", "session_id": "..."}` → 回答与完整轨迹 |
| POST | `/api/reset` | `{"session_id": "..."}` 清空会话记忆 |
| GET | `/api/trace` | 最近 20 条运行轨迹摘要 |
| GET | `/api/health` | 健康检查 |

`/api/chat` 返回字段：

| 字段 | 说明 |
| --- | --- |
| `answer` | Markdown 格式回答 |
| `intent` / `confidence` / `engine` | 意图、置信度、引擎（local / gateway） |
| `plan` | 子任务分解与工具选路 |
| `tool_calls` | 每个工具的调用结果、耗时、重试次数 |
| `citations` | 引用片段：文档号、章节、原文行号、摘录 |
| `facts` | 结构化事实，供前端与评测断言使用 |
| `audit` | 自检结论（通过 / 注意 / 失败） |
| `roles` | 角色时间线，前端据此渲染协作过程 |
| `elapsed_ms` | 端到端耗时 |
| `trace` | run_id / session_id / turn |
"""


def main() -> None:
    specs = reg.tool_specs()
    lines = [HEADER, f"共 **{len(specs)} 个**工具，课程库 {len(ds.courses())} 门，"
                     f"培养方案 {ds.program()['requirements']['total_credits']:g} 学分。\n"]
    for i, s in enumerate(specs, 1):
        lines.append(f"### 2.{i} `{s['name']}`\n")
        lines.append(f"{s['description']}\n")
        lines.append("| 参数 | 类型 | 必填 | 说明 |")
        lines.append("| --- | --- | --- | --- |")
        params = reg.registry()[s["name"]]["params"]
        if not params:
            lines.append("| — | — | — | 无参数 |")
        for pname, meta in params.items():
            required = "是" if meta.get("required") else "否"
            desc = meta.get("desc", "")
            enum = f"（枚举：{' / '.join(meta['enum'])}）" if meta.get("enum") else ""
            default = f"，默认 {meta['default']}" if "default" in meta else ""
            lines.append(f"| `{pname}` | {meta.get('type', '-')} | {required} | {desc}{enum}{default} |")
        lines.append("")
        lines.append(f"**返回**：`{s['returns']}`\n")
        raises = "、".join(f"`{r}`" for r in s["raises"]) if s["raises"] else "无"
        lines.append(f"**异常**：{raises}\n")
    text = "\n".join(lines) + TAIL
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(text)
    print("wrote", OUT, len(text), "chars")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""导入即注册全部工具。新增工具时只改第一行。

注意：这里刻意**不**把 registry 函数再导出为同名属性，避免遮蔽 registry 子模块。
"""
from src.tools import academic, knowledge, planning  # noqa: F401
from src.tools.registry import call, tool_specs  # noqa: F401

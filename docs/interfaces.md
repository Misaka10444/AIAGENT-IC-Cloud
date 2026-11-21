# 工具与接口说明

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


共 **10 个**工具，课程库 62 门，培养方案 144 学分。

### 2.1 `get_student_profile`

读取学生脱敏画像：年级、专业、目标方向、选课偏好、已修课程与成绩。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `student_id` | string | 是 | 学生代号，如 S001 |

**返回**：`{student_id, alias, grade, goal, target_direction, preferences, completed_count, failed_courses}`

**异常**：`STUDENT_NOT_FOUND`

### 2.2 `calc_credit_progress`

按培养方案六个模块核算已通过学分、缺口与未通过课程，输出可解释的学分进度。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `student_id` | string | 是 | 学生代号 |

**返回**：`{modules:[{module,required,passed,gap,status}], total:{required,passed,gap}, failed:[], unattempted_core:[]}`

**异常**：`STUDENT_NOT_FOUND`

### 2.3 `query_courses`

按学期、模块、关键字检索课程库，返回学分、先修、上课时间与容量余量。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `term` | integer | 否 | 开课学期 1-8；0 表示选修池 |
| `module` | string | 否 | （枚举：通识必修 / 通识选修 / 专业基础 / 专业核心 / 专业选修 / 集中实践） |
| `keyword` | string | 否 | 课程名或描述关键字 |
| `only_with_capacity` | boolean | 否 | 仅返回仍有容量的课程，默认 False |

**返回**：`{count, courses:[{id,name,credits,module,term,prereq,slot,capacity,enrolled,seats_left}]}`

**异常**：`ENUM_MISMATCH`

### 2.4 `check_prerequisites`

校验某门课程的先修要求是否满足。已通过=满足；在修=待确认（不计入缺失）；未修/未通过=缺失。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `course_id` | string | 是 | 课程代码，如 C5002 |
| `student_id` | string | 是 | 学生代号 |

**返回**：`{course_id, course_name, ok, prereq:[], missing:[], pending:[]}`

**异常**：`COURSE_NOT_FOUND`、`STUDENT_NOT_FOUND`

### 2.5 `check_timetable_conflict`

检测一组课程之间是否存在上课时间重叠，返回具体的冲突课程对与时隙。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `course_ids` | array | 是 | 课程代码列表，如 ["C4001","C4002"] |

**返回**：`{ok, conflicts:[{a,b,slot_a,slot_b,day,periods}], unscheduled:[]}`

**异常**：`COURSE_NOT_FOUND`

### 2.6 `check_graduation_eligibility`

按毕业审核五项必要条件逐项判定，输出不满足的条目与原因。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `student_id` | string | 是 | 学生代号 |

**返回**：`{eligible, conditions:[{no,item,ok,detail}], failed_count}`

**异常**：`STUDENT_NOT_FOUND`

### 2.7 `get_risk_warning`

按学业预警办法判定预警等级（黄/橙/红/无）。进度缺口=应修必修学分(当前学期及之前)−已通过必修学分，避免低年级被误判。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `student_id` | string | 是 | 学生代号 |

**返回**：`{level, reasons:[], actions:[], failed_count, progress_gap, should_have, passed_in_plan}`

**异常**：`STUDENT_NOT_FOUND`

### 2.8 `search_knowledge`

在培养方案、选课办法、重修规定、毕业审核、学业预警、课程简介与AI使用规范中检索，返回带文档号与章节的原文片段。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `query` | string | 是 | 自然语言问题或关键词 |
| `top_k` | integer | 否 | 返回片段数，默认 5 |

**返回**：`{count, chunks:[{doc_id,title,section,line_start,snippet,score}]}`

**异常**：`EMPTY_QUERY`

### 2.9 `get_kb_stats`

返回知识库规模统计（文档数、片段数、平均片段长度），用于答辩时说明索引构建结果。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| — | — | — | 无参数 |

**返回**：`{chunks, docs, avg_chunk_chars, vocab}`

**异常**：无

### 2.10 `build_study_plan`

生成指定学期的修读方案：满足先修、避开时间冲突、不超学分上限与容量，并给出取舍理由。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `student_id` | string | 是 | 学生代号 |
| `target_term` | integer | 否 | 目标学期 1-8，默认当前学期 |
| `elective_ids` | array | 否 | 希望额外加入的专业选修/通识选修课程代码，默认 [] |

**返回**：`{target_term, selected:[{id,name,credits,slot,role,reason}], total_credits, excluded:[{id,name,reason}], risks:[]}`

**异常**：`STUDENT_NOT_FOUND`、`COURSE_NOT_FOUND`、`INVALID_TERM`

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

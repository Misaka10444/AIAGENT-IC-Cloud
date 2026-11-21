# -*- coding: utf-8 -*-
"""Planner：意图识别 + 任务分解 + 工具选路。

本地模式用"关键词打分 + 实体抽取"做确定性规划；配置模型网关后可切换为 LLM 语义解析，
但**工具选路与参数仍由本地规则兜底校验**——这一层是刻意保留的：
学分与毕业结论不能交给概率模型自由发挥。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from src.agent.memory import Memory, detect_courses, detect_student
from src.agent.safety import check_input
from src.tools import data_store as ds

# 意图 → (关键词, 权重)。按顺序匹配，得分最高者胜出，同分取靠前者。
INTENT_RULES: List[Dict[str, Any]] = [
    {"intent": "graduation_check", "kw": ["毕业", "能不能毕", "毕业审核", "毕业资格", "还差多少能毕业",
                                          "论文", "毕设", "毕业设计"], "w": 3},
    {"intent": "risk_warn", "kw": ["预警", "帮扶", "挂科太多", "学业风险"], "w": 3},
    {"intent": "plan_build", "kw": ["规划", "方案", "怎么选", "选什么", "排课", "推荐课程", "帮我排",
                                    "下学期选", "该选", "课表"], "w": 2},
    {"intent": "conflict_check", "kw": ["冲突", "撞课", "时间重叠", "同一时间", "撞了"], "w": 3},
    {"intent": "prereq_check", "kw": ["先修", "前置", "能不能选", "可以选吗", "能选", "选得了",
                                      "条件够", "有资格选", "需要先学"], "w": 3},
    {"intent": "credit_progress", "kw": ["学分", "进度", "缺口", "差多少", "修了多少", "修够",
                                         "已修", "没通过", "挂科", "不及格"], "w": 2},
    {"intent": "profile_query", "kw": ["我的信息", "画像", "成绩单", "我挂", "我的专业", "我是谁",
                                       "我的目标", "我的偏好"], "w": 2},
    {"intent": "course_query", "kw": ["有哪些课", "开什么课", "开了哪些", "开哪些", "哪些课",
                                      "课程列表", "几门课", "多少学分", "开设", "容不容易选",
                                      "余量", "容量", "课程库"], "w": 2},
    {"intent": "policy_qa", "kw": ["规定", "办法", "要求", "标准", "怎么算", "什么意思", "是不是",
                                   "允许", "可以吗", "多少分", "几门"], "w": 1},
    {"intent": "greeting", "kw": ["你好", "您好", "hi", "hello", "在吗", "你是谁", "能做什么"], "w": 4},
]

FOLLOWUP_PATTERNS = [r"^(那|还有|继续|然后|再)", r"呢[？?]?$", r"^为什么", r"^具体"]

MODULES = ["通识必修", "通识选修", "专业基础", "专业核心", "专业选修", "集中实践"]
PERSONAL_MARKERS = ["我", "本人", "自己", "学生A", "学生B", "学生C", "他", "她"]
POLICY_MARKERS = ["要求", "标准", "多少", "几门", "规定", "是什么", "有哪些"]


def _is_personal(text: str) -> bool:
    """是否在问"某个具体学生"，而不是在问规则本身。"""
    if re.search(r"S?00\d", text, re.I):
        return True
    if re.search(r"学生\s*[ABC]", text):
        return True
    return any(p in text for p in PERSONAL_MARKERS)


def detect_module(text: str) -> Optional[str]:
    for m in MODULES:
        if m in text:
            return m
    if "必修" in text:
        return "通识必修"
    if "选修" in text:
        return "专业选修"
    return None


class Plan:
    def __init__(self, intent: str, **kw: Any):
        self.intent = intent
        self.student_id: Optional[str] = kw.get("student_id")
        self.course_ids: List[str] = kw.get("course_ids", [])
        self.term: Optional[int] = kw.get("term")
        self.need_retrieval: bool = kw.get("need_retrieval", False)
        self.retrieval_query: str = kw.get("retrieval_query", "")
        self.subtasks: List[Dict[str, Any]] = kw.get("subtasks", [])
        self.confidence: float = kw.get("confidence", 0.6)
        self.engine: str = kw.get("engine", "local")
        self.module: Optional[str] = kw.get("module")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent,
            "student_id": self.student_id,
            "course_ids": self.course_ids,
            "term": self.term,
            "module": self.module,
            "need_retrieval": self.need_retrieval,
            "retrieval_query": self.retrieval_query,
            "subtasks": self.subtasks,
            "confidence": self.confidence,
            "engine": self.engine,
        }


def _score_intents(text: str) -> List[tuple]:
    scored = []
    for order, rule in enumerate(INTENT_RULES):
        s = 0.0
        for kw in rule["kw"]:
            if kw in text:
                s += rule["w"] * (1.0 + 0.1 * len(kw))
        if s > 0:
            scored.append((s, -order, rule["intent"]))
    scored.sort(reverse=True)
    return scored


def classify(text: str, memory: Memory) -> tuple:
    if check_input(text)["blocked"]:
        return "out_of_scope", 0.95
    scored = _score_intents(text)
    is_followup = any(re.search(p, text.strip()) for p in FOLLOWUP_PATTERNS)
    if not scored:
        if is_followup and memory.slots.get("last_intent"):
            return memory.slots["last_intent"], 0.55
        return "policy_qa", 0.4
    best = scored[0][2]
    conf = min(0.95, 0.45 + scored[0][0] / 8.0)
    # 制度性提问 vs 个人核算：没有指到具体学生时，问的一定是规则本身
    if best in ("graduation_check", "credit_progress", "risk_warn") and not _is_personal(text):
        best, conf = "policy_qa", 0.6
    if is_followup and memory.slots.get("last_intent") == best:
        conf = min(0.95, conf + 0.05)
    return best, round(conf, 2)


def build_subtasks(intent: str, plan: Plan) -> List[Dict[str, Any]]:
    """把意图展开成可执行子任务（子任务 = 一个角色 + 一组工具）。"""
    sid = plan.student_id
    t = plan.term
    if intent == "credit_progress":
        return [
            {"actor": "Planner", "action": "识别为学分进度核算", "tools": []},
            {"actor": "ToolRunner", "action": "读取学生画像", "tools": ["get_student_profile"]},
            {"actor": "ToolRunner", "action": "按模块核算学分与缺口", "tools": ["calc_credit_progress"]},
            {"actor": "Retriever", "action": "检索学分与模块规则依据", "tools": ["search_knowledge"]},
            {"actor": "Auditor", "action": "校验模块与总分一致性", "tools": []},
        ]
    if intent == "prereq_check":
        return [
            {"actor": "Planner", "action": "识别为先修资格校验", "tools": []},
            {"actor": "ToolRunner", "action": "校验先修关系", "tools": ["check_prerequisites"]},
            {"actor": "Retriever", "action": "检索先修规则与课程关系", "tools": ["search_knowledge"]},
            {"actor": "Auditor", "action": "校验结论与课程库一致", "tools": []},
        ]
    if intent == "conflict_check":
        return [
            {"actor": "Planner", "action": "识别为时间冲突检测", "tools": []},
            {"actor": "ToolRunner", "action": "检测课程时间重叠", "tools": ["check_timetable_conflict"]},
            {"actor": "Retriever", "action": "检索冲突与容量规则", "tools": ["search_knowledge"]},
        ]
    if intent == "plan_build":
        return [
            {"actor": "Planner", "action": "识别为学期修读方案生成", "tools": []},
            {"actor": "ToolRunner", "action": "读取画像与选课偏好", "tools": ["get_student_profile"]},
            {"actor": "ToolRunner", "action": "在约束下生成方案", "tools": ["build_study_plan"]},
            {"actor": "ToolRunner", "action": "对方案课程做冲突复核", "tools": ["check_timetable_conflict"]},
            {"actor": "Retriever", "action": "检索选课与学分上限规定", "tools": ["search_knowledge"]},
            {"actor": "Auditor", "action": "校验方案学分、冲突与先修", "tools": []},
        ]
    if intent == "graduation_check":
        return [
            {"actor": "Planner", "action": "识别为毕业资格审核", "tools": []},
            {"actor": "ToolRunner", "action": "读取学生画像", "tools": ["get_student_profile"]},
            {"actor": "ToolRunner", "action": "五项条件逐项判定", "tools": ["check_graduation_eligibility"]},
            {"actor": "ToolRunner", "action": "核算模块学分缺口", "tools": ["calc_credit_progress"]},
            {"actor": "Retriever", "action": "检索毕业审核要点", "tools": ["search_knowledge"]},
            {"actor": "Auditor", "action": "校验结论与学分数据一致", "tools": []},
        ]
    if intent == "risk_warn":
        return [
            {"actor": "Planner", "action": "识别为学业预警评估", "tools": []},
            {"actor": "ToolRunner", "action": "读取学生画像", "tools": ["get_student_profile"]},
            {"actor": "ToolRunner", "action": "计算预警等级", "tools": ["get_risk_warning"]},
            {"actor": "ToolRunner", "action": "核算学分缺口", "tools": ["calc_credit_progress"]},
            {"actor": "Retriever", "action": "检索预警与帮扶办法", "tools": ["search_knowledge"]},
        ]
    if intent == "course_query":
        return [
            {"actor": "Planner", "action": "识别为课程查询", "tools": []},
            {"actor": "ToolRunner", "action": "按条件检索课程库", "tools": ["query_courses"]},
            {"actor": "Retriever", "action": "检索课程说明", "tools": ["search_knowledge"]},
        ]
    if intent == "profile_query":
        return [
            {"actor": "Planner", "action": "识别为画像查询", "tools": []},
            {"actor": "ToolRunner", "action": "读取学生画像", "tools": ["get_student_profile"]},
        ]
    if intent == "greeting":
        return [{"actor": "Composer", "action": "返回能力介绍", "tools": []}]
    if intent == "out_of_scope":
        return [{"actor": "SecurityGuard", "action": "命中边界规则，拒答", "tools": []}]
    return [
        {"actor": "Planner", "action": "识别为制度问答", "tools": []},
        {"actor": "Retriever", "action": "检索知识库原文", "tools": ["search_knowledge"]},
        {"actor": "Auditor", "action": "校验引用可溯源", "tools": []},
    ]


def make_plan(text: str, memory: Memory) -> Plan:
    intent, conf = classify(text, memory)

    student_id = detect_student(text, memory.slots.get("student_id"))
    if student_id is None and intent not in ("greeting", "policy_qa", "out_of_scope", "course_query"):
        student_id = "S001"          # 演示默认样本，真实部署由登录态注入
        conf = max(0.4, conf - 0.1)

    courses = detect_courses(text)
    current_term = None
    if student_id:
        try:
            current_term = int(ds.student(student_id)["current_term"])
        except Exception:
            current_term = None
    term = memory.term_from_text(text, current_term)
    if intent == "plan_build" and term is None:
        term = current_term

    plan = Plan(
        intent=intent,
        student_id=student_id,
        course_ids=courses,
        term=term,
        module=detect_module(text) if intent == "course_query" else None,
        need_retrieval=intent not in ("greeting", "out_of_scope", "profile_query"),
        retrieval_query=text,
        confidence=conf,
    )
    plan.subtasks = build_subtasks(intent, plan)
    return plan

# -*- coding: utf-8 -*-
"""内容安全与合规护栏：输入拦截 + 输出审查 + 生成内容标识。

对应规程"禁止行为"与《生成式人工智能服务管理暂行办法》要求：
不做成绩预测、不代写作弊、不接触真实个人信息、不承诺结果；
输出中若出现知识库/课程库之外的编造实体，必须被检出并降级。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from src.tools import data_store as ds

INPUT_RULES: List[Dict[str, Any]] = [
    {
        "category": "篡改与越权",
        "patterns": [r"改(一下)?(成绩|分数)", r"篡改", r"黑(进|掉)", r"入侵", r"绕过(系统|教务)",
                     r"帮我(删|改)(除)?(记录|成绩)"],
        "reply": "我不能修改或绕过教务系统的成绩与选课记录。成绩更正需要通过教务处正式流程办理："
                 "先向任课教师提出复核申请，由开课学院组织查卷，结论由教务处录入。"
                 "如果你怀疑成绩录入有误，可以让我帮你整理需要提交的复核材料清单。",
    },
    {
        "category": "成绩预测与结果承诺",
        "patterns": [r"预测.{0,6}(成绩|分数|过不过)", r"猜.{0,6}(分数|成绩)", r"保证(我)?(及格|通过|过)",
                     r"一定(能)?(过|及格|通过)", r"包过"],
        "reply": "我不能预测成绩，也不能对是否及格作任何承诺。课程是否通过取决于过程考核与期末考核的实际得分。"
                 "我能做的是：按培养方案核算你的学分进度、指出先修与冲突风险、给出有依据的修读方案。",
    },
    {
        "category": "学术不端",
        "patterns": [r"代写", r"替我(把)?.{0,8}(写|做)", r"帮我(把)?.{0,8}(写|做)(作业|论文|报告|毕业设计|毕设)",
                     r"帮我写(作业|论文|毕业设计)", r"考试答案", r"帮我(作弊|传答案)"],
        "reply": "代写作业、论文与提供考试答案是学术不端行为，我不能参与。"
                 "我可以帮你做的是：讲解课程知识点、审查你自己的代码逻辑、整理复习提纲。",
    },
    {
        "category": "个人信息与隐私",
        "patterns": [r"查(一下)?(同学|别人|室友|某个人)的", r"身份证", r"(手机|电话)号(码)?是多少",
                     r"真实姓名", r"拿到.{0,4}名单"],
        "reply": "本项目只使用脱敏后的样例画像（学生代号 S001—S003），不处理真实姓名、学号、联系方式"
                 "等个人信息，也无法查询他人数据。",
    },
    {
        "category": "违法违规内容",
        "patterns": [r"歧视", r"仇恨", r"违法(内容|信息)", r"骗(人|钱)", r"伪造(证明|证书)"],
        "reply": "这类内容我不能生成。若你有真实的学业困难，我可以帮你梳理补修路径与帮扶申请渠道。",
    },
]

OUTPUT_FORBIDDEN = ["保证", "绝对能", "一定能通过", "包过", "效果显著", "大幅提升", "毫无疑问"]
AI_DISCLOSURE = "本回答由 AI 智能体生成，结论仅基于本项目脱敏样例数据与公开制度文档，不替代教务处正式审核。"


def check_input(text: str) -> Dict[str, Any]:
    for rule in INPUT_RULES:
        for pat in rule["patterns"]:
            if re.search(pat, text):
                return {"blocked": True, "category": rule["category"],
                        "reason": f"命中规则：{rule['category']}", "reply": rule["reply"]}
    return {"blocked": False, "category": None, "reason": "", "reply": ""}


def check_output(text: str) -> Dict[str, Any]:
    """审查输出：虚构课程代码、承诺性表述、无依据量化。"""
    issues: List[Dict[str, str]] = []

    for cid in set(re.findall(r"\b[CE]\d{4}\b", text)):
        if cid not in ds.courses():
            issues.append({"type": "hallucinated_course", "value": cid,
                           "detail": f"课程代码 {cid} 不在课程库中"})

    for word in OUTPUT_FORBIDDEN:
        if word in text:
            issues.append({"type": "unsupported_claim", "value": word,
                           "detail": f"出现无依据的承诺或量化表述：{word}"})

    return {"flagged": len(issues) > 0, "issues": issues}


def refusal_result(guard: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "answer": guard["reply"] + "\n\n> " + AI_DISCLOSURE,
        "refused": True,
        "refusal_category": guard["category"],
        "citations": [],
        "tool_calls": [],
        "facts": {},
        "warnings": [guard["reason"]],
        "ai_disclosure": AI_DISCLOSURE,
    }

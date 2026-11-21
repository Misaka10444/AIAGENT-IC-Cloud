# -*- coding: utf-8 -*-
"""生成《项目设计与开发方案》docx。

排版严格按附件2要求：A4 纵向、页边距 2.54cm、正文宋体小四、1.5 倍行距。
目录为 Word 域，配合 tools/export_pdf.ps1 由 Word 更新页码后导出 PDF。
运行：python tools/build_plan_doc.py
"""
from __future__ import annotations

import os
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = str(Path(__file__).resolve().parent.parent)
FIG = os.path.join(ROOT, "docs", "figures")
OUT_DOCX = os.path.join(ROOT, "dist", "集成电路学院-Cloud-云梯学业规划与选课顾问Agent-方案.docx")

SONG, HEI, TNR = "宋体", "黑体", "Times New Roman"
BODY_PT = 12          # 小四
CAP_PT = 10.5         # 五号
TBL_PT = 9.5


# ------------------------------------------------------------------ 基础工具
def set_font(run, cn=SONG, en=TNR, size=BODY_PT, bold=False, color=None):
    run.font.name = en
    run.font.size = Pt(size)
    run.font.bold = bold
    if color:
        run.font.color.rgb = color
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), cn)
    rfonts.set(qn("w:ascii"), en)
    rfonts.set(qn("w:hAnsi"), en)


def style_font(style, cn=SONG, en=TNR, size=BODY_PT, bold=False):
    style.font.name = en
    style.font.size = Pt(size)
    style.font.bold = bold
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), cn)
    rfonts.set(qn("w:ascii"), en)
    rfonts.set(qn("w:hAnsi"), en)


def body(doc, text, indent=True, space_after=0, align=WD_ALIGN_PARAGRAPH.JUSTIFY):
    p = doc.add_paragraph()
    p.style = doc.styles["Normal"]
    pf = p.paragraph_format
    pf.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    pf.space_before = Pt(0)
    pf.space_after = Pt(space_after)
    pf.first_line_indent = Pt(BODY_PT * 2) if indent else Pt(0)
    p.alignment = align
    for seg in text.split("**"):
        pass
    # 支持 **加粗** 片段
    parts = text.split("**")
    for i, seg in enumerate(parts):
        if not seg:
            continue
        r = p.add_run(seg)
        set_font(r, SONG, TNR, BODY_PT, bold=(i % 2 == 1))
    return p


def bullet(doc, text, level=0):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    pf.left_indent = Pt(BODY_PT * (2 + 2 * level))
    pf.first_line_indent = Pt(-BODY_PT)
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    parts = text.split("**")
    for i, seg in enumerate(parts):
        if not seg:
            continue
        r = p.add_run(seg)
        set_font(r, SONG, TNR, BODY_PT, bold=(i % 2 == 1))
    return p


def h1(doc, text, page_break=True):
    p = doc.add_paragraph(style="Heading 1")
    pf = p.paragraph_format
    pf.page_break_before = page_break
    pf.space_before = Pt(0)
    pf.space_after = Pt(10)
    pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
    r = p.add_run(text)
    set_font(r, HEI, TNR, 16, bold=True)
    return p


def h2(doc, text):
    p = doc.add_paragraph(style="Heading 2")
    pf = p.paragraph_format
    pf.space_before = Pt(10)
    pf.space_after = Pt(4)
    pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
    r = p.add_run(text)
    set_font(r, HEI, TNR, 14, bold=True)
    return p


def h3(doc, text):
    p = doc.add_paragraph(style="Heading 3")
    pf = p.paragraph_format
    pf.space_before = Pt(8)
    pf.space_after = Pt(3)
    pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
    r = p.add_run(text)
    set_font(r, HEI, TNR, 12, bold=True)
    return p


def caption(doc, text, before=3, after=6, keep_next=True):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
    pf.keep_with_next = keep_next
    r = p.add_run(text)
    set_font(r, SONG, TNR, CAP_PT, bold=True)
    return p


def figure(doc, filename, cap, width_cm=15.9):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pf.space_before = Pt(6)
    pf.space_after = Pt(2)
    pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
    p.add_run().add_picture(os.path.join(FIG, filename), width=Cm(width_cm))
    caption(doc, cap, before=2, after=8)


def shade(cell, hex_color):
    tcpr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tcpr.append(shd)


def table_cell(cell, text, bold=False, size=TBL_PT, align=WD_ALIGN_PARAGRAPH.LEFT):
    cell.text = ""
    p = cell.paragraphs[0]
    p.alignment = align
    pf = p.paragraph_format
    pf.space_before = Pt(1.5)
    pf.space_after = Pt(1.5)
    pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
    for i, seg in enumerate(text.split("**")):
        if not seg:
            continue
        r = p.add_run(seg)
        set_font(r, SONG, TNR, size, bold=(bold or i % 2 == 1))


def table(doc, cap, headers, rows, widths, size=TBL_PT):
    caption(doc, cap, before=8, after=3, keep_next=True)
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    for i, h in enumerate(headers):
        c = t.rows[0].cells[i]
        table_cell(c, h, bold=True, size=size, align=WD_ALIGN_PARAGRAPH.CENTER)
        shade(c, "EEF2F8")
    hdr = t.rows[0]._tr.get_or_add_trPr()
    tblHeader = OxmlElement("w:tblHeader")
    tblHeader.set(qn("w:val"), "true")
    hdr.append(tblHeader)
    for k, row in enumerate(rows):
        cells = t.add_row().cells
        for i, v in enumerate(row):
            table_cell(cells[i], v, size=size,
                       align=WD_ALIGN_PARAGRAPH.CENTER if i == 0 or len(str(v)) <= 8
                       else WD_ALIGN_PARAGRAPH.LEFT)
    # 整表不跨页：除最后一行外，各行与下一行"保持同页"
    n = len(t.rows)
    for idx, r in enumerate(t.rows):
        trpr = r._tr.get_or_add_trPr()
        cant = OxmlElement("w:cantSplit")
        trpr.append(cant)
        if idx < n - 1:
            for c in r.cells:
                for p in c.paragraphs:
                    p.paragraph_format.keep_with_next = True
    for r in t.rows:
        for i, w in enumerate(widths):
            r.cells[i].width = Cm(w)
    # 表后留白
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
    for r in p.runs:
        set_font(r, SONG, TNR, 6)
    return t


def add_toc(doc):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(6)
    run = p.add_run()
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = 'TOC \\o "1-2" \\h \\z \\u'
    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(qn("w:fldCharType"), "separate")
    holder = OxmlElement("w:t")
    holder.text = "目录将在导出时自动更新页码"
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    run._r.append(fld_begin)
    run._r.append(instr)
    run._r.append(fld_sep)
    run._r.append(holder)
    run._r.append(fld_end)


def add_page_number_footer(section):
    footer = section.footer
    p = footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r1 = p.add_run("— ")
    set_font(r1, SONG, TNR, 9)
    run = p.add_run()
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    run._r.append(fld_begin)
    run._r.append(instr)
    run._r.append(fld_end)
    set_font(run, SONG, TNR, 9)
    r2 = p.add_run(" —")
    set_font(r2, SONG, TNR, 9)


# ------------------------------------------------------------------ 文档构建
def build():
    doc = Document()

    # 页面设置
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    sec.top_margin = sec.bottom_margin = Cm(2.54)
    sec.left_margin = sec.right_margin = Cm(2.54)
    sec.header_distance = Cm(1.5)
    sec.footer_distance = Cm(1.5)

    normal = doc.styles["Normal"]
    style_font(normal, SONG, TNR, BODY_PT)
    normal.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(0)

    for name in ("Heading 1", "Heading 2", "Heading 3"):
        st = doc.styles[name]
        style_font(st, HEI, TNR, 16 if name == "Heading 1" else 14, bold=True)
        st.font.color.rgb = RGBColor(0, 0, 0)

    add_page_number_footer(sec)

    # ---------------- 封面 ----------------
    for _ in range(2):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("北京科技职业大学 2026 年校级技能竞赛")
    set_font(r, HEI, TNR, 15, bold=True)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(28)
    r = p.add_run("“人工智能创新应用”赛项")
    set_font(r, HEI, TNR, 15, bold=True)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("项目设计与开发方案")
    set_font(r, HEI, TNR, 26, bold=True)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(6)
    r = p.add_run("云梯 · 学业规划与选课顾问 Agent")
    set_font(r, HEI, TNR, 18, bold=True)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(40)
    r = p.add_run("Yunti: An Academic Planning and Course-Selection Advisor Agent")
    set_font(r, SONG, TNR, 11)

    info = [("参赛队名称", "Cloud"),
            ("选题类别", "场景库选题（智慧校园 · 学业规划与选课）"),
            ("所属学院", "集成电路学院（人工智能学院）"),
            ("指导教师", "张维婷"),
            # 学号属于个人信息，不写入仓库；导出正式方案时用环境变量注入
            ("队长", f"黎家维　{os.environ.get('YUNTI_LEADER_ID', '（学号见报名表）')}"),
            ("队员", f"郑笑含　{os.environ.get('YUNTI_MEMBER_ID', '（学号见报名表）')}"),
            ("提交日期", "2026 年 11 月 21 日")]
    t = doc.add_table(rows=0, cols=2)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for k, v in info:
        cells = t.add_row().cells
        table_cell(cells[0], k, bold=True, size=12, align=WD_ALIGN_PARAGRAPH.RIGHT)
        table_cell(cells[1], v, size=12)
        cells[0].width = Cm(4.2)
        cells[1].width = Cm(9.0)

    # ---------------- 目录 ----------------
    p = doc.add_paragraph()
    p.paragraph_format.page_break_before = True
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(12)
    r = p.add_run("目　　录")
    set_font(r, HEI, TNR, 18, bold=True)
    add_toc(doc)

    # ================================================================ 正文
    h1(doc, "1　项目概述", page_break=True)

    h2(doc, "1.1　项目名称与一句话价值主张")
    body(doc, "项目名称：云梯 · 学业规划与选课顾问 Agent（以下简称“云梯”），提交仓库命名为 "
              "AIAGENT-集成电路-Cloud。")
    body(doc, "一句话价值主张：把培养方案里分散在六份制度文档、数十条规则中的选课约束，收敛成一次对话，"
              "并且每个结论都能点回到原文的哪一行。")
    body(doc, "这句话里的两个动词对应本项目的两个设计重心：“收敛”是能力，要求系统同时处理先修、"
              "时间冲突、学分上限、容量与偏好五类约束；“点回原文”是可信度，要求每个数字背后都有工具"
              "或原文片段作为依据。")

    h2(doc, "1.2　应用场景")
    body(doc, "选题类别为场景库选题，落在“智慧校园——学业规划与选课”。选择该场景基于四点判断：")
    bullet(doc, "**高频且周期性强**：每名学生每学期至少经历一次选课，需求随学期周期性出现，不是一次性功能。")
    bullet(doc, "**规则密集但可判定**：学分结构、先修关系、时间冲突、容量是否满足，都是确定性的布尔判断，"
                "适合交给工具而不是交给语言模型自由发挥。")
    bullet(doc, "**错误代价可控**：系统不涉及人身安全与资金交易，最坏结果是“建议了一门不合适的课”，"
                "可由教务流程纠正，属于可以上线试错的场景。")
    bullet(doc, "**数据可彻底脱敏**：学生画像用 S001—S003 代号即可承载全部推理逻辑，"
                "系统内不存在姓名、学号、联系方式字段，天然满足《原创性与数据合规承诺书》的要求。")

    h2(doc, "1.3　目标用户")
    body(doc, "主要用户：人工智能工程技术专业（职业本科）一至三年级在校生。他们的典型状态是——知道"
              "“要修满 144 学分”，但说不清六个模块各自的门槛；能看懂课表，但算不清某门课的学分究竟"
              "计入专业核心还是专业选修。")
    body(doc, "次要用户：辅导员与班主任。他们需要在学期初快速识别学分进度明显落后的学生用于学业预警初筛，"
              "而不是逐个翻阅成绩单。")
    body(doc, "边缘用户：学院教学秘书。重复回答“通识选修能不能用专业选修抵”“补考最高多少分”这类"
              "制度性问题，占用了本应处理个案的时间。")

    h2(doc, "1.4　与教务系统的定位关系")
    body(doc, "云梯不是教务系统的替代品，而是它前面的一层“解释器”。教务系统回答“你能选什么”，"
              "云梯回答“你该选什么、为什么、依据在哪”。所有正式结论——学分认定、毕业审核——仍以"
              "教务处与学院出具的结果为准，这一点在每次回答末尾都以固定声明标注，不做弱化。")

    h2(doc, "1.5　文档结构与评分项的对应关系")
    body(doc, "本方案按附件 2 要求的五章结构组织，章节与赛项评分项的对应关系如下，"
              "便于评审按项定位、按项对照。")
    bullet(doc, "**第 1—2 章对应“需求与场景”（8 分）**：业务痛点、目标用户画像与典型任务、"
                "现有方案比较、能力边界与非目标，其中非目标以代码护栏强制实现。")
    bullet(doc, "**第 3 章对应“架构与技术选型”（10 分）**：四层总体架构、单体与多智能体的范式选型依据、"
                "技术栈与模型选型理由、端到端数据流与调用链路。")
    bullet(doc, "**第 4 章对应“工具与知识库设计”（6 分）**：10 个工具的输入输出与异常定义、"
                "知识库来源与按章节切分策略、检索与重排方案、引用溯源与三道幻觉控制闸。")
    bullet(doc, "**第 5 章对应“评测与合规”（6 分）**：50 条功能用例与 25 条检索用例的量化结果、"
                "消融对比、隐私与内容标识等合规措施、风险预案。")

    # ---------------------------------------------------------------- 第2章
    h1(doc, "2　需求分析")

    h2(doc, "2.1　业务痛点")
    body(doc, "**痛点一：学分结构的隐性化。** 培养方案要求 144 学分，但它由六个模块分别约束：通识必修 29、"
              "通识选修 8、专业基础 25、专业核心 41、专业选修 15、集中实践 26，模块之间不可互替。"
              "学生的注意力通常集中在“总学分”这一个数字上，于是出现“总学分够了却毕不了业”的典型误判——"
              "按培养方案说明，总学分达到 144 但模块结构不达标，仍不能通过毕业审核。")
    body(doc, "**痛点二：五类约束耦合，人工排查易漏。** 一次选课同时受五类约束限制：先修关系（大模型应用"
              "开发要求先修深度学习与 Python 数据分析）、上课时间冲突、每学期 26 学分上限、教学班容量、"
              "集中实践的周次安排。在 6—8 门课的组合上逐条核对，漏掉任何一条都会导致选课当场失败或事后返工。")
    body(doc, "**痛点三：咨询产能与需求不匹配。** 一名辅导员面向数十名学生，教学秘书面向全年级。"
              "制度性提问高度重复，且答案几乎固定，属于“应该被自动化”的部分。")
    body(doc, "**痛点四：通用大模型的回答不可验证。** 把同样的问题抛给通用对话模型，它往往能给出"
              "“看起来对”的答案，却无法指出依据来自哪份文件的哪一条，也无法在数据变化后保持结论一致。"
              "在教务场景里，“听起来对”和“确实对”之间差着一个处分的距离。")

    h2(doc, "2.2　用户画像与典型任务")
    body(doc, "系统内置三个脱敏画像作为演示与评测样本，覆盖“有挂科”“成绩优秀”“临近毕业”三类典型状态。")
    table(doc, "表 1　用户画像与典型任务",
          ["画像", "学业状态", "目标", "典型任务"],
          [["学生A（S001）",
            "2025 级第 3 学期，已修 13 门，其中《面向对象程序设计》52 分未通过，另有 6 门第 3 学期课程在修",
            "就业，集成电路测试方向",
            "算清学分进度；规划第 4 学期课表；确认某门课的选课资格"],
           ["学生B（S002）",
            "2024 级第 5 学期，已修 25 门，成绩均在 80 分以上，6 门第 5 学期课程在修",
            "升学，人工智能方向",
            "核对专业选修结构；在不超学分上限的前提下安排后续学期"],
           ["学生C（S003）",
            "2023 级第 7 学期，已修 33 门，《概率论与数理统计》59 分未通过且未重修，缺《嵌入式系统》",
            "就业，智能硬件方向",
            "毕业资格逐项自查；识别最紧迫的补修项"]],
          widths=[2.6, 6.4, 2.6, 4.4])

    h2(doc, "2.3　现有方案比较")
    body(doc, "把学生真实的咨询路径拆成四条，逐条比较能力边界，可以看清本项目的差异化位置。")
    table(doc, "表 2　现有方案能力比较",
          ["对比维度", "教务系统", "通用大模型", "公众号与答疑群", "云梯"],
          [["学分结构解释", "展示已修学分，不解释模块约束", "能讲通用概念，不知道本校规则", "依赖人工回复", "按六模块逐项核算并给出缺口"],
           ["五类约束联合校验", "仅校验时间冲突与容量", "无数据，无法校验", "不校验", "工具内联合校验并给出取舍理由"],
           ["结论可溯源", "有数据无解释", "无来源，无法验证", "口头答复，无留痕", "每条结论带文档号、章节与原文行号"],
           ["多轮追问", "不支持自然语言", "支持，但会遗忘上下文实体", "支持，但成本高", "实体槽位记忆，支持指代消解"],
           ["离线可复现", "依赖校内网", "依赖外部服务与密钥", "依赖人工", "零第三方依赖，断网可运行"]],
          widths=[3.0, 3.4, 3.4, 3.0, 4.2])

    h2(doc, "2.4　能力边界与非目标")
    body(doc, "方案不得以设想替代设计，因此必须明确“不做什么”。以下五条是本项目的硬边界，"
              "其中前两条在系统内以代码规则强制实现，而不是靠提示词约束。")
    bullet(doc, "**不做成绩预测与及格承诺。** 预测需要历史成绩分布与考核难度数据，本项目不掌握，也不应给出。"
                "输入护栏中的规则会直接拦截“预测我能不能过”这类提问。")
    bullet(doc, "**不替代正式选课与学分认定。** 系统只产出建议方案，落地仍需在教务系统内操作；"
                "涉及学分认定的最终结论以学院审核为准。")
    bullet(doc, "**不评价教师。** 课程难度只引用公开的培养方案描述与课程简介，不做教师层面的横向比较。")
    bullet(doc, "**不处理真实个人信息。** 全部画像以代号承载，系统中不存在姓名、学号、联系方式字段。")
    bullet(doc, "**不宣称覆盖全校专业。** 当前知识库只覆盖人工智能工程技术专业 2025 版培养方案，"
                "超出范围的提问会明确弃答而不是套用其他专业的规则。")

    # ---------------------------------------------------------------- 第3章
    h1(doc, "3　系统架构")

    h2(doc, "3.1　总体架构")
    body(doc, "系统分为接入层、编排层、能力层与数据层四层，右侧是贯穿全程的可观测性通道。"
              "分层的目的不是好看，而是让“换掉其中一层”成为可能：换接入方式不影响编排，换检索算法不影响工具，"
              "换数据源不影响智能体逻辑。")
    figure(doc, "fig1_architecture.png", "图 1　系统总体架构")
    body(doc, "按规程要求的“感知—规划—记忆—工具—执行”五要素对应如下：**感知**由输入护栏与会话指代消解"
              "共同承担；**规划**由 Planner 完成意图识别与子任务分解；**记忆**由 Memory 维护实体槽位与轮次历史；"
              "**工具**是 10 个注册工具，统一以 {ok, data} 或 {ok:false, error} 信封返回；"
              "**执行**由 ToolRunner 调用、Auditor 校验、Composer 生成三段构成。")

    h2(doc, "3.2　智能体范式选型：单体还是多智能体")
    body(doc, "这是本方案的核心取舍，值得展开说明。常见做法是把“规划—检索—校验—生成”拆成四个各自持有"
              "独立对话上下文的 LLM 智能体，用消息传递协作。我们评估后没有采用这种方式，理由如下表。")
    table(doc, "表 3　单体智能体与多智能体方案比较",
          ["评估维度", "单体智能体", "多 LLM 智能体（各自独立上下文）", "本方案：轻量多智能体（同进程五角色）"],
          [["可解释性", "单次调用，过程不可见", "过程可见但每次调用引入随机性", "五个角色各自写入 trace 事件，可逐段回放"],
           ["失败定位成本", "只能整体重跑", "需要跨会话追踪", "工具错、检索空、校验失败分属不同角色，定位一次到位"],
           ["响应延迟", "较低", "串行多次模型调用，秒级", "单进程毫秒级（实测 P50 约 3 毫秒）"],
           ["结论稳定性", "受采样影响", "多级放大，稳定性最差", "确定性引擎，同一输入恒定输出"]],
          widths=[2.8, 3.6, 4.6, 6.0])
    body(doc, "我们的结论是：**角色要拆，模型调用不拆。** 五个角色（Planner、Retriever、ToolRunner、Auditor、"
              "Composer）在同一进程内以显式数据结构传递结果，既获得“分角色可观测”的好处，又不承担"
              "“多级模型协作”的不确定性代价。对于选课这类判定性任务，用第二个模型去校验第一个模型的输出，"
              "只会引入新的不确定性，工程上不划算。")

    h2(doc, "3.3　技术栈与模型选型理由")
    table(doc, "表 4　技术栈与选型理由",
          ["层次", "选型", "选型理由"],
          [["运行时", "Python 3.11 标准库", "零第三方运行时依赖：赛场断网、无 pip 环境也能直接运行"],
           ["检索", "自实现 BM25（中文字二元组）", "知识库仅 34 个片段，向量检索的边际收益不抵模型与依赖成本"],
           ["生成", "本地确定性引擎（默认）／OpenAI 兼容网关（可选）", "合规与可复现优先；网关不可用自动降级，不中断对话"],
           ["前端", "原生 HTML/CSS/JavaScript 单页", "无构建步骤，双击即用，演示环节没有工具链风险"],
           ["可观测", "JSONL 追加写（logs/trace.jsonl）", "结构化、可 grep，评测脚本可直接读取统计，无需额外组件"],
           ["文档与配图", "python-docx + Pillow", "方案正文与三张插图均可由脚本重新生成，改版成本低"]],
          widths=[2.4, 5.4, 8.2])
    body(doc, "模型选型上，本项目把“模型”定位为可替换的一层，而不是系统的前提。默认引擎用规则、词典与 BM25 "
              "完成意图识别、检索与生成，它带来两个直接好处：其一，同样的输入永远得到同样的输出，"
              "评测数字具备可复现性；其二，不向任何未报备的第三方服务发送数据，合规风险最低。"
              "配置模型网关后，意图分类可切换为语义解析，此时系统仍保留本地规则作为兜底，"
              "并且**工具选路与参数构造不交给模型**——这一层是刻意保留的人工控制点。")

    h2(doc, "3.4　数据流与调用链路")
    body(doc, "一次完整的问答经过七次显式交互，如下图所示。图中的编号与后端 trace 中的事件一一对应，"
              "答辩现场可以按编号回放。")
    figure(doc, "fig2_sequence.png", "图 2　端到端调用链路与多智能体协作时序")
    body(doc, "七个环节中，③④⑤ 是检索增强的关键段：检索式经意图改写后召回，经阈值与重排后得到 Top-5 片段，"
              "再与工具产出的结构化数据一起交给 Auditor 交叉校验。⑥⑦ 两段是可信度保障：校验结论以"
              "“通过／注意／失败”三级回传，失败时 Composer 不会照常输出，而是在回答中标注校验未通过的具体原因。")

    h2(doc, "3.5　会话记忆与指代消解")
    body(doc, "记忆不保存整段历史文本，而是维护四个实体槽位：student_id、course_id、term 与 last_intent。"
              "指代消解发生在规划之前，规则命中后退化为显式实体替换，替换过程写入 trace 的 resolve_references "
              "事件。")
    body(doc, "举例：第一轮提问“S001 下学期怎么选课”，方案首门课程为数据库原理与应用，槽位 course_id 记为 "
              "C4001；第二轮提问“那门课的先修够吗”，系统把“那门课”替换为《数据库原理与应用》后再进入先修校验，"
              "trace 中记录“pronoun=那门课, resolved_to=数据库原理与应用, evidence=上一轮提到课程 C4001”。")
    body(doc, "边界同样重要：槽位只在同一会话内有效，跨会话不继承。这条限制是为了避免“把上一个学生的画像"
              "带到下一个学生”的串号风险——在教育场景里，串号比遗忘严重得多。")

    # ---------------------------------------------------------------- 第4章
    h1(doc, "4　工具与知识库")

    h2(doc, "4.1　工具清单与接口定义")
    body(doc, "系统共注册 10 个工具，全部以装饰器声明参数规格，调用前强制校验。下表列出输入、输出要点"
              "与主要异常，完整签名可通过 python -m src.cli --tools 导出。")
    table(doc, "表 5　工具清单与接口定义",
          ["工具", "输入", "输出要点", "主要异常"],
          [["get_student_profile", "student_id", "年级、专业、目标、偏好、已修与未通过课程", "STUDENT_NOT_FOUND"],
           ["calc_credit_progress", "student_id", "六模块要求/已通过/缺口、总分缺口、未通过清单、未修核心课", "STUDENT_NOT_FOUND"],
           ["query_courses", "term、module、keyword、only_with_capacity", "课程清单、学分、先修、时隙、余量", "ENUM_MISMATCH"],
           ["check_prerequisites", "course_id、student_id", "是否满足、缺失先修、在修待确认", "COURSE_NOT_FOUND"],
           ["check_timetable_conflict", "course_ids[]", "冲突课程对、重叠节次、非排课时段", "COURSE_NOT_FOUND"],
           ["check_graduation_eligibility", "student_id", "五项条件逐项结论与说明", "STUDENT_NOT_FOUND"],
           ["get_risk_warning", "student_id", "预警等级、触发原因、帮扶建议", "STUDENT_NOT_FOUND"],
           ["build_study_plan", "student_id、target_term、elective_ids", "选课方案、总学分、排除原因、风险提示", "INVALID_TERM"],
           ["search_knowledge", "query、top_k", "带文档号/章节/行号的片段与得分", "EMPTY_QUERY"],
           ["get_kb_stats", "—", "文档数、片段数、平均片段长度、词表规模", "—"]],
          widths=[4.4, 4.2, 5.4, 2.6])

    h2(doc, "4.2　工具调用的可靠性设计")
    body(doc, "**参数校验三关。** 必填、类型、枚举依次校验。对常见类型漂移（“2”传给整数参数）做容忍转换，"
              "其余一律拒绝并返回 TYPE_MISMATCH，不做猜测性修补。")
    body(doc, "**错误分级与重试策略。** 工具错误分为可重试（IO 错误、超时）与不可重试（课程不存在、"
              "参数缺失）两类。只有可重试错误才做退避重试，最多 2 次。重试一个不存在的课程不是健壮，"
              "是浪费——这条判断写进了代码而不是文档。")
    body(doc, "**局部失败不阻断。** 某次工具调用失败时，整轮对话继续，但回答中会列出失败工具与错误码，"
              "并且当所有数据类工具都失败时，Composer 不再生成推测性内容，而是直接回填错误明细。")
    body(doc, "**结果回填可核对。** 每个工具的输出写入 trace 的 data_keys 字段，评测与答辩时可核对"
              "“模型到底看到了什么”，避免用最终回答反推中间过程。")

    h2(doc, "4.3　知识库来源与切分策略")
    body(doc, "知识库由 7 篇 Markdown 文档构成，每篇带文档号、来源、版本、更新日期、适用范围五项元数据，"
              "对应学生最常问的七类制度问题：培养方案说明（KB-01）、选课管理办法（KB-02）、重修与学分认定"
              "（KB-03）、毕业资格审核要点（KB-04）、学业预警与帮扶（KB-05）、课程简介汇编（KB-06）、"
              "生成式人工智能使用规范（KB-07）。")
    body(doc, "切分策略：**先按二级标题分节，再在节内按 400 字窗口切分，窗口间保留 80 字重叠**，"
              "最终得到 34 个片段，每个片段保留其在原文中的起始行号。")
    body(doc, "为什么按章节而不是固定长度切分：制度条款的语义边界就是章节边界。把“条件”和“例外”切到"
              "两个片段里，检索到的答案会自相矛盾；而按章节切分后，一个片段通常就是一条完整规则，"
              "引用时也更容易定位到“某章某节”。80 字重叠是为了避免条款在窗口边界处被截断后失去主语。")

    h2(doc, "4.4　检索与重排方案")
    figure(doc, "fig3_rag_pipeline.png", "图 3　知识库构建与检索重排流程")
    body(doc, "**召回。** BM25，参数 k1=1.5、b=0.75；中文以字二元组为词元，并用 20 余个高频疑问词"
              "（请问、如何、是否、多少等）作为停用词过滤。这一组合在本场景下的优势是无需分词词典，"
              "对“学分认定”“时间冲突”这类专业复合词的切分结果稳定。")
    body(doc, "**重排。** 在 BM25 得分基础上叠加两个可解释特征：标题命中率（查询词出现在章节名与文档名中的"
              "占比）与查询覆盖率（查询词出现在片段中的占比），权重分别为 0.8 与 0.5。重排不是黑盒模型，"
              "权重可以逐条解释，答辩时能说清“为什么这一条排在前面”。")
    body(doc, "**阈值。** 原始 BM25 得分低于 3.5 时判定为“知识库无依据”，不生成答案。该阈值来自实测标定："
              "无关提问（如“学校食堂几点开门”）的 Top-1 得分集中在 2.9—3.0，有效提问的 Top-1 得分在 5.4 以上，"
              "取 3.5 使两侧各留约 15% 余量。")
    body(doc, "**实测增益。** 在 25 条专用检索用例上，重排使 Top-1 文档命中率从 84.0% 提升到 88.0%，"
              "MRR@5 从 0.900 提升到 0.920，而章节命中率保持 96.0% 不变。后一个数字说明重排改善的是"
              "排序而非召回上限——剩余误差来自片段切分边界，这也是下一步优化的方向。")

    h2(doc, "4.5　引用溯源与幻觉控制")
    body(doc, "引用格式统一为 `KB-04 §1 五项必要条件 · 原文第 4 行`，回答正文与右侧引用面板都能回到原文片段。"
              "在此之上设三道闸：")
    bullet(doc, "**检索前——阈值闸。** 没有依据就不答。系统宁可回复“没有找到依据”，也不生成听起来合理的推测。")
    bullet(doc, "**生成后——审查闸。** 扫描回答中出现的课程代码，若不在课程库中即判定为虚构引用，"
                "整条回答被拦截并提示核对；同时拦截“保证通过”“包过”等承诺性表述。")
    bullet(doc, "**全程——交叉校验闸。** Auditor 对学分模块合计与总分是否自洽、方案内是否存在时间冲突、"
                "先修关系是否满足做独立重算，任一项不一致即标记校验失败，并在回答中披露。")
    body(doc, "三道闸的实测效果：50 条功能用例中，幻觉与越界表述命中 0 条；2 条“知识库确实不覆盖”的提问"
              "均被正确识别为弃答（弃答正确率 100%），没有出现编造。")

    # ---------------------------------------------------------------- 第5章
    h1(doc, "5　实施计划")

    h2(doc, "5.1　进度安排与里程碑")
    body(doc, "项目周期为竞赛规程发布至提交截止的 11 天，采用“先跑通最小闭环，再逐个加固”的推进方式，"
              "每个里程碑都有可运行的交付物，不留“最后一晚才集成”的风险。")
    table(doc, "表 6　进度安排与里程碑",
          ["时间", "里程碑", "交付物"],
          [["11.12—11.13", "需求调研与选题确认", "痛点清单、场景与用户画像定义"],
           ["11.14—11.15", "架构设计与数据构造", "四层架构图、62 门课程库、六模块学分结构"],
           ["11.16—11.17", "工具层实现", "10 个工具与注册中心，CLI 可跑通八类意图"],
           ["11.18—11.19", "智能体编排与知识库", "五角色编排、34 片段索引、引用溯源"],
           ["11.20", "评测与迭代", "50 条功能用例、25 条检索用例、评测报告与消融对比"],
           ["11.21", "方案撰写与演示录制", "本方案、演示视频脚本、Web 演示界面"],
           ["11.22", "提交", "仓库、方案 PDF、演示视频、报名表与承诺书"]],
          widths=[3.0, 4.6, 8.4])

    h2(doc, "5.2　团队分工")
    table(doc, "表 7　团队分工",
          ["成员", "角色", "承担工作"],
          [["黎家维", "队长／架构与智能体核心",
            "总体架构与范式选型、Planner 与 Composer 实现、工具注册中心、现场答辩主陈述"],
           ["郑笑含", "知识库与评测",
            "知识库文档整理与切分策略、BM25 与重排实现、评测集构建与指标分析、演示界面与视频录制"],
           ["张维婷", "指导教师", "场景可行性把关、制度条款准确性审核、答辩问题预演"]],
          widths=[2.6, 5.0, 8.4])

    h2(doc, "5.3　评测方案与结果")
    body(doc, "评测分两部分，口径与复现命令写进仓库，任何人可在本机重跑。第一部分是 50 条功能用例，"
              "覆盖制度问答、学分核算、先修校验、冲突检测、方案生成、毕业审核、学业预警、多轮指代、"
              "安全拒答与无依据弃答十类；第二部分是 25 条只测检索排序的用例，用于剥离工具与生成的干扰，"
              "单独衡量重排模块的增益。")
    body(doc, "在优化后配置下（重排与自检开启），50 条功能用例全部通过：任务成功率 100%，意图准确率 100%，"
              "工具调用准确率 100%，引用命中率 100%，引用 Top-1 命中率 90%，多轮指代正确率 100%，"
              "安全拒答率 100%，弃答正确率 100%，幻觉与越界表述 0 条。端到端延迟 P50 为 3 毫秒、"
              "P95 为 8 毫秒（本机实测，含规划、工具、检索、校验与生成全链路）。")
    body(doc, "需要说明的是，功能用例集在两种配置下均已满分，这本身说明该用例集的区分度不足——"
              "它更适合做回归而不是做优化效果的证据。因此我们把“优化有前后对比”的举证责任放到了检索子集上："
              "重排带来的 Top-1 命中率提升 4.0 个百分点、MRR 提升 0.020，是本方案中唯一可被单独归因的"
              "算法级改进。这一取舍写进评测报告，而不藏在附录里。")

    h2(doc, "5.4　合规与安全措施")
    body(doc, "合规不是文档里的承诺，而是四处在代码中强制执行的机制：")
    bullet(doc, "**数据合规。** 全部数据为脱敏构造样例，仓库内不存在真实姓名、学号、联系方式；"
                "data/SOURCES.md 逐文件说明来源与处理方式。")
    bullet(doc, "**内容标识。** 每条回答末尾固定追加“本回答由 AI 智能体生成”的显著标识，"
                "符合《人工智能生成合成内容标识办法》对生成内容标识的要求。")
    bullet(doc, "**内容安全。** 输入护栏拦截成绩预测、代写作弊、隐私查询、篡改成绩等五类越界请求；"
                "输出审查拦截虚构课程引用与承诺性表述。两类护栏的规则与拦截文案均在 src/agent/safety.py 中可查。")
    bullet(doc, "**密钥管理。** 仓库只提供 .env.example 占位说明，不含任何真实密钥；"
                "模型网关为可选项，未配置时系统以本地引擎运行，不对外发起任何网络请求。")

    h2(doc, "5.5　风险预案")
    table(doc, "表 8　风险预案",
          ["风险", "可能影响", "预案"],
          [["模型网关不可用或未报备", "无法演示模型侧能力", "默认使用本地确定性引擎，全链路不依赖网关；网关仅作为可替换增强层"],
           ["演示现场断网或环境异常", "现场演示无法进行", "系统零第三方运行时依赖，可完全离线运行；视频作为备份证据"],
           ["培养方案数据与真实条款有出入", "结论失真", "知识库元数据标注版本与适用范围，回答末尾固定声明以教务处结论为准"],
           ["评审追问制度细节", "答辩失分", "每条结论可追溯到文档号、章节与原文行号，现场可即时调取"],
           ["时间不足导致功能裁剪", "交付不完整", "按模块化优先级交付：先保工具+编排闭环，再补前端与文档，任何阶段都有可运行版本"]],
          widths=[4.2, 3.6, 8.2])

    # ---------------------------------------------------------------- 附录
    h1(doc, "附录")

    h2(doc, "附录 A　参考资料")
    body(doc, "［1］北京科技职业大学. 2026 年校级技能竞赛“人工智能创新应用”赛项竞赛规程［Z］. 2026-11-11.", indent=False)
    body(doc, "［2］北京科技职业大学. 《项目设计与开发方案》编写要求（附件 2）［Z］. 2026.", indent=False)
    body(doc, "［3］北京科技职业大学. 作品提交规范（附件 3）［Z］. 2026.", indent=False)
    body(doc, "［4］国家互联网信息办公室等. 生成式人工智能服务管理暂行办法［Z］. 2023-07-13.", indent=False)
    body(doc, "［5］国家互联网信息办公室等. 人工智能生成合成内容标识办法［Z］. 2025-03-14.", indent=False)
    body(doc, "［6］Robertson S, Zaragoza H. The Probabilistic Relevance Framework: BM25 and Beyond［J］. "
              "Foundations and Trends in Information Retrieval, 2009, 3(4): 333-389.", indent=False)

    h2(doc, "附录 B　开源组件及许可证清单")
    table(doc, "表 B-1　第三方组件使用情况",
          ["组件", "版本", "许可证", "使用范围"],
          [["Python", "3.11", "PSF License", "运行环境；本项目全部源码仅使用其标准库"],
           ["Pillow", "12.3.0", "MIT-CMU (HPND)", "仅用于生成方案插图，不进入运行时依赖"],
           ["python-docx", "1.2.0", "MIT", "仅用于生成本方案文档，不进入运行时依赖"],
           ["微软雅黑 / 黑体 / 宋体", "系统字体", "随操作系统授权", "方案正文与插图字体"]],
          widths=[3.6, 3.0, 3.6, 5.8])
    body(doc, "说明：本项目运行时零第三方依赖，requirements.txt 中无第三方包，"
              "上表中 Pillow 与 python-docx 仅用于生成交付文档与配图，不影响作品运行。", indent=False)

    h2(doc, "附录 C　数据来源与脱敏说明")
    body(doc, "课程库（62 门）与培养方案的学分结构，参照学校公开的培养方案框架整理，课程代码、教学班、"
              "容量与已选人数为构造数据；三个学生画像完全虚构，以 S001—S003 代号标识，不含任何真实身份信息；"
              "七篇知识库文档依据公开教学管理文件的条款结构整理，具体数值为构造数据。逐文件说明见仓库 "
              "data/SOURCES.md。", indent=False)

    h2(doc, "附录 D　评测结果摘要")
    table(doc, "表 D-1　检索排序子集（25 条用例）消融对比",
          ["指标", "仅 BM25", "BM25 + 特征重排", "变化"],
          [["Top-1 文档命中率", "84.0%", "88.0%", "+4.0pt"],
           ["章节命中率", "96.0%", "96.0%", "0"],
           ["Recall@5", "96.0%", "96.0%", "0"],
           ["MRR@5", "0.900", "0.920", "+0.020"]],
          widths=[6.0, 3.4, 3.8, 2.8])
    table(doc, "表 D-2　功能用例集（50 条）主要指标",
          ["指标", "结果", "样本数"],
          [["任务成功率", "100.0%", "50"],
           ["意图准确率", "100.0%", "44"],
           ["工具调用准确率", "100.0%", "31"],
           ["引用命中率 / Top-1", "100.0% / 90.0%", "10"],
           ["多轮指代正确率", "100.0%", "4"],
           ["安全拒答率 / 弃答正确率", "100.0% / 100.0%", "4 / 2"],
           ["幻觉与越界表述", "0 条", "50"],
           ["延迟 P50 / P95", "3ms / 8ms", "50"]],
          widths=[6.0, 5.0, 4.0])
    body(doc, "复现命令：python -m eval.run_eval --compare 与 python -m eval.run_retrieval。", indent=False)

    os.makedirs(os.path.dirname(OUT_DOCX), exist_ok=True)
    doc.save(OUT_DOCX)
    print("saved", OUT_DOCX)


if __name__ == "__main__":
    build()

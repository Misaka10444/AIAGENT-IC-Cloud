# -*- coding: utf-8 -*-
"""绘制方案文档用图（A4 版面可读版）。

关键约束：图会以 15.2cm 宽度排进 A4，画布宽度 1500px 对应约 250dpi，
因此 26px 文字的印刷字号约 7.5pt、32px 约 9.2pt。所有文字不得小于 24px，
否则打印后不可读——这也是本文件把架构图精简到"层 + 关键角色"的原因。

运行：python tools/draw_figs.py
"""
from __future__ import annotations

import math
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT = str(Path(__file__).resolve().parent.parent / "docs" / "figures")
FONT = r"C:\Windows\Fonts\msyh.ttc"
FONT_B = r"C:\Windows\Fonts\msyhbd.ttc"

INK = (28, 34, 48)
MUTED = (99, 110, 128)
LINE = (200, 208, 222)
BLUE = (24, 100, 220)
BLUE_L = (230, 239, 255)
GREEN = (22, 118, 70)
GREEN_L = (230, 245, 236)
AMBER = (170, 100, 0)
AMBER_L = (253, 242, 226)
GRAY_L = (245, 247, 250)
PURPLE = (100, 68, 180)
PURPLE_L = (240, 236, 250)
WHITE = (255, 255, 255)


def f(size, bold=False):
    return ImageFont.truetype(FONT_B if bold else FONT, size, index=0)


def text(d, xy, s, size=26, color=INK, bold=False):
    d.text(xy, s, font=f(size, bold), fill=color)


def wof(d, s, size, bold=False):
    b = d.textbbox((0, 0), s, font=f(size, bold))
    return b[2] - b[0]


def center_x(d, box, s, size, color=INK, bold=False):
    x0, y0, x1, y1 = box
    b = d.textbbox((0, 0), s, font=f(size, bold))
    w, h = b[2] - b[0], b[3] - b[1]
    d.text(((x0 + x1) / 2 - w / 2 - b[0], (y0 + y1) / 2 - h / 2 - b[1]),
           s, font=f(size, bold), fill=color)


def box(d, r, fill, outline=LINE, w=2, radius=10):
    d.rounded_rectangle(r, radius=radius, fill=fill, outline=outline, width=w)


def arrow(d, p0, p1, color=MUTED, w=3, head=11, dashed=False):
    x0, y0 = p0
    x1, y1 = p1
    if dashed:
        n = max(2, int(math.hypot(x1 - x0, y1 - y0) / 14))
        for i in range(0, n, 2):
            a = (x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n)
            b = (x0 + (x1 - x0) * min(1, (i + 1) / n), y0 + (y1 - y0) * min(1, (i + 1) / n))
            d.line([a, b], fill=color, width=w)
    else:
        d.line([p0, p1], fill=color, width=w)
    ang = math.atan2(y1 - y0, x1 - x0)
    for s in (-0.45, 0.45):
        d.line([(x1, y1), (x1 - head * math.cos(ang + s), y1 - head * math.sin(ang + s))],
               fill=color, width=w)


# ------------------------------------------------------------ 图1 总体架构
def fig_architecture():
    W, H = 1500, 940
    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)

    L, R = 30, 1470
    CX0 = 190           # 内容区左边界（左侧留层名）

    def band(y0, y1, name, sub):
        box(d, (L, y0, R, y1), GRAY_L, LINE, 2, 12)
        box(d, (L + 10, y0 + 10, L + 150, y1 - 10), WHITE, LINE, 2, 9)
        center_x(d, (L + 10, y0 + 16, L + 150, y0 + 66), name, 30, INK, True)
        if sub:
            center_x(d, (L + 10, y0 + 66, L + 150, y1 - 14), sub, 24, MUTED)

    # 接入层
    band(20, 160, "接入层", "交互入口")
    box(d, (CX0, 46, 1470 - 10, 134), WHITE, LINE, 2, 9)
    center_x(d, (CX0, 46, 1470 - 10, 134), "Web 演示界面　·　命令行 CLI　·　HTTP API", 30, INK)

    # 编排层
    band(180, 470, "编排层", "多智能体")
    agents = [("Planner", "意图分解", BLUE_L, BLUE),
              ("Retriever", "检索召回", PURPLE_L, PURPLE),
              ("ToolRunner", "工具执行", GREEN_L, GREEN),
              ("Auditor", "交叉校验", AMBER_L, AMBER),
              ("Composer", "结构化生成", BLUE_L, BLUE)]
    bw, gap = 230, 18
    for i, (name, sub, fill, edge) in enumerate(agents):
        x0 = CX0 + 10 + i * (bw + gap)
        box(d, (x0, 216, x0 + bw, 336), fill, edge, 3, 10)
        center_x(d, (x0, 226, x0 + bw, 290), name, 26, edge, True)
        center_x(d, (x0, 292, x0 + bw, 330), sub, 24, INK)
        if i < 4:
            arrow(d, (x0 + bw + 2, 276), (x0 + bw + gap - 4, 276), edge, 3, 8)

    box(d, (CX0 + 10, 356, 940, 448), WHITE, LINE, 2, 9)
    text(d, (CX0 + 26, 372), "会话记忆：实体槽位（学生 / 课程 / 学期）", 25, INK)
    text(d, (CX0 + 26, 408), "指代消解 + 轮次历史 + 输入输出护栏", 25, MUTED)
    box(d, (960, 356, 1470 - 10, 448), WHITE, LINE, 2, 9)
    text(d, (976, 372), "模型网关：可选，不可用自动降级", 25, INK)
    text(d, (976, 408), "日志：logs/trace.jsonl（JSONL）", 25, MUTED)

    # 能力层
    band(490, 700, "能力层", "10 个工具")
    box(d, (CX0, 516, 800, 676), WHITE, LINE, 2, 9)
    center_x(d, (CX0, 528, 800, 580), "教务核算工具　×7", 27, GREEN, True)
    center_x(d, (CX0, 584, 800, 668),
             "学分进度 · 先修校验 · 时间冲突\n毕业资格 · 学业预警 · 选课方案 · 画像", 24, MUTED)
    box(d, (820, 516, 1470 - 10, 676), WHITE, LINE, 2, 9)
    center_x(d, (820, 528, 1470 - 10, 580), "检索与规划工具　×3", 27, PURPLE, True)
    center_x(d, (820, 584, 1470 - 10, 668),
             "知识检索（BM25 + 重排）· 索引统计\n方案生成：在五类约束下求解", 24, MUTED)

    # 数据层
    band(720, 910, "数据层", "离线文件")
    data = [("课程库　62 门", "学分 · 先修 · 时隙"), ("培养方案　144 学分", "六模块 · 五项条件"),
            ("知识库　7 篇 34 片段", "带文档号与行号")]
    dw, dgap = 406, 24
    for i, (t1, t2) in enumerate(data):
        x0 = CX0 + i * (dw + dgap)
        box(d, (x0, 744, x0 + dw, 886), WHITE, LINE, 2, 9)
        center_x(d, (x0, 768, x0 + dw, 818), t1, 25, INK, True)
        center_x(d, (x0, 822, x0 + dw, 868), t2, 24, MUTED)

    for x in (560, 1010):
        arrow(d, (x, 162), (x, 214), BLUE, 3)
    arrow(d, (500, 472), (500, 512), GREEN, 3)
    arrow(d, (1120, 472), (1120, 512), PURPLE, 3)
    arrow(d, (500, 702), (500, 740), GREEN, 3)
    arrow(d, (1120, 702), (1120, 740), PURPLE, 3)

    img.save(os.path.join(OUT, "fig1_architecture.png"))
    print("fig1 ok")


# ------------------------------------------------------------ 图2 时序图
def fig_sequence():
    W, H = 1500, 900
    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)

    actors = [("用户", BLUE), ("Planner\n规划", BLUE), ("ToolRunner\n工具", GREEN),
              ("Retriever\n检索", PURPLE), ("Auditor\n校验", AMBER), ("Composer\n生成", BLUE)]
    aw, margin = 200, 30
    step = (W - 2 * margin - aw) / (len(actors) - 1)
    xs = []
    for i, (name, color) in enumerate(actors):
        x0 = margin + i * step
        xs.append((x0, x0 + aw))
        box(d, (x0, 16, x0 + aw, 108), WHITE, color, 3, 10)
        parts = name.split("\n")
        if len(parts) == 2:
            center_x(d, (x0, 26, x0 + aw, 66), parts[0], 26, INK, True)
            center_x(d, (x0, 66, x0 + aw, 102), parts[1], 24, MUTED)
        else:
            center_x(d, (x0, 26, x0 + aw, 100), parts[0], 28, INK, True)
    cx = [(a + b) / 2 for a, b in xs]
    for x in cx:
        for y in range(108, H - 20, 18):
            d.line([(x, y), (x, y + 8)], fill=(212, 219, 230), width=3)

    def msg(i, j, y, label, color=MUTED):
        x0, x1 = cx[i], cx[j]
        d0 = 12 if x1 > x0 else -12
        arrow(d, (x0 + d0, y), (x1 - d0, y), color, 3, 10)
        mid = (x0 + x1) / 2
        w = wof(d, label, 24)
        d.rectangle((mid - w / 2 - 8, y - 40, mid + w / 2 + 8, y - 6), fill=WHITE)
        d.text((mid - w / 2, y - 38), label, font=f(24), fill=color)

    def note(i, y, s, color=MUTED):
        x = cx[i] + 14
        w = wof(d, s, 23) + 22
        box(d, (x, y - 20, x + w, y + 22), (249, 250, 252), (226, 231, 240), 2, 8)
        d.text((x + 11, y - 14), s, font=f(23), fill=color)

    ys = [150, 225, 300, 375, 450, 525, 600, 675, 750, 825]
    msg(0, 1, ys[0], "① 提问（可多轮）", BLUE)
    note(1, ys[1], "指代消解 + 意图分类", BLUE)
    msg(1, 2, ys[2], "② 子任务 + 工具", GREEN)
    note(2, ys[3], "校验 → 调用 → 重试", GREEN)
    msg(1, 3, ys[4], "③ 检索式", PURPLE)
    note(3, ys[5], "BM25 → 阈值 → 重排", PURPLE)
    msg(3, 1, ys[6], "④ 片段 + 出处", PURPLE)
    msg(1, 4, ys[7], "⑤ 结构化结果", AMBER)
    msg(4, 5, ys[8], "⑥ 校验结论", AMBER)
    msg(5, 0, ys[9], "⑦ 回答 + 引用 + 生成标识", BLUE)

    img.save(os.path.join(OUT, "fig2_sequence.png"))
    print("fig2 ok")


# ------------------------------------------------------------ 图3 检索流程
def fig_rag():
    W, H = 1500, 700
    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)

    def center_lines(box_, s, size, color=MUTED, bold=False, lh=26):
        lines = s.split("\n")
        total = lh * len(lines)
        x0, y0, x1, y1 = box_
        cy = (y0 + y1) / 2 - total / 2
        for i, ln in enumerate(lines):
            center_x(d, (x0, cy + i * lh, x1, cy + i * lh + lh), ln, size, color, bold)

    M, GAP = 30, 22
    BW = (W - 2 * M - 4 * GAP) / 5
    x = [M + i * (BW + GAP) for i in range(5)]

    def step(col, y0, title, sub, fill=WHITE, edge=LINE):
        r = (x[col], y0, x[col] + BW, y0 + 118)
        box(d, r, fill, edge, 3, 9)
        center_lines((x[col], y0 + 8, x[col] + BW, y0 + 56), title, 28, INK, True, 32)
        center_lines((x[col], y0 + 58, x[col] + BW, y0 + 114), sub, 24, MUTED, False, 29)
        return r

    text(d, (M, 10), "离线索引", 26, BLUE, True)
    step(0, 48, "知识库 7 篇", "文档号 · 版本\n适用范围")
    step(1, 48, "章节切分", "400 字窗口\n80 字重叠")
    step(2, 48, "34 个片段", "保留原文行号")
    step(3, 48, "BM25 索引", "字二元组\n无分词词典")
    for i in range(3):
        arrow(d, (x[i] + BW + 2, 107), (x[i + 1] - 4, 107), BLUE, 3)

    text(d, (M, 192), "在线检索", 26, PURPLE, True)
    step(0, 230, "用户提问", "自然语言\n+ 会话上下文")
    step(1, 230, "检索式改写", "意图模板\n+ 关键词")
    step(2, 230, "BM25 召回", "候选 12 条")
    step(3, 230, "阈值 3.5", "低于即判\n无依据", AMBER_L, AMBER)
    step(4, 230, "弃答", "回复「没有\n找到依据」", AMBER_L, AMBER)
    for i in range(3):
        arrow(d, (x[i] + BW + 2, 289), (x[i + 1] - 4, 289), PURPLE, 3)
    arrow(d, (x[3] + BW + 2, 289), (x[4] - 4, 289), AMBER, 3)

    # 通过阈值 → 下一行
    arrow(d, (x[3] + BW / 2, 350), (x[3] + BW / 2, 414), GREEN, 3)
    d.text((x[3] + BW / 2 + 10, 368), "通过", font=f(22), fill=GREEN)

    step(3, 418, "特征重排", "标题 ×0.8\n覆盖 ×0.5")
    step(2, 418, "Top-5 片段", "同章节去重")
    step(1, 418, "引用拼装", "文档号 §章节\n+ 原文行号")
    step(0, 418, "输出审查", "拦截虚构引用", WHITE, GREEN)
    for i in (3, 2, 1):
        arrow(d, (x[i] - 4, 477), (x[i - 1] + BW + 2, 477), PURPLE, 3)

    note_r = (x[1], 566, W - M, 660)
    box(d, note_r, (249, 250, 252), LINE, 2, 9)
    text(d, (note_r[0] + 18, note_r[1] + 12),
         "重排实测（25 条检索用例）：Top-1 文档命中 84.0% → 88.0%，MRR 0.900 → 0.920", 24, MUTED)
    text(d, (note_r[0] + 18, note_r[1] + 50),
         "阈值标定：无关提问 Top-1 得分 2.9—3.0，有效提问 5.4 以上，取 3.5 两侧各留余量", 24, MUTED)

    img.save(os.path.join(OUT, "fig3_rag_pipeline.png"))
    print("fig3 ok")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    fig_architecture()
    fig_sequence()
    fig_rag()

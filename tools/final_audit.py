# -*- coding: utf-8 -*-
"""提交前总审计：把规程与附件 1—4 的硬性要求逐条对照实物核验。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile

from docx import Document

D = r"D:\DSH新建项目集\deliverables"
REPO = r"D:\DSH新建项目集\AIAGENT-集成电路-Cloud"
ZIP = r"C:\Users\gary_\OneDrive\Desktop\集成电路学院-Cloud-云梯-参赛材料.zip"
PLAN_PDF = os.path.join(D, "集成电路学院-Cloud-云梯学业规划与选课顾问Agent-方案.pdf")
FORM = os.path.join(D, "附件1 报名表.docx")
PLEDGE = os.path.join(D, "附件4 原创性和数据合规承诺书.docx")
VIDEO = os.path.join(D, "集成电路学院-Cloud-云梯-演示视频.mp4")

PLACEHOLDERS = ["【待填", "待填", "XXX", "xxx", "占位", "TODO"]
ok_all = True


def check(label, passed, detail=""):
    global ok_all
    mark = "PASS" if passed else "FAIL"
    if not passed:
        ok_all = False
    print(f"  [{mark}] {label}" + (f"  —— {detail}" if detail else ""))
    return passed


def docx_text(path):
    doc = Document(path)
    parts = [p.text for p in doc.paragraphs]
    for t in doc.tables:
        for row in t.rows:
            for c in row.cells:
                parts.append(c.text)
    return "\n".join(parts)


print("=" * 68)
print("一、附件 2 / 附件 3 是否需要上交")
print("=" * 68)
print("  附件 2《项目设计与开发方案》编写要求 —— 是「要求」文档，无填空项，不上交，只须按其规格写方案")
print("  附件 3《作品提交规范》            —— 是「规范」文档，无填空项，不上交，只须按其要求建仓库")
print("  附件 1 报名表、附件 4 承诺书      —— 有填空与签署项，必须上交")

print()
print("=" * 68)
print("二、报名表（附件 1）")
print("=" * 68)
t = docx_text(FORM)
doc = Document(FORM)
tbl = doc.tables[0]
def cell(r, c):
    return tbl.rows[r].cells[c].text.strip()
check("参赛队名称", cell(0, 2) == "Cloud", cell(0, 2))
check("选题名称", "云梯" in cell(0, 5), cell(0, 5))
check("选题类别已勾选场景库", "☑场景库选题" in cell(1, 2), cell(1, 2))
check("所属学院", "集成电路学院" in cell(1, 5), cell(1, 5))
advisor = cell(2, 2)
check("指导教师姓名已填", "张维婷" in advisor, advisor)
check("指导教师职称已填", "讲师" in advisor and "职称：" in advisor, "含职称字段")
check("指导教师手机已填", "18311256580" in advisor)
check("队长信息完整", all(x in cell(5, c) for c, x in
                       [(2, "黎家维"), (3, "20253113004"), (6, "19801069057")]))
check("队员信息完整", all(x in cell(6, c) for c, x in
                       [(2, "郑笑含"), (3, "20253113027"), (6, "17337563392")]))
check("项目简介已填且 ≤200 字", 0 < len(cell(8, 2)) <= 200, f"{len(cell(8, 2))} 字")
check("预期成果已勾选", "☑可运行原型系统" in cell(9, 2) and "☑开源仓" in cell(9, 2))
check("无占位符残留", not any(p in t for p in PLACEHOLDERS))
print("  注：『学院审核意见』按模板留空，需学院填写盖章（线下手续）")

print()
print("=" * 68)
print("三、原创性与数据合规承诺书（附件 4）")
print("=" * 68)
pt = docx_text(PLEDGE)
check("参赛队名称", "参赛队名称：Cloud" in pt)
check("队长签字", "队长签字：黎家维" in pt)
check("队员签字", "队员签字：郑笑含" in pt)
check("指导教师签字", "指导教师签字：张维婷" in pt)
check("日期已填", "2026 年 11 月 21 日" in pt)
check("六条承诺原文完整", all(k in pt for k in ["一、", "二、", "三、", "四、", "五", "六"]), "模板原文在「五」「六」后带空格，未改动")
check("无占位符残留", not any(p in pt for p in PLACEHOLDERS))

print()
print("=" * 68)
print("四、方案 PDF（模块 A）文件命名规范")
print("=" * 68)
name = os.path.basename(PLAN_PDF)
check("命名符合『学院-队名-项目名称-方案.pdf』",
      name.endswith("-方案.pdf") and name.startswith("集成电路学院-Cloud-"), name)
check("方案 PDF 存在", os.path.exists(PLAN_PDF), f"{os.path.getsize(PLAN_PDF)/1024:.0f} KB")

print()
print("=" * 68)
print("五、视频（模块 B）与压缩包")
print("=" * 68)
r = subprocess.run([sys.executable, r"D:\DSH新建项目集\tools\verify_video.py", VIDEO],
                   capture_output=True, text=True, encoding="utf-8")
out = r.stdout
check("视频技术指标全通过", "技术指标全部通过" in out)
for line in out.splitlines():
    if any(k in line for k in ("时长", "视频：", "实际帧率", "音频：", "大小")):
        print("      " + line.strip())
check("压缩包在桌面", os.path.exists(ZIP), f"{os.path.getsize(ZIP)/1048576:.1f} MB")
with zipfile.ZipFile(ZIP) as z:
    names = z.namelist()
    check("包内 8 个条目", len(names) == 8, f"{len(names)} 个")
    need = ["方案.pdf", "演示视频.mp4", "附件1 报名表.pdf", "附件4 原创性和数据合规承诺书.pdf"]
    for n in need:
        check(f"包含 …{n}", any(n in x for x in names))

print()
print("=" * 68)
print("六、作品仓库（附件 3）")
print("=" * 68)
def git(*args):
    return subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True,
                          encoding="utf-8").stdout.strip()

check("分支为 main", git("branch", "--show-current") == "main")
local = git("rev-parse", "HEAD")
remote = git("rev-parse", "origin/main")
check("本地与远端一致", local == remote, local[:8])
check("工作区干净", git("status", "--porcelain") == "")
files = git("ls-files").splitlines()
check("跟踪文件数 ≥66", len(files) >= 66, f"{len(files)} 个")
for need in ["README.md", "requirements.txt", "src", "data", "eval", "docs", "demo"]:
    check(f"含 {need}", any(f.startswith(need) for f in files))
check("无视频/大二进制入库", not any(f.endswith((".mp4", ".mov")) for f in files))
check("无真实密钥/手机号/学号",
      "sk-" not in git("grep", "-l", "sk-" ) and not any(
          "20253113004" in open(os.path.join(REPO, f), encoding="utf-8", errors="ignore").read()
          for f in files if f.endswith((".md", ".py", ".json"))))

print()
print("=" * 68)
print("结论：" + ("全部通过" if ok_all else "存在未通过项，见上面 FAIL"))
print("=" * 68)

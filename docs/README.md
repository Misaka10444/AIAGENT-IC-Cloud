# 文档目录

本目录存放架构图、接口说明与设计文档。

| 文件 | 内容 |
| --- | --- |
| `design.md` | 设计说明与关键决策记录（含检索阈值标定、评测口径、已知取舍） |
| `interfaces.md` | 工具与 HTTP 接口说明（由 `python tools/gen_interfaces.py` 从注册中心自动导出） |
| `figures/fig1_architecture.png` | 图 1　系统总体架构 |
| `figures/fig2_sequence.png` | 图 2　端到端调用链路与多智能体协作时序 |
| `figures/fig3_rag_pipeline.png` | 图 3　知识库构建与检索重排流程 |

## 关于《项目设计与开发方案》PDF

方案 PDF 作为**模块 A 的独立成果随报名材料提交**，未纳入本仓库，原因有二：

1. 方案封面包含队员学号，属于个人信息，不宜在公开仓库中留存（见附件 3 第 3 条第 3 项）；
2. 方案正文可直接由 `tools/build_plan_doc.py` 从本仓库内容重新生成，无需重复存放二进制文件。

重新生成方式：

```bash
# 学号通过环境变量注入，不写入仓库
set YUNTI_LEADER_ID=2025XXXXXXX
set YUNTI_MEMBER_ID=2025XXXXXXX
python tools/build_plan_doc.py
# 输出到 dist/ 目录（已在 .gitignore 中排除）
```

导出的 docx 用 Microsoft Word 更新目录页码后另存为 PDF，即为提交版本。
仓库内的 `docs/design.md` 与 `docs/interfaces.md` 覆盖了方案的技术内容，
可作为方案正文的补充材料单独阅读。

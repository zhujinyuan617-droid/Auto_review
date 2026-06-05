# Document Decomposer Handoff

这个文件用于给接手项目的人或 AI 快速了解当前项目。

## 项目简介

`Document_Decomposer` 是 `Auto_review` 里的文献处理模块。它的目标是把下载好的论文 PDF 变成可以被综述写作使用的结构化资料。

基本流程是：

```text
PDF
-> Docling JSON/Markdown
-> clean paper package
-> ai_sections.json
-> reading_blocks.json / reading.md
-> literature_card.json
-> evidence_atoms.json
-> paper_syntheses.json
-> 后续矩阵导出 / 跨论文综合
```

现在的重点是英文论文。中文/非英文论文和非论文文件暂时默认延后处理。

## 当前代码和数据状态

仓库：

```text
https://github.com/zhujinyuan617-droid/Auto_review
```

本地分支：

```text
main
```

本地生成数据不进 Git：

```text
Document_Decomposer/config/ai.local.json
Document_Decomposer/data/
Document_Decomposer/library/
Document_Decomposer/reports/
Document_Decomposer/envs/
paper_pool/paper/
```

不要打印或提交 `config/ai.local.json`，里面有本地 API key。

## 当前已经跑通的内容

单篇烟雾测试：

```text
S05
```

已知 S05 状态：

```text
title: Hindered settling velocity and microstructure in suspensions of solid spheres with moderate Reynolds numbers
doi: 10.1063/1.2764109
content_blocks: 191
reading_blocks: 168
literature_card: ok
evidence_atoms: ok
paper_syntheses: ok
```

英文批量测试：

```text
S10-S19
```

S10-S19 已完成：

```text
Docling: ok
clean: ok
sections: ok
reading: ok
literature_card: ok
evidence_atoms: ok
paper_syntheses: ok
final validators: ok
AI fallback warnings: none
```

## 当前主要文件

核心模块：

```text
src/docdecomp/package_builder.py
src/docdecomp/reading_blocks.py
src/docdecomp/literature_card.py
src/docdecomp/evidence_synthesis.py
src/docdecomp/ai_client.py
src/docdecomp/ai_cache.py
src/docdecomp/io_utils.py
src/docdecomp/library_index.py
```

主要脚本：

```text
scripts/ingest_paper_downloads.py
scripts/run_from_paper_downloads.py
scripts/run_pipeline.py
scripts/interactive_assistant.py
scripts/ai_organize_sections.py
scripts/ai_build_reading_blocks.py
scripts/ai_build_literature_card.py
scripts/ai_build_evidence_atoms.py
scripts/ai_build_paper_syntheses.py
```

验证脚本：

```text
scripts/validate_reading_blocks.py
scripts/validate_literature_card.py
scripts/validate_evidence_atoms.py
scripts/validate_paper_syntheses.py
```

## 当前遇到的问题

1. 元数据识别还不够稳。

   title、DOI、year、journal 现在主要靠脚本规则从首页、文件名、页眉页脚里识别。S10-S19 能跑通，但这个方式还可能误判。

2. 不应该继续堆单篇论文的人工规则。

   例如为了某篇论文补一个期刊名或出版社规则，短期能解决问题，长期会变得难维护。

3. 验证器还缺少完整性检查。

   目前 validators 能检查已经生成的结果是否合格，但还需要明确检查：用户指定的每篇论文是否都真的完成了所有必需阶段。

4. 全库大批量处理还没有完成。

   已经验证了 S10-S19 十篇英文论文，但还没有对整个 `paper_pool/paper` 做完整批处理。

5. 内存和并行策略还没有系统设计。

   10 篇并行已经测试过，但更大批量时还需要根据剩余内存、PDF 长度、Docling 成本和 AI 调用成本来调度。

6. 矩阵导出还没有实现。

   当前已有 `literature_card.json`、`evidence_atoms.json`、`paper_syntheses.json`，但还没有把它们导出成综述矩阵。

7. 跨论文综合还没有实现。

   现在的 `paper_syntheses.json` 是单篇论文内部综合，不是多篇论文之间的综合。

8. 中文/非英文论文路线暂时延后。

   当前产品重点是英文论文。中文论文后续可以单独设计。

9. 新电脑迁移仍需要注意本地配置。

   代码在 GitHub 上，但 AI key、Docling 环境、本地 PDF、生成结果都不进 Git。换电脑时需要重新配置。

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
（以上为“单篇抽取链”，已建成；跨篇关联 / 找灵感 / 接地出稿见下方“目标与技术路线”）
```

现在的重点是英文论文。中文/非英文论文和非论文文件暂时默认延后处理。

## 目标与技术路线（2026-06 重新规划）

> 状态：这是**目标与规划，大部分尚未实现**。已建成的只有“单篇抽取链”
> （见下方“当前已经跑通的内容”）。下面的关联层、灵感层、出稿层都还没做。

**最终目标**：一个**有真实素材底座的综述写作助手**，四步——
1. AI 从论文库**找灵感**，给几个综述切入角度；
2. 用户对每个角度**追问、刨析**；
3. 双方在**关键论点上达成一致**；
4. AI 从素材库**接地产出正式综述**：可溯源、可组合、贴用户真实写作风格。
与“上网搜几十篇现写”的区别在于：底座是**被结构化、被核实、能跨篇重组**的真材料。

**核心架构决定（取代原来的“自底向上摘要金字塔”）：**
- **不做卡片重组 / 逐层合并**——摘要的摘要会丢细节、累积误差。
- 改为**给卡片织一张“关联网”——只连不合**：用**笼统批注**（主题 / 机理 /
  定性结论，不含精确数字）在**卡片层**建跨篇关系（同题 / 支持 / 反驳 / 延伸 / 空白）。
- **原子层（精细、带逐字引文）= 可溯源证据，只在最后“定了论点、钻取原文”时才用**；
  措辞漂移问题因此被挪到最不致命的一步，且有用户在场把关。
- **综合发生在“定了论点之后、贴着原子即时拼出”，不预先烤好。**
- 借用 **Obsidian 的连接模型（链接 / 标签 / 图）**，但关联是**我们 AI 算出来写进去的**，
  Obsidian 只负责存 / 显示；是否使用 Obsidian App 本身可选。

**砍 / 留 / 加：**
- **砍**：卡片重组金字塔；原子措辞完美化（把 verifier 当强制闸 + 用 Pro 升级修措辞）；
  独立的静态“矩阵导出”任务（并入关联网的一种视图）。
- **留**：抽取链 1–6（`card` 升为“笼统层”核心，质量重点转向**定性方向对 + 词表统一**）；
  `evidence_atoms`（降级为“可溯源证据”，只保留**防编造 + 逐字引文**两道闸，不再追求措辞完美）；
  单篇 `paper_syntheses`（当一种笼统素材，不再加码）。
- **加**：① 统一词表 / 标签归一；② 跨篇关联层（关系网 + 主题索引）；
  ③ 笼统批注“方向对不对”轻校验；④ 灵感层；⑤ 接地出稿层；
  ⑥ markdown / vault 产出（可导航）；⑦ 论点驱动的跨篇检索。
- **地基顺序**：①② 先行；③ 配合 ②；④⑤⑦ 建在 ② 之上；⑥ 随时可做。

**待定依赖**：第 ⑤ 步“按用户风格成稿”需要用户**过去的论文 / 综述**当风格样本；
没有则先做“可溯源初稿”，风格留到后面。

**与质量纠结的关系**：之前为“原子措辞逐字接地”上 verifier、上 Pro 是把劲使偏了——
那条尾巴只在最后钻取时才碰、且有用户兜底。详见末尾“质量校验的已知局限与根因”。

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

已完整跑通全链路（reading_blocks + literature_card + evidence_atoms +
paper_syntheses 全部产出）的论文共 14 篇：

```text
S05, S06, S08, S09, S10, S11, S12, S13, S14, S15, S16, S17, S18, S19
```

说明：

- 最早的单篇烟雾测试是 S05，后续扩展到 S06/S08/S09 和英文批量 S10-S19。
- S07 没有进入 docling 输入（缺该篇），不在已完成清单内。
- S02 只跑到早期阶段（有 content_blocks / evidence / ai_sections，
  缺 reading_blocks / literature_card / evidence_atoms / paper_syntheses），
  属于半成品，尚未完成。
- 以 `library/index.json` 与各 `library/Sxx/` 目录下的实际产物文件为准。

已知 S05 状态（烟雾基线）：

```text
title: Hindered settling velocity and microstructure in suspensions of solid spheres with moderate Reynolds numbers
doi: 10.1063/1.2764109
content_blocks: 191
reading_blocks: 168
literature_card: ok
evidence_atoms: ok
paper_syntheses: ok
```

上述 14 篇的每篇产出状态：

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

   已经跑通约 133 篇英文论文（S05-S193 区间内的多批），但还没有对整个
   `paper_pool/paper`（约 380 篇 PDF，其中英文约 269 篇）做完整批处理。
   注意：这 133 篇是不同版本管线产出的拼接物，质量不一致，见下方
   "质量校验的已知局限与根因"。

5. 内存和并行策略还没有系统设计。

   10 篇并行已经测试过，但更大批量时还需要根据剩余内存、PDF 长度、Docling 成本和 AI 调用成本来调度。

6. 跨篇关联 / 灵感 / 出稿都还没实现。

   现在只有单篇抽取链；上方“目标与技术路线”规划的关联网、灵感层、接地出稿层都还没建。
   （原来的“矩阵导出 / 自底向上跨论文综合”已按新路线调整：矩阵并入关联网视图，跨篇不再
   靠合并而是靠“关联网 + 用时现拼”。详见“目标与技术路线”。）

7. 中文/非英文论文路线暂时延后。

   当前产品重点是英文论文。中文论文后续可以单独设计。

8. 新电脑迁移仍需要注意本地配置。

   代码在 GitHub 上，但 AI key、Docling 环境、本地 PDF、生成结果都不进 Git。换电脑时需要重新配置。

## 质量校验的已知局限与根因

这一节记录一次完整审计（用 133 个子 agent 逐篇核对全库）暴露出的深层问题，
给下一个接手的人，避免重复踩坑。结论先行：**乐观的"机械全过/30 篇全合格"和
悲观的"41 篇 major"两个数都不可信，真实大约一半干净。**

### A. 产出本身为什么会错
1. **"机械可校验" ≠ "正确"（最根本）。** 现有校验都是脚本能判定的代理指标：
   逐字子串、字段非空、数字在引文里。模型可以全部满足、却依然语义错：结论
   多加 "R²>0.98"（S146）、把方向写反（S08 把"增大"综合成"减小"）、补回
   OCR 丢的负号（S190）。规则一条没违反，机械层就判"干净"——校验给的信心
   超过了它能保证的范围。
2. **单次生成、没有"语义复核-返工"环节。** 第 6 步让模型一次性既挑引文又写
   结论；LLM 的天性是润色/补全，会写出比引文那一句更完整的结论。所以
   `minimal_claim` 超出 `quote` 的**漂移是默认行为，不是偶发**。需要的是
   generate→独立语义核对→不符就重写的闭环，而不是一次生成。
3. **逐层垒加，错误向上传染。** atoms 错 → syntheses 在错的 atom 上综合 →
   错误放大（S08 综合矛盾、S09 综合引用问题）。没有任何一层会语义上回头
   复核下一层。
4. **引文边界无人管。** 提示词让模型"截取更短的连续子串"，它就从 "9," 或
   "(Teklu et al." 这种句中位置切——逐字合法但难看（S09、S33）。缺"必须落在
   句子边界"的检查。
5. **元数据其实大体没坏。** 审计一度报告 21 篇元数据错，但核对发现
   `literature_card.json` 里的**最终** `paper.title/journal` 多数是对的
   （S08/S28/S92 都正确）。错的是 `metadata_candidates.json` 那个**故意装
   候选垃圾**的中间文件——不是真实缺陷。

### B. 为什么这些错没被干净发现（流程/度量的问题）
6. **修复是逐批打补丁，从不回填全库。** 只修了当时扫到/重跑的论文；S05-S19
   这些最早的在所有修复之前生成、之后再没重跑，所以 study_design 仍空
   （S05/S10/S14/S16/S18/S19）。整个 library 是不同版本管线产出的拼接物，
   从没"用当前最终标准把全库重跑一遍"。
7. **标准边跑边改（rubric 不固定）。** "数字接地""语义接地"是后期才加的，
   前几轮没按这个判。所谓"连续 3 轮全合格"是在一把会移动的尺子下得到的，
   不成立。
8. **量尺和被量物一样不可靠。** 用会幻觉的 LLM 评会漂移的 LLM 产出：审查员
   凭空捏造过坏引用（S09）、把中间垃圾文件当最终错、把"句中截断"判成 major。
   而且审查 prompt 本身有 bug（指向了 `metadata_candidates.json`）。所以两端
   的数字都偏。**任何 LLM 自评结论都要再抽样人工/脚本复核后才可信。**
9. **底层模型有天花板。** deepseek 快推理模型整体不错，但"只准逐字、一字不
   多加"这种严格指令遵循做不到 100%，部分漂移就是模型本身的局限。

### C. 给接手人的建议
- 不要把"机械 validators 全过"当成"正确"；那只是形式合规。
- 任何"全库已合格"的说法，先确认是否**全库在同一版管线、同一冻结标准下重跑过**；
  没有的话，先做一次统一重跑。
- LLM 审计结果先**抽样核对真实率**再行动（本次抽 10 篇，约 3 真 major、3 误报、
  4 过严），否则会按虚高的数字做无用功。
- 真正缺的是：(1) 逐原子/逐综合的**语义复核-返工**工序；(2) 有地面真值锚点的
  评测集；(3) 全库统一重跑的纪律。这些比继续加机械补丁更值得做。

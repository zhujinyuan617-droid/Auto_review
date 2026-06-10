# scripts/ 职责表

每个脚本只做一件事:解析参数 → 调逻辑 → 写一个产物。架构见 `../CONNECTION_PLAN.md`,
规则见仓库根 `CLAUDE.md`,问题见 `../ISSUES.md`。

## 抽取链(留在 `scripts/` 外层 —— 被 `run_pipeline.py` 按路径调用,勿移)
- `ingest_paper_downloads.py` — 扫 PDF、去重、分配 Sxx、分类、暂存。
- `run_from_paper_downloads.py` — 跑 Docling(缺则补)再调 `run_pipeline.py`。**全量入库**:`--all`
  处理 manifest 里所有 active 篇,**中文/非文章(deferred)默认自动跳过**(勿加 `--include-deferred`);断点续跑加 `--resume`;`--include-legacy-stages` 透传。
- `run_workflow_with_recovery.py` — 上层安全调度器:主流程 → 失败队列 → AI/validator 阶段重跑 → 最终验证报告;坏 PDF 默认只标记(`../config/docling_unresolved.json`);核心产物 = reading/card/elements。
- `run_review_workspace.py` — 综述工作台上层调度器:可选提取恢复 → 词表 → 候选边 → AI typed edges → 概念索引 → HTML 图谱 → 候选综述角度;只编排,不手改 AI 生成内容。**注意:词表步骤已退役为 derive(见 elements/ 与 ISSUES I18 顺序铁律)。**
- `run_pipeline.py` — 编排,**默认链(换代后):clean → sections → reading → card → elements → card_tags**(每篇 4 次 AI 调用);v1 遗留 `evidence_atoms / paper_syntheses` 挂 `--include-legacy-stages` 才跑。card_tags 为进程内机械步(从要素派生卡片标签,写 `card_tags.stamp`)。
- `ai_organize_sections.py` / `ai_build_reading_blocks.py` — AI 分章节 / 规划阅读块。
- `ai_build_literature_card.py` — **建瘦卡片 v3**(AI 只产 objective/main_findings/methods_systems/domain_tags;research_objects/methods/topic_ids 由系统从要素派生;逻辑在 `src/docdecomp/slim_card.py`)。
- `ai_build_evidence_atoms.py` / `ai_build_paper_syntheses.py` — (v1 遗留,默认链外,`--include-legacy-stages` 启用)。
- `validate_*.py` — 各阶段机械校验(slim 卡 0.2.0/0.3.0 双版本兼容)。

## connect/ —— 建关联网
- `build_vocabulary.py` — (退役)卡片标签 AI 归一;由 `elements/derive_vocabulary.py` 取代(见 ISSUES I12/I18)。
- `build_candidate_edges.py` — IDF 加权共享概念 → 候选边(纯脚本)。
- `ai_build_edges.py` — AI 读卡片**摘要**判 supports/contradicts/complements → `edges.json`。
- `build_concept_index.py` — 概念→段落索引(中心/一笔带过 + 空白榜 + central_evidence;纯脚本)。

## portfolio/ -- topic portfolio and shortlist
- `build_paper_portfolio.py` -- build the candidate manuscript portfolio matrix from the library, **elements (finding/analysis + material 气体识别)**, concept index, edges, figures, and overlap with accepted manuscripts.
- `build_topic_shortlist.py` -- product-facing pre-manuscript layer: select a human-reviewable shortlist of 3-5 candidate topics before running full manuscript generation. It writes candidate proposals, AI/fallback ranking, and `topic_shortlist_report.md`.

## use/ —— 用关联网(找灵感 → 刨析 → 出稿)
**交互流程(每步对应一个脚本,AI 只在脚本里干活,人在最后定):**
1. `propose_angles.py` — DeepSeek 从矛盾/空白/互补簇捞**候选创新点**(提示词里编码了标准:
   优先 矛盾>空白>新框架综合;排除"方法流行度/趋势总结/泛泛";宁缺毋滥)。
2. `query_network.py` — 纯脚本,把某角度的论文+关系+片段**拉到面前**(只读)。
3. `verify_angle.py` — **对抗式全文裁决**所给矛盾是 真/假/有条件/**证据不足(undetermined)**:喂全文(不按
   词检索,避免漏句)→ 控方/辩方各读全文**逐字举证 + 推理** → 脚本逐字核真引文(带省略号会拆段核)→ 裁判
   **4 步独立判定**(先认"度量本身":异度量=假;同度量异系统=有条件;关键篇无核真引文=证据不足,不靠"没证据"判假)。
   **默认纯 pro**(实测纯 flash 在难对子上会自信判错;hybrid 仍可用 `--model`/`--escalate-model` 切换);
   信心非 high 标记交人裁(I10)。产出 verdict + 调和变量 + 双方核真引文。设计/bug/判据/选型证据见 ISSUES I14。
4. 人(你)对着证据**最终定夺**;定了论点再 `draft_section.py` 出稿。
- `draft_section.py` — 接地出稿(从 block 取逐字引文 + 数字保真闸;可选风格 pass)。
- `build_graph_html.py` — 导出自建 HTML 交互图(非 Obsidian)。

## elements/ —— 研究要素索引(SP1+换代;设计见 docs/superpowers/specs/ 两份 2026-06-10 文档)
- `ai_extract_elements.py` — AI 抽取每篇用过的 制备/测量/表征/模拟/分析/材料/条件/**发现** 八类要素;逐字引文双档核真(存在性+数字保真),核不过即丢;`--parallel`(默认 6)。
- `backfill_findings.py` — 对已有要素文件的论文**只补抽 finding**(幂等、并行);补完自动归一+重建索引。
  归一默认**批量判同 bulk**(提案并行/落账串行,全库自愈);`--match-mode stream` 走旧逐篇路径。
- `bootstrap_element_registry.py` — 一次性引导:全库 surface 归并 → `data/elements/registry.json` + SQLite 索引;防大杂烩桶(I12 纪律);registry 已存在时拒绝重跑。
- `import_topic_vocabulary.py` — 一次性:把旧词表 topic canonical 导入注册表 topic 类(种子,幂等)。
- `derive_vocabulary.py` — 从注册表**纯脚本派生** `vocabulary.json`(topic←topic、method←制备∪测量∪模拟、object←material;首跑自动备份原词表;人工锁定条目在冲突时优先)。
- `build_elements_index.py` — 从 elements.json + registry 重建 `data/elements/elements_index.sqlite`(随时可重建)。
- `audit_element_buckets.py` — 列出别名数超限的条目(疑似过度合并,人工复查)。

## audit/ —— 抽查(都需人复核,见 ISSUES I10)
- `audit_summary_directions.py` — 抽样核瘦卡片摘要方向(写反/没依据)。
- `audit_card_grounding.py` — 核引文是否真出自原文(v1 厚卡片用;瘦卡片无引文)。

## write/ —— 可追踪 AI 综述写作闭环
- `build_writing_brief.py` — 从本地关系网/概念索引/卡片和 `config/writing_sources.json` 构建写作 brief。
- `run_writing_loop.py` — DeepSeek 作者 agent 出稿 → 机械引用/证据/claim_catalog 门禁 → 四个专家 agent 独立评审 → 裁决 revision plan → 迭代到 internal acceptance gate;每轮保存输入、输出、评分和 sha256 manifest。若仅引用格式失败,确定性修复引用语法,不改 claim register、不手改草稿。引用门禁会拦截 bare/parenthetical `Sxx`、相邻引用块 `[S09][S108]`、以及 `[S298] reports ...` 这类引用作句子主语的写法。
- `run_manuscript_funnel.py` — 生产级上层漏斗:同一候选方向生成 3-5 个独立 seed 草稿,每个 seed 保留完整 writing_loop run;选出 top seed 后可扩展 3-5 个 full manuscript,再横评、可选融合,全程保存选择理由和 manifest。
- `run_sectioned_manuscript.py` — 长综述分节/分块写作器;便宜模型只写 bounded chunk,每块和合并节都过引用/证据/字数门禁,最终合并为可导出的 writing-loop 兼容 run。当前 prompt 要求 Introduction 按「问题汇合→核心机制问题→主要矛盾→相邻证据边界→全文路线」组织。
- `validate_writing_loop.py` — 校验写作闭环 run 目录的 manifest、专家覆盖、门禁一致性和最终状态。

## manuscript/ -- single-manuscript production controller
- `run_single_manuscript_v2.py` -- production pipeline for one selected portfolio topic: sectioned DeepSeek writing/review, evidence trace, LaTeX export, figure brief/planning/validation/rendering, Docling source figure packaging, and final manuscript-with-figures export.
- `auto_finalize_single_manuscript_v2.py` -- final delivery controller for existing `sm2_*` runs. It replaces manual intervention: checks whether the expert gate passed, refreshes stale reports, resumes DeepSeek final review only when needed, reuses validated figure runs, locates a LaTeX compiler, regenerates the PDF, checks TeX logs for missing-character warnings, and writes `auto_finalize_report.json/.md`.
- `publish_manuscript_delivery.py` -- publish a clean reader-facing delivery under `reports/manuscript_deliveries/<slug>/<version>/` and update `latest.json`. For explicit manual revisions, pass `--manual-revision-dir` so `manual_revision_notes.md` and `source_version.json` are copied into the delivery trace.
- Rule: if a single-manuscript v2 run needs mid-course rescue, put the rescue behavior in this controller or a called validator/exporter. Do not hand-edit AI manuscript outputs or patch generated JSON by hand.

## figures/ —— 独立图表规划与校验
- `build_figure_brief.py` — 从已接受的 writing funnel / writing loop 中提取标题、章节、claim register、claim catalog 和证据上下文,生成可追溯 `figure_brief.json`。
- `plan_figures.py` — AI 图表规划器:只读 `figure_brief.json`,输出 `figure_plan.json`;失败时可用 `--fallback-on-error` 生成机械备用计划,不手改 AI 输出。
- `validate_figures.py` — 机械校验图表计划:检查 claim_id/paper_id 可追溯、数字来源、禁用 unsupported/needs_exclusion 图元。
- `render_figures.py` — 机械渲染已通过校验的图表计划,输出 SVG 预览、trace CSV、evidence map 和 LaTeX 表格片段。
- `collect_source_figures.py` — 从 `library/<paper_id>/figures/` 收集 Docling 原文图片候选,按最终稿引用论文、caption、章节、尺寸和主题词筛选,输出 `source_figure_candidates.json`。
- `export_manuscript_with_figures.py` — 将已通过校验的合成图表和 Docling 原文图插入已导出的论文 TeX,生成新的带图 PDF;不修改原始 AI 草稿和原文字版导出。
- 这个目录只负责图表 brief/plan/validation/rendering;后续插入主文、PDF 编译由导出脚本组合,不并入 `write/`。

## 公共库
- `../src/docdecomp/connect.py` — 连接层共享(目前:`load_deferred`)。延后名单见
  `../reports/connection/deferred.json`。后续可把更多共享逻辑收进来。

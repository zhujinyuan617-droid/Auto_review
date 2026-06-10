# Document Decomposer Handoff

给接手项目的人或 AI 的快速入口。**先读仓库根 `CLAUDE.md`(导航+规则)。**

## 项目简介
`Document_Decomposer` 是 `Auto_review` 的文献处理模块,把下载好的论文 PDF 变成可被综述写作
使用的结构化资料。单篇抽取链:

```text
PDF → Docling → clean package → ai_sections.json → reading_blocks.json
   → literature_card.json(架构 v2:瘦卡片 = metadata+标签+粗摘要)
   → [evidence_atoms / paper_syntheses 为 v1 遗留,瘦卡片路线下非必需]
```

之上的跨篇连接层(词表→关联网→概念索引→灵感→接地出稿)**已建成(架构 v2)**,详见 `CONNECTION_PLAN.md`。
当前重点是英文论文;中文/非英文/非论文默认延后。

## 技术路线(高层;细节与状态见 CONNECTION_PLAN.md)
**最终目标**:有真实素材底座的综述写作助手——AI 从论文库找灵感→用户追问→达成关键论点→
AI 从可溯源、可重组的网里接地产出贴用户风格的正式综述(区别于「上网搜几十篇现写」)。

**核心架构决定**:
- **只连不合**:不做自底向上摘要金字塔(会丢细节、累积误差),改为给卡片织**有类型的关联网**。
- **两层分工**:笼统层(卡片:主题/机理/定性结论,对措辞不敏感)负责连接与找灵感;
  精细层(原子/逐字引文)只在最后钻取时用。
- 连接层的完整 keep/discard/add 计划与各步状态,见 `CONNECTION_PLAN.md`。

## 当前代码和数据状态
- 仓库:`https://github.com/zhujinyuan617-droid/Auto_review`;主分支:`main`。
- 不进 Git(生成物/机密):`config/ai.local.json`、`data/`、`library/`、`reports/`、`envs/`、
  `paper_pool/paper/`。**勿打印或提交 `config/ai.local.json`(含本地 API key)。**
- 进 Git 与 commit 规则见根 `CLAUDE.md`。

## 当前进度(以产物为准,勿信此处概数)
- 单篇抽取链:全库恢复入口已跑通;当前英文主线 **255 篇核心论文**已完成并通过
  `validate_reading / validate_card / validate_evidence_atoms / validate_paper_syntheses`。
- 默认跳过/排除项:语言/正文 CJK 门控 **3 篇**(`S56`, `S85`, `S251`);
  Docling 无法转换 **6 篇**(`S290`, `S293`, `S294`, `S352`, `S353`, `S354`)。
  坏 PDF 列表在 `config/docling_unresolved.json`,默认只标记不抢救。
- 推荐全库入口:`scripts/run_workflow_with_recovery.py --all --config config/ai.local.json --parallel 6 --docling-parallel 2`。
  交互助手菜单 `12. 带恢复的智能全库运行` 调用同一流程。
- 推荐综述工作台入口:`scripts/run_review_workspace.py --skip-extraction --config config/ai.local.json`。
  交互助手菜单 `19. 一键更新综述工作台` 调用同一流程;如需要先补全单篇抽取,去掉 `--skip-extraction`。
- 写作闭环入口:`scripts/write/run_writing_loop.py`。它从本地证据与权威写作规范构建 brief,由作者 AI 出稿,
  先过机械引用/证据/claim_catalog 门禁,再由 4 个专家 agent 评审到 internal acceptance gate;每轮输入/输出/评分/sha256 manifest 都保存在 `reports/writing/`。
  若原始草稿只因引用格式失败,系统只允许作者 AI 做一次可追踪的引用格式修复;不要手改 `draft_v*.md`、`reviews_v*.json` 或 `decision_v*.json`。
- 当前写作约束已固化进 prompt + gate:长综述 Introduction 按「问题汇合→核心机制问题→主要矛盾→相邻证据边界→全文路线」组织;
  矛盾必须写成 disputed finding + boundary conditions + why it matters;机械引用门禁会拦截 bare/parenthetical `Sxx`、相邻引用块 `[S09][S108]`,
  以及 `[S298] reports ...` 这类引用作句子主语的写法。style gate 会提示防守式范围说明、空泛 future-work 句和自证价值句。
- 若用户明确允许人工修订正文,不要覆盖 AI accepted run。新建 `reports/manual_manuscript_revisions/<name>/`,记录 `source_version.json` 和
  `manual_revision_notes.md`,再用 delivery 发布为独立版本。Hydrogen 手工版示例:
  `reports/manuscript_deliveries/hydrogen-methane-and-carbon-dioxide-competition-in-subsurface-nanoporous-storage-systems/v20260608_040900_manual01/`。
- 单篇 manuscript v2 最终交付入口:`scripts/manuscript/auto_finalize_single_manuscript_v2.py --run-dir reports/single_manuscripts_v2/<sm2_run_dir> --config config/ai.local.json --basename <paper_slug>`。
  该 controller 负责自动检查 expert gate、刷新 stale report、必要时续跑 DeepSeek final review、复用已验证 figure run、编译 PDF、检查 TeX 缺字警告并写 `auto_finalize_report.json/.md`。
  接手 AI 不应在中途人工改稿或手工补 JSON;缺什么自动化能力,就补 controller/validator/exporter 后重跑。
- 跨篇连接层:词表/候选边/关系/概念索引/灵感/出稿脚本均已建成,状态见 `CONNECTION_PLAN.md`。
- **管线换代(2026-06-10,feature/pipeline-regen 分支)**:代码与测试已完成——默认链收敛为每篇 4 次 AI 调用
  (v1 atoms/syntheses 挂 `--include-legacy-stages`),要素新增 finding 类 + 存量补抽工具,卡片 v3(标签从要素派生),
  词表改由注册表纯脚本派生(AI 归一退役),authorship+机构注册表,抽取并行化。**全库回填批次未跑,顺序铁律见 ISSUES I18。**
- DeepSeek 上下文缓存说明:各阶段 system 提示词恒定且前置,批量运行自动享受缓存,无需改造。
- 当前机械验证已通过;质量风险仍见 `ISSUES.md`(尤其 I1 论断正确性、I12 词表非确定性、I18 换代过渡期)。

> 更正:本节早前写「已跑通 14 篇(S05–S19)/连续3轮全合格」,与同文件「约133篇」自相矛盾,
> 且「连续3轮合格」是在会移动的标准下得到、不成立。现统一改为「以 library/index.json 为准 +
> 质量见 ISSUES.md」。

## 主要文件
单篇抽取链核心模块:`src/docdecomp/` 下 `package_builder.py`、`reading_blocks.py`、
`literature_card.py`、`evidence_synthesis.py`、`slim_card.py`、`card_tags.py`、`ai_client.py`、`ai_cache.py`、
`io_utils.py`、`library_index.py`。

抽取链脚本:`scripts/` 下 `ingest_paper_downloads.py`、`run_from_paper_downloads.py`、
`run_workflow_with_recovery.py`、`run_review_workspace.py`、`run_pipeline.py`、`ai_organize_sections.py`、`ai_build_reading_blocks.py`、
`ai_build_literature_card.py`、`ai_build_evidence_atoms.py`、`ai_build_paper_syntheses.py`、
`interactive_assistant.py`;校验:`validate_{reading_blocks,literature_card,evidence_atoms,paper_syntheses}.py`。

连接层脚本已按职责分组到 `scripts/{connect,use,audit}/`,每个脚本一行职责见 `scripts/README.md`;
架构与状态见 `CONNECTION_PLAN.md`。抽取链脚本仍在 `scripts/` 外层(被 `run_pipeline.py` 按路径调用)。

研究要素索引(要素抽取/注册表/SQLite 索引,SP1+换代):`src/docdecomp/element_*.py`、`derive_vocabulary.py` +
`scripts/elements/`,桌面两屏(要素检索/全库统计)在 desktop_app;设计与状态见
`docs/superpowers/specs/2026-06-09-element-index-design.md` 与两份 2026-06-10 文档(数据框架、管线换代)。

## 已知问题
全部集中在 `ISSUES.md`(唯一台账)。遇到问题先查那里。

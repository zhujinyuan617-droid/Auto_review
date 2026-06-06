# Document Decomposer Handoff

给接手项目的人或 AI 的快速入口。**先读仓库根 `CLAUDE.md`(导航+规则)。**

## 项目简介
`Document_Decomposer` 是 `Auto_review` 的文献处理模块,把下载好的论文 PDF 变成可被综述写作
使用的结构化资料。单篇抽取链:

```text
PDF → Docling JSON/Markdown → clean package → ai_sections.json
   → reading_blocks.json/reading.md → literature_card.json
   → evidence_atoms.json → paper_syntheses.json
```

之上再叠跨篇连接层(词表→关联网→概念索引→灵感→出稿),详见 `CONNECTION_PLAN.md`。
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
- 单篇抽取链:已对一批英文论文产出全链路;**确切清单与状态以 `library/index.json` 为准**。
- 跨篇连接层:词表/候选边/关系/概念索引/灵感/出稿脚本均已建成,状态见 `CONNECTION_PLAN.md`。
- **质量参差,不可当「全库已合格」**——见 `ISSUES.md`(尤其 I1 卡片质量、I2 未冻结标准重跑)。

> 更正:本节早前写「已跑通 14 篇(S05–S19)/连续3轮全合格」,与同文件「约133篇」自相矛盾,
> 且「连续3轮合格」是在会移动的标准下得到、不成立。现统一改为「以 library/index.json 为准 +
> 质量见 ISSUES.md」。

## 主要文件
单篇抽取链核心模块:`src/docdecomp/` 下 `package_builder.py`、`reading_blocks.py`、
`literature_card.py`、`evidence_synthesis.py`、`ai_client.py`、`ai_cache.py`、`io_utils.py`、
`library_index.py`。

抽取链脚本:`scripts/` 下 `ingest_paper_downloads.py`、`run_from_paper_downloads.py`、
`run_pipeline.py`、`ai_organize_sections.py`、`ai_build_reading_blocks.py`、
`ai_build_literature_card.py`、`ai_build_evidence_atoms.py`、`ai_build_paper_syntheses.py`、
`interactive_assistant.py`;校验:`validate_{reading_blocks,literature_card,evidence_atoms,paper_syntheses}.py`。

连接层脚本(`build_vocabulary` / `build_candidate_edges` / `ai_build_edges` / `build_concept_index`
/ `build_graph_html` / `query_network` / `propose_angles` / `draft_section`):见 `CONNECTION_PLAN.md`。

## 已知问题
全部集中在 `ISSUES.md`(唯一台账)。遇到问题先查那里。

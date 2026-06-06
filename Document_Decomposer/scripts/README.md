# scripts/ 职责表

每个脚本只做一件事:解析参数 → 调逻辑 → 写一个产物。架构见 `../CONNECTION_PLAN.md`,
规则见仓库根 `CLAUDE.md`,问题见 `../ISSUES.md`。

## 抽取链(留在 `scripts/` 外层 —— 被 `run_pipeline.py` 按路径调用,勿移)
- `ingest_paper_downloads.py` — 扫 PDF、去重、分配 Sxx、分类、暂存。
- `run_from_paper_downloads.py` — 跑 Docling(缺则补)再调 `run_pipeline.py`。
- `run_pipeline.py` — 编排:clean → sections → reading → card → evidence_atoms → paper_syntheses。
- `ai_organize_sections.py` / `ai_build_reading_blocks.py` — AI 分章节 / 规划阅读块。
- `ai_build_literature_card.py` — **建瘦卡片**(metadata+标签+粗摘要;聚焦读;逻辑在 `src/docdecomp/slim_card.py`)。
- `ai_build_evidence_atoms.py` / `ai_build_paper_syntheses.py` — (v1 遗留,瘦卡片路线下非必需)。
- `validate_*.py` — 各阶段机械校验。

## connect/ —— 建关联网
- `build_vocabulary.py` — 卡片标签 → 统一受控词表(AI 归一;见 ISSUES I12 非确定性)。
- `build_candidate_edges.py` — IDF 加权共享概念 → 候选边(纯脚本)。
- `ai_build_edges.py` — AI 读卡片**摘要**判 supports/contradicts/complements → `edges.json`。
- `build_concept_index.py` — 概念→段落索引(中心/一笔带过 + 空白榜 + central_evidence;纯脚本)。

## use/ —— 用关联网
- `query_network.py` — 按概念/按论文接地查询(只读)。
- `propose_angles.py` — 从矛盾/空白/互补簇生成候选综述角度。
- `draft_section.py` — 接地出稿(从 block 取逐字引文 + 数字保真闸;可选风格 pass)。
- `build_graph_html.py` — 导出自建 HTML 交互图(非 Obsidian)。

## audit/ —— 抽查(都需人复核,见 ISSUES I10)
- `audit_summary_directions.py` — 抽样核瘦卡片摘要方向(写反/没依据)。
- `audit_card_grounding.py` — 核引文是否真出自原文(v1 厚卡片用;瘦卡片无引文)。

## 公共库
- `../src/docdecomp/connect.py` — 连接层共享(目前:`load_deferred`)。延后名单见
  `../reports/connection/deferred.json`。后续可把更多共享逻辑收进来。

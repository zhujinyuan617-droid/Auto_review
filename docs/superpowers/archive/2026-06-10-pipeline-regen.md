# 管线换代 实施计划(SP-Regen)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development。Steps use checkbox (`- [ ]`) syntax。

**Goal:** 默认管线收敛为每篇 4 次 AI 调用;要素增 finding 类并对存量补抽;卡片 v3(概括归 AI、标签归派生);词表 AI 归一退役(topic 入注册表);拆解页迁移要素;authorship+机构注册表;抽取并行化。

**Architecture:** 见 `docs/superpowers/specs/2026-06-10-data-framework.md`(schema 合同)与 `2026-06-10-pipeline-regeneration-design.md`(实施决策)。本计划只写怎么动手。

**Tech Stack:** 同 element-index 计划;OpenAlex API(免费,UA 标识)。

---

## 仓库纪律(执行者必读;与上一计划相同,另加两条)

1. 分支:`feature/pipeline-regen`(由控制器自 `feature/element-index` 建出);逐任务 commit,绝不 push,绝不 `git add -A`。工作区有他人未提交改动与正在运行的全库构建——**绝不运行任何 git checkout/restore/stash/reset/clean;绝不删改任务清单外的文件**。
2. **全库构建正在后台逐篇写 `library/*/elements.json` 与 data/elements/***:引擎测试一律用 tmp_path 假库,绝不把测试指向真实 library/ 或真实 data/。
3. 测试命令:引擎 `cd Document_Decomposer; ..\desktop_app\.venv\Scripts\python -m pytest tests -q`(当前 52 绿);桌面 `cd desktop_app; .venv\Scripts\python -m pytest -q`(当前 154 绿)。
4. AI 全部注入;测试用 `tests/_fake_ai.py` SequencedFakeClient / `tests/_fake_transport.py` FakeTransport。

## 关键事实(侦察已核实,直接用)

- `run_pipeline.py:24` `STAGE_ORDER = ["clean","sections","reading","card","evidence_atoms","paper_syntheses"]`;stage 经 `command_for_stage` 以 subprocess 调 scripts;完成哨兵 = `STAGE_ORDER[-1]`(372–391)。
- `run_workflow_with_recovery.py:24-30` `CORE_OUTPUTS`(四件)与同款 `STAGE_ORDER`;失败队列按 `missing_core_outputs` 与 `retry_pipeline_stages` 驱动。
- `interactive_assistant.py:27` `STAGES = [...同六阶段..., "validate"]`;`local_status()`(296–305)探测 atoms/syntheses 文件;菜单 748–778。
- `slim_card.py`:`SLIM_SCHEMA_VERSION="0.2.0"`;`ensure_slim_defaults` 105–141(classification 五键循环在 127);`validate_slim_card` 144–158;`build_slim_prompt` user 文本 65–91(含 gas_systems/scale 字样两处)。
- ThreadPool 样板:`run_from_paper_downloads.py:382-408`(futures dict + as_completed + 单篇异常不挡批)。
- portfolio 读 legacy 的行:414-417, 431-432, 435-441, 508, 641, 695, 776-777, 809-810, 982-983;另 `flatten_card_text` 378-390、`sample_claims` 560-612 引用 atoms/syntheses 内容。
- `vocabulary.json` 消费者只用两条:`raw_to_canonical[facet][tag_lower]`(candidate_edges:49,92;FACET_KEYS={topic,method,object})与 `facets.<f>.concepts[].{canonical,members}`(concept_index:63-67,119)。现 topic canonicals=192。
- `element_extraction.py` `_SYSTEM` 六条规则 + `ELEMENTS_SCHEMA_HINT`(facet 枚举来自 seeds,加类即生效);`element_seeds.json` facets 现七项。
- 桌面 `decomposition.py`(全文 89 行):atoms→analyses{method,variable,mechanism}/results{result,quantitative_result};syntheses→result_relations;payload 键 `paper_id/card/abstract_blocks/intro_blocks/glossary/analyses/results/result_relations`;atom 视图键 `evidence_atom_id/atom_type/minimal_claim/quote/reading_block_id/confidence`;relation 键 `synthesis_id/synthesis_type/claim/supporting_evidence_atom_ids`。前端 `papers.js renderDecomposition`(117-164)按这些键渲染;**实现前先读 papers.js 的 `atomList()` 确认其字段引用**。
- 桌面唯一读 atoms/syntheses 的生产代码 = decomposition.py(grep 已证)。
- groups:`store.py` 单表 `authors(doi TEXT PRIMARY KEY, authors TEXT)`;`populate.py` 从卡片 doi → Crossref `fetch_by_doi(doi, transport)`;`identity.py` 姓+首字母键,senior=末位作者。Transport 协议 `get_json(url, params)/get_bytes(url)`;来源类无状态,transport 作参数注入;测试用 `_fake_transport.FakeTransport(json_responses={url: canned})`。
- 桌面 `elements/service.py run_bootstrap`:抽取循环(84-94)可并行;**流匹配循环(99-101)串行保留**(registry 原地变更)。
- DeepSeek 上下文缓存:各 stage system 恒定且前置,批量跑同 stage 已自动享缓存——无需改造,R10 文档说明即可。

## 任务总表(执行波次)

| 波 | 任务 | 侧 | 主要文件 | 模型建议 |
|---|---|---|---|---|
| 1 | R1 finding 入抽取 | 引擎 | element_seeds.json, element_extraction.py, tests | 实现 sonnet/质量 opus |
| 1 | R7 authorship+机构 | 桌面 | discovery/sources/openalex.py(新), groups/authorship.py(新), api.py, tests | 实现 sonnet/质量 opus |
| 2 | R3 卡片 v3+派生标签 | 引擎 | slim_card.py, card_tags.py(新), tests | 实现 sonnet/质量 **fable** |
| 2 | R2 finding 补抽 CLI | 引擎 | scripts/elements/backfill_findings.py(新) | sonnet |
| 3 | R4 默认链砍 v1 | 引擎 | run_pipeline.py, run_workflow_with_recovery.py, interactive_assistant.py | 实现 sonnet/质量 opus |
| 3 | R6 topic 注册表+派生词表 | 引擎 | scripts/elements/import_topic_vocabulary.py(新), derive_vocabulary.py(新), card_tags.py 扩展, tests | sonnet |
| 4 | R5 拆解页双源 | 桌面 | decomposition.py, papers.js(如需), tests | 实现 sonnet/质量 **fable** |
| 4 | R8 抽取并行化 | 双侧 | ai_extract_elements.py, backfill_findings.py, elements/service.py, elements_stats.js 文案 | sonnet |
| 5 | R9+R10 portfolio 迁移+文档+终验 | 双侧 | build_paper_portfolio.py, scripts/README.md(注意混改动文件不 commit), desktop README, 缓存说明 | sonnet |

同波内文件集不相交,可在前一任务的审查期并行开工(评审流水线);**commit 仍按完成顺序逐个落**,避免 git index 竞争。

---

### R1 finding 入要素抽取(引擎)

**Files:** Modify `config/element_seeds.json`、`src/docdecomp/element_extraction.py`;Test `tests/test_element_extraction.py` 追加。

- [ ] seeds.facets 追加(放 condition 之后):
```json
{"id": "finding", "name_zh": "发现", "name_en": "findings & conclusions",
 "description": "Conclusions THIS paper itself establishes: directional effects (e.g. water reduces CH4 adsorption), measured outcomes, demonstrated mechanisms. The quote must contain the concluding statement. Findings restated from other papers belong to role=mentioned."}
```
- [ ] `_SYSTEM` 追加第 7 条规则(编号顺延,原第 6 条"Output strictly..."改为第 8 条):
```text
7. facet='finding': report ONLY conclusions this paper itself establishes (directional
effects, measured outcomes, demonstrated mechanisms). surface = a short declarative
noun phrase (e.g. 'water reduces methane adsorption capacity'). The quote must contain
the concluding statement verbatim. A review restating另文结论 -> role='mentioned'.
```
   (英文写法保持与现有条目一致;中文注释勿入 prompt。)
- [ ] 新测试 3 个(先红后绿;沿用 `_fixtures.write_reading_blocks`,blocks 自定义含一句结论文本):
  `test_finding_facet_extracted_with_quote`(canned 响应含 finding 项→入库,facet=finding);
  `test_finding_fabricated_quote_dropped`(结论引文不在 block→dropped quote_not_found);
  `test_prompt_lists_finding_facet`(messages 串含 "finding")。
- [ ] 全引擎套件绿(52+3);commit `feat(engine): finding facet for element extraction (anchored conclusions)`。

### R7 authorship + 机构注册表(桌面)

**Files:** Create `src/autoreview_app/discovery/sources/openalex.py`、`src/autoreview_app/groups/authorship.py`;Modify `api.py`(+2 路由 + 注入 runner);Test `tests/test_openalex_source.py`、`tests/test_authorship.py`、`tests/test_api_authorship.py`。

- [ ] OpenAlexSource(无状态,镜像 crossref.py):
```python
OPENALEX_WORKS_URL = "https://api.openalex.org/works/doi:{doi}"
class OpenAlexSource:
    def fetch_authorship(self, doi: str, transport: Transport) -> dict | None:
        data = transport.get_json(OPENALEX_WORKS_URL.format(doi=doi.strip().lower()), {})
        auths = data.get("authorships") or []
        if not auths: return None
        return {"authors": [{
            "name": (a.get("author") or {}).get("display_name") or "",
            "position": i + 1,
            "is_senior": i == len(auths) - 1,
            "raw_affiliations": [inst.get("display_name") or "" for inst in (a.get("institutions") or []) if inst.get("display_name")],
        } for i, a in enumerate(auths)], "source": "openalex"}
```
- [ ] `groups/authorship.py`:`populate_authorship(library_dir, institutions_dir, fetch, log_path, progress)`——
  逐篇读卡片 doi(无 doi → skip 计数);fetch 失败/None → **PDF 兜底**:读 `content_blocks.json` 前 12 块文本,
  正则收含 `University|Institute|Laboratory|College|Academy|School of` 的行为 raw_affiliations(authors 为空,source="pdf_front_page");
  机构归一:经 engine_bridge 用 `docdecomp.element_registry`(facet 固定 `"institution"`,id 前缀即 `elem:institution/<slug>`,
  registry 文件在 `data/institutions/registry.json` + 同目录 log;不存在则 `{"schema_version":"0.1.0","facets":[{"id":"institution"}],"entries":{}}` 起步);
  `find_by_surface` 命中挂别名,未命中 `create_entry(origin="auto-stream")`(v1 无 AI 兜底,纯精确/别名——机构 AI 判同留待后续);
  写 `library/Sxx/authorship.json`(framework §1.3 schema,institution_ids 为解析结果);返回 `{populated, pdf_fallback, skipped_no_doi, failed}`。
- [ ] api.py:`POST /authorship/populate`(job,注入 `authorship_runner: ... | None = None`,默认 runner 用 OpenAlexSource+UrllibTransport)、`GET /authorship/coverage`(数 authorship.json 份数/总数)。路由放 /elements 块旁;**新 create_app 参数保持向后兼容**。
- [ ] 测试:FakeTransport canned OpenAlex 响应(两作者两机构,一机构重名变体验证别名归并);PDF 兜底用例(transport 抛 KeyError);coverage 计数;job 端点用注入 runner。桌面套件全绿(154+8 左右)。
- [ ] commit `feat(desktop): authorship via OpenAlex with PDF fallback + institution registry (stable IDs)`。

### R3 卡片 v3 + 派生标签(引擎;质量审查用 fable)

**Files:** Modify `src/docdecomp/slim_card.py`;Create `src/docdecomp/card_tags.py`;Test `tests/test_slim_card_v3.py`(新)、`tests/test_card_tags.py`(新)。

- [ ] slim_card v3:`SLIM_SCHEMA_VERSION="0.3.0"`;`ensure_slim_defaults` 的 classification 循环改为
  `("research_objects","methods","domain_tags","topic_ids")`(删 gas_systems/scale;topic_ids 默认 []);
  `build_slim_prompt` user 文本:classification 行改为 `{domain_tags}`-only(说明 research_objects/methods 由系统派生,模型勿填;删除 gas_systems/scale 字样两处);
  `validate_slim_card`:classification_empty 检查改为仅 domain_tags;n_tags 同步。
- [ ] `card_tags.py`(纯机械,无 AI):
```python
FACET_TO_FIELD = {"material": "research_objects",
                  ("preparation", "measurement", "simulation"): "methods"}
def derive_classification(elements_doc: dict, registry: dict, top_n: int = 5) -> dict:
    """used 角色按 canonical 计数,取各组 top_n 的 display_name 列表。"""
def apply_derived_tags(card: dict, derived: dict) -> dict   # 写回并返回 card
def derive_topic_ids(card: dict, registry: dict) -> list[str]
    """domain_tags 逐个 find_by_surface(facet='topic');未命中返回空缺(不强塞),留待 R6 的批量解析。"""
```
  (实现者自定函数体;display_name 经 `resolve_id` 后取;计数并列时按字母序稳定。)
- [ ] 测试:派生 top_n 截断与排序稳定;空 elements → 空列表不报错;v3 默认值含 topic_ids;v3 prompt 不含 gas_systems;validate 仅查 domain_tags。注意:现有桌面 `_library_fixtures.write_card` 写 v2 卡(含 gas_systems)——**引擎侧不动它**;桌面套件如因 schema 字样断言失败,修桌面 fixture 为 v3(在本任务 commit 中一并改并说明)。
- [ ] 两侧套件全绿;commit `feat(engine): slim card v3 (AI keeps summary+domain_tags; tags derived from elements; dead fields dropped)`。

### R2 finding 存量补抽 CLI(引擎)

**Files:** Create `scripts/elements/backfill_findings.py`;Test `tests/test_backfill_findings.py`。

- [ ] 模块函数进 `src/docdecomp/element_extraction.py`:`build_finding_prompt(reading, seeds)`(裁剪版 _SYSTEM:仅 finding 规则+核真要求)与 `backfill_findings(paper_dir, client, seeds) -> dict`:
  读现有 elements.json → 删 facet=="finding" 旧条目(幂等)→ 调 AI 仅抽 finding → `parse_elements_response` 复用(facet 白名单临时收窄为 {"finding"})→ 合并写回;返回 {added, dropped}。
- [ ] CLI:`--library-dir/--config/--paper/--parallel(默认 6)`;目标 = 有 elements.json 的论文;ThreadPool 样板照抄(关键事实节);抽完后串行:`load_registry → 逐篇 match_paper_elements(client) → save_registry → build_index`;打印汇总。registry/data 路径默认 `ROOT/data/elements`。
- [ ] 测试(fake client):幂等(跑两次 finding 不翻倍);合并不动其他 facet;核真失败丢弃。
- [ ] commit `feat(engine): finding backfill for existing element extractions (idempotent, parallel)`。

### R4 默认链砍 v1(引擎)

**Files:** Modify `run_pipeline.py`、`run_workflow_with_recovery.py`、`scripts/interactive_assistant.py`;Test:无引擎单测设施覆盖这些脚本——验证 = `--dry-run` 冒烟 + 全套件不回归。

- [ ] run_pipeline:`STAGE_ORDER = ["clean","sections","reading","card","elements","card_tags"]`;
  `LEGACY_STAGES = ["evidence_atoms","paper_syntheses"]`;`--include-legacy-stages` 开启时插回 card 之后;
  `script_by_stage` 加 `"elements": "elements/ai_extract_elements.py"`(传 `--paper` 单篇)——注意该脚本参数为 `--paper` 非 `--paper-id`,在 `command_for_stage` 分支适配;
  `"card_tags"` 不走 subprocess:直接 import `card_tags` + `element_registry` 就地执行(读 data/elements/registry.json,缺则跳过并警告);
  完成哨兵改用 `STAGE_ORDER[-1]`(自动随表);`--stage` choices 同步。
- [ ] recovery:`CORE_OUTPUTS` 改为 reading/card/elements 三件;`STAGE_ORDER` 同步为 clean/sections/reading/card/elements/card_tags;
  legacy 仅在新旗标透传时参与;最终验证报告文案同步。
- [ ] assistant:`STAGES` 常量同步;`local_status()` 探测 elements.json 替代 atoms/syntheses;菜单文案两处微调。
  (该文件曾有用户未提交改动疑似丢失;现按已提交版本修改,commit message 注明。)
- [ ] 冒烟:`run_pipeline.py --paper-id S05 --stage all --dry-run`(假库 tmp 不可行——dry-run 不执行只打印命令,允许对真库 paper-id 仅打印)输出含 elements、不含 atoms;`--include-legacy-stages` 时含。两侧套件绿。
- [ ] commit `feat(engine): default chain = 4 AI calls (legacy atoms/syntheses behind flag; elements+card_tags stages wired)`。

### R6 topic 入注册表 + 派生词表(引擎)

**Files:** Create `scripts/elements/import_topic_vocabulary.py`、`scripts/elements/derive_vocabulary.py`;Modify `src/docdecomp/card_tags.py`(批量 topic 解析助手);Test `tests/test_derive_vocabulary.py`、`tests/test_topic_import.py`。

- [ ] import_topic_vocabulary:读 `reports/connection/vocabulary.json`(--vocab 可指),对 facets.topic.concepts[] 逐条:
  registry 无该 canonical(facet="topic")则 `create_entry(origin="seed")` 并把 members 全部 `add_alias`;幂等(重跑零新增);打印 {created, aliased, skipped}。
- [ ] derive_vocabulary:从 registry 生成兼容 vocabulary.json:
  facet 映射 topic←topic、method←preparation∪measurement∪simulation、object←material;
  concepts[] = 每个非 redirect 条目 {canonical: display_name, members: [display_name]+aliases};
  raw_to_canonical[facet][member.lower()] = canonical(冲突时先到先得并警告);
  顶层 {card_count: len(library 卡片), model: "derived-from-registry"};`--out` 默认写 reports/connection/vocabulary.json,**默认先备份原文件为 vocabulary.pre_derive.json**(只此一次,存在则不覆盖备份)。
- [ ] card_tags 增 `resolve_topics_bulk(cards_dir, registry, client|None, log_path)`:全库 domain_tags 去重集合 → find_by_surface;未命中且 client 给定 → 复用 `element_matching.build_match_prompt` 风格一次批量判同(facet="topic");命中挂别名,未命中 create_entry(origin="auto-stream");随后逐卡写 topic_ids。
- [ ] 测试:导入幂等;派生输出两把钥匙(raw_to_canonical / facets.*.concepts[].{canonical,members})形状与消费者预期一致(直接按 candidate_edges/concept_index 的取法断言);method 合并视图正确;批量 topic 解析(fake client)未命中走新建。
- [ ] commit `feat(engine): topic facet seeded from legacy vocabulary; vocabulary derived from registry (AI normalization retired)`。

### R5 拆解页双源(桌面;质量审查用 fable)

**Files:** Modify `src/autoreview_app/decomposition.py`(必要时 `frontend/views/papers.js`);Test `tests/test_decomposition.py` 扩展、`tests/test_api_decomposition.py` 扩展。

- [ ] 实现前先读 `papers.js atomList()`,锁定 UI 实际字段;目标:**payload 键与字段名完全不变**,仅换数据源。
- [ ] decomposition.py:若 `elements.json` 存在且 occurrences 非空 → elements 源:
  analyses ← facet∈{analysis,simulation,measurement} 且 role=used → `{"evidence_atom_id": f"EL-{i:04d}", "atom_type": facet, "minimal_claim": surface, "quote": quote, "reading_block_id": ..., "confidence": ""}`;
  results ← facet=="finding" 且 role=used 同构(atom_type="finding");
  result_relations ← 有 syntheses 文件则旧逻辑;否则卡片 main_findings → `{"synthesis_id": f"MF-{i:02d}", "synthesis_type": "main_finding", "claim": 文本, "supporting_evidence_atom_ids": []}`;
  payload 加 `"source": "elements"|"legacy"`(新增键不影响 UI)。
  否则(无 elements)→ 旧 atoms/syntheses 逻辑原样保留。
- [ ] papers.js:仅当 atomList 渲染受 atom_type 影响需微调时改(如 finding 标签文案);否则不动。
- [ ] 测试:elements 源(写假 elements.json 含 analysis+finding)断言三板块来源正确;legacy 回退;两源 payload 键集合相同。
- [ ] commit `feat(desktop): decomposition view reads elements(+finding) with legacy fallback (UI contract unchanged)`。

### R8 抽取并行化(双侧)

**Files:** Modify `scripts/elements/ai_extract_elements.py`、`scripts/elements/backfill_findings.py`(若 R2 未含)、`src/autoreview_app/elements/service.py`、`frontend/views/elements_stats.js`(文案);Test `tests/test_elements_service.py` 扩展。

- [ ] CLI `--parallel` 默认 6:抽取循环换 ThreadPool 样板(单篇异常计 failed 不挡批;打印保留逐篇行)。
- [ ] service.run_bootstrap:抽取循环 ThreadPool(max_workers 参数默认 6,经 runner 透传可测);**流匹配循环保持串行**并加注释(registry 原地变更,勿并行)。
- [ ] stats 文案:"逐篇运行…十几个小时到一天" → "并行运行,全库约 1–2 小时";保留费用与续跑说明。
- [ ] 测试:fake client 下并行抽取 3 篇结果与串行一致(occurrences 齐、文件全在);一篇抛错其余完成。
- [ ] commit `feat: parallel element extraction (engine CLI + desktop bootstrap), honest duration copy`。

### R9 portfolio 迁移 + R10 文档与终验(合并执行)

**Files:** Modify `scripts/portfolio/build_paper_portfolio.py`;Modify `desktop_app/README.md`(可 commit)+ `Document_Decomposer/scripts/README.md` 与 `HANDOFF.md`(**只改不 commit**,与既有未提交改动同车);Test:portfolio 无套件——加 `tests/test_portfolio_inputs.py` 仅测新数据装配函数。

- [ ] portfolio:行级迁移(关键事实节列了全部行号)——
  atoms/syntheses 读取改为 elements.json:`atoms` 概念 → finding+analysis occurrences(`minimal_claim`←surface,`quote`←quote,`atom_type`←facet);`syntheses` 概念 → 卡片 main_findings 包装;
  `gas_systems` 来源改为 material 类中气体名单(CH4/CO2/H2O/N2/H2 等常量表过滤);`scale` 引用直接删除;
  evidence 存在性探测(776-777)改 elements.json;CSV 列名保持。封装为 `collect_paper_inputs(paper_dir, card)` 纯函数以便单测。
- [ ] 文档:desktop README 状态段补换代摘要与 4 调用账;scripts/README 抽取链小节同步(elements/card_tags 入默认链、legacy 旗标、backfill/import/derive 新脚本三行);HANDOFF「当前进度」加一行换代说明 + DeepSeek 缓存说明一句(system 恒定前置,批量自动享缓存,无需改造)。
- [ ] 终验:两侧全套件;`run_pipeline --dry-run` 双态冒烟;`derive_vocabulary` 对真库跑一次并 diff 两把钥匙的覆盖率(报告数字,不改判)。
- [ ] commit(仅可提交文件)`feat(engine): portfolio reads elements; docs: regen registered`。

## 运营清单(代码外,按序执行;顺序铁律见 ISSUES I18)
1. 全库要素构建完成(桌面后台任务跑完,coverage 接近 261)。
2. finding 补抽:`python scripts\elements\backfill_findings.py --config config\ai.local.json --parallel 6`(无 --all,默认即全库;约 261 次轻调用)。
3. card_tags 回填:`python scripts\run_pipeline.py --all --stage card_tags`(机械,零 AI)。
4. topic 种子导入:`python scripts\elements\import_topic_vocabulary.py`(一次性,幂等)。
5. 主题批量解析:`python scripts\elements\resolve_topics_bulk.py --config config\ai.local.json`(至多 1 次 AI 调用)。
6. 词表派生:`python scripts\elements\derive_vocabulary.py`(纯脚本;首跑自动备份旧词表)。
7. 机构拉取:桌面 `POST /authorship/populate`(或界面按钮;OpenAlex,261 次礼貌限速请求)。
8. 连接层重建:`build_candidate_edges → ai_build_edges → build_concept_index → use/build_graph_html`(注意 build_graph_html 在 scripts/use/)。
9. 抽样审计并登记 ISSUES:finding 20 条 + 机构归一 20 家 + 超大桶审计(`audit_element_buckets.py`)。

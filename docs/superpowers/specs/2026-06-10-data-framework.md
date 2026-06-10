# 数据输出框架(换代后的单一事实源)

- 日期:2026-06-10
- 状态:**已与用户逐节确认(对话内)**;实施由「管线换代」「地图与找」两份 spec 引用本文件,不重抄
- 原则:schema 是合同,AI 是承包商——先定产物,再派工,后写脚本
- 前置:`2026-06-09-element-index-design.md`(要素层已建成);本框架在其上扩展

## 1. 每篇论文的产物(library/Sxx/)

| 文件 | 层 | 状态 | 说明 |
|---|---|---|---|
| `content_blocks.json` | 底料 | 不变 | Docling/PyMuPDF 原始块 |
| `ai_sections.json` | 中间件 | 不变 | 分节;只服务阅读块构建 |
| `reading_blocks.json` | ① 原文层 | 不变 | **事实底座**;一切引用的最终出处 |
| `elements.json` | ② 要素层 | **改版** | 八类要素(见 §1.1) |
| `literature_card.json` | ③ 概括层 | **改版** | v3 瘦卡(见 §1.2) |
| `authorship.json` | 归属 | **新增** | 作者+机构(见 §1.3) |
| `figures/` | 底料 | 不变 | Docling 图;首次被界面消费(图墙) |
| `evidence_atoms.json` / `paper_syntheses.json` | — | **退役** | 不再生成;旧文件保留作拆解页回退 |

### 1.1 elements.json(schema 0.2.0,八类)

facet 枚举:`preparation / measurement / characterization / simulation / analysis / material / condition / finding(新)`。
occurrence 五件套不变:`surface + quote(逐字) + reading_block_id + role(used/mentioned) + 核真双标(quote_verified/digits_verified)`;
condition 类带机械解析 `values`;**finding 类 = 论文自己的结论,同一道核真闸**,是拆解页"结果"板块与未来结论级关系的数据源。
`canonical_id` 指向要素注册表稳定 ID。

### 1.2 literature_card.json(schema 0.3.0)

- **AI 字段**(整篇概括,一次调用):`summary.objective / summary.main_findings / summary.methods_systems / classification.domain_tags`
- **机械字段**(派生写回,消费者无感):`classification.research_objects / classification.methods`(要素 top-N)
  + `classification.topic_ids`(domain_tags 经注册表 topic 类解析的稳定 ID)
- **删除**:`gas_systems / scale`(零界面消费者;portfolio 改读要素)
- 元数据 `paper.*` 不变

### 1.3 authorship.json(新,schema 0.1.0)

```json
{"paper_id": "S09",
 "authors": [{"name": "...", "position": 1, "is_senior": false,
              "raw_affiliations": ["China University of Petroleum (East China)"],
              "institution_ids": ["inst:china-university-of-petroleum-east-china"]}],
 "source": "openalex|pdf_front_page|crossref", "fetched_at": "..."}
```
机构名解析到机构注册表稳定 ID;来源优先 OpenAlex,PDF 首页机械兜底。

## 2. 全库级产物(data/ 与 reports/connection/)

| 路径 | 状态 | 说明 |
|---|---|---|
| `data/elements/registry.json` + `registry_log.jsonl` | 改版 | **增 topic 类**(种子从旧词表 canonical 导入);人工事件永久保存 |
| `data/elements/elements_index.sqlite` | 改版 | 含 finding/topic 行;随时可重建 |
| `data/institutions/registry.json` + `registry_log.jsonl` | **新增** | 机构归一,复用 element_registry 同一套模块(稳定 ID/别名/重定向/日志) |
| `data/map/layout_<lens>.json` | **新增** | 地图布局缓存(节点坐标/分区/区名/参数指纹);可重生产物 |
| `data/user/` | 占位 | 个人层与裁决台账(SP3)预留命名空间 |
| `reports/connection/vocabulary.json` | **改版** | 由注册表**纯脚本派生**(AI 归一退役);消费者(候选边/概念索引)接口不变 |
| `reports/connection/edges.json` | 不变 | AI 判边照旧 |
| `reports/connection/concept_index.json` | 不变(暂) | 后续随 topic 注册表升级 |

**主题词闭环**:卡片 AI 产 domain_tags → 流式匹配进注册表 topic 类 → 稳定 ID 同时供 地图主题镜头 / 派生词表 / 概念索引。一份归一,三处受益。

## 3. AI 工作清单(一岗一认知,不混岗)

**每篇自动(导入触发,4 次调用)**:
1. 分节(结构整理)→ ai_sections
2. 阅读块(结构整理)→ reading_blocks
3. 概括(整篇概括)→ 卡片 v3 AI 字段
4. 要素抽取 v2(罗列抽取,八类)→ elements

**流式兜底(精确/别名失手才调用;归一判同)**:要素判同 / 主题词判同 / 机构判同——同一个匹配器服务三种实体。

**全库低频**:判边(关系判断,不变)| finding 存量补抽(一次性批)| 引导归并(已完成,永久冻结,绝不重跑)。

**按需(人触发,不变)**:角度提议、对抗式核查(pro 区)、写作工厂全家、图表规划。

## 4. 脚本处置单

- **改**:`element_extraction`(+finding)、`run_pipeline`/恢复入口(默认链砍 atoms/syntheses)、`slim_card`(v3)、`build_vocabulary`→`derive_vocabulary`(纯脚本)、`build_paper_portfolio`(改读要素)、桌面 `decomposition.py`(改读要素,无要素回退旧 atoms)
- **新**:`fetch_authorship.py`(OpenAlex+PDF 兜底)、`build_institution_registry.py`(复用注册表模块)、`backfill_findings.py`(存量补抽)、`build_map_layout.py`、抽取并行化(`--parallel`,抄引擎现成线程池模式)
- **退役**(文件保留、出默认链、文档标注):`ai_build_evidence_atoms`、`ai_build_paper_syntheses`、`ai_verify_evidence_atoms`、`build_vocabulary` 的 AI 路径
- **省钱不合并**:各 stage 提示词前缀布局统一,蹭 DeepSeek 自动上下文缓存(输入重复部分约一折)

## 5. 迁移与兼容纪律

- 旧产物**只退役不删除**;拆解页对无 elements 论文回退 atoms 显示。
- 注册表只增不改;topic/机构两类新实体走同一引导→流式纪律(topic 种子=旧词表 canonical,机构种子=空)。
- schema_version 全部递增;消费者按版本兼容读。
- 任何"已验证/合格"表述须有抽样审计支撑(家规)。

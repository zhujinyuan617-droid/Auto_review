# 管线换代 设计(SP-Regen)

- 日期:2026-06-10
- 状态:方向已与用户确认;**本文件待用户审阅**;实施排在「全库要素构建验收」之后
- 单一事实源:产物 schema 与 AI 分工见 `2026-06-10-data-framework.md`(本文不重抄,只写实施决策)
- 缘起:AI 调用全景审计(17 个调用点)+ 产物→消费者地图;结论=省钱大头在**淘汰**而非合并

## 1. 目标 / 非目标

**目标**
- 默认管线收敛到框架 §3 的"每篇 4 次调用";v1 遗留(atoms/syntheses)出默认链。
- 要素八类(+finding)落地;存量 261 篇补抽 finding。
- 卡片 v3:概括归 AI、标签归派生、死字段删除。
- 词表 AI 归一退役;topic/机构进注册表(同一套机制)。
- 抽取并行化(全库批从"一天"级降到 1–2 小时)。

**非目标**
- 不动判边/概念索引/写作工厂/figures 的 AI 逻辑(只换它们的输入来源)。
- 不删任何旧产物文件;不重跑引导归并(注册表冻结纪律)。
- 裁决评审家族(verify/experts/审计脚本)的统一复核机制 = 记录方向,不在本期。

## 2. 实施决策(逐项)

### 2.1 砍 v1 阶段
- `run_pipeline.py` 默认链改为 clean → sections → reading → card → elements;
  atoms/syntheses 改为 `--include-legacy-stages` 显式开启(脚本文件保留)。
- `run_workflow_with_recovery.py` 同步:默认验证集合改为 reading/card/elements 三类;
  legacy validator 仅在显式开启时执行。
- `interactive_assistant.py` 菜单文案同步(注:该文件曾有未提交用户改动疑似丢失,改动前先与用户确认现状)。

### 2.2 finding 第八类 + 存量补抽
- `element_extraction`:facet 枚举与提示词加 finding(定义:**本篇自己得出的结论/效应/数值结果**,
  must 带逐字引文;综述转述他人结论 = mentioned)。schema 0.2.0。
- `backfill_findings.py`(新):对已有 elements.json 的论文跑**只抽 finding** 的轻量调用
  (提示词裁剪到单类),结果 merge 进现有 occurrences(按 facet=finding 去重后追加),
  再流式匹配 + 重建索引。并行执行(2.6)。
- 质量纪律:补抽完成后抽样 20 条 finding 人工核(引文核真是机械保障,核的是"是否真为本篇结论")。

### 2.3 卡片 v3 + 派生标签
- `slim_card.py`:schema 0.3.0;AI 输出字段收缩(objective/main_findings/methods_systems/domain_tags);
  删除 gas_systems/scale。
- 新机械步 `derive_card_tags`(并入管线 elements 之后):research_objects ← material 类 top-N(used);
  methods ← preparation/measurement/simulation 类 top-N(used);写回卡片。
- 存量迁移:一次性脚本对 261 篇重派生标签写回(不重跑卡片 AI);消费者(SQLite 索引/候选边/简报)无感。
- 回退:卡片 v2 字段名不变,只是来源变;无破坏性。

### 2.4 词表退役 + topic 入注册表
- 注册表增 facet `topic`;种子 = 现行 `vocabulary.json` 的 topic canonical(一次性导入,
  origin="seed");卡片 domain_tags 经流式匹配器解析到 topic 稳定 ID(存 authorship 同级的轻量映射或卡片内 `topic_ids` 字段——**定:卡片内加 `classification.topic_ids`**,机械写回)。
- `derive_vocabulary.py`(新,纯脚本):从注册表导出 vocabulary.json 兼容格式
  (raw_to_canonical + facets),供候选边/概念索引零改动消费。
- method/object 两个 facet 的词表派生:method ← preparation/measurement/simulation 合并视图,
  object ← material。映射规则写死在派生脚本,带单元测试。

### 2.5 拆解页迁移(桌面)
- `decomposition.py`:analyses ← elements(analysis/simulation/measurement,used,带 quote);
  results ← elements(finding,used);result_relations 板块在无 syntheses 数据时显示卡片
  main_findings(标注"方向级,无锚点")。
- 回退:论文无 elements.json 时维持读旧 atoms/syntheses(不删旧逻辑,加数据源开关)。

### 2.6 抽取并行化
- `ai_extract_elements.py` 与桌面 `run_bootstrap` 的抽取循环加 ThreadPool(`--parallel`,默认 6),
  模式照抄 `run_from_paper_downloads.py` 已验证实现;单篇失败不挡批(沿现状)。
- 注册表写入仍串行(匹配阶段);抽取阶段无共享写,天然安全。
- 统计屏构建提示文案同步改("1–2 小时"量级)。

### 2.7 机构层(数据侧;镜头属地图 spec)
- `fetch_authorship.py`(新):DOI → OpenAlex authorships(机构名+ROR);失败回退 PDF 首页
  机械抽取(正则+行位置启发);写 `authorship.json`。
- `build_institution_registry.py`(新):复用 element_registry 模块建 `data/institutions/`;
  机构归一走同一三层(精确/别名 → 流式 AI 兜底);超大桶审计同款。
- 桌面 groups 屏后续改读机构注册表(属地图/IA 批次,不在本期强求)。

### 2.8 提示词前缀统一(蹭缓存)
- 四个 per-paper stage 的 messages 统一为「固定 system 前缀 + 论文负载」结构,负载内部
  字段顺序稳定;DeepSeek 上下文缓存自动生效。只动布局不动语义;各 stage 金样本测试锁行为。

## 3. 质量与验证

- 两侧测试套件全程绿;新增:finding 抽取金样本、派生标签单测、derive_vocabulary 单测、
  authorship 解析单测(OpenAlex 假响应)、拆解页双数据源测试。
- 换代后跑一次全库**机械**校验:卡片 v3 字段完整性、elements 八类计数、索引重建一致。
- 人工抽样(家规,做完才许写"已验证"):finding 20 条 + 机构归一 20 家。

## 4. 切片建议(给 writing-plans)

R1 finding 入抽取 + 金样本 → R2 backfill_findings(并行)→ R3 卡片 v3 + 派生标签 + 存量迁移 →
R4 默认链砍 v1 + 恢复入口同步 → R5 拆解页迁移(双源)→ R6 topic 入注册表 + derive_vocabulary →
R7 authorship + 机构注册表 → R8 并行化 + 文案 → R9 前缀统一 + 金样本 → R10 文档同步 + 全库机械校验。

## 5. 风险(预登记)

- finding 抽取质量未知(新认知类)→ 金样本 + 20 条抽样,先抽样后扩量。
- domain_tags→topic 流式匹配的命中率未知 → 低命中时批量 AI 兜底成本可控(每篇 ≤1 次)。
- OpenAlex 覆盖率/限流 → 兜底 PDF;失败标 pending 不挡导入(P0)。
- 拆解页双源切换的回归 → 双数据源测试 + 旧逻辑保留。

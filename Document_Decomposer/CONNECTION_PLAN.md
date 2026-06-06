# 关联层（②）方案

> 路线见 `HANDOFF.md`「目标与技术路线」。本文件只细化第 ② 步：在统一词表（①，已建成
> `reports/connection/vocabulary.json`）之上，给 134 张卡片织一张**有类型的跨篇关系网**，
> 并导成一个 Obsidian vault。
>
> 一句话定位：**我们自己负责「存、看、算」。** 借鉴 Obsidian 的连接*思路*
> （双向链接 / MOC 索引 / 图谱 / tags），但**不依赖 Obsidian App**——存是我们的 JSON，
> 看是我们自建的 HTML 图谱，算（有类型的关系）更是我们的核心增量。
> 它的相似度只能堆出毛球；我们要的是「这两篇在 XX 上互相印证 / 打架 / 补空白」。
>
> **查看器决定（已定）**：自建静态 HTML 交互图给用户看，**不用 Obsidian**。

## 0. 设计依据（已用真实数据验证）

- 归一化后 134 篇里 **39% 的论文对至少共享 1 个规范主题** → 底料足。
- 但主题重尾:`adsorption` 覆盖 63 篇、`shale gas` 54 篇。**只按「共享 1 主题」连边会变毛球**
  (63 篇互连 ≈ 1900 条无信息边)。→ 候选打分必须**降权高频概念**。
- Obsidian 原生链接无类型;Smart Connections 的 embedding 相似度也无类型,且**会把结论相反的
  论文判成最相似**——恰恰漏掉写综述最值钱的「矛盾/互补」信号。→ 关系类型必须我们自己用 AI 算。

## 1. 数据模型

**节点 = 一张 literature_card**(已有,不动)。

**边 = `reports/connection/edges.json`**,每条:

```json
{
  "a": "S08", "b": "S44",
  "relation": "extends",              // 见 §3 关系类型
  "direction": "a->b",               // 仅非对称关系(extends/fills_gap)有意义;对称关系为 null
  "shared": {                         // 触发这条边的共享规范概念(可溯源,不含精确数字)
    "topic": ["adsorption"],
    "object": ["kerogen", "nanopores"],
    "method": ["grand canonical monte carlo"]
  },
  "candidate_score": 7.8,            // §2 脚本算的召回分(IDF 加权)
  "rationale": "两篇都用 GCMC 研究 kerogen 纳米孔吸附;S44 把 S08 的单组分推广到竞争吸附。",
  "model": "deepseek-..."
}
```

**双向**:边只存一次,但导出 vault 时两端都生成 wikilink(抄 Obsidian backlink)。

## 2. 召回候选边(纯脚本,不调 AI)——先看边稠不稠

目标:从 8911 个论文对里筛出**少而像话**的候选,既降噪又把 AI 判关系的成本框住。

**打分 = 共享概念的 IDF 加权和**(这是杀毛球的关键):

```
score(a,b) = Σ_facet w_facet · Σ_{c ∈ shared_facet(a,b)} log(N / df(c))
```

- `df(c)` = 概念 c 覆盖的论文数;`N` = 134。
- 共享 `adsorption`(df=63)几乎不加分;共享 `kerogen type II-D`(df=1~2)大幅加分。
  → **「都研究吸附」不算关系,「都研究同一种 kerogen 的竞争吸附」才算。**
- facet 权重初值:object 1.0、method 0.8、topic 0.6(对象/方法重叠比泛主题更能说明真有关系),
  可调。

**剪枝**:每篇只保留 **top-K 邻居**(初值 K=10),再合并对称对。预计候选边数量级 ~几百条,
而不是几千。

**先交付物**:候选边表 + 一张「边稠密度 / 度分布 / 最强 20 条边」报告,给你肉眼判:
筛出来的边像不像话、毛球散没散。**这一步不调 AI,可反复重跑调参。**

## 3. 关系类型(AI 判,§4)

| relation | 含义 | 对称? |
|---|---|---|
| `supports` | 同向印证:结论/机理一致或互相佐证 | 对称 |
| `contradicts` | 张力:同问题下结论相反 / 适用条件冲突 | 对称 |
| `extends` | 延伸:b 在 a 基础上推广(对象/方法/尺度扩展) | a→b |
| `fills_gap` | 互补:b 补上 a 明说或暗含的空白 | a→b |
| `shared_context` | 背景同但无强关系 → **丢弃**(降噪用,不进网) | — |

只判**定性方向**,不碰精确数字(精确证据留给原子层,最后钻取时才用)。

## 4. AI 判关系(分篇批处理,控成本)

- 对每篇 a,把它的 top-K 候选邻居的**卡片笼统摘要**(core_question + key_findings +
  mechanisms + 共享概念)拼进**一次** AI 调用,让模型对每个候选邻居输出 {relation, direction,
  rationale}。→ 约 **134 次调用**(不是按边数),成本可控。
- 硬约束写进提示词:
  - rationale **必须引用共享的规范概念**(可溯源);
  - 不得编造精确数字 / 不得把「同主题」当「supports」;
  - 拿不准就判 `shared_context`(宁可丢边也不要假关系)。
- 产出 `edges.json`(过滤掉 `shared_context`)。

## 5. 主题簇 + MOC 索引(脚本 + 轻 AI)

- 用规范主题/对象做聚类(可先用「共享高 IDF 概念」的连通分量,或简单图社区发现)。
- 每个簇生成一篇 **MOC 笔记**:列出成员论文(wikilink)、簇内主要 supports/contradicts 边、
  一句 AI 写的簇主旨。→ 这是后面「找灵感(④)」的入口。

## 6. 自建 HTML 交互图(纯脚本)—— 给用户看

`reports/connection/graph.html`,单文件、可双击打开、不依赖 Obsidian:

- **力导向图**:节点=论文(大小∝度数,颜色∝主题簇),边按关系类型上色
  (supports/contradicts/extends/fills_gap 各一色,`contradicts` 用醒目色)。
- 点节点 → 侧栏显示该篇卡片笼统摘要(title/core_question/key_findings)+ 按关系类型分组的
  邻居列表(每条带 rationale + 触发的共享概念)。
- 顶部按关系类型 / 主题簇过滤;MOC 簇可作为图里的「超级节点」入口。
- 实现:Python 把 `edges.json` + 卡片摘要序列化进一个 HTML 模板,JS 用 CDN 力导向库
  (如 vis-network / d3)渲染;数据内联,无需起服务器。
- 注意:这是**给人肉眼探索 + 抽样校验**用的;AI 消费仍直接读 `edges.json`,不经过 HTML。

## 7. 质量校验(笼统层哲学:方向对就行,不追字字精确)

- 关系是**方向级**判断,对卡片个别措辞漂移不敏感(这正是当初选「笼统批注」的原因)。
- ③ 轻校验:抽样核对一批边的 relation 是否方向正确(尤其 `contradicts`,最容易误判);
  你做最终裁判,我不手改 `edges.json`,只改提示词重跑(沿用既定纪律)。
- 已知风险(诚实记录):
  1. 卡片质量不均(全库约一半干净)→ 烂卡片产烂边。粗关系较鲁棒但非免疫。
  2. AI 可能滥用 `contradicts` 或脑补关系 → 用「必须引用共享概念 + 拿不准判
     shared_context」压制,再靠你抽样兜底。
  3. embedding 第二召回通道**本期不做**,留给 ⑦(检索)。先用词表召回。

## 8. 落地顺序与交付物

1. ✅ **候选边脚本**(§2)`scripts/build_candidate_edges.py` → `candidate_edges.json`(899 边,毛球已散)。
2. ✅ **AI 判关系**(§4)`scripts/ai_build_edges.py` → `edges.json`(536 typed:complements 315 / supports 214 / contradicts 7;v2 四类法,抽样读原文验过)。
3. ✅ **自建 HTML 交互图**(§6)`scripts/build_graph_html.py` → `graph.html`(124 节点/536 彩色边)。
4. ✅ **概念→段落索引**(③)`scripts/build_concept_index.py` → `concept_index.json`(404 概念,中心/一笔带过 + 研究空白榜;精度修过,召回有天花板待 embedding)。
5. ✅ **查询缝**`scripts/query_network.py`(--concept / --paper:接地查询)。
6. ✅ **接地出稿**`scripts/draft_section.py`:
   - pass1 `--concept` → 可溯源忠实初稿(引用已读原文核实零编造);
   - pass2 `--style-corpus <用户论文>`(或 demo 用 `--style-paper Sxx` 替身)→ **风格化稿**,
     带程序化保真闸(引用零增减 + 不新增数字,已验 True)。

7. ✅ **灵感层(④)**`scripts/propose_angles.py` → `angles.md`:从矛盾边/研究空白/互补簇
   生成候选综述角度,每个带关键论文 [Sxx] + 一个「你需要先定」的追问点 —— 即终点句
   「用户与 AI 就关键论点达成一致」的入口。

每步都是独立产物、可重跑、不动现有卡片数据。查看器=自建 HTML,不用 Obsidian。

**「终点」状态**:端到端能力**已全部建成**(找角度→追问→接地素材→忠实初稿→风格 pass→风格化稿,带保真校验)。
「贴用户真实写作风格」现在是一个**数据输入**(`--style-corpus`),不再是缺失的能力——
只需用户提供过去的论文/综述当语料。代码侧无可再自给的部分;这是唯一不可替代的外部输入。

# CLAUDE.md — 本仓库的导航 + 开发规则(每次会话必先读)

> 这是路由器,不是内容仓库。只放:文档地图、何时读哪个、永久硬规则。
> 具体内容在各子文档里,谁也不抄谁(抄=两处事实=漂移)。

## 这是什么
Auto_review:把论文 PDF 变成可溯源、可重组的综述写作素材底座。
两个模块:`paper_pool`(入库/下载/去重)、`Document_Decomposer`(抽取→关联→出稿)。
当前主战场:`Document_Decomposer` 的连接层与出稿。

## 开工前必读(按序)
1. 本文件(规则)
2. MEMORY.md(自动记忆里已核实的事实)
3. `Document_Decomposer/CONNECTION_PLAN.md`(当前工作:连接层路线+状态)
4. `Document_Decomposer/ISSUES.md`(已知问题——很可能你要碰的坑已登记)

## 文档地图(每个事实只有一个权威处)
| 文件 | 唯一职责 |
|---|---|
| `CLAUDE.md`(本文件) | 导航 + 永久开发规则 |
| `Document_Decomposer/HANDOFF.md` | 项目总览 + 技术路线(给新人/新会话) |
| `Document_Decomposer/CONNECTION_PLAN.md` | 连接层路线 + 建设状态 ← **当前工作的唯一状态源** |
| `Document_Decomposer/ISSUES.md` | 已知问题的**唯一台账** |
| `Document_Decomposer/AI_GUIDE.md` | 单篇抽取管线的详细操作规则 |
| `Document_Decomposer/README.md` | Document_Decomposer 人类向导览 |
| `Document_Decomposer/DOCLING_INSTALL.md` | Docling 环境搭建 |
| `README.md`(根) | 仓库总导览(人类向) |
| 自动记忆 `memory/`(MEMORY.md 索引) | 耐久已核实事实 + 指针 |
| `paper_pool/README.md`、`paper_pool/AI_GUIDE.md` | paper_pool 模块(**当前只登记,不在本轮维护**) |
| `font-fallback-fix/`(非本项目产物) | **不归我们管,不读不改** |

## 何时去读哪个(触发条件)
- 遇到任何问题/异常 → **先翻 `ISSUES.md`**(可能已知,别重复踩)
- 不清楚现状/刚接手 → `HANDOFF.md` → `CONNECTION_PLAN.md`
- 要改抽取管线 / 卡片逻辑 → `AI_GUIDE.md`
- 要 commit / 动 git → 见下「git 规则」
- 要写/改 md 或记忆 → 见下「写改 md」「改记忆」

## 永久硬规则(优先于默认行为)

### 元原则
**代码 + `reports/` 等产物 = 事实。md 和记忆只是「描述」,可能漂移。冲突时信产物,不信文档。**

### 写 / 改 md
- 状态/结果类 claim **必带三样**:证据(哪个文件/命令)+ 方法(怎么验)+ 范围(抽样 N 篇 / 全库)。
- 没有「同一冻结标准下全库重跑过」之前,**禁写**「全部合格/已验证/完成/干净」。不确定一律标 `未核实` / `抽样N篇` / 🔶。
- 改一条曾经写错的事实:**不许静默覆盖**,留一行 `更正:原写X,实为Y(因…)`。
- 状态/结果类 claim **落盘前先在对话里给用户看、点头**。
- 小范围定点改,不大段重写。

### 改记忆(自动记忆 memory/)
- 只存**耐久、已核实**的事实 + 指针;**不冻结易变的「质量有多好」**。
- 区分「能力存在」(可写)与「质量多好」(易变,不写死)。
- 项目状态类记忆**先问用户**;引用/偏好类可直接加;发现错就删/改。

### git
- **只在用户明确说「提交」时才 commit;永不擅自 push。**
- substantial 改动**走分支**,用户 review 再并。
- 进 git:源码 / schema / md。**不进**:`reports/ library/ data/ envs/ *.local.json`。
- commit message **不夸大**:只写做了什么 + 真实状态(不写「完成综述助手」这类)。

### 单一事实源 + 同步
现实变了 → **只改对应的那一个权威文档** → 若是耐久事实,再加一行记忆指针。
**绝不在多处抄同一句话。**

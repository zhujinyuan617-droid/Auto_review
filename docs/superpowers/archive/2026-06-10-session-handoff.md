# 会话交接(2026-06-09 深夜 → 06-10 凌晨;给无上下文的新会话)

> 本文件是**状态快照 + 路由器**,不重抄事实。每个事实的权威出处在括号里。
> 开工前仍按根 CLAUDE.md 的顺序读:CLAUDE.md → MEMORY.md → CONNECTION_PLAN.md → ISSUES.md(尤其 **I18**)。

## 30 秒状态

- 本会话完成两大施工:**要素索引层(SP1+SP2)** 与 **管线换代(SP-Regen)**。代码+测试全部完成:
  引擎测试 **140**、桌面测试 **194**,全绿;fable 全分支终审结论:可交付。
- git:两条**未合并、未 push**的分支,严格线性堆叠:
  `feature/element-index`(29 commits)← `feature/pipeline-regen`(16+ commits,当前分支)。
  合并顺序:element-index → main,再 pipeline-regen → main(或直接合后者,等效)。
- 全库要素构建(用户在统计屏点的按钮)通宵运行,凌晨 02:32 时 190/261,**应已自然完成**——
  新会话先核 `Document_Decomposer/library/*/elements.json` 计数与 `GET /elements/coverage`。
- **数据回填批次一个都没跑**(等用户点头):见「待拍板」§3。跑之前拆解页/词表/卡片标签的质量都不作数(ISSUES I18)。

## 文档地图(本轮新增/修订)

| 文件 | 内容 |
|---|---|
| `docs/superpowers/specs/2026-06-10-data-framework.md` | **数据合同单一事实源**:八类要素/卡片v3/authorship/双注册表/AI 分工 |
| `docs/superpowers/specs/2026-06-10-pipeline-regeneration-design.md` | 换代实施决策(R1–R10) |
| `docs/superpowers/specs/2026-06-09-element-index-design.md` | 要素层原始设计(SP1+SP2,已实现) |
| `docs/superpowers/specs/2026-06-09-map-home-design.md`(**v2**) | 下一个子项目:知识地图首页+导航重组+检索屏v1.1;含全部产品决策记录 |
| `docs/superpowers/plans/2026-06-10-pipeline-regen.md` | 换代实施计划;**末尾 = 运营清单 9 步(命令已逐条核对)** |
| `docs/superpowers/plans/2026-06-09-element-index.md` | 要素层实施计划(已执行完) |
| `Document_Decomposer/ISSUES.md` **I18/I19** | 换代过渡期 + **重建顺序铁律** + 机构归一缺口 |
| `Document_Decomposer/CONNECTION_PLAN.md` | 重建链已更正(词表退役,按 I18 顺序) |

## 工作区精确状态(新会话必核)

- **4 个"有意未提交"文件**(内容是干净完整的,等用户过目后提交):
  `Document_Decomposer/HANDOFF.md`、`Document_Decomposer/scripts/README.md`、
  `desktop_app/frontend/index.html`、`desktop_app/frontend/styles.css`。
  ⚠ 它们经历过两次被子代理误删又被主会话重建——**别再让任何 agent 碰 git 恢复类命令**(见安全规则)。
- 用户自己的未跟踪目录(writing/、scripts/write|manuscript|figures|portfolio、prompts/、graph.js、vendor/ 等)= 用户资产,不碰。
- `font-fallback-fix/` 按根 CLAUDE.md:不读不改。

## 待用户拍板(按优先级;新会话开场先问这些)

1. **装 hookify 拦截**(PreToolUse 封 `git checkout -- / restore / stash / reset / clean / add -A`):
   两次事故的根治方案,用户尚未点头。
2. **分支合并**:顺序如上;合并由用户 review 后决定(仓库铁律)。
3. **运营清单 9 步**(plans/2026-06-10-pipeline-regen.md 末尾):finding 补抽(约 ¥50/1h 并行)→
   card_tags 回填(免费)→ topic 导入/解析 → 词表派生 → 机构拉取(OpenAlex)→ 连接层重建 → 抽样审计登记 ISSUES。
   **必须按序**(I18 铁律);跑完 261 篇才是完整新架构形态。
4. 四个混合文件的提交(见上)。
5. **地图 spec v2 审阅** → 下一个子项目(走老流程:writing-plans → 子代理执行;管线已为它铺平)。
6. 次要悬案:flash 抽取质量是否升 pro(等抽样审计)、第一次事故丢失文件要不要 pyc 反编译抢救
   (`interactive_assistant.pyc` 06-07 版本仍在)、个人层小 SP(已读/星标/批注)排期。

## 安全规则(血泪,两次事故)

- **每一个**子代理提示词(实现者、审查者、探索者,无一例外)必须带:
  `NEVER git checkout/restore/stash/reset/clean/add -A;NEVER push`;
  审查历史版本只许 `git show <sha>:<path>`,**绝不 checkout 旧 commit**。
- 引擎测试一律 tmp_path 假库;真库 `library/` 与 `data/elements/` 是生产数据。
- 注册表**绝不重新归并**(一次性冻结);`run_bootstrap` 再点 = 增量补漏,这是设计好的。
- 详见持久记忆 [[subagent-git-safety]] 与 [[delegate-cheap-ops-to-sonnet]]。

## 常用命令

```powershell
# 测试
cd Document_Decomposer ; ..\desktop_app\.venv\Scripts\python -m pytest tests -q   # 140
cd desktop_app ; .venv\Scripts\python -m pytest -q                                 # 194
# 浏览器预览(端口 8000;桌面窗口形态 = python -m autoreview_app.main)
cd desktop_app ; .venv\Scripts\python _serve_fixed.py
# 构建覆盖率
curl http://127.0.0.1:8000/elements/coverage
```

## 本会话的产品决策史(找"为什么"去这里)

头脑风暴全程结论已固化在三处:地图 spec v2 的 §0/决策记录(产品观:库是会生长的地图;可切换镜头;
机构层;检索屏联动计数)、数据框架 §3(一岗一认知的 AI 分工)、换代 spec §1(淘汰/瘦身/不合并的判决)。
试点与全库构建的质量数字在本分支 desktop README 状态段与 ISSUES I18。

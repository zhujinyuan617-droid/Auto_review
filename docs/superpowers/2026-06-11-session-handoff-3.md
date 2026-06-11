# 会话交接 #3(2026-06-11;给无上下文的新会话)

> 状态快照 + 路由器,不重抄事实;权威出处在括号里。开工前按根 CLAUDE.md 顺序读:
> CLAUDE.md → MEMORY.md → 本文件 → ISSUES.md。交接 #2(2026-06-10)已被本文件取代。

## 30 秒状态

- **git**:`main` = origin/main = **41ebdac**,工作区干净(只剩惯常未跟踪文件)。
  2026-06-10 晚 ~ 06-11 共推送 19 笔,全部用户验收后逐批下令 push。
- **测试**:引擎 **164** / 桌面 **277** 全绿(命令见文末)。
- **服务器**:`desktop_app/_serve_fixed.py`(8000 端口)跑 main 最新代码;**改后端必须重启**;
  全站响应已带 no-cache(改前端用户普通刷新即见)。**全机只许一个服务器进程**——
  曾因双进程打架让用户"改了看不见"(怀疑先查 `netstat -ano | findstr :8000`)。
- **库**:260 篇(误入库的医学论文 S152 已移至 `Document_Decomposer/_removed/`,可恢复)。

## 本轮做完的(已 push;细节看各 commit message,质量口径看 ISSUES)

1. **Wave-3 五项**(f1e0d14/4133b0e/93384ad/7bd70d9/b838a8f):径向布局(权重向心+区内年轮)、
   撤并统计与图墙两屏、拆解页(PDF/原文锚点/condition/来源徽标)、机构五大洲、检索屏+送写作。
2. **标题优先**(9d1343a/577bdf9):前台一律论文标题,S 号退后台;论文卡按"人读顺序"重写。
3. **体验四连**(bb96816/45798a5/27af13e):区面板瘦身(≥2 篇共性)、详情页作者/机构/DOI 上屏、
   列表排序+综述徽标、图表过滤出版社杂项+真图注(抽样 86% 覆盖)。
4. **机构镜头两级**(fa1a8fa…9e6c70f):论文→机构→洲;机构团子轮廓/悬停/点击面板/缩放标签;
   课题组屏并入机构面板(ea76659)。
5. **分区算法 v4.3**(e967178/24d17a9/c77ec0c/6d572a5/745a97f):灰点拆"待构建/无此类要素";
   方法镜头补 characterization+analysis 两类;大路货孤点补弱边;容量自适应≈N/4(四五个大主题);
   单篇并入满员区给 5% 余量。方法镜头零散残留 ~10 篇 = 已接受的边际。
6. **作者机构兜底链**(e040c6c/2bc1100):一次性 PDF-AI 回填(14/15,机构缺失 15→3)+
   **长效**:卡片 AI 顺手抽 `authors_raw`,导入链自动落 authorship(OpenAlex 有 DOI 仍为准);
   抽样 5/5 全对,但 pdf-ai/card-ai 来源**未全量人工审核**。
7. **词条展示重设计**(fbf7226,260 篇全库统计背书):五类不合并、同要素去重、行折叠 6、
   条件值智能追加、超长截断。根因记 **ISSUES I23**(抽取侧同篇重复 + 34 条 facet 错挂)。
8. **同病三连修**(41ebdac):检索树 43 个 `proposed:*` 碎组折叠成一行;写作"张力"角度
   去 S 号 + 点击填共享概念;`facetLabel()`(ui.js)中文标签五处统一。

## 排队事项(均未动工)

- **双语版面 = 下一大批次**(用户拍板,设计锁定在 map spec **§11**:设置切换 zh/en、
  全部界面文案进词典、AI 区名/描述双语、要素英文名不翻译)。
- 小件:AI 机构一句话描述(用户提过一次);simulation 内部再分层(软件/力场/系综,需词表或 AI);
  I23 根治(抽取侧);S83/S328/S337 机构数据边界(首页版面抽不出,属数据边界)。
- 旧积压 P1/P2/P3 见交接 #2 §积压(仍有效:提速包、断头路、成稿流水线按钮化等)。

## 接手必知的坑(新增的在前,旧的照抄仍有效)

- **新**:机构注册表混有三种来源(openalex-search / pdf-ai / card-ai / pdf-affiliation-text 标注在
  country_source/origin 字段),错配风险未审计(ISSUES I22);人工 merge 机构后无需重跑派生链
  (机构不在 I18 链上),但**地图机构镜头缓存按注册表国别指纹自动失效**。
- **新**:`proposed:*` 43 组是数据治理欠账(I21 系列),前端只是折叠,没治本。
- card 阶段重跑会抹机制补标(必须接 enrich+card_tags);注册表写路径必须持 registry_locks;
  派生链铁律 = ISSUES I18;子代理提示词必须带破坏性 git 硬禁;
  push 由 hookify 拦,用户明说才临时关→推→**立刻恢复 enabled:true**。
- 模型分配:按需分级(机械=sonnet/评审=opus/难判断=fable),质量优先。
- 对用户讲话:老师式(CLAUDE.md 风格节);先大白话结论;一次一件事;**别拍脑袋——
  用户两次纠正"不要片面",方案要全库统计/多篇抽样背书**。

## 文档地图

- 活文档:`specs/2026-06-09-map-home-design.md`(§10 Wave-3 决策、**§11 双语决策**)、
  `plans/2026-06-10-map-home.md`(尾部 Wave-3 实施记录)、`specs/2026-06-10-data-framework.md`。
- 台账:ISSUES **I18(派生链)/I22(机构国别口径)/I23(要素显示噪声根因)** 最新。
- 历史:`docs/superpowers/archive/`;交接 #2(同目录)已过时,只作当时记录。
- 桌面现状唯一源:`desktop_app/README.md`(注:其 Wave-3 小节之后的 8 批改动以 git log 为准,
  README 尚未补写——接手后若要更新,走"用户过目后落盘"规矩)。

## 常用命令

```powershell
cd Document_Decomposer ; ..\desktop_app\.venv\Scripts\python -m pytest tests -q   # 164
cd desktop_app ; .venv\Scripts\python -m pytest -q                                 # 277
cd desktop_app ; .venv\Scripts\python _serve_fixed.py                              # 服务器(改后端后重启)
```

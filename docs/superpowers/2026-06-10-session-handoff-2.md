# 会话交接 #2(2026-06-10 全天;给无上下文的新会话)

> 状态快照 + 路由器,不重抄事实;权威出处在括号里。开工前按根 CLAUDE.md 顺序读:
> CLAUDE.md → MEMORY.md → 本文件 → ISSUES.md。上一份交接(凌晨版)已归档,勿再读作现状。

## 30 秒状态

- **git**:`main` 已推 GitHub(含三轮施工:要素层+换代+提速,全部合并)。当前分支
  **`feature/map-home`(未合并、未 push,约 20 commits,HEAD=2d3bf3c)**:
  知识地图首页全量(Wave1 首发 + Wave2 十项 + 聚类质量 v3)+ P0 七雷修复 + opus 评审
  Critical 修复 + 标签质量(发现主角保席/种子平票/机制补标)+ 主题检索 bug 修复 + 文档归档。
- **测试**:引擎 **164** / 桌面 **258** 全绿(各自 `..\desktop_app\.venv\Scripts\python -m pytest`)。
- **服务器**:`_serve_fixed.py` 跑本分支代码(端口 8000,后台任务);改后端必须重启才生效。
- **数据**:261 篇全量就位;+529 机制标签已灌入(主题镜头 25 区/最大 30/零散 4);
  注册表派生链经新鲜度门禁验证全新鲜(`scripts/audit/check_derived_freshness.py`)。

## 已批未做:Wave-3(用户逐项拍板,本文件是唯一完整记录)

1. **2D 布局升级**(最优先,做完用户刷新即见):
   - 权重向心:大区放画布中心、小区放外环(确定性径向排布,替换现 spread_clusters 的均匀推开);
   - **区内按年份排成年轮/弧**(老内新外)→ 据此**退役时间镜头**;"要素首现"挪进区面板(API 已有);
   - 灰点(未构建要素)收进最外圈"待构建"弧区 + 按钮一键增量构建(POST /elements/bootstrap 现成)。
2. **撤并两屏**:全库统计屏撤销(总览并入地图区面板、共现抽屉并入检索屏、构建按钮挪到待构建弧区;
   后端接口保留);图表墙屏撤销(缩略图进地图论文卡前 3 张 + 论文详情页完整画廊;API 保留)。
3. **拆解页**:加 `GET /papers/{id}/pdf`(source.pdf 每篇都在)+ 详情/拆解页按钮;
   **"原文段↗"锚点兑现**(现在是假承诺:不渲染不滚动,见五屏体检);condition 要素上屏;
   素材来源(elements/legacy)诚实标注。
4. **机构五大洲镜头**:先跑一次性国别补查(243 家机构 → OpenAlex institutions,几分钟),
   再按洲分区布点。
5. **检索屏**:观感重做 + 命中集"一键送写作"(写作屏 paper_ids 现成,DraftSelection 已有)。

## 积压(已审计、带证据、待排期;证据在六份审读报告,结论已大半进 ISSUES)

- **P1 提速**:单篇导入判同换 bulk 短名单(整 facet 1360 条进提示词 → 8 条);
  reindex/build_index 三处"每读重建世界"换文件指纹;抽取链四刀(单篇 -40~50%);
  写作链并行化(2.1h → ~30min);边判缓存键加内容哈希。
- **P2 互通**:九条断头路(五屏体检报告的总表);详情页补作者机构/要素 chips/DOI 链接。
- **P3 整备**:厚卡 ~900 行死代码下架;funnel 旧链降级归档;每阶段模型选择接线;
  写作链去领域硬编码(换库通用化);M3 下载链接线(顺带导入 sha256 查重);
  桌面按钮化 v2 成稿流水线(建议立为下一个 SP)。

## 接手必知的坑(血泪,按新近排序)

- **card 阶段重跑会抹掉机制补标与派生标签**(opus 评审 I-1):重跑 card 后必须接
  `ai_enrich_topic_tags.py` + card_tags 回填(脚本尾部有 DEPENDENCY 提示)。
- **注册表写路径必须持锁**:`registry_locks.py` 两把锁(elements/institutions),
  新写路径先拿锁;曾因漏锁丢数据两次(凌晨竞态 + opus C1)。
- **派生链顺序铁律 = ISSUES I18**;机械门禁 `check_derived_freshness.py`(只管 registry 之后的纯派生段)。
- 方法镜头剩一个 **69 篇 "Materials Studio 生态系"密核**,锚分组也拆不动,已接受为已知边界。
- 子代理提示词必须带破坏性 git 硬禁(hookify 已在拦截:checkout/restore/stash/reset/clean/add -A/push)。
- 模型分配(用户最新指示):**按需分级**——机械=sonnet、评审=opus、难判断=fable;质量优先,评审不省。
- 对用户讲话:老师式(CLAUDE.md 风格节);不对用户个人时间指手画脚;一次只推进一件事。

## 文档地图(2026-06-10 归档后)

- 活文档:`specs/2026-06-10-data-framework.md`(数据合同)、`specs/2026-06-09-map-home-design.md` +
  `plans/2026-06-10-map-home.md`(进行中,含 Wave2 决策;**Wave3 决策在本文件 §已批未做**,
  动工时先并入 spec)。
- 历史:`docs/superpowers/archive/`(24 份,带索引 README,"当时状态勿当现状")。
- 台账:ISSUES **I18(已跑完)/I19(机构)/I20(finding 压缩)/I21(注册表伞桶)** 为最新。

## 待用户拍板

- `feature/map-home` → main 的合并(用户 review;两侧套件已绿);合并后 push 由用户决定。
- Wave-3 做完后的下一个 SP 方向(候选:桌面按钮化成稿流水线 / P1 提速包)。

## 常用命令

```powershell
# 测试
cd Document_Decomposer ; ..\desktop_app\.venv\Scripts\python -m pytest tests -q   # 164
cd desktop_app ; .venv\Scripts\python -m pytest -q                                 # 258
# 服务器(改后端后必须重启)
cd desktop_app ; .venv\Scripts\python _serve_fixed.py
# 派生链新鲜度门禁
cd Document_Decomposer ; ..\desktop_app\.venv\Scripts\python scripts\audit\check_derived_freshness.py
```

# 提速小 SP:批量判同 + 管线时延压缩 设计(SP-Speed)

- 日期:2026-06-10 凌晨;状态:**已实现(代码+测试绿:引擎 152 / 桌面 204;commit f59cad1…531d7c2)**;
  真库验收数字待回填(§6;计划 Task 8)
- 缘起(用户原话):「我们要尽可能加快每个环节,用户的耐心有限。要是它一口气放五十个论文进来……要搞五个小时,我想用户已经换软件了」「我们先做能提高效率的事情」
- 单一事实源:要素/注册表 schema 见 `2026-06-10-data-framework.md`;并发上限事实见持久记忆
  `batch-pipeline-perf`(DeepSeek 账号级:flash 2500 / pro 500,2026-06-10 用户提供)
- 排期:**本 SP 在地图首页(SP-Map)之前**;地图的"丢新文献"体验踩在本 SP 之上

## 0. 目标与指标

两个时钟:
- **完成时钟**:50 篇从导入到深加工全毕。目标:5 小时级 → **10 分钟级**(本 SP);
  快模型换档(范围外)再压到 ~5 分钟。
- **感知时钟**(地图 SP 负责,本 SP 铺数据基础):首个可见结果 < 1 分钟。

## 1. 现状与瓶颈(2026-06-10 实测,261 篇全库)

| 环节 | 实测 | 根因 |
|---|---|---|
| 要素抽取 23:10→03:49 | ~4.5 h | 每篇链 ~6 min × 并行 6 路排队(并行设置页已于今晚建成,默认拉满) |
| 归一串行尾巴 | ~2 h | **逐篇**一次 AI 判同(~30 s/篇)× 261 篇纯排队 ← 本 SP 主攻 |
| finding 补抽(对照) | 10 min | 同 6 路但调用轻——证明瓶颈 = 单次调用时长 × 排队深度 |

另:两个归一进程并发会竞态改注册表(今晚实际发生,已止损)——本 SP 不改"串行落账"
的单写入者纪律,只把"等 AI"挪出串行段。

## 2. 方案:批量判同(提案并行、落账串行)

新引擎能力 `bulk_match_elements(library_dir, registry, client, log_path, parallel)`,四阶段:

1. **收集(纯脚本)**:遍历目标论文的 `elements.json`,凡 occurrence 的 surface 经
   exact/alias 查表不可解析者,按 `(facet, norm_key)` 去重,汇成全局生面孔清单。
2. **配候选(纯脚本)**:每个生面孔配同 facet 的注册表候选短名单(token 重叠/前缀等
   廉价启发式,上限 ~8 条)。不把整本注册表塞给 AI(防看串、防大杂烩桶)。
3. **判同(AI,并行)**:生面孔分块(每块 ~30 个,附各自候选)发 DeepSeek:
   只许「match 候选之一 / create」二选一(沿用现有 streaming match 的提示词纪律,
   宁可新建不硬塞)。只读不写,ThreadPool,并行数由调用方传入(来设置页档位)。
4. **落账(纯脚本,串行)**:按确定顺序应用判决——create_entry(沿用 -2 后缀防撞)、
   add_alias、回写各篇 canonical_id、append 日志、**save_registry 一次**、重建索引。

幂等:重跑收敛(已解析的不再上 AI);防大桶纪律不变(audit_element_buckets 仍兜底)。

### 实现要求(DRY)
- 优先**重构复用** `element_matching.py` 现有内部件(exact/alias 查表、批判同提示词、
  create-not-force),抽出 `_resolve_batch(surfaces_with_candidates, client)` 共用;
  禁止复制粘贴出第二份判同逻辑。现有测试保护重构。
- streaming(单篇)路径保留不动:单篇导入本来就是一篇一小批,无需换。

## 3. 集成点与文件清单

| 落点 | 改动 |
|---|---|
| `Document_Decomposer/src/docdecomp/element_matching.py` | 重构出共用件 + 新增 bulk_match_elements |
| `Document_Decomposer/scripts/elements/backfill_findings.py` | Phase B 由逐篇循环改调 bulk(行为开关:`--match-mode bulk|stream`,默认 bulk) |
| `desktop_app/src/autoreview_app/elements/service.py` | run_bootstrap 串行尾巴改调 bulk;判同并行数取设置页档位(parallel_for_model);"串行落账"注释保留 |
| `Document_Decomposer/tests/` + `desktop_app/tests/` | 见 §5 |

## 4. 安全与不变量

- **单写入者不变**:阶段 4 仍是唯一注册表写入点,且进程内串行;两个归一进程并发仍属禁止
  (今晚竞态的教训另登记 ISSUES:启动写入者前确认前任务真正退出)。
- AI 只能在"给定候选"里选或 create;不许自由发明 merge(防大桶)。
- 引文核真闸门不在本 SP 范围内,不碰。

## 5. 测试清单(全部 tmp_path 假库)

引擎:
1. 收集:跨 3 篇假库,canonical_id 空且查表不中者被去重收集(同 surface 两篇只出现一次)。
2. 配候选:同 facet 才入选;上限截断;无候选 → 候选空表(仍可判 create)。
3. 判同分块:30/块;假 client 断言收到候选;返回 match → 加 alias 并回写两篇 canonical_id。
4. create 路径:AI 答 create 或不识 → 新条目 + 回写;重跑幂等(第二次零新建)。
5. 落账原子性:save_registry 仅调用一次;日志行含 facet 与 source=bulk-match。
6. backfill --match-mode stream 仍走旧路(回归保护)。
桌面:
7. run_bootstrap 尾巴调 bulk 且并行数 = 设置页 flash 档(monkeypatch 断言)。
8. 设置页档位变更 → 下次 bootstrap 生效(复用今晚 test_parallel_settings 模式)。

## 6. 验收(真库,跑完后报数字,不写"合格")

- 对 261 篇真库重跑 backfill(bulk 模式):报「判同 AI 调用次数、并行数、墙上耗时」,
  与今晚 stream 模式的 ~2 h 对照;目标量级:**分钟级**(估 1–3 min,待实测)。
- audit_element_buckets 跑一遍,超限桶数不高于 stream 基线。

**实测(2026-06-10 05:27–05:30,261 篇真库,--parallel 64)**:
- 墙上 **3.2 分钟**(含 Phase A 重抽 261 篇 finding + Phase B bulk 归一 + 索引重建);
  归一段本身约 1 分钟,对照 stream 串行尾巴实测 ~2 小时(28–40 s/篇)。
- bulk match: groups=4573, ai_calls=**154**, resolved_ai=625, created=4049,
  failed_chunks=0, papers_written=260;`done: 261 ok, 0 failed`。
- 自愈核查:全库 occurrences=8688,canonical_id **null=0、悬空=0**(注册表 4937 条)——
  当晚两次中断(补抽进程被杀、桌面尾巴被杀)残局一次收清。
- 大桶审计:6 条超限(shale 22 / NMR 18 / MD 16 / ML 15 / coal 14 / MC 14),
  均为真高频概念,待步骤 9 人工复核;无 stream 完整基线可比(stream 从未跑完过全库)。

## 7. 范围外(另立项)

- **快模型换档**(分章节/阅读块换非推理模型):最大单点杠杆,但需质量抽样对比,单独走。
- **增量索引**:先实测全量重建耗时,>10 s 才立项(261 篇 ~万行,预计秒级,大概率 YAGNI)。
- 设置页并行数接到"关联边重建"等更多入口:归地图 SP(那时才有对应按钮)。
- 感知层(渐进点亮/着陆卡):地图 SP。

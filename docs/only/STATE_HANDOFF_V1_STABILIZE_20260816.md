# 压缩交接 — 第一版稳定化：全量 2068 绿 + 内存/挂起根治 + 学习闭环持久化 + 孤儿糅合 + trace_id 传播（2026-08-16）

> 状态: 压缩恢复唯一入口（本轮）
> 前置: docs/only/STATE_HANDOFF_SELFREPAIR_20260816.md
> 恢复三步: 读本文档 → 读 RECOVERY_PLAN（顶部已指向）→ 读 AGENTS.md +
>  追踪矩阵 + 关键设计文档（§六）
> 环境: 8000（.venv API, 本轮代码）+ 8080（网关）+ 4173（前端, 用户
>  正在改 UI）在跑; 全量 pytest 5min 内可复跑

## 〇、本轮主线

1. **接线核查**（用户"现在基本功能都接线无误了吗?"）→ 代码探针挖出真缺口:
   LEARNED_TEMPLATES 无持久化（学到即丢）/ 孤儿组件 7+ 处 / trace_id 传播断 /
   response.intent 恒 chat
2. **全量运行崩溃**（用户观察到 15GB 被系统杀）→ 参数级定位: 非单例模型
   ×8（每 engine +2~3GB）+ stanza 联网挂起 ×6 + HF hub 联网 ×4 + pytest-asyncio
   缺失（54 个 async 测试从未真跑）
3. **先做第一版自洽**（用户"先把后端尽可能自洽, 先做完第一版"）→ 本轮
   补完学习闭环持久化 + 二阶抽象测试, 全量稳定到 2068 绿 / 4:21 / 峰值 3.3GB

## 一、本轮完成（全部实测）

### 1. 全量运行根治（核心基建, 参数量化见 FULL_RUN_QUANT）
- 内存: 8 处直接 `SemanticEncoder()` → 统一 `get_encoder()` 单例
  （4 engine 峰值 9.7GB→4.0GB; 全量 15GB OOM → 3.3GB）
- 挂起: stanza.download ×6（pcr_router_v2/literal_chain/pronoun_resolver/
  grammar_tagger/tiered_stanza_parser）+ HF hub ×4（topic_tree/semantic_coref/
  bge_embedder/behavior_embedding）→ download_method=None / local_files_only
  + conftest 全局离线
- pytest-asyncio 装入 .venv（54 个 async 测试补齐）; faulthandler_timeout
  40→180（容忍慢 LLM）; test_linkage_quality_v2 标 slow
- 终态: **2068 passed / 25 skipped / 0 failed / 4:21 / 峰值 3.3GB**

### 2. 学习闭环持久化（第一版"自增长"卖点最后一块）
- BlueprintDAG.to_dict/from_dict + LEARNED_TEMPLATES 落盘
  data/learned_templates.json（DM_LEARNED_TEMPLATES_PATH 可覆盖; 导入恢复
  + learn 后原子写盘 + lifecycle 裁剪同步）
- 修 bug: 恢复时 `=` 重绑全局 → 外部引用失效 → 改原地 clear+update
- 二阶抽象测试 6 项（DAG round-trip / learn→落盘→重启→match 命中 / 无
  tool 不学 / A24 coverage 三档 0.6/0.4/1.0）

### 3. 召回/元认知（接上次压缩后 P1/P2-①）
- 经验 RAG（P2-①）: 语义+关键词混合, sidecar 持久化, 0.45 语义下限
  （全量实测 0.15 过松导致无关召回）
- P1-① 主动体检 / P1-② 预热+预算 / P1-③ LLM 凝练（均上轮完成, 本轮实测）

### 4. 孤儿组件糅合（"能接的接, 该归档的明确归档"）
- 接线: suggest_blueprints（GAP-D3）→ /v6/blueprint/suggestions
- 归档标注 7 处: HybridSearchEngine/WaveQueryEngine/AuditTrail/WriteAheadLog/
  SandboxExecutor + executor 占位与 P2 项（不删码 A17）
- 裁决记录: docs/only/ORPHAN_RULING_20260816.md

### 5. trace_id 传播（§11.2）+ response.intent 修复
- send_message 入口 set_trace_context + task_runner 执行线程 + planning
  to_thread 显式透传（thread-local 不跨线程!）+ call_recorder 自动附加
- 端到端实测: 同请求 intent_classify/planning/tool_loop 全链同一 trace_id
- SendMessageResponse.intent 恒 "chat"（分类器正确, 响应层漏传）→ 实测
  写代码请求 intent=代码分析

## 二、提交线（均本地, 未推 GitHub）

```
40e1f3e 孤儿糅合 + trace_id + intent 修复（2068 绿）
4e09cd8 学习持久化 + 二阶抽象测试 + 全量量化记录
9b5884b stanza 第六处 + HF 离线 + RAG 阈值 + pytest-asyncio（2063 绿）
e8bf120 stanza ×4 + BGE 单例 ×8（内存根因）
087f71b 经验向量回填 + 测试隔离
8064b67 经验 RAG + README 元认知/高可用
f78a86f P1-③ LLM 凝练
5a96772 P1-② 预热 + 预算
99e6b0e P1-① 主动体检
```

工作树: 前端改动（用户并行, omnibox/P1c-P1d）未暂存未提交。

## 三、本轮经验（重点, 防重蹈）

1. **"测试绿 ≠ 生产通", "全量跑不过 ≠ 代码错"** —— 先做基建核查再改业务:
   内存/挂起问题用**参数级探针**（内存采样 + faulthandler 线程转储）定位,
   不猜。本轮的 15GB OOM 与 40s 杀进程, 单看业务代码永远找不到。
2. **模型单例纪律**: `SemanticEncoder()` ≠ `get_encoder()`。凡"重模型"必须
   走全局单例; 注册/定义新组件时同步检查是否重复加载模型。
3. **联网加载一律离线优先**: stanza.download / SentenceTransformer /
   from_pretrained 在受限网络会**无超时挂起**（requests/httpx 默认无超时）。
   统一 download_method=None / local_files_only / HF_HUB_OFFLINE。
4. **thread-local 不跨线程**: asyncio.to_thread / ThreadPoolExecutor 里
   trace/context 不继承 —— 跨线程必须显式透传（planning 落默认 uuid 即此）。
5. **模块级可变全局**: `from ... import LEARNED_TEMPLATES` 拿的是引用;
   函数内重绑全局会让外部引用失效（= 重绑 vs 原地 clear+update）。
6. **响应字段默认值陷阱**: SendMessageResponse.intent 默认 "chat" 且 return
   漏传 → 前端看到的永远默认值。改响应模型/构造时检查"默认值是否被真实值
   覆盖"。
7. **pytest 基建**: --strict-markers 下未装 pytest-asyncio 会让 async 测试
   收集即 ERROR（静默消失）; 全量"绿"可能是没跑到。装齐插件 + 定期全量。
8. **测试隔离**: 任何写生产 data/ 的测试必须隔离（经验库/学习模板都踩过
   污染）; fixture 模式: 存全局→清→跑→恢复 + 路径 env 重定向。

## 四、待办（优先级 + 开工设计要点）

### P0 下一批（用户已排, 需设计讨论后开工）
1. **跨域召回 25% 提升**: 评测驱动（DOC_RECALL_BENCH）, 建议先复跑 eval_100
   拿 doc 类 miss 明细, 再做消融（切分/索引/融合权重）。基线上轮已定
   （doc top1 31.1% / dialogue 69.2%）。
2. **贝叶斯概率加权（A13 数值化）**: 设计要点 —— prior = 经验库历史命中率
   （verify_passed 比例）, likelihood = 本次诊断建议与既往相似度的置信度;
   P = prior + (1-prior)×likelihood 进 diagnosis 的 confidence; 需拍板
   prior/likelihood 来源与更新时机。
3. **约束空间化（A12 合法/可达/禁止）**: 大设计, 先出设计文档 —— 约束从
   文本摘要（_design_constraints）变结构化 {allowed/reachable/forbidden},
   注入点: 诊断 prompt / 规划约束 / 执行层 TaskConstraint; 与追踪矩阵
   A12 行联动。

### P1
4. **前端绑定**（用户 UI 改完后）: /v6/governor /v6/diagnosis /v6/repairs
   /v6/system-profile /v6/warmup /v6/probe /v6/blueprint/suggestions /
   v6/llm-calls（trace_id 已可展示）
5. **经验库存量清理**: data/self_repairs.jsonl 有 10 条历史测试残留
   （"测试修复", 已防新增）; 用户拍板后清。

### P2（记录, 不排期）
- 统一审计聚合视图（AuditTrail 重启用）/ WAL 分布式阶段 / 来源可信度学习
  （GAP-D4）/ 跨域联邦 / 七树 CRUD 编辑

## 五、环境坑（续用）

- 8000 必须 .venv 起（anaconda torch 死锁）; 沙箱无出网 → 网关需提权/start.bat
- PowerShell 管道 GBK 乱码 → 中文脚本写 UTF-8 文件执行
- 全量跑: `python -m pytest core/agent -q --tb=short -p no:cacheprovider`
  （~5min, 默认排除 slow）
- ctypes GetProcessMemoryInfo 本机返回 0 → 内存采样用外部 PowerShell
  Get-Process -Id <pid>.WorkingSet64
- 重启 API 后首请求若慢: 先 GET /v6/health + 等 warmup（v6/warmup 可查）

## 六、关键文档

- docs/only/test/FULL_RUN_QUANT_20260816.md（全量运行量化记录）
- docs/only/blueprint/LEARNED_PERSISTENCE_20260816.md（学习闭环持久化）
- docs/only/ORPHAN_RULING_20260816.md（孤儿组件裁决）
- docs/only/wise/PARADIGM_TRACEABILITY.md（A13/A16 行已更新）
- 上轮: execution/HA_EXECUTION_ANALYSIS / EXECUTION_GOVERNOR_DESIGN /
  ASYNC_DIAGNOSIS_DESIGN / SELF_REPAIR_DESIGN / PROACTIVE_PROBE_IMPL /
  WARMUP_BUDGET_IMPL（均在 docs/only/execution/）

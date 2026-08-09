# 外围服务域盘点 — orchestrator / coordinator / observation / memory / learning / world / frontend / task / user / security / document

> 日期: 2026-08-03 | 触发: 用户核查新增「未归入代码域」清单（GLOBAL_AUDIT_PLAN §B P2 可选）。
> 方法: 目录盘点 + 全库 rg 消费矩阵 + 关联既有审计结论。
> 定位: **第一轮盘点级**（消费矩阵 + 一句话结论），非深读。按"与施工相关性"分级，
> 深读建议见 §五。

---

## 〇、总览（11 域，体量实测）

| 域 | 体量 | 活跃度（消费方）| 一句话结论 |
|---|---|---|---|
| orchestrator/ | 141.4KB/9f | 🔴 活跃（A 路径宿主）| 双宿主并存（agent_native v6 + Orchestrator v3），v6 是主路径；已部分审计 |
| coordinator/ | 91.3KB/7f | 🟢 活跃（discourse_manager 消费 5 处）| bayesian/mode_router/multi_tier_llm 被 context_manager 深度消费 |
| observation/ | 56.7KB/23f | 🟢 活跃（document→pool + behavior/adapter + cli）| 观察编译器真接线：DocumentPipeline.put→ObservationPool |
| memory/ | 44.8KB/6f | 🔴 孤儿（全库 0 import）| xml_cards/federated_index/ragraph 全零引用——确认孤儿 |
| learning/ | 52.7KB/8f | 🟢 活跃（blueprint/llm_dag_builder + meta_feedback + cli）| 学习管线真接线（内容抓取/可信度/入库）|
| world/ | 42.7KB/9f | 🟢 活跃（adapter/code + v4/world 门面 + context/source）| 世界模型完整实现（TRACEABILITY "42L stub" 已过时确认）；compiler 被 context 消费 |
| frontend/ | 85.5KB/8f | 🟢 活跃（service/ 层真消费）| 澄清 FSM/多模态/WS 事件被 agent_service/async 消费 |
| task_engine/ | 42.8KB/4f | 🟢 活跃（discourse_manager:74-154）| TaskManager 在 context_manager 路径真实例化 |
| user_engine/ | 52.7KB/5f | 🟢 活跃（discourse_manager + context_layer）| UserManager/Extractor 真接线（画像审计已触及）|
| security/ | 28.9KB/7f | 🟡 半活跃（fact_store + v3_0 门面）| input_sanitizer 被画像消费；bias/hallucination 仅 v3_0 门面 |
| document/ | 52.0KB/7f | 🟢 活跃（chunking + cli/main + observation adapter）| 文档→观察管线真接线 |

> 修正两处用户清单：① memory/ 确认为孤儿（全库 0 import，实锤）；② world/ 与
> observation/ 的 TRACEABILITY "闲置/42L stub" 说法均已过时——两者都活跃。

---

## 一、orchestrator/（141.4KB/9f）— 双宿主，A 路径核心

```
agent_native.py 16.9KB   v6 AgentOrchestrator（A 路径宿主，本批已审计: process/process_dag/9 阶段）
bootstrap_v6.py 8.1KB    v6 装配（已审计: Execution/Cognition/Feedback 等 10 组件加载）
orchestrator.py 45.0KB   v3 Orchestrator（v3_0 门面导出，planner/models 断链时连带炸——规划审计 P0）
algorithm_engine 14.7KB  v3 算法引擎（PCR/Intent 并行）
fusion_engine.py 14.2KB  融合（tiered/fusion + v3_2 复用）
hybrid_engine.py 8.4KB   算法+LLM 并行（v3）
bootstrap.py 22.0KB      SystemBootstrap（v3_0 门面，未深审）
models.py 11.8KB         v3 模型（SystemContainer）
```

### 消费矩阵
```
v6 路径:  api/chat_api.py:31 + api/v6_app.py:269 → bootstrap_v6.bootstrap（真接线）
v3 路径:  v3_0/orchestrator/__init__ 门面导出（Orchestrator/AlgorithmEngine/FusionEngine/
          HybridEngine/SystemBootstrap）→ v3_0 活跃度待定（规划审计已点 orchestrator v3 连带炸）
```

---

## 二、coordinator/（91.3KB/7f）— context_manager 的决策/路由大脑

```
adaptive_threshold.py 17.3KB  ThresholdProfile（discourse_manager:411/546 + user_profile:130）
bayesian_engine.py 20.8KB     BayesianEngine（用户画像/意图多源融合，消费 UserExtractor 输出）
complexity_evaluator.py 9.9KB ComplexityEvaluator（consistency_checker 真消费）
mode_router.py 7.7KB          ModeRouter/ProcessingMode（discourse_manager:59-118 真实例化）
multi_tier_llm_client.py 19.1KB invoke_llm（discourse_manager 3 处真调用）
small_model_client.py 15.3KB  get_small_model_client（discourse_manager/user_extractor/task_detector）
```

### 结论
- **不是孤儿**：被 context_manager（discourse_manager 5 处）、user_engine（3 处）、
  task_engine（1 处）真消费 → 归并上下文审计补充（GLOBAL_AUDIT_PLAN §B 判断成立）。
- 深读建议：multi_tier_llm_client（19.1KB，LLM 分层调用）与 bayesian_engine（20.8KB）
  是 context_manager 路径的关键组件，施工上下文时需精读。

---

## 三、observation/（56.7KB/23f）— 真接线（TRACEABILITY 已过时）

```
消费链（实锤）:
  document/pipeline.py:141-145 → pool.put(obs_bundle)     文档→观察
  behavior/adapter.py:19       → ObservationBundle         行为消费观察
  cli/main.py:49-59            → ObservationPool            CLI 挂载
  cli/registry.py:290          → 注册 observation_pool
  context/graph_source + source:145 → 观察检索
  20 文件 = 5 域适配器（behavior/dialogue/document/engineering/memory/user）
           + 5 解释器 + tiered_relation_extractor + pool/builder/normalizer/projector/models
```

### 结论
- 活跃域；与上下文/关联链/行为链均有真实接口。深读建议：pool.py（4.5KB）与
  tiered_relation_extractor.py（5.5KB）在施工关联链时补充。

---

## 四、memory/（44.8KB/6f）— 孤儿确认

```
xml_cards.py 8.8KB / federated_index.py 7.8KB / strategy_federation.py 10.0KB /
cluster_map.py 6.3KB / ragraph.py 6.5KB / compression_router.py 5.3KB
全库 rg（core/cli/api/service/runtime，排除自身）: 0 处 import → 确认孤儿
```

### 结论
- 与 L5 记忆设计（meta DESIGN_FULL_READ 已精读）同名概念，但从未接线。
- 处置待拍板：归档 un_use or 接持久化层（与 persistence 审计的存储架构拍板联动）。

---

## 五、learning/（52.7KB/8f）— 真接线（学习管线）

```
blueprint/llm_dag_builder.py:211  → IngestionPipeline      蓝图学习
blueprint/meta_feedback.py:204    → CredibilityEvaluator   元反馈可信度
cli/engine.py:306-308             → Arxiv/DuckDuckGo/Scholar + ContentFetcher + Credibility
cli/subsystem_registrations.py    → content_fetcher/credibility_eval/learning_sources 注册
chroma_store.py 12.6KB            → 独立（storage/chunk_store 与 event/pluggable 各自有 chroma 实现）
```

### 结论
- 活跃域；与蓝图/元认知强关联（归并蓝图审计补充成立）。chroma_store 与另外两处 chroma
  实现并存 → P-2 多代演进分裂 +1（3 套 chroma 入口）。

---

## 六、world/（42.7KB/9f）— 完整实现（TRACEABILITY "42L stub" 已过时确认）

```
adapter/code/adapter.py + extractor + lsp_extractor → world.schema + world.extractor（真消费）
v4/world/__init__.py → 门面重导出全部 9 类（schema/extractor/community/importance/updater/
                       params/compiler）
context/source.py:522 → StructuralContextCompiler（真消费）
runtime/engine.py:22 → WorldParams
```

### 结论
- 世界模型 42.7KB 完整实现，非 stub；与上下文（compiler）、执行（adapter/code）真接线。
- 归并上下文/执行层审计补充；importance.py（12.8KB）与 compiler.py（11.8KB）施工时精读。

---

## 七、frontend/（85.5KB/8f）— service 层真消费

```
service/agent_service.py:23-28 + service/protocol → ClarificationFSM/EventBuilder
service/async_agent_service.py:20-24 → MultimodalPipeline/MediaAttachment
service/api.py:36 → EventBuilder/EventSerializer/WebSocketEvent
service/api/main.py:179-196 → WS 事件推送
```

### 结论
- 活跃域，服务层（B 路径 API）直接消费；clarification_fsm（18.2KB）是澄清闭环核心。
- 归并服务层/蓝图审计补充；P2。

---

## 八、task_engine / user_engine / security / document（挂既有模块）

| 域 | 消费方 | 归属 |
|---|---|---|
| task_engine/ 42.8KB | discourse_manager:74-154（TaskManager(sm_client) 真实例化）| 挂上下文审计 |
| user_engine/ 52.7KB | discourse_manager:49-145 + context_layer:128 | 挂画像/上下文审计（画像审计已触及 v3 规则）|
| security/ 28.9KB | fact_store:28（InputSanitizer 真消费）+ v3_0/security 门面 | 挂画像/工程链审计 |
| document/ 52.0KB | chunking/strategies + cli/main + observation/document_domain_adapter | 挂观察/工程链审计 |

---

## 九、问题清单（外围域）

| # | 级别 | 问题 | 方向 |
|---|---|---|---|
| PE-1 | P2 | memory/ 六文件孤儿（L5 概念零接线）| 归档 or 接持久化层 |
| PE-2 | P2 | chroma 三套并存（learning/chroma_store + storage/chunk_store + event/pluggable）| 归一拍板 |
| PE-3 | P2 | orchestrator v3（45KB）与 agent_native v6 双宿主并存，v3 受 planner/models 断链影响 | 与规划审计联动归一 |
| PE-4 | P2 | coordinator/multi_tier_llm_client 与 llm_providers 的关系未定义（两套 LLM 分层）| LLM 认知层审计联动 |
| PE-5 | P2 | world/importance + compiler、observation/pool + tiered_relation_extractor 深读待施工时补 | 挂上下文/关联链施工 |

---

## 十、与全局拍板池的关系

- **P-2 多代演进分裂** +2 例: chroma 三套并存 / orchestrator v3-v6 双宿主。
- **P-1 接线断裂** 反例 1 个: observation/learning/world/frontend/coordinator 均是
  真接线（与"组件齐备接线断裂"的普遍现象相反——外围服务层反而更健康）。
- memory/ 孤儿确认 → 拍板池新增"L5 记忆实现去留"。


# 归档审计 — 高价值断线排查（2026-08-07）

> 触发: 用户质疑"归档的模块有没有可能也是高价值但未被连接导致被归档？
> （像 world/importance 一样）"。
> 方法: 全量盘点 un_use/（后端 6 处 + 前端 1 处）→ 逐模块判类:
> 真历史遗留（有替代）vs 设计好但断线（零消费高价值）。

---

## 一、后端归档盘点

| 归档模块 | 体量 | 判定 | 依据 |
|---|---|---|---|
| **memory_strategy_federation/**（cluster_map/compression_router/federated_index/ragraph/strategy_federation/xml_cards） | 46KB/6f | 🟡 **高价值未接** | 多策略聚类联邦（LLM/blueprint/Markov/greedy + 验证循环 + 内聚/熵监控）— 与二阶抽象聚类凝练同型; 全库零外部消费 = 设计好但断线候选 |
| **v4/un_use/negative_kb.py**（TieredNegativeKB） | 3.7KB | 🟡 **高价值未接** | 多层负知识库（keyword 快路径 → fuse 慢路径 + learned overrides）; 底层 v3_2/negative_kb 活跃目录但也零消费 |
| **v3_2/un_use/integration.py**（V32Pipeline） | 32KB | 🟢 保持归档（记录） | integration_bridge 仍 lazy import（enable_v32=False 默认关）— 显式功能开关未开, 非意外断线; AgentPipeline 非生产主链 |
| **v3_2/un_use/parameter_registry.py** | 55KB | 🟢 归档正确 | compiler/parameter_registry 活跃替代（M3） |
| **v3_common/un_use/intent_parser.py** | 59KB | 🟢 归档正确 | I4 已切新 intent 包 |
| **v4/un_use/**（signal_filter/llm_profile_analyst/rule_engine/cognitive_loop_v1/metacognition_v3/intent_parser） | ~36KB | 🟢 归档正确 | 均有替代（PCR 统一 / 意图新包 / 元认知 v4 内核） |
| **topic_tree/un_use/manager_v1.py** | 5KB | 🟢 归档正确 | T4 已归一 V2 唯一内核 |
| **v3_0/un_use/** | 0 | 🟢 归档正确 | M7 服务层归档, 零引用 |

## 二、前端归档盘点

| 归档模块 | 判定 | 依据 |
|---|---|---|
| task 全家桶（TaskFlow/TaskNode/TaskEdge/TaskDetailPanel/TaskStatsBar/TaskExecutionControls/index） | 🟢 归档正确 | TaskPlanningPage 已用 FlowchartCanvas（纯 SVG）替代 |
| useChat / chatConnection / WS 四套 | 🟢 归档正确 | ChatPage 走 HTTP（api/session.ts）+ 原生 WS |

## 三、结论（回答用户问题）

**存在**——至少 2 处高价值断线被归档（memory_strategy_federation +
TieredNegativeKB），与 world/importance 同型（设计好但零消费）。
其余归档均有活跃替代（正确）。

## 四、处置建议

1. **memory_strategy_federation → 二阶抽象聚类器候选**（P2）:
   其多策略联邦 + 验证循环可直接作为 HeuristicDistiller 的聚类环节
   （当前 distill 用简单序列计数; federation 提供 LLM/blueprint/Markov
   多策略聚类 + cohesion/entropy 验证）。恢复需先确认其依赖
   （cluster_map/ragraph 是否依赖已归档 memory/ 旧结构）。
   ✅ **2026-08-07 已接入**: 恢复至 core/agent/memory/strategy_federation/
   + distiller 规则兜底 P×I 信息论路由（CompressionRouter 语义 +
   LLM information_value）— 见 MEMORY_FEDERATION_CLUSTERING_20260807.md
2. **TieredNegativeKB → 负知识约束候选**（P2）:
   负面知识（禁止/降权）与权限引擎/规则引擎互补; 评估 PCR 规则覆盖度后
   决定接线 or 保持资产。
   ✅ **2026-08-07 已接入**: 恢复为 core/agent/negative_kb/tiered.py
   （自包含两层, 去 v4/tiered 依赖）+ executor 工具调用前校验
   （HARD_BLOCK 拦截 / WARN taint 联动）— 见
   TIERED_NEGATIVE_KB_IMPL_20260807.md
3. **v3_2/integration** 保持归档, 记录: enable_v32 默认 False, 如需
   v3_2 集成链再恢复（integration_bridge 引用已在, 恢复成本低）。

## 五、防复发机制（审计教训）

- **归档前判类**: 零消费 ≠ 历史遗留 — 先查 docstring/设计对应, 区分
  "有替代的旧版" vs "设计好但断线"（接线断裂 P-1 型）。
- **归档时检查活跃引用**: rg 全库（含 lazy import, 如 integration_bridge
  的 enable_v32 分支）。
- 本次教训: world/importance 差点被归档（用户拦截）→ 新增
  `UN_USE_AUDIT` 流程: 归档 = 先判类 + 记录待接候选, 不直接删除。

# PCR (Pre-Cognitive Router) 深度调研报告

> 调研日期: 2026-07-31
> 范围: 设计文档 × 代码实现 × CLI/API/引擎接线 × 测试
> 结论先行: PCR 是"设计多代演进、代码分裂成 3 套、引擎从未接线"的典型模块。

---

## 一、PCR 是什么

DialogMesh 的**输入层网关**。在所有认知处理之前对用户消息做"第一眼判断"：

```
用户输入 → PCR → {期望类型, 噪声度, 复杂度, 认知画像, 策略} → 下游 (IntentParser → Engine)
```

设计哲学（v2.4 原文）:
- 先理解用户，再理解任务（认知先行）
- 确定性优先：规则处理 90%+，LLM 仅 fallback
- 歧义即显式：不确定时不猜，标记歧义并路由消解
- 零额外模型：PCR 自身不引入新模型，用结构特征 + 现有能力
- 连续值优于离散标签（v4.0 核心）

---

## 二、设计文档时间线（4 代演进）

| 代 | 文档 | 日期 | 核心内容 | 状态 |
|---|------|------|---------|------|
| v2.4 | `design_layer0_pcr_and_layer1_intent_parser.md` (2124行) | 2025-06-24 | Layer 0 PCR + Layer 1 IntentParser 双入口架构；5 阶段 Pipeline；三维认知刷新模型；8 条设计原则 | 历史基准 |
| v2.2.1 | `design_pcr_interface_v2_1.md` (940行) | 2025-06-24 | `IPCRRouter` 抽象基类 + 插件生命周期 + 数据契约版本化；8 大修正 | 历史基准 |
| v2.1 | `design_pcr_issues_discussion.md` (625行) | 2025-06-24 | 3 个问题讨论：多模态分发、硬编码阈值→统计学阈值、认知刷新感知 | 历史基准 |
| v3.0 | `ENGINEERING_PCR.md` | 2026-07-19 | 数据模型 PCRInput_v1/PCROutput_v1/CognitiveProfile_v1；算法伪代码；YAML 配置 | 工程基准 |
| — | `checkpoint_pcr_p13.md` | 2026-06-15 | P8-P13 集成测试：168/170 PASS | 历史记录 |
| — | `pcr_gap_assessment.md` / `_v2_2.md` | 2026-06-15 | 完成度 78%；7 核心模块 100%；配置外化 0% | 已关闭 |
| **当前** | `BUSINESS_CHAIN_00_PCR.md` (328行) | 2026-07-21 | **5 阶段 Pipeline + NoiseSpan 拓扑 + 8 链调控 + 决策矩阵 + 生命周期 + 3 级降级**；声称"代码3500行 9模块，测试168/170，接入 on_event ❌" | 主设计 A |
| **当前** | `DESIGN_V4.0_COGNITIVE_COORDINATE_ROUTER.md` (257行) | 2026-07-22 | **范式跃迁：离散标签 → 三维连续坐标(X认知距离/Y操作粒度/Z反馈期望) → 6 zone 路由** | 主设计 B |
| v5.0 | `PCR_SIGNAL_SPEC.md` | 2026-07-21 | PCR → 8 条下游链信号接口规范（仅链02已接） | 规范 |
| v5.0 | `PCR_FALLBACK_SPEC.md` | 2026-07-21 | 3 级降级规范（conservative/degraded/pass_through）+ Telemetry | 规范 |
| — | `PCR_DESIGN_AUDIT_REPORT.md` | 2026-07-24 | 审计：X 轴公式断裂、5 阶段零实现、3 套 router 代码冲突 | 审计 |
| — | `PCR_COMPLETE.md` | 2026-07-21 | 完整整理（文档溯源 + 5 信号 + 数据契约） | 综合 |

**关键观察**: 当前存在两套"主设计"并行——`BUSINESS_CHAIN_00_PCR.md`（5 阶段 Pipeline，旧契约）与 `DESIGN_V4.0_COGNITIVE_COORDINATE_ROUTER.md`（3D 坐标，新范式）。代码实现偏向后者，但两套都没接进引擎。

---

## 三、设计契约（两套）

### 3.1 旧契约（v2.4/v3.0/BUSINESS_CHAIN_00）: PCROutput_v1

```python
class PCROutput_v1:
    expectation: str          # TOOL / ADVISOR / COMPANION / UNKNOWN
    noise_level: float        # 0-1（设计升级为 NoiseSpan[] 拓扑）
    complexity_level: float   # 0-1
    cognitive_profile: CognitiveProfile_v1
    execution_mode: str       # FAST_EXECUTE / CLARIFICATION / DEEP_RESEARCH / CONVERSATIONAL / BALANCED
    prompt_style: str         # BRIEF / EXPLANATORY / TUTORIAL / BALANCED
    ambiguity_strategy: str   # AGGRESSIVE_AUTO / CONSERVATIVE_ASK / BALANCED
```

5 阶段 Pipeline: ExpectationIdentifier → NoiseSpanDetector → ComplexityEstimator → CognitiveProfiler → StrategyDeriver

### 3.2 新契约（V4.0）: PCRResult (3D 坐标)

```python
class PCRResult:
    x_axis: float   # 认知距离 0=near 1=far（BGE SVO 语义引力 + IDF 修正）
    y_axis: float   # 操作粒度 0=atomic 1=complex（StructuralFeatures 三板斧）
    z_axis: float   # 反馈期望 -1=mirror 0=explore +1=solution（BGE 情绪向量）
    zone: str       # PSYCHE / ATOMIC / ABYSS / PRECISION / EXPLORE / MIXED
    execution_mode / prompt_style / cognitive_level
```

6 zone 阈值（设计）:
| zone | 条件 | 策略 |
|------|------|------|
| PSYCHE | z < -0.5 | 小模型 + 共情, 禁技术 |
| ATOMIC | x<0.2, y<0.2 | cache/rule, 0ms, 无 LLM |
| ABYSS | x>0.7, y>0.7, z>0.5 | full ReAct+CoT, 递归5 |
| PRECISION | x<0.5, y>0.5, z>0 | planner agent, JSON plan |
| EXPLORE | x>0.5, y<0.5, z<=0 | socratic, 高温检索 |
| MIXED | 其余 | balanced |

---

## 四、代码实现盘点（4 套 + 旧包）

### 4.1 旧包 `core/agent/pcr/`（"僵尸包"——契约完整但无实现类注册）

| 文件 | 行数 | 功能 | 状态 |
|------|:---:|------|------|
| `interface.py` | ~240 | `IPCRRouter` 抽象基类: evaluate/warm_up/shutdown/reload_config/get_health/get_telemetry/get_capabilities/get_schema | ✅ 定义 |
| `datacontract.py` | ~900 | PCRInput_v1 / PCROutput_v1 / CognitiveProfile_v1 / HistoryEntry / Modality | ✅ 完整 |
| `registry.py` | ~250 | 插件注册表: register_pcr/create_pcr/discover_pcr_plugins | ✅ 完整 |
| `lifecycle.py` | ~400 | PCRLifecycleManager: initialize/evaluate/shutdown + 健康检查线程 | ✅ 完整 |
| `config.py` | ~280 | PCRGlobalConfig: YAML + 环境变量 + 热加载 | ✅ 完整 |
| `fallback.py` | ~320 | FallbackEngine: conservative/degraded/pass_through + retry | ✅ 完整 |
| `telemetry.py` | ~120 | TelemetryCollector: 滑动窗口 + p50/p99 | ✅ 完整 |
| `grammar_tagger.py` | ~140 | Stanza 双轨语法标记 (S/V/O/NEG...) | ✅ 完整 |
| `llm_expertise.py` | ~140 | LLM 专业度探针（5 维，零硬编码） | ✅ 完整 |
| `rule_based.py` | ~45 | **RuleBasedPCR(PCRRouterV2) 兼容包装** + _PCRLegacyOutput 适配器 | ⚠️ 已废弃 |

**致命问题**: `register_pcr()` 要求 `issubclass(cls, IPCRRouter)`，但 `RuleBasedPCR` 继承的是 `PCRRouterV2`（不继承 IPCRRouter）→ **注册必然抛 TypeError**。旧包 7 个完整模块（lifecycle/registry/config/fallback/telemetry）全是"无实现可管的空壳"。

### 4.2 `core/agent/pcr_router_v2.py`（599 行）—— 实际主实现

| 方法 | 功能 |
|------|------|
| `StructuralFeatures.extract(text)` | Y 轴结构特征: verb/entity/word/question/imperative/CJK，零硬编码 |
| `route(text, history=None)` → PCRResult | 3D 坐标 → zone（classmethod） |
| `_compute_granularity` | Y = min(v/5,1)*0.4 + min(e/5,1)*0.3 + min(w/20,1)*0.3 ✅ 符合设计 |
| `_compute_mood` | Z 轴: LM Studio nomic 768d → sentence_transformers → fastembed → NRC-VAD → 结构 fallback |
| `_compute_distance` | X 轴: **nomic(S,O)cosine + IDF**（git d5b6f68 升级，偏离设计 BGE 但方向一致） |
| `_zone_from_xyz` | 6 zone 路由（阈值与设计有差异） |
| `_llm_entities` | LLM 实体补全（正则漏掉中文术语时） |
| `_llm_review` | LLM 协同审查（模型大小感知: <7B 3信号 / 7-13B 语法标签 / 70B+ 仅坐标） |
| `enable_llm_review(provider)` | 注入远程 LLM（如 DeepSeek） |

**结论**: 最接近 V4.0 设计，零硬编码方向正确，Y/Z 轴符合设计，但 **X 轴偏离公式**、**无 5 阶段 Pipeline**、**无测试文件**（rg 全仓库未找到对 PCRRouterV2 的测试）。

### 4.3 `core/agent/llm_providers/llm_instances/pcr_llm.py` —— CLI 实际挂载的实现（空壳）

```python
class PCRLLM(LLMEngine):
    def route(self, text, *args, **kwargs):
        """Alias for process (engine compatibility)."""   # ← 只有 docstring，返回 None！
    def show/history/get_config/set_config/reset_config:  # CLI 支撑
    # process() 继承 LLMEngine.process(context_data: Dict, ...) — 异步、参数是 dict 不是 text
```

`LLMEngine.process(context_data)` 签名与 CLI 调用 `pcr.process(text)`（传 str）**不匹配**；且 `_PROMPT` 的 `{user_input}`/`{context}` 占位符从未被填充（`_build_prompt` 直接返回模板原文）。

### 4.4 `core/agent/router/router_v4.py` + `coordinate_router.py` —— 弃用/影子实现

| 文件 | 行数 | 状态 | 问题 |
|------|:---:|------|------|
| `router_v4.py` | ~117 | ⚠️ DEPRECATED 标记 | Y 轴用 Stanza（与设计矛盾）；engine 仍引用 `_router_v4` 但从不赋值 |
| `coordinate_router.py` | ~257 | 影子实现 | 最接近设计（CognitiveCoordinate.zone() 阈值完全一致）但依赖 BGE、无测试 |

### 4.5 其他引用点

| 文件 | 用法 | 结果 |
|------|------|------|
| `core/agent/engineering_bridges.py:31` | `from core.agent.pcr_router_v2 import PCRV2Router` | **类名错误（实际 PCRRouterV2）→ ImportError 被吞 → PCRBridge 永远降级** |
| `core/agent/mcp/server.py:60` | `pcr or RuleBasedPCR()` | 旧包装 |
| `core/agent/service/agent_service.py` | `RuleBasedPCR` + `pcr.evaluate(inp)` | 旧契约 |
| `core/agent/tools/cognitive_tools.py` | `PCRInput_v1(query=..., session_history=...)` + `evaluate` | 旧契约 |
| `core/agent/v3_common/gates.py` | `PCRGate` + `pcr_instance.evaluate(inp)` | 旧契约 |

---

## 五、接线盘点（CLI / API / 引擎 / 编排器）

| 层 | 挂载的 PCR | 调用方式 | 实际结果 |
|---|---|---|---|
| 引擎 `runtime/engine.py` | `_pcr_router = None`（**从不赋值**） | — | **PCR 从不执行**（注释说 lazy init in start()，但引擎类没有 start()，只有 stop()） |
| 引擎 `_on_event_continue` | `self._router_v4.route(...)` | 仅当 `_router_v4 is not None` | `_router_v4` 也从不赋值 → 永不执行 |
| CLI `cli/registry.py` | `_pcr_factory()` → **PCRLLM** | 注册为 "pcr_router" | 挂载了错误的实现 |
| CLI `start_engine()` | `setattr(engine, f"_{name}", instance)` | 把 registry 结果塞进 `_pcr_router` | `_pcr_router = PCRLLM` |
| CLI `cmd_pcr` (`pcr_intent_cmd.py`) | `pcr.process(text)` async | hasattr(process) → 调用 | 签名不匹配（str vs dict），`route()` 返回 None |
| API `v6_app.py /v6/pcr` | `_pcr_router` / `_last_pcr` | getattr | last_zone 永远 none/mixed |
| 编排器 `bootstrap_v6.py` | `bootstrap(pcr_router=None)` 默认 None | `orch.pcr = None` | **PCR 不执行** |
| 编排器 `agent_native.py` | `self.pcr.route(text, override=...)` | 若传入 PCRRouterV2 | **TypeError**（route 无 override 参数）→ 被 except 吞掉；且读 `.x/.y/.z`（实际字段是 x_axis/y_axis/z_axis）→ 恒为 0.5 |
| 事件 `event/handlers.py` | `hasattr(pcr,'route')` → `pcr.route(text)` | PCRLLM.route 返回 None | 恒回退 `{"zone": "MIXED", "source": "mock"}` |

**结论**: PCR 在生产路径上**从未真正运行过**。CLI 挂错实现（PCRLLM）、引擎不接线（None）、编排器不传参（None）、旧包无实现类、桥接层类名拼错。

---

## 六、测试状况

| 测试 | 内容 | 状态 |
|------|------|------|
| `core/agent/pcr/tests/` 13 文件 (~280KB) | test_datacontract / test_integration / test_mcp_layer / test_service_layer / test_frontend_layer / test_v24_orchestration / test_production_optimizations / adversarial_suite / benchmark / demo_full_pipeline_trace / intent_trace_cli / mock_pcr | 覆盖**旧契约**（IPCRRouter/mock），文档称 168/170 PASS |
| `PCRRouterV2` 专属测试 | — | **不存在**（全仓库 rg 无结果） |
| `router_v4` / `coordinate_router` 测试 | — | 不存在 |

即: 文档引用的"168/170 PASS"是旧包 mock 实现的成绩，与当前主实现 PCRRouterV2 无关。

---

## 七、问题清单（按优先级）

### 🔴 P0 — 阻塞接线

| # | 问题 | 位置 | 影响 |
|---|------|------|------|
| P0-1 | 引擎 `_pcr_router`/`_router_v4` 从不赋值，且引擎无 `start()` | `runtime/engine.py:189,198` | PCR 生产路径零执行 |
| P0-2 | CLI 挂载 PCRLLM（空壳 route），`cmd_pcr` 调 `process(text)` 签名不匹配 | `cli/registry.py:260` / `pcr_intent_cmd.py` | `dialogmesh pcr route` 无有效输出 |
| P0-3 | 三套实现并存且接口不同（IPCRRouter.evaluate / PCRRouterV2.route / PCRLLM.process） | 全局 | 无单一契约可接 |
| P0-4 | `engineering_bridges.py` 类名拼错 PCRV2Router→PCRRouterV2 | `engineering_bridges.py:31` | PCRBridge 永远降级 |
| P0-5 | `agent_native.py` 传 `override=` + 读 `.x/.y/.z` 字段名错误 | `agent_native.py:141-149` | PCR 一旦接入也会静默失败 |

### 🟡 P1 — 设计未落地

| # | 问题 | 设计来源 | 现状 |
|---|------|---------|------|
| P1-1 | 5 阶段 Pipeline（ExpectationIdentifier/NoiseSpan/Complexity/CognitiveProfiler/StrategyDeriver）零实现 | BUSINESS_CHAIN_00 §二 | ❌ |
| P1-2 | NoiseSpan 拓扑（6 种噪声类型 + 差异化下游处理）零实现 | BUSINESS_CHAIN_00 §三 | ❌ |
| P1-3 | 8 链调控映射零实现（仅链02在文档中"已接"但代码无对应） | PCR_SIGNAL_SPEC | ❌ |
| P1-4 | 3 级降级 FallbackEngine 已写但无实现类可包 | PCR_FALLBACK_SPEC / pcr/fallback.py | ⚠️ 空转 |
| P1-5 | X 轴公式偏离设计（entity_density+rarity vs BGE SVO 语义引力+IDF） | V4.0 §3.1 | ⚠️ 部分 |
| P1-6 | 6 zone 阈值三套代码不一致 | V4.0 §四 | ⚠️ |
| P1-7 | EventBus PCR_COMPUTED 事件未发布（agent_native 有 `_publish("PCR_COMPUTED")` 但 PCR 未运行） | DESIGN_ALIGNMENT_CHECK | ❌ |

### 🟢 P2 — 增强

- 后验校准（用户反馈 → 坐标权重微调）仅 coordinate_router 有骨架
- Z 轴 LLM MoodClassifier fallback（设计 75%，代码无）
- Telemetry/Lifecycle 集成到真实运行路径
- PCRRouterV2 测试覆盖（当前 0）
- 多模态输入（PCRInput 有 Modality 定义，无实现）

---

## 八、建议收敛方案

1. **定主实现**: `PCRRouterV2`（最接近 V4.0 设计，零硬编码，有 LLM 协同审查）
2. **定主契约**: `route(text) -> PCRResult`（3D 坐标）；`PCROutput_v1` 降级为兼容适配层或废弃
3. **修 CLI**: `_pcr_factory` 改为返回 PCRRouterV2（或适配器），`cmd_pcr` 改调 `route()`
4. **修引擎**: 补 `start()` 或在 `__init__` 默认装配 PCRRouterV2
5. **修桥接**: `PCRV2Router` → `PCRRouterV2`
6. **修 agent_native**: 去掉 `override=`，字段名改 `x_axis/y_axis/z_axis`
7. **旧包处置**: 明确废弃 `pcr/`（保留 IPCRRouter 文档价值），或让 RuleBasedPCR 真正实现 IPCRRouter
8. **补设计落地**: 按 BUSINESS_CHAIN_00 补齐 5 阶段（至少 ExpectationIdentifier Tier0 + NoiseSpan）
9. **补测试**: PCRRouterV2 单元测试 + zone 阈值测试
10. **接 8 链**: PCR 输出 → 链01/02/04/05/07/08/09/10 信号投递（参照 PCR_SIGNAL_SPEC）

---

## 九、相关文件索引

**设计**: `docs/BUSINESS_CHAIN_00_PCR.md` · `docs/PCR_COMPLETE.md` · `docs/v5/DESIGN_V4.0_COGNITIVE_COORDINATE_ROUTER.md` · `docs/v5/PCR_SIGNAL_SPEC.md` · `docs/v5/PCR_FALLBACK_SPEC.md` · `docs/v5/PCR_DESIGN_AUDIT_REPORT.md` · `docs/v3.0/design_layer0_pcr_and_layer1_intent_parser.md` · `docs/v3.0/design_pcr_interface_v2_1.md` · `docs/v3.0/design_pcr_issues_discussion.md` · `docs/v3.0/ENGINEERING_PCR.md` · `docs/v3.0/checkpoint_pcr_p13.md` · `docs/legacy/pcr_gap_assessment*.md`

**代码**: `core/agent/pcr_router_v2.py` · `core/agent/pcr/`（interface/datacontract/registry/lifecycle/config/fallback/telemetry/rule_based/grammar_tagger/llm_expertise/tests）· `core/agent/router/router_v4.py` · `core/agent/router/coordinate_router.py` · `core/agent/router/zone_strategy.py` · `core/agent/llm_providers/llm_instances/pcr_llm.py` · `core/agent/llm_providers/llm_instances/llm_engine.py`

**接线**: `core/agent/runtime/engine.py` · `core/agent/cli/registry.py` · `core/agent/cli/engine.py` · `core/agent/cli/commands/pcr_intent_cmd.py` · `core/agent/api/v6_app.py` · `core/agent/orchestrator/bootstrap_v6.py` · `core/agent/orchestrator/agent_native.py` · `core/agent/event/handlers.py` · `core/agent/engineering_bridges.py` · `core/agent/v3_common/gates.py` · `core/agent/tools/cognitive_tools.py` · `core/agent/service/agent_service.py` · `core/agent/mcp/server.py`

**Obsidian 索引**: `C:\Users\APTShark\Documents\Obsidian Vault\dialogmesh-design\00-INDEX-PCR.md` · `01-MOC-PCR.md`

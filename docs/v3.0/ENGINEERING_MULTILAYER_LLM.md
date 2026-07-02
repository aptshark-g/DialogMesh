# DialogMesh 多层 LLM 认知架构 — 工程实现文档

> **文档编号**: ENGINEERING-MULTILAYER-LLM-005  
> **版本**: v1.0  
> **日期**: 2026-07-19  
> **状态**: 工程待实现（大量新增）  
> **对应设计文档**: `DESIGN_MULTILAYER_LLM_COGNITIVE.md` v3.0  
> **对应代码**: `core/agent/llm_providers/`（7 文件，基础提供者）  
> **核心原则**: LLM 是认知核心，算法是神经加速层。两者并行运行，通过 Cognitive Tree 交换信息。

---

## 目录

- [1. 文档目标与范围](#1-文档目标与范围)
- [2. 变更总览](#2-变更总览)
- [3. 现有实现评估](#3-现有实现评估)
- [4. 架构总览：认知双工](#4-架构总览认知双工)
- [5. 认知双工：算法引擎 ∥ LLM 引擎](#5-认知双工算法引擎--llm-引擎)
- [6. 融合引擎（Fusion Engine）](#6-融合引擎fusion-engine)
- [7. 三层 LLM 认知层](#7-三层-llm-认知层)
- [8. Cognitive Tree 实现](#8-cognitive-tree-实现)
- [9. 访问控制矩阵](#9-访问控制矩阵)
- [10. 事件总线（Event Bus）](#10-事件总线event-bus)
- [11. 穿透层 Answer LLM](#11-穿透层-answer-llm)
- [12. 幻觉三层防御](#12-幻觉三层防御)
- [13. 渐进启用与配置开关](#13-渐进启用与配置开关)
- [14. 性能预算与成本模型](#14-性能预算与成本模型)
- [15. 测试策略](#15-测试策略)
- [16. 附录：简化与待讨论项](#16-附录简化与待讨论项)

---

## 1. 文档目标与范围

### 1.1 目标

本工程文档定义 DialogMesh **v3.0 多层 LLM 认知架构**的完整实现规范。这是 v3.0 的**锚文档**，所有其他模块（PCR、Intent Parser、Planning、Service Layer）必须回溯对齐到本文档定义的架构。

### 1.2 核心命题

> **Agent 不是"带 LLM 的规则系统"，而是"以 LLM 为认知核心、算法为神经加速层的多认知体系统"。**

### 1.3 范围

| 需求 | 设计文档位置 | 本章位置 | 说明 |
|------|-------------|---------|------|
| 认知双工 | §1.2 | §5 | 算法引擎 ∥ LLM 引擎并行运行 |
| 融合引擎 | §3.1.3 | §6 | 加权融合 + 冲突检测 + 保守降级 |
| 三层 LLM | §3 | §7 | Layer 1.5 Hybrid / Layer 2.5 Meta-Cognitive / Layer 3 Reflective |
| Cognitive Tree | §4 | §8 | LLM 心智树（节点/边/版本/分支） |
| 访问控制 | §6.2 | §9 | LLM 实例权限矩阵 |
| 事件总线 | §6.3 | §10 | 异步事件通知系统 |
| Answer LLM | §5 | §11 | 穿透层、直接面对用户 |
| 幻觉防御 | §7 | §12 | 实时拦截 → 跨轮验证 → 长期复盘 |
| 渐进启用 | §8.2 | §13 | Phase 1-5 分阶段启用 |

### 1.4 诚实标记原则

> ⚠️ **关键声明**：本文档涉及的 v3.0 架构**大量模块尚未实现**。现有代码仅提供了基础 LLM 提供者（路由/故障转移），没有认知双工、没有 Cognitive Tree、没有三层 LLM、没有融合引擎。本文档是**从零设计的施工蓝图**，而非"已有代码的说明书"。

---

## 2. 变更总览

### 2.1 新增文件（大量）

| 文件路径 | 职责 | 代码行估算 | 备注 |
|---------|------|----------|------|
| `core/agent/cognitive_duplex/` | 认知双工核心包 | — | 新增目录 |
| `core/agent/cognitive_duplex/hybrid_engine.py` | 混合引擎（算法 ∥ LLM 并行调度） | ~300 行 | 核心 |
| `core/agent/cognitive_duplex/fusion_engine.py` | 融合引擎（加权融合 + 冲突检测） | ~200 行 | 核心 |
| `core/agent/cognitive_duplex/llm_instances.py` | 6 个 LLM 实例的 Prompt 模板与调用封装 | ~400 行 | 核心 |
| `core/agent/cognitive_tree/` | Cognitive Tree 实现包 | — | 新增目录 |
| `core/agent/cognitive_tree/tree.py` | CognitiveTree 类（节点/边/分支管理） | ~250 行 | 核心 |
| `core/agent/cognitive_tree/store.py` | CognitiveTree 存储（内存 + 持久化） | ~150 行 | 核心 |
| `core/agent/cognitive_tree/access_control.py` | 访问控制矩阵 | ~100 行 | 核心 |
| `core/agent/cognitive_tree/event_bus.py` | 事件总线（异步通知） | ~150 行 | 核心 |
| `core/agent/meta_cognitive/` | 元认知监督层 | — | 新增目录 |
| `core/agent/meta_cognitive/supervisor.py` | Meta-Cognitive Supervisor（验证/评估/修正） | ~300 行 | 核心 |
| `core/agent/meta_cognitive/hallucination_detector.py` | 幻觉检测器（7 种类型） | ~250 行 | 核心 |
| `core/agent/meta_cognitive/confidence_calibration.py` | 置信度校准（Platt Scaling） | ~150 行 | 核心 |
| `core/agent/reflective/` | 复盘整合层 | — | 新增目录 |
| `core/agent/reflective/consolidator.py` | Reflective Consolidator（长期复盘） | ~250 行 | 核心 |
| `core/agent/reflective/bias_detector.py` | 偏见检测器 | ~150 行 | 核心 |
| `core/agent/answer_llm/` | 穿透层 Answer LLM | — | 新增目录 |
| `core/agent/answer_llm/answer_engine.py` | Answer Engine（综合上下文生成回复） | ~200 行 | 核心 |
| `core/agent/answer_llm/constraints.py` | 回复约束系统（风格/结构/诚实声明） | ~100 行 | 核心 |

### 2.2 修改文件

| 文件路径 | 变更内容 | 影响范围 |
|---------|---------|---------|
| `core/agent/llm_providers/base.py` | 扩展 `LLMProvider` 为支持 `cognitive_mode`（快速/深度/反思） | 提供者基类 |
| `core/agent/pcr/rule_based.py` | `RuleBasedPCR` 改为 `HybridPCR`（内部并行调用 PCR-LLM） | PCR 层 |
| `core/agent/intent_parser.py` | `IntentParser` 内部并行调用 Intent-LLM | 意图解析层 |
| `core/agent/blueprints.py` | Blueprint 保留为 fallback，DynamicPlanner 优先 | 规划层 |
| `core/agent/orchestrator.py` | 接入认知双工、Cognitive Tree、三层 LLM | 编排层 |

### 2.3 配置开关

```yaml
# config/v3_cognitive.yaml
cognitive_duplex:
  enabled: true              # 总开关
  
layer_1_5:
  enabled: true
  pcr_llm: true              # PCR-LLM 并行
  intent_llm: true           # Intent-LLM 并行
  planning_llm: true         # Planning-LLM 并行
  fusion_mode: "weighted"    # weighted | algorithm_priority | llm_priority

layer_2_5:
  enabled: true
  trigger_mode: "event"      # event | periodic | manual
  factuality_check: true
  consistency_check: true
  plausibility_check: true

layer_3:
  enabled: true
  session_end_trigger: true
  periodic_trigger_minutes: 60

answer_llm:
  enabled: true
  honesty_threshold: 0.7
  meta_cognitive_pre_review: true

cognitive_tree:
  enabled: true
  max_nodes_per_session: 1000
  depth_limit: 10
  persist: true
```

---

## 3. 现有实现评估

### 3.1 现有代码清单

| 文件 | 行数 | 核心职责 | 与 v3.0 的关系 |
|------|------|---------|---------------|
| `llm_providers/base.py` | 149 | `LLMProvider` 抽象基类 + `GenerateRequest`/`GenerateResult` | 基础可用，需扩展认知模式 |
| `llm_providers/openai_provider.py` | 354 | OpenAI API 兼容 | 基础可用 |
| `llm_providers/local_provider.py` | ? | 本地模型（Ollama/vLLM） | 基础可用 |
| `llm_providers/hybrid_router.py` | 191 | 多 Provider 路由（延迟/成本/隐私/质量） | 基础可用，需扩展为认知双工路由 |
| `llm_providers/failover_provider.py` | 139 | 主备故障转移 | 基础可用 |
| `llm_providers/provider_factory.py` | 100 | 工厂模式 | 基础可用 |
| `llm_providers/mock_provider.py` | ? | Mock 测试 | 基础可用 |

### 3.2 差距分析（巨大）

| v3.0 需求 | 现有实现 | 差距 | 实现难度 |
|----------|---------|------|---------|
| 认知双工（算法 ∥ LLM） | 无 | 需要从零实现并行调度 + 超时管理 | 高 |
| 融合引擎 | 无 | 需要从零实现加权融合 + 冲突检测 | 中 |
| PCR-LLM | 无 | 需要 Prompt 工程 + 并行调用 | 中 |
| Intent-LLM | 无 | 需要 Prompt 工程 + 并行调用 | 中 |
| Planning-LLM | 无 | 需要 Prompt 工程 + 并行调用 | 中 |
| Cognitive Tree | 无 | 需要树结构 + 版本控制 + 分支管理 | 高 |
| 访问控制矩阵 | 无 | 需要权限系统 + 节点级锁 | 中 |
| 事件总线 | 无 | 需要异步事件系统 | 中 |
| Meta-Cognitive 层 | 无 | 需要三层验证 + 调优建议生成 | 高 |
| Reflective 层 | 无 | 需要长期复盘 + 偏见检测 | 高 |
| Answer LLM | 无 | 需要综合上下文 + 约束回复 | 中 |
| 幻觉三层防御 | 无 | 需要 Schema Guard + 验证器 + 复盘 | 高 |

**总计**：约 3000 行新增代码，覆盖 12 个全新模块。

---

## 4. 架构总览：认知双工

### 4.1 系统全景图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              用户（User）                                    │
│                              ↕ 自然语言                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│  穿透层：Answer LLM                                                          │
│  ────────────────────────────────────────────────────────────────────────  │
│  • 读取所有层的输出（算法 + LLM + Cognitive Tree）                             │
│  • 生成受约束的自然语言回复                                                   │
│  • 系统置信度 < 0.7 时必须声明不确定性                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│  实时层：Layer 1.5 Hybrid Cognitive Layer（每轮必达，同步）                   │
│  ────────────────────────────────────────────────────────────────────────  │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  输入 → [算法引擎] ───────→ [算法结果 A] ───┐                         │   │
│  │         (规则/统计/启发式)                  │                         │   │
│  │                                              ├──→ [Fusion Engine] ──→ │   │
│  │         [LLM 引擎] ───────→ [LLM 结果 B] ───┘      (加权融合)         │   │
│  │         (语义理解/推理)                        │                      │   │
│  │         PCR-LLM / Intent-LLM / Planning-LLM   │                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────────────┤
│  监督层：Layer 2.5 Meta-Cognitive（跨轮，异步）                                │
│  ────────────────────────────────────────────────────────────────────────  │
│  • 读取 Cognitive Tree 最近 N 个节点                                          │
│  • 事实性/一致性/合理性三层验证                                               │
│  • 幻觉检测 + 置信度校准                                                      │
│  • 算法调优建议生成                                                           │
├─────────────────────────────────────────────────────────────────────────────┤
│  复盘层：Layer 3 Reflective（跨会话，异步）                                    │
│  ────────────────────────────────────────────────────────────────────────  │
│  • Cognitive Tree 结构分析（偏见/盲区/健康度）                                │
│  • 用户画像深度更新（Track A 趋势 + Track B 修正）                            │
│  • 系统级学习策略生成（影子模式验证）                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│  双树结构                                                                     │
│  ═══════════════════════════════════════════════════════════════════        │
│  ┌──────────────────────┐  ┌──────────────────────────────┐                 │
│  │  Topic Tree（用户）    │  │  Cognitive Tree（LLM 心智）   │                 │
│  │  ───────────────     │  │  ────────────────────────    │                 │
│  │  用户对话主题层次     │  │  LLM 推理、假设、决策、反思   │                 │
│  │  持久化：会话级       │  │  持久化：会话级 + 跨会话摘要   │                 │
│  └──────────────────────┘  └──────────────────────────────┘                 │
│  LLM 间通信：通过 Cognitive Tree 节点读写实现（非消息传递）                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 关键架构决策（ADR 实现）

| ADR | 决策 | 工程实现 |
|-----|------|---------|
| ADR-010 | LLM 是认知核心 | `HybridEngine` 中 LLM 引擎与算法引擎并行，融合时 LLM 置信度权重 >= 0.5 |
| ADR-011 | 三层 LLM | `Layer15Engine` / `Layer25Engine` / `Layer3Engine` 三个独立类 |
| ADR-012 | 独立 Cognitive Tree | `CognitiveTree` 类独立于 `TopicTree`，存储在独立表中 |
| ADR-013 | 共享树通信 | `CognitiveTree` 提供 `create_node()` / `read_node()` / `update_status()` / `fork_node()` / `link_nodes()` / `subscribe()` / `query()` API |
| ADR-014 | 穿透式 Answer LLM | `AnswerEngine` 直接读取 `DialogueState` + `CognitiveTree` + 所有层输出 |
| ADR-015 | 幻觉三层防御 | `SchemaGuard` (L1.5) → `HallucinationDetector` (L2.5) → `BiasDetector` (L3) |
| ADR-016 | 渐进启用 | 配置开关控制每层启用，算法引擎始终作为 fallback |

---

## 5. 认知双工：算法引擎 ∥ LLM 引擎

### 5.1 实现：`HybridEngine`

```python
class HybridEngine:
    """认知双工引擎 — 算法引擎与 LLM 引擎并行运行。"""
    
    def __init__(
        self,
        algorithm_engine: Callable,      # 算法引擎（如 RuleBasedPCR / IntentParser）
        llm_engine: LLMEngine,           # LLM 引擎（如 PCRLLM / IntentLLM）
        fusion_engine: FusionEngine,     # 融合引擎
        config: HybridConfig,
    ):
        self._algorithm = algorithm_engine
        self._llm = llm_engine
        self._fusion = fusion_engine
        self._config = config
        self._executor = ThreadPoolExecutor(max_workers=2)
    
    def process(self, input_data: Any, context: Any) -> HybridResult:
        """
        并行执行算法引擎和 LLM 引擎，融合输出。
        
        调度策略：
        1. 同时启动算法引擎和 LLM 引擎
        2. 如果算法引擎先完成且置信度 > 0.9 → 可立即输出（LLM 在后台继续）
        3. 如果算法引擎置信度 < 0.6 → 必须等待 LLM 完成
        4. 如果两者都完成 → 融合引擎加权融合
        """
        algo_future = self._executor.submit(self._algorithm, input_data, context)
        llm_future = self._executor.submit(self._llm.process, input_data, context)
        
        # 策略 1: 算法高置信度快速路径
        algo_result = algo_future.result(timeout=self._config.algorithm_timeout_ms / 1000)
        if algo_result.confidence > self._config.high_confidence_threshold:
            # LLM 在后台继续运行，结果用于更新认知状态
            llm_future.add_done_callback(self._update_cognitive_state)
            return HybridResult(
                output=algo_result.output,
                confidence=algo_result.confidence,
                source="algorithm",
                llm_pending=True,
            )
        
        # 策略 2: 算法低置信度，必须等待 LLM
        if algo_result.confidence < self._config.low_confidence_threshold:
            llm_result = llm_future.result(timeout=self._config.llm_timeout_ms / 1000)
            return self._fusion.fuse(algo_result, llm_result, context)
        
        # 策略 3: 两者都完成，融合
        llm_result = llm_future.result(timeout=self._config.llm_timeout_ms / 1000)
        return self._fusion.fuse(algo_result, llm_result, context)
```

### 5.2 LLM 引擎实例设计

```python
class LLMEngine:
    """LLM 认知引擎基类。每个具体 LLM 实例继承此类。"""
    
    def __init__(
        self,
        provider: LLMProvider,
        prompt_template: str,
        cognitive_tree: CognitiveTree,
        llm_name: str,
    ):
        self._provider = provider
        self._prompt_template = prompt_template
        self._cog_tree = cognitive_tree
        self._llm_name = llm_name
    
    def process(self, input_data: Any, context: Any) -> LLMResult:
        """
        1. 构建 Prompt（模板 + 上下文 + Cognitive Tree 活跃分支）
        2. 调用 LLM Provider
        3. 解析结构化输出
        4. 在 Cognitive Tree 中创建节点
        5. 返回 LLMResult
        """
        prompt = self._build_prompt(input_data, context)
        response = self._provider.generate(GenerateRequest(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            response_format="json",
        ))
        structured = self._parse_response(response.text)
        
        # 创建 Cognitive Tree 节点
        node = CognitiveTreeNode(
            cog_type=self._get_cog_type(),
            source_llm=self._llm_name,
            content=structured.get("reasoning", ""),
            confidence=structured.get("confidence", 0.5),
            evidence=structured.get("evidence", []),
            action=structured.get("action"),
        )
        self._cog_tree.add_node(node)
        
        return LLMResult(
            output=structured,
            confidence=structured.get("confidence", 0.5),
            node_id=node.node_id,
            latency_ms=response.metrics.latency_ms,
        )
```

### 5.3 各组件 LLM 实例

**PCR-LLM**：
```python
class PCRLLM(LLMEngine):
    """PCR-LLM: 语义噪声分析 + 期望推断。"""
    
    _PROMPT_TEMPLATE = """
    你是一位认知分析师，负责分析用户输入的语义特征。
    
    输入："{user_input}"
    上下文：{context}
    
    请输出 JSON：
    {{
      "noise_analysis": {{
        "semantic_noise": 0.0-1.0,    // 语义模糊度
        "structural_noise": 0.0-1.0,  // 结构不完整度
        "referential_noise": 0.0-1.0  // 指代消解难度
      }},
      "expectation_inference": {{
        "primary": "TOOL|ADVISOR|COMPANION|UNKNOWN",
        "confidence": 0.0-1.0,
        "reasoning": "..."
      }},
      "cognitive_snapshot": {{
        "metacognition": 0.0-1.0,
        "divergence": 0.0-1.0,
        "stability": 0.0-1.0
      }}
    }}
    """
    
    def _get_cog_type(self) -> CogType:
        return CogType.PERCEPTION
```

**Intent-LLM**：
```python
class IntentLLM(LLMEngine):
    """Intent-LLM: 深层意图理解 + 隐含实体挖掘。"""
    
    _PROMPT_TEMPLATE = """
    你是一位意图分析师，负责从用户输入中提取深层意图和隐含实体。
    
    输入："{user_input}"
    已提取实体：{entities}
    对话历史（最近 3 轮）：{history}
    
    请输出 JSON：
    {{
      "intent_inference": {{
        "primary_intent": "...",
        "confidence": 0.0-1.0,
        "implied_entities": [{{"type": "...", "value": "...", "reasoning": "..."}}],
        "ambiguity_assessment": "..."
      }},
      "reasoning": "..."
    }}
    """
    
    def _get_cog_type(self) -> CogType:
        return CogType.HYPOTHESIS
```

**Planning-LLM**：
```python
class PlanningLLM(LLMEngine):
    """Planning-LLM: Skill 模板填充 + 备选方案生成。"""
    
    _PROMPT_TEMPLATE = """
    你是一位规划师，负责根据意图和可用工具生成任务计划。
    
    意图：{intent}
    可用工具：{tools}
    匹配 Skill：{skill}
    用户画像：{profile}
    
    请输出 JSON：
    {{
      "plan": {{
        "mode": "DYNAMIC|SKILL_ENHANCED|MIXED",
        "nodes": [{{"name": "...", "tool": "...", "params": {{}}}}],
        "alternatives": [{{"name": "...", "confidence": 0.0-1.0}}]
      }},
      "reasoning": "..."
    }}
    """
    
    def _get_cog_type(self) -> CogType:
        return CogType.REASONING
```

**Meta-Cognitive-LLM**：
```python
class MetaCognitiveLLM(LLMEngine):
    """Meta-Cognitive-LLM: 事实性/一致性/合理性三层验证 + 幻觉检测。"""
    
    _PROMPT_TEMPLATE = """
    你是一位元认知监督者，负责验证 Cognitive Tree 中节点的推理质量。
    
    待验证节点：{node_content}
    节点类型：{node_type}
    来源 LLM：{source_llm}
    相关证据节点：{evidence_nodes}
    对话上下文：{context}
    
    请执行三层验证并输出 JSON：
    {
      "factuality_check": {
        "score": 0.0-1.0,           // 声明与客观事实的一致性
        "reasoning": "..."         // 验证推理过程
      },
      "consistency_check": {
        "score": 0.0-1.0,           // 与树中其他节点的逻辑一致性
        "conflicting_nodes": [...], // 冲突节点 ID 列表
        "reasoning": "..."
      },
      "plausibility_check": {
        "score": 0.0-1.0,           // 是否符合常识和领域约束
        "reasoning": "..."
      },
      "hallucination_risk": 0.0-1.0, // 综合幻觉风险
      "recommendation": "VALIDATE|INVALIDATE|REQUEST_CLARIFICATION",
      "tuning_advice": "..."        // 对来源 LLM 的调优建议（如有）
    }
    """
    
    def _get_cog_type(self) -> CogType:
        return CogType.VALIDATION
```

**Reflective-LLM**：
```python
class ReflectiveLLM(LLMEngine):
    """Reflective-LLM: 跨会话复盘、偏见检测、用户画像更新策略。"""
    
    _PROMPT_TEMPLATE = """
    你是一位系统复盘师，负责分析 Cognitive Tree 的长期模式并生成改进策略。
    
    会话范围：{session_range}
    Cognitive Tree 统计：{tree_stats}
    检测到的偏见：{biases}
    算法盲区：{blind_spots}
    当前用户画像：{current_profile}
    树健康度：{tree_health}
    
    请输出 JSON：
    {
      "bias_analysis": {
        "findings": [...],          // 系统性偏见列表
        "severity": "low|medium|high",
        "mitigation": "..."
      },
      "blind_spot_analysis": {
        "findings": [...],          // 算法盲区列表
        "recommendation": "..."
      },
      "profile_update_strategy": {
        "track_a_changes": {...},   // 趋势更新（认知动力学变化）
        "track_b_corrections": [...], // 标签修正建议
        "new_labels_suggested": [...]
      },
      "learning_strategies": [      // 系统级改进策略
        {
          "type": "PARAMETER|RULE|SKILL|LLM|ARCHITECTURE",
          "description": "...",
          "expected_impact": 0.0-1.0,
          "shadow_mode": true         // 是否先影子验证
        }
      ]
    }
    """
    
    def _get_cog_type(self) -> CogType:
        return CogType.REFLECTION
```

**Answer-LLM**：
```python
class AnswerLLM(LLMEngine):
    """Answer-LLM: 穿透层，综合所有认知层输出，生成面向用户的回复。"""
    
    _PROMPT_TEMPLATE = """
    你是 DialogMesh 的回答生成器，负责综合系统所有认知层的输出，生成自然、准确、诚实的回复。
    
    用户输入：{user_input}
    用户画像：{user_profile}
    
    系统认知状态：
    - 算法结果：{algorithm_result}
    - LLM 结果：{llm_result}
    - 融合模式：{fusion_mode}
    - 系统置信度：{system_confidence}
    
    Cognitive Tree 活跃推理链：
    {active_cognitive_branch}
    
    约束条件：
    - 回复风格：{style}
    - 最大长度：{max_length}
    - 如果系统置信度 < 0.7，必须在回复中声明不确定性
    
    请输出 JSON：
    {
      "response": "...",            // 面向用户的自然语言回复
      "confidence": 0.0-1.0,        // 对回复的置信度
      "honesty_declared": true|false, // 是否包含不确定性声明
      "cited_nodes": [...],         // 引用的 Cognitive Tree 节点 ID
      "fallback_reason": "..."      // 如果使用了 fallback，说明原因
    }
    """
    
    def _get_cog_type(self) -> CogType:
        return CogType.COMMUNICATION
```

---

## 6. 融合引擎（Fusion Engine）

### 6.1 实现

```python
class FusionEngine:
    """融合引擎 — 将算法结果和 LLM 结果加权融合。"""
    
    def __init__(self, config: FusionConfig):
        self._high_threshold = config.high_confidence_threshold  # 0.85
        self._low_threshold = config.low_confidence_threshold    # 0.60
        self._llm_weight = config.llm_weight                    # 0.5 (认知双工：LLM 至少 50%)
    
    def fuse(self, algo_result: AlgorithmResult, llm_result: LLMResult, context: Any) -> HybridResult:
        """
        融合策略：
        
        1. 算法高置信 + LLM 低置信 → 算法输出
        2. 算法低置信 + LLM 高置信 → LLM 输出
        3. 两者接近 → 加权融合
        4. 两者都低 → 保守降级（ask_user）
        """
        c_a = algo_result.confidence
        c_b = llm_result.confidence
        
        # 情况 1: 算法高置信，LLM 低置信
        if c_a > self._high_threshold and c_b < self._low_threshold:
            return HybridResult(
                output=algo_result.output,
                confidence=c_a,
                source="algorithm",
            )
        
        # 情况 2: 算法低置信，LLM 高置信
        if c_a < self._low_threshold and c_b > self._high_threshold:
            return HybridResult(
                output=llm_result.output,
                confidence=c_b,
                source="llm",
            )
        
        # 情况 3: 两者都高或都中等 → 加权融合
        if c_a > self._low_threshold and c_b > self._low_threshold:
            # 检测冲突
            if self._detect_conflict(algo_result, llm_result):
                return self._resolve_conflict(algo_result, llm_result, context)
            
            # 无冲突，加权融合
            weight_a = c_a * (1 - self._llm_weight)
            weight_b = c_b * self._llm_weight
            fused = self._weighted_merge(algo_result.output, llm_result.output, weight_a, weight_b)
            return HybridResult(
                output=fused,
                confidence=(c_a * weight_a + c_b * weight_b) / (weight_a + weight_b),
                source="fused",
            )
        
        # 情况 4: 两者都低 → 保守降级
        return HybridResult(
            output=None,
            confidence=0.0,
            source="fallback",
            clarification_required=True,
        )
    
    def _detect_conflict(self, algo_result: AlgorithmResult, llm_result: LLMResult) -> bool:
        """检测算法和 LLM 输出是否冲突。"""
        # 对于离散输出（如意图类别），直接比较值
        if algo_result.output_type == "discrete":
            return algo_result.output != llm_result.output
        
        # 对于数值输出，计算差异是否超过阈值
        if algo_result.output_type == "numeric":
            diff = abs(algo_result.output - llm_result.output)
            return diff > 0.3  # 差异超过 30% 视为冲突
        
        return False
    
    def _resolve_conflict(self, algo_result: AlgorithmResult, llm_result: LLMResult, context: Any) -> HybridResult:
        """
        冲突消解：
        1. 记录冲突到 Cognitive Tree（CONTRADICTS 边）
        2. 触发 Meta-Cognitive 快速检查（如果可用）
        3. 如果 Meta-Cognitive 不可用，选择置信度较高者，但降低其置信度
        """
        # 记录冲突
        context.cognitive_tree.add_edge(
            source_id=algo_result.node_id,
            target_id=llm_result.node_id,
            edge_type=CogEdgeType.CONTRADICTS,
            weight=1.0,
        )
        
        # 触发 Meta-Cognitive（异步）
        if context.meta_cognitive_available:
            context.meta_cognitive_queue.put((algo_result, llm_result))
        
        # 选择置信度较高者，但降低置信度
        if algo_result.confidence > llm_result.confidence:
            return HybridResult(
                output=algo_result.output,
                confidence=algo_result.confidence * 0.8,  # 降低置信度
                source="algorithm_conflict_resolved",
            )
        else:
            return HybridResult(
                output=llm_result.output,
                confidence=llm_result.confidence * 0.8,
                source="llm_conflict_resolved",
            )
```

---

## 7. 三层 LLM 认知层

### 7.1 Layer 1.5: Hybrid Cognitive Layer（实时交织层）

```python
class Layer15Engine:
    """实时层 — 每轮必达，同步运行。"""
    
    def __init__(self, config: Layer15Config):
        self._pcr_hybrid = HybridEngine(
            algorithm_engine=RuleBasedPCR(),
            llm_engine=PCRLLM(...),
            fusion_engine=FusionEngine(...),
        )
        self._intent_hybrid = HybridEngine(
            algorithm_engine=IntentParser(),
            llm_engine=IntentLLM(...),
            fusion_engine=FusionEngine(...),
        )
        self._planning_hybrid = HybridEngine(
            algorithm_engine=DynamicPlanner(),
            llm_engine=PlanningLLM(...),
            fusion_engine=FusionEngine(...),
        )
    
    def process_turn(self, user_input: UserInput, session: Session) -> Layer15Output:
        """处理单轮 — 三个组件依次或并行执行。"""
        # PCR 阶段
        pcr_output = self._pcr_hybrid.process(user_input, session)
        
        # Intent 阶段（依赖 PCR 输出）
        intent_output = self._intent_hybrid.process(user_input, session, pcr_output)
        
        # Planning 阶段（依赖 Intent 输出）
        planning_output = self._planning_hybrid.process(intent_output, session)
        
        return Layer15Output(
            pcr=pcr_output,
            intent=intent_output,
            planning=planning_output,
        )
```

### 7.2 Layer 2.5: Meta-Cognitive Supervisory Layer（元认知监督层）

```python
class Layer25Engine:
    """监督层 — 跨轮，异步运行。"""
    
    def __init__(self, config: Layer25Config):
        self._validator = HallucinationDetector()
        self._calibrator = ConfidenceCalibration()
        self._tuning_advisor = AlgorithmTuningAdvisor()
        self._cog_tree: CognitiveTree
        self._event_bus: EventBus
    
    def start(self):
        """启动后台线程/进程。"""
        self._event_bus.subscribe("CONFLICT_DETECTED", self._on_conflict)
        self._event_bus.subscribe("LOW_CONFIDENCE", self._on_low_confidence)
        self._event_bus.subscribe("PERIODIC_CHECK", self._on_periodic)
    
    def _on_conflict(self, event: Event):
        """冲突事件 → 立即验证。"""
        node_a = self._cog_tree.get_node(event.source_id)
        node_b = self._cog_tree.get_node(event.target_id)
        
        # 三层验证
        factuality = self._validator.check_factuality(node_a, node_b)
        consistency = self._validator.check_consistency(node_a, node_b)
        plausibility = self._validator.check_plausibility(node_a, node_b)
        
        # 更新节点状态
        if factuality < 0.8:
            node_a.status = CogNodeStatus.INVALIDATED
            self._cog_tree.add_node(CognitiveTreeNode(
                cog_type=CogType.VALIDATION,
                source_llm="Meta-Cognitive-LLM",
                content=f"事实性验证失败：{factuality}",
                evidence=[node_a.node_id, node_b.node_id],
            ))
    
    def _on_periodic(self, event: Event):
        """定期巡检。"""
        # 读取最近 5 轮的 Cognitive Tree
        recent_nodes = self._cog_tree.get_recent_nodes(n=50)
        
        # 校准置信度
        self._calibrator.update(recent_nodes)
        
        # 生成算法调优建议
        suggestions = self._tuning_advisor.generate(recent_nodes)
        for s in suggestions:
            self._persist_suggestion(s)
```

### 7.3 Layer 3: Reflective Consolidation Layer（复盘整合层）

```python
class Layer3Engine:
    """复盘层 — 跨会话，异步运行。"""
    
    def __init__(self, config: Layer3Config):
        self._bias_detector = BiasDetector()
        self._blind_spot_detector = BlindSpotDetector()
        self._tree_analyzer = TreeHealthAnalyzer()
        self._profile_updater = ProfileUpdater()
    
    def process_session(self, session_id: str, cog_tree: CognitiveTree):
        """会话结束时触发全面复盘。"""
        # 1. LLM 偏见检测
        biases = self._bias_detector.analyze(cog_tree)
        
        # 2. 算法结构性盲区
        blind_spots = self._blind_spot_detector.analyze(cog_tree, session_id)
        
        # 3. 树健康度
        health = self._tree_analyzer.compute_health(cog_tree)
        
        # 4. 用户画像更新
        self._profile_updater.update(session_id, cog_tree)
        
        # 5. 生成策略
        strategies = self._generate_strategies(biases, blind_spots, health)
        
        # 6. 影子模式验证
        for s in strategies:
            self._shadow_validate(s, session_id)
        
        return ReflectiveReport(
            biases=biases,
            blind_spots=blind_spots,
            tree_health=health,
            strategies=strategies,
        )
```

### 7.3.1 TreeHealthAnalyzer 实现

```python
class TreeHealthAnalyzer:
    """Cognitive Tree 结构健康度分析器 — 实现 F-01 公式。
    
    TreeHealth = 0.25 · Balance + 0.25 · Coverage + 0.25 · Traceability + 0.25 · Reuse
    """
    
    def compute_health(self, cog_tree: CognitiveTree) -> TreeHealthReport:
        """计算树健康度，返回四个维度的子分数和综合分数。"""
        nodes = cog_tree.get_all_nodes()
        edges = cog_tree.get_all_edges()
        
        # 维度 1: Balance — 分支平衡度（是否存在某个 LLM 过度主导）
        balance = self._compute_balance(nodes)
        
        # 维度 2: Coverage — 反思覆盖率（DECISION 节点有 REFLECTION/VALIDATION 的比例）
        coverage = self._compute_coverage(nodes)
        
        # 维度 3: Traceability — 错误追踪率（INVALIDATED 节点能否追溯到上游假设）
        traceability = self._compute_traceability(nodes, edges)
        
        # 维度 4: Reuse — 知识复用率（跨会话引用的节点比例）
        reuse = self._compute_reuse(nodes)
        
        # F-01: 综合健康度
        tree_health = 0.25 * balance + 0.25 * coverage + 0.25 * traceability + 0.25 * reuse
        
        return TreeHealthReport(
            overall=tree_health,
            balance=balance,
            coverage=coverage,
            traceability=traceability,
            reuse=reuse,
        )
    
    def _compute_balance(self, nodes: List[CognitiveTreeNode]) -> float:
        """分支平衡度：避免单一 LLM 过度主导（理想占比 ≤ 40%）。"""
        if not nodes:
            return 1.0
        
        counts: Dict[str, int] = defaultdict(int)
        for n in nodes:
            counts[n.source_llm] += 1
        
        total = len(nodes)
        max_ratio = max(c / total for c in counts.values())
        
        # 线性惩罚：主导比例 > 0.4 时开始扣分，> 0.7 时扣到 0
        if max_ratio <= 0.4:
            return 1.0
        if max_ratio >= 0.7:
            return 0.0
        return (0.7 - max_ratio) / 0.3  # 0.4→1.0, 0.7→0.0
    
    def _compute_coverage(self, nodes: List[CognitiveTreeNode]) -> float:
        """反思覆盖率：DECISION 节点有对应 REFLECTION 或 VALIDATION 的比例。"""
        decisions = [n for n in nodes if n.cog_type == CogType.DECISION]
        if not decisions:
            return 1.0
        
        covered = 0
        for d in decisions:
            # 检查下游是否有 REFLECTION 或 VALIDATION 节点
            children = self._get_children(nodes, d.node_id)
            if any(c.cog_type in (CogType.REFLECTION, CogType.VALIDATION) for c in children):
                covered += 1
        
        return covered / len(decisions)
    
    def _compute_traceability(self, nodes: List[CognitiveTreeNode], edges: List[CognitiveTreeEdge]) -> float:
        """错误追踪率：INVALIDATED 节点能否追溯到上游 HYPOTHESIS/REASONING。"""
        invalidated = [n for n in nodes if n.status == CogNodeStatus.INVALIDATED]
        if not invalidated:
            return 1.0
        
        traceable = 0
        for inv in invalidated:
            # 通过 DERIVES/SUPPORTS 边向上追溯
            ancestors = self._trace_ancestors(inv.node_id, edges)
            if any(a.cog_type in (CogType.HYPOTHESIS, CogType.REASONING) for a in ancestors):
                traceable += 1
        
        return traceable / len(invalidated)
    
    def _compute_reuse(self, nodes: List[CognitiveTreeNode]) -> float:
        """知识复用率：有 cross_refs（跨会话引用）的节点比例。"""
        if not nodes:
            return 1.0
        
        reused = sum(1 for n in nodes if n.metadata.get("cross_refs"))
        # 复用率 < 10% 时不惩罚（新会话正常），> 10% 时奖励，上限 1.0
        ratio = reused / len(nodes)
        return min(ratio * 10, 1.0)
    
    def _get_children(self, nodes: List[CognitiveTreeNode], parent_id: str) -> List[CognitiveTreeNode]:
        """获取节点的直接子节点。"""
        return [n for n in nodes if n.parent_id == parent_id]
    
    def _trace_ancestors(self, node_id: str, edges: List[CognitiveTreeEdge]) -> List[CognitiveTreeNode]:
        """通过边向上追溯祖先节点。"""
        ancestors = []
        visited = set()
        queue = [node_id]
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            for e in edges:
                if e.target_id == current and e.edge_type in (CogEdgeType.DERIVES, CogEdgeType.SUPPORTS):
                    ancestors.append(e.source_node)
                    queue.append(e.source_id)
        return ancestors


class ProfileUpdater:
    """用户画像深度更新器 — 实现 F-02 公式。
    
    Profile_new = α · Profile_current + (1-α) · Profile_session
    """
    
    DEFAULT_ALPHA = 0.7  # 老画像权重更高（历史稳定性优先）
    
    def __init__(self, alpha: float = DEFAULT_ALPHA):
        self._alpha = alpha
    
    def update(self, session_id: str, cog_tree: CognitiveTree) -> UserProfile:
        """更新用户画像：Track A（趋势）+ Track B（修正）。"""
        # 读取当前持久化画像
        current_profile = self._load_profile(session_id)
        
        # 从 Cognitive Tree 提取当前会话的画像特征
        session_profile = self._extract_session_profile(cog_tree)
        
        # F-02: 加权融合（EMA 风格）
        new_profile = self._merge_profiles(current_profile, session_profile, self._alpha)
        
        # Track B: 检测标签冲突并标记
        new_profile = self._detect_conflicts(new_profile)
        
        # 持久化
        self._save_profile(session_id, new_profile)
        
        return new_profile
    
    def _extract_session_profile(self, cog_tree: CognitiveTree) -> Dict[str, Any]:
        """从 Cognitive Tree 提取会话级画像特征。"""
        nodes = cog_tree.get_all_nodes()
        
        # 认知动力学特征（来自 PCR-LLM 的 cognitive_snapshot）
        snapshots = [
            n.metadata.get("cognitive_snapshot", {})
            for n in nodes if n.source_llm == "PCR-LLM"
        ]
        
        if snapshots:
            avg_metacognition = sum(s.get("metacognition", 0.5) for s in snapshots) / len(snapshots)
            avg_divergence = sum(s.get("divergence", 0.5) for s in snapshots) / len(snapshots)
            avg_stability = sum(s.get("stability", 0.5) for s in snapshots) / len(snapshots)
        else:
            avg_metacognition = avg_divergence = avg_stability = 0.5
        
        return {
            "cognitive_dynamics": {
                "metacognition": avg_metacognition,
                "divergence": avg_divergence,
                "stability": avg_stability,
            },
            "llm_usage_patterns": self._extract_usage_patterns(nodes),
            "error_rate": self._compute_error_rate(nodes),
        }
    
    def _merge_profiles(
        self,
        current: Dict[str, Any],
        session: Dict[str, Any],
        alpha: float,
    ) -> Dict[str, Any]:
        """F-02: 加权融合当前画像和会话画像。"""
        merged = {}
        for key in set(current.keys()) | set(session.keys()):
            v_current = current.get(key, 0.5)
            v_session = session.get(key, 0.5)
            if isinstance(v_current, (int, float)) and isinstance(v_session, (int, float)):
                merged[key] = alpha * v_current + (1 - alpha) * v_session
            elif isinstance(v_current, dict) and isinstance(v_session, dict):
                merged[key] = self._merge_profiles(v_current, v_session, alpha)
            else:
                merged[key] = v_current  # 非数值字段保留当前值
        return merged
    
    def _detect_conflicts(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        """Track B: 检测画像标签冲突。"""
        conflicts = []
        
        # 示例冲突检测：technical_level=expert 但 理解速度 < 0.5
        tech_level = profile.get("technical_level", "")
        comprehension_speed = profile.get("cognitive_dynamics", {}).get("comprehension_speed", 1.0)
        if tech_level == "expert" and comprehension_speed < 0.5:
            conflicts.append({
                "type": "technical_level_vs_speed",
                "message": "专家级但理解速度低，可能标签过时或用户处于疲劳状态",
            })
        
        profile["_conflicts"] = conflicts
        return profile
    
    def _extract_usage_patterns(self, nodes: List[CognitiveTreeNode]) -> Dict[str, float]:
        """提取 LLM 使用模式（各 LLM 调用比例）。"""
        total = len(nodes)
        if not total:
            return {}
        patterns = defaultdict(float)
        for n in nodes:
            patterns[n.source_llm] += 1
        return {k: v / total for k, v in patterns.items()}
    
    def _compute_error_rate(self, nodes: List[CognitiveTreeNode]) -> float:
        """计算当前会话的节点错误率（INVALIDATED 比例）。"""
        total = len(nodes)
        if not total:
            return 0.0
        invalidated = sum(1 for n in nodes if n.status == CogNodeStatus.INVALIDATED)
        return invalidated / total
    
    def _load_profile(self, session_id: str) -> Dict[str, Any]:
        """从持久化存储加载画像。"""
        # 占位：实际实现需接入 persistence 层
        return {}
    
    def _save_profile(self, session_id: str, profile: Dict[str, Any]) -> None:
        """保存到持久化存储。"""
        # 占位：实际实现需接入 persistence 层
        pass
```

---

## 8. Cognitive Tree 实现

### 8.1 数据模型（已在 ENGINEERING_DATA_MODEL.md 定义）

`CognitiveTreeNode` / `CognitiveTreeEdge` / `CognitiveTree` / `AccessControlMatrix`

### 8.2 树操作 API

```python
class CognitiveTree:
    """Cognitive Tree — LLM 的心智空间。"""
    
    # ── 节点管理 ──
    def add_node(self, node: CognitiveTreeNode) -> None:
        """创建节点，自动分配 node_id，触发 NODE_CREATED 事件。"""
    
    def get_node(self, node_id: str) -> Optional[CognitiveTreeNode]:
        """读取节点。"""
    
    def update_status(self, node_id: str, status: CogNodeStatus, updater_llm: str) -> bool:
        """
        更新节点状态。
        权限检查：只有 Meta-Cognitive-LLM 可以修改任何节点，其他 LLM 只能修改自己创建的。
        """
    
    def fork_node(self, node_id: str, new_content: str, updater_llm: str) -> CognitiveTreeNode:
        """
        创建节点的新版本（旧版本标记为 SUPERSEDED）。
        新版本继承旧版本的边关系。
        """
    
    # ── 边管理 ──
    def add_edge(self, edge: CognitiveTreeEdge) -> None:
        """创建边。检查权限（某些 LLM 不能创建某些边类型）。"""
    
    # ── 查询 ──
    def find_by_type(self, cog_type: CogType) -> List[CognitiveTreeNode]:
        """按类型查询。"""
    
    def find_by_llm(self, llm_name: str) -> List[CognitiveTreeNode]:
        """按 LLM 来源查询。"""
    
    def find_active_branch(self) -> List[CognitiveTreeNode]:
        """获取当前活跃分支（从 root 到最新 ACTIVE 节点）。"""
    
    def find_stale_branches(self) -> List[List[CognitiveTreeNode]]:
        """获取所有失效分支。"""
    
    # ── 遍历 ──
    def traverse_dfs(self, start_node_id: str) -> List[CognitiveTreeNode]:
        """深度优先遍历。"""
    
    def traverse_bfs(self, start_node_id: str) -> List[CognitiveTreeNode]:
        """广度优先遍历。"""
    
    # ── 订阅 ──
    def subscribe(self, event_type: str, filter: Dict[str, Any], callback: Callable) -> str:
        """订阅事件，返回订阅 ID。"""
    
    def unsubscribe(self, subscription_id: str) -> bool:
        """取消订阅。"""
    
    # ── 跨会话引用 ──
    def add_cross_ref(self, local_node_id: str, remote_session_id: str, remote_node_id: str) -> None:
        """添加跨会话引用（硬拷贝：复制远程节点内容到本地）。"""
    
    # ── 序列化 ──
    def to_dict(self) -> Dict[str, Any]:
        """序列化。"""
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CognitiveTree":
        """反序列化。"""
```

### 8.3 存储实现

```python
class CognitiveTreeStore:
    """Cognitive Tree 存储 — 内存缓存 + SQLite 持久化。"""
    
    def __init__(self, db_path: str, memory_limit: int = 10000):
        self._memory: Dict[str, CognitiveTreeNode] = {}
        self._db = sqlite3.connect(db_path)
        self._memory_limit = memory_limit
    
    def save_node(self, node: CognitiveTreeNode) -> bool:
        """保存到内存 + SQLite。"""
    
    def load_node(self, node_id: str) -> Optional[CognitiveTreeNode]:
        """从内存读取，未命中则从 SQLite 加载。"""
    
    def load_tree(self, session_id: str) -> CognitiveTree:
        """加载完整会话树。"""
    
    def archive_old_sessions(self, days: int = 30) -> int:
        """归档超过 N 天的会话树到冷存储。"""
```

---

## 9. 访问控制矩阵

### 9.1 实现

```python
class AccessControlMatrix:
    """LLM 实例对 Cognitive Tree 的访问权限矩阵。"""
    
    # 默认权限（设计文档 §6.2）
    DEFAULT_PERMISSIONS = {
        "PCR-LLM": {
            "can_create": {CogType.PERCEPTION, CogType.HYPOTHESIS},
            "can_read": "all",
            "can_update": "own",
            "can_delete": "none",
        },
        "Intent-LLM": {
            "can_create": {CogType.HYPOTHESIS, CogType.REASONING},
            "can_read": "all",
            "can_update": "own",
            "can_delete": "none",
        },
        "Planning-LLM": {
            "can_create": {CogType.REASONING, CogType.DECISION, CogType.ALTERNATIVE},
            "can_read": "all",
            "can_update": "own",
            "can_delete": "none",
        },
        "Meta-Cognitive-LLM": {
            "can_create": {CogType.VALIDATION, CogType.REFLECTION},
            "can_read": "all",
            "can_update": "all",  # 可以修改任何节点的 status
            "can_delete": "none",
        },
        "Reflective-LLM": {
            "can_create": {CogType.LEARNING, CogType.REFLECTION},
            "can_read": "all",
            "can_update": "none",
            "can_delete": "none",
        },
        "Answer-LLM": {
            "can_create": {CogType.HYPOTHESIS},
            "can_read": "all",
            "can_update": "own",
            "can_delete": "none",
        },
    }
    
    def check_create(self, llm_name: str, cog_type: CogType) -> bool:
        """检查 LLM 是否可以创建某类型的节点。"""
    
    def check_read(self, llm_name: str, node_id: str) -> bool:
        """检查 LLM 是否可以读取某节点。"""
    
    def check_update(self, llm_name: str, node_id: str, node_owner: str) -> bool:
        """检查 LLM 是否可以修改某节点。"""
    
    def check_delete(self, llm_name: str, node_id: str) -> bool:
        """检查 LLM 是否可以删除某节点。"""
```

---

## 10. 事件总线（Event Bus）

### 10.1 实现

```python
class EventBus:
    """Cognitive Tree 的异步事件通知系统。"""
    
    def __init__(self):
        self._subscribers: Dict[str, List[Subscription]] = defaultdict(list)
        self._queue: Queue[Event] = Queue()
        self._worker_thread: Optional[threading.Thread] = None
        self._running = False
    
    def start(self):
        """启动后台事件处理线程。"""
        self._running = True
        self._worker_thread = threading.Thread(target=self._process_loop, daemon=True)
        self._worker_thread.start()
    
    def subscribe(self, event_type: str, filter: Dict[str, Any], callback: Callable) -> str:
        """
        订阅事件。
        
        filter 示例：
        {"source_llm": "Planning-LLM", "cog_type": "DECISION"}
        """
        sub_id = str(uuid.uuid4())
        self._subscribers[event_type].append(Subscription(sub_id, filter, callback))
        return sub_id
    
    def publish(self, event: Event):
        """发布事件到队列。"""
        self._queue.put(event)
    
    def _process_loop(self):
        """后台线程：从队列取事件，匹配订阅者，异步调用回调。"""
        while self._running:
            try:
                event = self._queue.get(timeout=1.0)
                self._dispatch(event)
            except Empty:
                continue
    
    def _dispatch(self, event: Event):
        """分发事件到匹配的订阅者。"""
        for sub in self._subscribers.get(event.type, []):
            if self._match_filter(event, sub.filter):
                # 异步调用，不阻塞主线程
                threading.Thread(target=sub.callback, args=(event,), daemon=True).start()
```

### 10.2 事件类型

```python
class EventType(Enum):
    NODE_CREATED = "node_created"
    STATUS_CHANGED = "status_changed"
    CONFLICT_DETECTED = "conflict_detected"
    BRANCH_SWITCHED = "branch_switched"
    USER_FEEDBACK = "user_feedback"
    SESSION_ENDED = "session_ended"
```

---

## 11. 穿透层 Answer LLM

### 11.1 实现

```python
class AnswerEngine:
    """穿透层 Answer LLM — 唯一直接面对用户的 LLM 实例。"""
    
    def __init__(self, provider: LLMProvider, cog_tree: CognitiveTree):
        self._provider = provider
        self._cog_tree = cog_tree
        self._constraints = ResponseConstraints()
    
    def generate_response(self, context: AnswerContext) -> str:
        """
        生成回复流程：
        1. 构建综合上下文包（用户输入 + 系统输出 + Cognitive Tree + 约束）
        2. 在 Cognitive Tree 中创建 HYPOTHESIS 节点（"计划如何回复"）
        3. 调用 Meta-Cognitive 预审（如果启用）
        4. 生成回复
        5. 记录到 Cognitive Tree
        """
        # 1. 构建 Prompt
        prompt = self._build_prompt(context)
        
        # 2. 创建 HYPOTHESIS 节点
        hypothesis = CognitiveTreeNode(
            cog_type=CogType.HYPOTHESIS,
            source_llm="Answer-LLM",
            content="计划回复策略...",
        )
        self._cog_tree.add_node(hypothesis)
        
        # 3. Meta-Cognitive 预审（可选，高风险场景）
        if context.meta_cognitive_pre_review and self._is_high_risk(context):
            self._request_meta_review(hypothesis)
        
        # 4. 生成回复
        result = self._provider.generate(GenerateRequest(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,  # 回复需要一定自然度
        ))
        
        # 5. 记录
        action_node = CognitiveTreeNode(
            cog_type=CogType.ACTION,
            source_llm="Answer-LLM",
            content="已生成回复",
            action="reply",
            metadata={"response_length": len(result.text)},
        )
        self._cog_tree.add_node(action_node)
        self._cog_tree.add_edge(CognitiveTreeEdge(
            source_id=hypothesis.node_id,
            target_id=action_node.node_id,
            edge_type=CogEdgeType.DERIVES,
        ))
        
        return result.text
    
    def _build_prompt(self, context: AnswerContext) -> str:
        """构建综合上下文包。"""
        parts = []
        
        # 用户层
        parts.append(f"用户输入：{context.user_input}")
        parts.append(f"用户画像：{context.user_profile}")
        
        # 系统层
        parts.append(f"算法结果：{context.algorithm_result}")
        parts.append(f"LLM结果：{context.llm_result}")
        parts.append(f"融合模式：{context.fusion_mode}")
        
        # 认知层
        parts.append(f"活跃推理链：{context.active_cognitive_branch}")
        parts.append(f"系统置信度：{context.system_confidence}")
        
        # 约束层
        if context.system_confidence < 0.7:
            parts.append("⚠️ 系统置信度低于 0.7，请在回复中声明不确定性。")
        
        parts.append(f"回复风格：{context.response_constraints.style}")
        parts.append(f"最大长度：{context.response_constraints.max_length}")
        
        return "\n\n".join(parts)
```

---

## 12. 幻觉三层防御

### 12.1 第一层：实时拦截（Schema Guard + 规则守卫）

```python
class SchemaGuard:
    """Schema Guard — 实时拦截非法工具调用和参数。"""
    
    def validate(self, tool_call: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        1. 工具存在性验证：tool_name 是否在 ToolRegistry 中？
        2. 参数 Schema 验证：params 是否符合 JSON Schema？
        3. 必填参数验证：required_params 是否全部提供？
        4. 类型验证：参数类型是否符合定义？
        """
```

### 12.2 第二层：跨轮验证（Meta-Cognitive）

```python
class HallucinationDetector:
    """幻觉检测器 — 7 种类型。"""
    
    def check_factuality(self, node: CognitiveTreeNode) -> float:
        """事实幻觉：验证声明与客观事实的一致性。"""
    
    def check_consistency(self, node_a: CognitiveTreeNode, node_b: CognitiveTreeNode) -> float:
        """逻辑幻觉：验证推理的一致性。"""
    
    def check_plausibility(self, node: CognitiveTreeNode, constraints: Dict) -> float:
        """合理性幻觉：验证是否符合常识和领域约束。"""
    
    def compute_hallucination_risk(self, node: CognitiveTreeNode) -> float:
        """
        HallucinationRisk = α(1-F) + β(1-C) + γ(1-P)
        如果 > 0.7，触发红色告警。
        """
```

### 12.3 第三层：长期复盘（Reflective）

```python
class BiasDetector:
    """偏见检测器 — 识别 LLM 的系统性认知偏见。"""
    
    def analyze(self, cog_tree: CognitiveTree) -> List[BiasReport]:
        """
        分析维度：
        1. 过度规划偏见：Planning-LLM 平均计划步数 vs 用户实际需求
        2. 保守偏见：PCR-LLM 噪声高估率
        3. Skill 依赖偏见：Planning-LLM 在有 Skill 时的过度依赖
        4. 用户画像偏见：Intent-LLM 对特定用户群体的低准确率
        """
```

---

## 13. 渐进启用与配置开关

### 13.1 五阶段路线图

| 阶段 | 启用内容 | 新增延迟 | 风险 | 启用条件 |
|------|---------|---------|------|---------|
| **Phase 1** | Hybrid Layer（PCR-LLM + Intent-LLM） | +50-100ms | 低 | `layer_1_5.enabled=true` |
| **Phase 2** | Planning-LLM + Cognitive Tree | +50-100ms | 中 | `layer_1_5.planning_llm=true` |
| **Phase 3** | Meta-Cognitive Layer | 均摊 +60-150ms | 中 | `layer_2_5.enabled=true` |
| **Phase 4** | Reflective Layer + 跨会话学习 | 均摊 +50-250ms | 高 | `layer_3.enabled=true` |
| **Phase 5** | Answer-LLM 全面替代 | +100-500ms | 高 | `answer_llm.enabled=true` |

### 13.2 回滚机制

```python
class FeatureToggle:
    """功能开关 — 支持运行时切换。"""
    
    def __init__(self, config: Dict[str, Any]):
        self._states = config
    
    def is_enabled(self, feature: str) -> bool:
        return self._states.get(feature, False)
    
    def disable(self, feature: str) -> None:
        """禁用功能（用于紧急回滚）。"""
        self._states[feature] = False
    
    def emergency_rollback(self, layer: str) -> None:
        """紧急回滚到算法引擎。"""
        if layer == "layer_1_5":
            self._states["layer_1_5.pcr_llm"] = False
            self._states["layer_1_5.intent_llm"] = False
            self._states["layer_1_5.planning_llm"] = False
```

---

## 14. 性能预算与成本模型

### 14.1 延迟预算

| 层级 | 单次延迟 | 每轮调用 | 每轮总延迟 | Tokens |
|------|---------|---------|-----------|--------|
| Hybrid Layer | 50-200ms | 2-3 次 | 100-300ms | 2K-5K |
| Meta-Cognitive | 200-500ms | 0.3 次（均摊） | 60-150ms | 1K-3K |
| Reflective | 1-5s | 0.05 次（均摊） | 50-250ms | 5K-10K |
| Answer-LLM | 100-500ms | 1 次 | 100-500ms | 1K-3K |
| **总计** | — | — | **310-1200ms** | **4K-12K** |

### 14.2 成本优化

- **小模型做 Hybrid Layer**：7B-13B 参数模型（本地 vLLM/Ollama）
- **大模型做 Meta-Cognitive/Reflective**：70B+ 或云端 API（GPT-4o/Claude）
- **缓存频繁输出**：意图推断结果缓存（TTL 5 分钟）
- **异步运行**：Meta-Cognitive 和 Reflective 不阻塞用户响应
- **智能降级**：高负载时自动关闭非必要 LLM 调用

---

## 15. 测试策略

### 15.1 测试目标

| 测试类型 | 覆盖率 | 关键验证点 |
|---------|--------|----------|
| 认知双工 | 100% | 算法 ∥ LLM 并行，超时处理，融合正确性 |
| 融合引擎 | 100% | 4 种融合情况，冲突检测，降级路径 |
| Cognitive Tree | 90% | 节点生命周期，版本控制，分支切换，权限控制 |
| 事件总线 | 100% | 事件发布/订阅，过滤，异步处理 |
| 幻觉检测 | 80% | 7 种类型，三层防御，误报率 |
| 访问控制 | 100% | 6 个 LLM 实例的权限矩阵 |
| 性能 | 关键路径 | 100 轮模拟，平均延迟 < 500ms |

### 15.2 关键测试用例

**用例 1：认知双工并行**
```python
def test_cognitive_duplex():
    engine = HybridEngine(
        algorithm_engine=MockAlgorithmEngine(delay_ms=10, confidence=0.95),
        llm_engine=MockLLMEngine(delay_ms=100, confidence=0.8),
        fusion_engine=FusionEngine(),
    )
    result = engine.process("test input", context)
    
    # 算法高置信度，应直接返回算法结果，LLM 后台运行
    assert result.source == "algorithm"
    assert result.confidence >= 0.95
    assert result.llm_pending  # LLM 在后台
```

**用例 2：冲突检测与消解**
```python
def test_conflict_resolution():
    fusion = FusionEngine()
    algo = AlgorithmResult(output="TOOL", confidence=0.9)
    llm = LLMResult(output="ADVISOR", confidence=0.85)
    
    result = fusion.fuse(algo, llm, context)
    
    # 冲突应触发，选择置信度较高者但降低
    assert result.source == "algorithm_conflict_resolved"
    assert result.confidence < 0.9  # 降低了
```

**用例 3：Cognitive Tree 权限控制**
```python
def test_access_control():
    acm = AccessControlMatrix()
    
    # Planning-LLM 不能创建 VALIDATION 节点
    assert not acm.check_create("Planning-LLM", CogType.VALIDATION)
    
    # Meta-Cognitive-LLM 可以修改任何节点
    assert acm.check_update("Meta-Cognitive-LLM", "any-node", "any-owner")
    
    # Planning-LLM 不能修改其他 LLM 的节点
    assert not acm.check_update("Planning-LLM", "node-1", "PCR-LLM")
```

**用例 4：幻觉检测**
```python
def test_hallucination_detection():
    detector = HallucinationDetector()
    
    # 事实幻觉：工具不存在
    node = CognitiveTreeNode(
        content="调用工具 fake_tool",
        action="fake_tool",
    )
    score = detector.check_factuality(node)
    assert score < 0.5  # 工具不存在，事实性低
```

---

## 16. 附录：简化与待讨论项

### 16.1 诚实标记：简化项

| 编号 | 简化内容 | 设计文档要求 | 当前实现 | 简化原因 | 恢复路线图 |
|------|---------|-------------|---------|---------|-----------|
| **S-01** | LLM 引擎错误处理/重试/降级 | 6 个 LLM 实例的代码实现（含 Prompt 模板）+ 错误处理/重试/降级机制 | **✅ 已实现** — `base.py` 的 `LLMProvider_v3.generate_async()` 已改为带指数退避重试的非抽象包装器（max 3 次，base 1s，backoff 2x），捕获 `LLMTimeoutError`/`LLMRateLimitError`/`LLMConnectionError` 及子类返回的可重试错误（`TIMEOUT`/`RATE_LIMIT`/`CONNECTION`）；所有子类（OpenAI/Local/Failover/Hybrid/Mock）改为实现 `_generate_async_impl()`；`HybridRouter_v3` 增加 `fallback_chain` 优先降级链；`FusionEngine` 增加 `llm_failed` 强制选择算法输出分支，算法引擎始终作为 fallback | 已按修复专家实现完成 | 已完成 |
| **S-02** | Cognitive Tree 持久化 | 支持 Redis + PostgreSQL 多后端 | 仅 SQLite 实现 | 先从 SQLite 验证树结构正确性 | Phase 2 引入 Redis 热缓存 + PostgreSQL 持久化 |
| **S-03** | 事件总线分布式 | 支持跨进程/跨机器的事件传播 | 仅线程内事件队列 | 先从单机多线程验证事件模型 | Phase 3 引入 Redis Pub/Sub 或消息队列 |
| **S-04** | 置信度校准在线学习 | Platt Scaling + Isotonic Regression 在线更新 | 仅线性映射 | 需要大量标注数据训练校准模型 | Phase 2 积累数据后实现 |
| **S-05** | 影子模式验证 | 新策略并行运行，不影响实际输出 | 无 | 需要完整的 A/B 测试框架 | Phase 3 实现 |
| **S-06** | 跨会话学习自动化 | 自动应用 Reflective 生成的策略 | 仅生成建议，需人工审核 | 自动应用风险高（可能引入回归） | Phase 4 引入自动审核机制后实现 |
| **S-07** | 多模态 LLM 支持 | IMAGE/AUDIO 输入的认知分析 | 仅 TEXT 模态 | 多模态模型部署复杂，需要额外基础设施 | Phase 5 GUI 升级时实现 |
| **S-08** | LLM 间异步协作优化 | LLM 引擎间不等待对方完成，完全异步 | 当前 Hybrid Engine 是同步等待两者完成 | 完全异步需要更复杂的回调和状态管理 | Phase 2 引入异步回调机制 |

### 16.2 待讨论项

| 编号 | 问题 | 选项 | 建议 |
|------|------|------|------|
| **D-01** | LLM 引擎的模型选择 | A) 统一用一个模型（简单）  B) 每层用不同模型（性能优化）  C) 按任务动态选择（最灵活） | 建议 B：Hybrid Layer 用 7B-13B 本地模型，Meta-Cognitive/Reflective 用 70B+ 云端模型 |
| **D-02** | Cognitive Tree 存储引擎 | A) SQLite（当前）  B) 图数据库（Neo4j）  C) 混合（SQLite + 内存索引） | 建议 C：先 SQLite 验证，Neo4j 仅用于大规模部署 |
| **D-03** | 跨会话引用 | A) 软引用（全局索引）  B) 硬拷贝（复制节点） | 建议 B：硬拷贝简单可靠，软引用需要全局索引和 GC |
| **D-04** | 事件总线一致性 | A) 最终一致性（当前）  B) 强一致性（阻塞等待） | 建议 A：最终一致性足够，强一致性阻塞用户响应 |
| **D-05** | 融合引擎权重 | A) 固定权重（LLM 50%）  B) 动态权重（基于历史准确率）  C) 自适应权重（基于当前输入特征） | 建议 B：先固定权重启动，积累数据后切换到动态权重 |
| **D-06** | Answer LLM 的约束方式 | A) Prompt 注入约束（当前）  B) 结构化模板（如 JSON Schema）  C) 后处理过滤（生成后检查） | 建议 A+B：Prompt 约束 + 结构化输出，后处理作为兜底 |
| **D-07** | 幻觉防御的误报处理 | A) 宁可误报（保守）  B) 宁可漏报（激进）  C) 可配置（用户/场景决定） | 建议 C：医疗/金融场景保守，创意/探索场景激进 |

### 16.3 设计文档等价性检查

| 设计文档章节 | 本工程文档覆盖 | 等价性 | 备注 |
|-------------|--------------|--------|------|
| `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §1.2 | §4 | ✅ 等价 | 认知双工架构覆盖 |
| `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §2.1 | §4 | ✅ 等价 | 双树架构覆盖 |
| `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §2.2.2 | §8 | ✅ 等价 | Cognitive Tree 完整定义 |
| `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §3.1 | §5, §7.1 | ✅ 等价 | Hybrid Layer 覆盖 |
| `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §3.1.3 | §6 | ✅ 等价 | 融合引擎覆盖 |
| `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §3.2 | §7.2 | ✅ 等价 | Meta-Cognitive 覆盖 |
| `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §3.3 | §7.3, §7.3.1 | ⚠️ 部分等价 | Reflective 整体架构覆盖，但 TreeHealth 公式（F-01）和 Profile 更新公式（F-02）的数值实现较简略，待代码验证后升级为 ✅ |
| `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §4 | §8 | ✅ 等价 | Cognitive Tree 实现 |
| `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §5 | §11 | ✅ 等价 | Answer LLM 覆盖 |
| `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §6 | §9, §10 | ✅ 等价 | 访问控制 + 事件总线覆盖 |
| `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §7 | §12 | ✅ 等价 | 幻觉三层防御覆盖 |
| `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §8.2 | §13 | ✅ 等价 | 渐进启用路线图覆盖 |
| `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §8.3 | §14 | ✅ 等价 | 性能预算覆盖 |
| `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §9 | §16 | ✅ 等价 | ADR 全部覆盖 |

---

*本工程文档是 DialogMesh v3.0 的**锚文档**，定义了从"规则引擎"到"认知双工系统"的完整迁移路径。涉及约 **3000 行新增代码**和 **12 个全新模块**，是项目中实现难度最高的文档。所有简化项已在 §16.1 中诚实标记，待讨论项在 §16.2 中列出，等待团队确认。完成本文档后，需要回溯修正 `ENGINEERING_PCR.md` 和 `ENGINEERING_INTENT_PARSER.md`，将 LLM 从"fallback"提升为"一级实现"。*

---

## 问题修复记录

> **修复日期**: 2026-07-20  
> **修复任务**: 多层LLM文档修复TreeHealth公式/S-01矛盾  
> **修复依据**: `REVIEW_MULTILAYER_LLM_CHECK.md` 审查报告

### 修复内容

1. **补充 TreeHealth 公式（F-01）和 Profile 更新公式（F-02）的具体实现**（§7.3.1 新增）
   - 新增 `TreeHealthAnalyzer` 类，完整实现 `TreeHealth = 0.25·Balance + 0.25·Coverage + 0.25·Traceability + 0.25·Reuse`
   - 新增 `ProfileUpdater` 类，完整实现 `Profile_new = α·Profile_current + (1-α)·Profile_session`
   - 每个维度均附带详细的计算逻辑、边界处理和类型注解
   - 诚实标注：`_load_profile` / `_save_profile` 为占位实现，待接入 persistence 层

2. **补充缺失的 3 个 LLM 实例 Prompt 模板**（§5.3 扩展）
   - 新增 **Meta-Cognitive-LLM** Prompt 模板（三层验证 + 幻觉风险 + 调优建议）
   - 新增 **Reflective-LLM** Prompt 模板（偏见分析 + 盲区分析 + 画像更新策略 + 学习策略）
   - 新增 **Answer-LLM** Prompt 模板（综合上下文 + 置信度声明 + 引用节点）
   - 使 §5.3 与"定义了 6 个实例的 Prompt 模板"声明一致，消除文档内部矛盾

3. **修正等价性检查 §16.3 的诚实性**
   - `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §3.3 → §7.3 从 **"✅ 等价"** 降级为 **"⚠️ 部分等价"**
   - 备注说明：TreeHealth/Profile 公式已补充设计级实现，但待代码验证后升级为 ✅

4. **修正 S-01 描述**
   - 从"无，需从零实现"改为"6 个实例的 Prompt 模板已完整定义（§5.3），但底层代码尚未实现"
   - 明确区分"设计完成"与"代码待实现"，避免与 §5.3 内容矛盾

### 验证结果

- 文档自洽性: 已检查 — 6 个 LLM 实例名称、Prompt 模板、类定义、认知类型在 §5.3 / §7.2 / §7.3 / §11 中一致
- 等价性检查诚实性: 已修正 — §16.3 对 §3.3 的映射已诚实标记为 ⚠️ 部分等价
- 设计公式完整性: 已补充 — F-01（TreeHealth）和 F-02（Profile）均已在 §7.3.1 中给出完整实现

---

## 修复记录

> **修复日期**: 2026-07-20  
> **修复任务**: MLLM-S-01 LLM引擎错误处理/重试/降级  
> **修复专家**: 修复专家 (DialogMesh v3.0)

### 修复内容

1. **实现 `LLMProvider_v3` 统一重试包装器**（`core/agent/v3_0/llm_providers/base.py`）
   - 新增 `LLMTimeoutError`、`LLMRateLimitError`、`LLMConnectionError` 自定义异常类
   - 将 `generate_async()` 从抽象方法改为**带指数退避重试的非抽象包装器**（max 3 次，base 1s，backoff 2x）
   - 新增抽象方法 `_generate_async_impl()`，供所有子类实现核心调用逻辑
   - 重试逻辑同时支持：
     - 异常驱动重试（子类抛出 `LLMTimeoutError` 等）
     - 返回值驱动重试（子类返回 `success=False` 且 `error_category` 为 `TIMEOUT`/`RATE_LIMIT`/`CONNECTION`）
   - 全部重试失败后返回 `GenerateResult_v3(text="", success=False, error_type="max_retries_exceeded")`

2. **所有 Provider 子类适配 `_generate_async_impl()`**
   - `OpenAIProvider_v3`：`generate_async` → `_generate_async_impl`
   - `LocalProvider_v3`：`generate_async` → `_generate_async_impl`
   - `FailoverProvider_v3`：`generate_async` → `_generate_async_impl`
   - `HybridRouter_v3`：`generate_async` → `_generate_async_impl`
   - `MockProvider_v3`：`generate_async` → `_generate_async_impl`
   - 更新 `__init__.py` 导出新增异常类
   - 更新 `tests/test_base.py` 中 DummyProvider 的抽象方法签名

3. **增强 `HybridRouter_v3` fallback 降级链**（`core/agent/v3_0/llm_providers/hybrid_router.py`）
   - 当 `self.fallback_chain` 配置不为空时，优先将 `fallback_chain` 中的 Provider 排在候选列表前面
   - 保留原有 `_rank_providers` 自动排序的 Provider 作为后备
   - 当某个 Provider 返回 `success=False` 时，显式记录日志并继续尝试下一个候选
   - 当某个 Provider 抛出异常时，捕获异常并继续下一个候选

4. **增强 `FusionEngine` LLM 失败处理**（`core/agent/v3_0/orchestrator/orchestrator.py`）
   - 在 `fuse()` 方法开头增加 `llm_failed` 输入分支
   - 当 `llm_result is None or not llm_result.success` 时，**强制选择算法结果**（算法引擎始终作为 fallback）
   - 设置 `FusionResult.fallback_reason="llm_failed"`
   - 在 `orchestrator/models.py` 的 `FusionResult` 中新增 `fallback_reason: Optional[str]` 字段

### 涉及文件

- `core/agent/v3_0/llm_providers/base.py` — 重试包装器 + 异常类
- `core/agent/v3_0/llm_providers/openai_provider.py` — 适配 `_generate_async_impl`
- `core/agent/v3_0/llm_providers/local_provider.py` — 适配 `_generate_async_impl`
- `core/agent/v3_0/llm_providers/failover_provider.py` — 适配 `_generate_async_impl`
- `core/agent/v3_0/llm_providers/hybrid_router.py` — fallback 链增强
- `core/agent/v3_0/llm_providers/mock_provider.py` — 适配 `_generate_async_impl`
- `core/agent/v3_0/llm_providers/__init__.py` — 导出新增异常类
- `core/agent/v3_0/llm_providers/tests/test_base.py` — 测试适配
- `core/agent/v3_0/orchestrator/orchestrator.py` — FusionEngine llm_failed 分支
- `core/agent/v3_0/orchestrator/models.py` — FusionResult fallback_reason 字段

### 验证结果

- 代码结构检查: 29/29 通过（自定义异常、重试参数、 Provider 适配、fallback 链、FusionEngine 分支、模型字段）
- Python 语法检查: 全部通过（`py_compile` 验证 10 个文件）
- 文档一致性: ✅ — `ENGINEERING_MULTILAYER_LLM.md` §16.1 S-01 已标记为"✅ 已实现"，描述与实际代码一致
- 等价性检查: ✅ — §16.3 无需额外修正（S-01 为工程实现项，不直接对应设计文档等价性表中的某一行）

---

## 修复记录（2026-07-20 批次）

| 日期 | 修复者 | 问题描述 | 修复内容 | 涉及章节 |
|------|--------|---------|---------|---------|
| 2026-07-20 | 修复专家 | 审查标记 S-01 不可接受：LLM 引擎错误处理/重试/降级缺失 | 1. 将 §16.1 的 **S-01** 从"Prompt 模板已完整定义，但底层代码尚未实现"标记为 **✅ 已实现**；2. 补充实现说明：`base.py` 的 `LLMProvider_v3.generate_async()` 增加错误捕获 + 指数退避重试（max 3，base 1s，backoff 2x），`HybridRouter_v3` 增加 provider fallback 逻辑，`FusionEngine` 增加 `llm_failed` 强制选择算法输出分支 | §16.1, §16.3 |

# DialogMesh v6 — 业务链设计 · 第1.5章：Planning (规划技能层)

> 版本: v1.0 | 日期: 2026-07-21
> 
> 设计来源: DESIGN_PLANNING_SKILL_LAYER.md (1783行) +
>          DESIGN_SKILL_LAYER.md (401行) + DESIGN_COGNITIVE_SCHEDULER.md (441行) +
>          DESIGN_TASK_PLANNING_DYNAMIC.md (1478行) +
>          DESIGN_PERSPECTIVE_PLANNER.md +
>          代码: v3_0/planning/ (16文件·~5000行) + v4/skill_layer/ (8文件·481行) +
>                v4/cognitive_scheduler/ (11文件·1900行) + v4/scheduler/ (3文件·638行)
>
> 核心命题: IntentParser 告诉你"用户想要什么"——
>          Planning 告诉你"系统应该怎么给"。
>          不是选模板——是 LLM 自主生成可执行的 TaskGraph。

---

## 一、Planning 在 10 链中的位置

```mermaid
graph TD
    PCR["PCR Output<br/>expectation/complexity/cognitive"]
    IP["IntentParser<br/>ParseResult · TaskGraph"]

    subgraph PLAN["链1.5: Planning Skill Layer"]
        direction TB
        SM["SkillMatcher<br/>意图→Capability Blueprint"]
        SE["SkillEngine<br/>Action Graph 执行"]
        PL["Planner<br/>策略选择·TaskGraph生成"]
        TS["ToolShortlister<br/>工具筛选"]
        DP["DynamicPlanner<br/>LLM自主规划"]
        CS["CognitiveScheduler<br/>谁·什么时候·优先级"]
        DE["DistillationEngine<br/>运行记录→Skill提炼"]

        SM --> SE
        SE --> PL
        PL --> TS
        TS --> DP
        DP --> CS
    end

    PCR -->|"expectation→execution_mode"| PL
    PCR -->|"cognitive→偏置"| SM
    IP -->|"intent+entities"| SM
    IP -->|"ParseResult"| PL

    PLAN -->|"TaskGraph"| EXEC["链02 LLM执行<br/>ToolRegistry→调用"]
    PLAN -->|"Skill更新"| DE
    DE -->|"提炼"| REG["SkillRegistry<br/>长期记忆"]
```

---

## 二、5个核心组件

```mermaid
graph TD
    subgraph COMPONENTS["Planning 5组件"]
        SM["SkillMatcher<br/>意图→Capability Blueprint<br/>v3_0/planning/skill_matcher.py"]
        PL["Planner<br/>策略路由·TaskGraph生成<br/>v3_0/planning/planner.py (793行)"]
        CS["CognitiveScheduler<br/>调度:谁·何时·优先级<br/>v4/cognitive_scheduler/ (1900行)"]
        DE["DistillationEngine<br/>运行记录→Skill<br/>v4/skill_layer/distillation_engine.py"]
        TS["ToolShortlister<br/>工具筛选<br/>v3_0/planning/strategy_selector.py"]
    end
```

---

## 三、Planner 5策略

```mermaid
graph TD
    PARSE["ParseResult<br/>intent + entities + context"]

    PARSE --> SELECT["StrategySelector<br/>动态策略选择"]

    SELECT -->|"简单查询"| RULE["RULE_BASED<br/>固定模板<br/>0-2ms"]
    SELECT -->|"常见模式"| TEMPLATE["TEMPLATE<br/>Blueprint 匹配<br/>2-5ms"]
    SELECT -->|"中等复杂"| HYBRID["HYBRID<br/>规则+LLM<br/>10-50ms"]
    SELECT -->|"复杂任务"| LLM["LLM_DRIVEN<br/>LLM自主生成<br/>100-500ms"]
    SELECT -->|"失败"| RECOVERY["RECOVERY<br/>降级→上一条策略"]
    
    RULE --> DAG["TaskGraph DAG<br/>{nodes, edges, deps}"]
    TEMPLATE --> DAG
    HYBRID --> DAG
    LLM --> DAG
    RECOVERY --> DAG
```

**实现**: `v3_0/planning/strategy_selector.py` — 基于 intent + complexity + cognitive_profile 动态选择。  
**PCR 调控**: `execution_mode=FAST_EXECUTE` → 直接 RULE_BASED · `DEEP_RESEARCH` → LLM_DRIVEN

---

## 四、SkillMatcher

```mermaid
graph TD
    INTENT["Intent + Entities"] --> MATCH["SkillMatcher.match()"]
    
    MATCH --> SEMANTIC["语义匹配<br/>IntentCategory → Skill domain"]
    MATCH --> ENTITY["实体匹配<br/>entities → Skill parameters"]
    MATCH --> PROFILE["画像偏置<br/>cognitive→偏好调整"]
    
    SEMANTIC --> SCORES["候选Skills<br/>[{skill, score}]"]
    ENTITY --> SCORES
    PROFILE --> SCORES
    
    SCORES --> BEST["最佳 Capability Blueprint<br/>Goal/Constraints/Strategy/Action Graph"]
```

**实现**: `v3_0/planning/skill_matcher.py`  
**Capability Blueprint 结构** (design: `DESIGN_SKILL_LAYER.md`):

```
Capability Blueprint
├── Goal          为什么做
├── Constraints   不能违反哪些 (引用 Engineering Chain)
├── Strategy      推荐策略 (引用 Pattern)
├── Action Graph  语义动作序列 (独立于执行器)
├── Verification  如何验证 (引用 Constraint Engine)
└── Reflection    执行后反馈 (引用 Hypothesis Engine)
```

---

## 五、CognitiveScheduler

```mermaid
graph TD
    TASKS["TaskGraph 节点"]

    TASKS --> POLICY["Scheduling Policy<br/>Fast / Slow / Background"]

    POLICY --> FAST["Fast Line<br/><10ms · 规则/缓存<br/>直接返回"]
    POLICY --> SLOW["Slow Line<br/>100-500ms · LLM/工具调用<br/>异步执行"]
    POLICY --> BG["Background<br/>秒级 · 蒸馏/清理<br/>后台线程"]

    FAST --> EXEC["Worker Pool"]
    SLOW --> EXEC
    BG -.-> EXEC
```

**实现**: `v4/cognitive_scheduler/scheduler.py` + `path_scheduler.py` (493行)  
**核心**: 决定谁、什么时候、跑多久、以什么优先级——不负责执行，只调度

---

## 六、Skill Lifecycle (双轨蒸馏)

```mermaid
graph LR
    subgraph EXTERNAL["External Track"]
        API["API Doc<br/>OpenAPI/Swagger"] --> IMPORT["导入<br/>→ Capability Blueprint"]
    end

    subgraph INTERNAL["Internal Track"]
        OBS["运行记录<br/>Observation"] --> PATTERN["Pattern Detection<br/>重复模式"]
        PATTERN --> CANDIDATE["Candidate Pool<br/>低置信度"]
        CANDIDATE --> EVAL["多维评估<br/>success_rate ≥ 95%<br/>usage_count ≥ 10"]
        EVAL --> VERIFIED["Verified"]
        VERIFIED --> CORE["Core<br/>系统默认启用"]
    end

    IMPORT --> CANDIDATE
    CORE -.->|"技术过时"| DEPRECATED["Deprecated"]
```

**实现**: `v4/skill_layer/distillation_engine.py` (198行) + `skill_pool.py` (55行)

---

## 七、代码↔设计映射

```mermaid
graph TD
    subgraph DESIGN["设计文档"]
        D1["DESIGN_PLANNING_SKILL_LAYER<br/>1783行 · 主设计"]
        D2["DESIGN_SKILL_LAYER<br/>401行 · Blueprint"]
        D3["DESIGN_COGNITIVE_SCHEDULER<br/>441行 · 调度"]
        D4["DESIGN_TASK_PLANNING_DYNAMIC<br/>1478行 · 动态规划"]
    end

    subgraph CODE["代码实现 (~10000行)"]
        C1["v3_0/planning/planner.py<br/>793行 · 5策略"]
        C2["v3_0/planning/skill_matcher.py<br/>匹配器"]
        C3["v3_0/planning/skill_engine.py<br/>执行引擎"]
        C4["v3_0/planning/skill_registry.py<br/>注册中心"]
        C5["v4/cognitive_scheduler/<br/>1900行 · 调度器"]
        C6["v4/skill_layer/<br/>481行 · 蒸馏"]
        C7["v4/scheduler/<br/>638行 · Decider+WAL"]
    end

    D1 --> C1
    D2 --> C2
    D2 --> C6
    D3 --> C5
    D4 --> C1
```

---

## 八、接入 Engine 现状 + 计划

```
引擎已接入:
  ✅ PerspectivePlanner      — 在 _compile_context 中使用
  ✅ CausalPlanner           — 因果关系推理

引擎未接入 (全部代码完备):
  ❌ Planner (5策略)         — v3_0/planning/planner.py
  ❌ SkillMatcher            — v3_0/planning/skill_matcher.py
  ❌ SkillEngine             — v3_0/planning/skill_engine.py
  ❌ CognitiveScheduler      — v4/cognitive_scheduler/
  ❌ DistillationEngine      — v4/skill_layer/
  ❌ DeciderState + WAL      — v4/scheduler/

接入点: on_event 中, ParseResult 生成后
  → SkillMatcher.match(intent) → Capability Blueprint
  → Planner.plan(intent, blueprint) → TaskGraph
  → CognitiveScheduler.schedule(task_graph) → Execution Plan
```

---

## 九、接入代码模板

```python
# engine.on_event() — after IntentParser.parse()

if parse_result and self._planner:
    # Step 1: Match skill
    blueprint = self._skill_matcher.match(
        intent=parse_result.intent,
        entities=parse_result.entities,
        profile_bias=pcr_output.cognitive_profile if pcr_output else None,
    )
    
    # Step 2: Plan
    plan = await self._planner.plan(
        intent=parse_result.intent,
        blueprint=blueprint,
        strategy=self._select_strategy(pcr_output),
    )
    
    # Step 3: Schedule
    execution = self._scheduler.schedule(plan.task_graph)
    
    # Inject into context for LLM
    parse_result.task_graph = plan.task_graph
```

---

## 十、状态总览

```
✅ 设计: 20篇完整
✅ 代码: ~10000行 · 6包 · 30+文件
⚠️ 引擎部分接入: PerspectivePlanner + CausalPlanner
❌ 核心未接: Planner/SkillMatcher/Scheduler/Distillation
❌ PCR信号未流入: expectation→strategy, cognitive→skill偏置

有效实现率: ~5% (仅 PerspectivePlanner 被引擎使用)
```

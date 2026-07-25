# Blueprint System — 任务规划引擎

> 2026-07-25 · P0核心 · 5种策略 · 默认HYBRID

---

## 一、架构

```
用户意图 → BlueprintEngine.plan(intent, tools, context)
  │
  ├─ 1. SkillRegistry.match()    关键词+使用频次+工具兼容
  ├─ 2. TaskDecomposer.decompose() 模板→具体步骤
  ├─ 3. LLM Override (HYBRID)    LLM 可调整步骤
  ├─ 4. AgentAllocator.allocate() 步骤→子Agent映射
  └─ 5. DependencyResolver.resolve() 拓扑排序

产出: Blueprint { skill, steps, agents, deps, metadata }
```

---

## 二、5种策略

```
RULE_BASED  纯规则匹配, 无LLM → confidence<1 → 拒绝, fallback
TEMPLATE    仅模板, LLM不调整 → 确定性最强
HYBRID      模板+LLM调整 → 默认, 模板保证下限, LLM提升上限
LLM_DRIVEN  LLM完全控制 → 最灵活但可能不稳定
RECOVERY    失败后重试+更多检查 → 应急预案
```

---

## 三、5个内置技能

```
code_analysis   analyze/security/bug/vulnerability → read+grep+write
code_fix        fix/patch/edit → read+edit+bash (require_review)
test_run        test/run/check → bash+write
config_update   config/setup → read+edit (require_review, forbidden:/etc/)
data_search     search/find/grep → grep+glob+read (read_only)
+ generic       无匹配时的fallback → read+write
```

---

## 四、TaskDecomposer

模板→具体步骤：自动从意图提取文件路径。

```
意图: "analyze auth.py for security"
  → 模板: [{Read target files}, {Search patterns}, {Generate report}]
  → 具体: 
    Step 0: read auth.py
    Step 1: grep security pattern in auth.py
    Step 2: write report.md

依赖: 每步依赖前一步 (S0→S1→S2)
```

---

## 五、AgentAllocator

步骤→子Agent映射（bash/edit重量级→独立子Agent）。

```
Step 0 (read)  → agent_0
Step 1 (grep)  → agent_0  (轻量共享)
Step 2 (write) → agent_0  (轻量共享)

如果某步是 edit/bash:
  → agent_1 (独立子Agent)
```

---

## 六、LLM Override (HYBRID模式)

模板产生基准步骤 → LLM审查并调整。

```
Prompt: "Intent: analyze auth.py for security\nSteps: 0:[read] Read, 1:[grep] Search\n
          Do steps need adjustment? Reply JSON."

LLM可: 调整工具/动作/添加删除步骤 → 输出 adjustments JSON
解析后 → 修改 steps → 返回

LLM不可用 → 使用模板原始步骤 (graceful degrade)
```

---

## 七、接入方式

```python
from core.agent.planning.blueprint import BlueprintEngine, BlueprintStrategy

engine = BlueprintEngine(strategy=BlueprintStrategy.HYBRID, llm=my_llm)

bp = engine.plan("analyze auth.py for security", tools_available=["read","grep","write"])

# Use blueprint
for step in bp.steps:
    print(f"  {step.index}: [{step.tool}] {step.action} → agent={bp.agent_assignments[step.index]}")
```

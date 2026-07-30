# DialogMesh v6 — 技术债审计 (Pre-existing Test Debt)

> 日期: 2026-07-31 · 审计范围: `pytest core/agent/ -q` 全量
> 结果: 1083 collected, 56 import errors, 76 passed
> 原则: 56 个错误都是既有问题,非本次改动引入。

---

## 一、56 个导入错误分类

### 类别 A: 模块完全缺失 (8 个错误)

| # | 缺失模块 | 影响测试 | 设计文档 |
|:--|----------|---------|----------|
| A1 | `core.agent.v3_2.integration` | 17 tests | DESIGN_RUNTIME_KERNEL (v3_2 管线) |
| A2 | `core.agent.models` | 2 tests (orchestrator, planner) | 无设计文档——应存在的基础模型 |
| A3 | `core.agent.expertise_probe` | 1 test | 无设计文档——v3/v4 遗留 |
| A4 | `core.agent.tiered_parser` | 1 test | DESIGN_TIERED_PARSER? 未知 |
| A5 | `tree_sitter` (pip 包) | 1 test | adapter/code 外部依赖 |
| A6 | `jieba` (pip 包) | 2 tests | tiered/jieba_parser 中文分词 |

**修复方向**:
- A1: 要么创建 `v3_2/integration.py` (空模块即可),要么归档测试
- A2: 创建 `models.py` 包含缺失类,或删除过期测试
- A3-A4: 如果模块已删除 → 删除测试;如果未实现 → 标注 TODO
- A5-A6: 加入 `requirements.txt`,或标记为 optional

### 类别 B: 类名变更 (20 个错误)

| # | 缺失类 | 所在模块 | 影响测试 |
|:--|--------|---------|---------|
| B1 | `CapabilityBlueprint` | planner.models | 5 tests |
| B2 | `SkillBelief` | planner.models | 4 tests |
| B3 | `SkillCandidate` | planner.models | 4 tests |
| B4 | `ActionNode` | planner.models | 1 test |
| B5 | `CompiledInput` | cognitive_compiler.compiler | 2 tests |
| B6 | `ArtifactRegistry` | engineering | 4 tests |
| B7 | `ArtifactType` | engineering | 3 tests |
| B8 | `MetaReflection` | v4.cognitive.metacognition | 1 test |
| B9 | `RoutingDecision` | topic_tree.manager | 1 test |
| B10 | `MockProvider_v3` | llm_providers.mock_provider | 1 test |
| B11 | `OpenAIProvider` | llm_providers | 2 tests |
| B12 | `DomainSelector` | context | 1 test |
| B13 | `Domain` | context_compiler | 1 test |
| B14 | `ExpectationIdentifier` | pcr.rule_based | 1 test |
| B15 | `AsyncStructuredLogger` | observability.logger | 1 test |
| B16 | `ChunkStrategyRegistry` | chunking | 1 test |
| B17 | `MockProvider` | llm_providers | 2 tests |

**根因**: 代码重构时改了类名/删了类,但测试里的 import 没更新。

**修复方向**:
- 查设计文档 → 找到正确的类名
- 更新测试 import → 指向正确的类
- 如果类真的不存在 → 实现它,或删除过期测试

### 类别 C: 语法错误 (2 个错误)

| # | 文件 | 问题 | 影响测试 |
|:--|------|------|---------|
| C1 | `observability/metrics.py:210` | `from __future__ import annotations` 不在文件顶部 | 2 tests |

**修复**: 移 `from __future__` 到第 1 行。

### 类别 D: 空构造器 (1 个错误)

| # | 文件 | 问题 |
|:--|------|------|
| D1 | `pcr/tests/test_frontend_service_integration.py` | `TypeError: NoneType takes no arguments` |

**修复**: 检查测试 fixture,可能返回了 None。

---

## 二、按设计文档对齐

### DESIGN_RUNTIME_KERNEL.md → A1 (v3_2 管线)

```
设计说: v3_2 是完整的集成管线
代码: integration.py 不存在
测试: 17 个测试等它
```

### DESIGN_METACOGNITION_RUNTIME.md → B8 (MetaReflection)

```
设计说: MetaReflection 是元认知反馈对象
代码: metacognition.py 无 MetaReflection 类
测试: test_metacognition.py import 失败
```

### DESIGN_ENGINEERING_KNOWLEDGE.md → B6/B7 (Engineering)

```
设计说: ArtifactRegistry + ArtifactType 是工程知识库核心
代码: engineering/ 有 KnowledgeGraph 但无 ArtifactRegistry
测试: 4+3 个测试等它们
```

### DESIGN_PLANNER_ORCHESTRATION.md → B1/B2/B3/B4 (Planner)

```
设计说: CapabilityBlueprint 是规划输出
代码: planner/models.py 可能有不同命名的类
测试: 5 个测试 import 失败
```

---

## 三、修复优先级

### P0 — 阻塞性 (阻塞全量测试,优先修)

| 编号 | 问题 | 修复成本 |
|:-----|------|:-----:|
| C1 | observability `from __future__` 语法错 | 5 分钟 |
| A1 | v3_2/integration.py 缺失 | 30 分钟 |
| A2 | core.agent.models 缺失 | 20 分钟 |

### P1 — 高影响 (大量测试受影响)

| 编号 | 问题 | 修复成本 |
|:-----|------|:-----:|
| B1-B4 | planner models 类缺失 | 1 小时 |
| B6-B7 | engineering 类缺失 | 45 分钟 |
| B5 | cognitive_compiler 类缺失 | 30 分钟 |

### P2 — 低影响 (1-2 测试受影响)

| 编号 | 问题 | 修复成本 |
|:-----|------|:-----:|
| A3-A4 | expertise_probe / tiered_parser | 各 15 分钟 |
| B8-B17 | 其余类缺失 | 各 10-15 分钟 |
| A5-A6 | tree_sitter / jieba 依赖 | 加到 requirements.txt |
| D1 | NoneType 空构造器 | 10 分钟 |

---

## 四、修复策略

### 方法 1: 对照设计文档实现缺失类

```
对每个缺失类:
  1. 查 DESIGN_*.md → 理解设计意图
  2. 查现有代码 → 是否有替代实现
  3. 如果替代存在 → 更新测试 import
  4. 如果完全缺失 → 实现最小版本(stub) + 标记 TODO
```

### 方法 2: 归档过期测试 (谨慎)

```
对于确认已废弃的模块:
  1. 移动测试到 un_use/tests_archived/
  2. 记录原因 + 日期
  3. 不删除——git history 永远可恢复
```

### 建议: 方法 1 为主,仅 P2 低优先级的过期测试可归档。

---

## 五、预计工作量

```
P0 (3项):   1 小时
P1 (3项):   2 小时 15 分
P2 (20项):  3 小时
─────────────────
总计:       6 小时 15 分
```

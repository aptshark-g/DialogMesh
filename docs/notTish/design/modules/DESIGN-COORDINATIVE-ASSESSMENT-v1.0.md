# Literature Cortex — 协同层设计完备性评估

> **评估对象:** 协同层 (Coordinative Layer)
> **评估日期:** 2026-06-20
> **评估依据:** 
> - `coordination/health_monitor.py` (实现)
> - `DESIGN-DIVERGENT-v0.1-draft.md` 第 8.7 节 (概念退化设计)
> - `DESIGN-v5.2b-self-reference.md` (自引用机制)
> - `persistence/schema_divergent_v2.sql` (预留表)

---

## 一、协同层当前状态

### 1.1 架构定位

协同层在整体架构中的定位是清晰的：

```
┌─────────────────────────────────────────────────┐
│  收敛层 (Convergent)    发散层 (Divergent)       │
│  ────────────────       ────────────────        │
│  A→B→C 验证             A→B→C 破坏              │
│  规则校验               替代路径生成              │
├─────────────────────────────────────────────────┤
│  协同层 (Coordinative) —— 概念退化 + 系统健康    │
│  ─────────────────────────────────────────────   │
│  激活监测 → 退化判断 → 跨层同步 → 压缩归档       │
├─────────────────────────────────────────────────┤
│              持久化层 (Persistence)              │
└─────────────────────────────────────────────────┘
```

**定位正确：** 协同层不是独立"第三层"，而是渗透层——在收敛/发散背后运行，像操作系统的内存管理器。

### 1.2 已有组件

| 组件 | 状态 | 来源 | 完成度 |
|------|------|------|--------|
| 概念健康监测 (僵尸概念识别) | ✅ 已实现 | `health_monitor.py` | 40% |
| 永久节点保护 | ✅ 已实现 | `health_monitor.py` | 100% |
| 激活衰减骨架 | ⚠️ 骨架 | `health_monitor.py` | 20% |
| 概念退化记录表 | ✅ 预留 | `schema_divergent_v2.sql` | 10% |
| 低效区 (Limbo) | ✅ 预留 | `schema_divergent_v2.sql` | 10% |
| 归档区 (Archive) | ✅ 预留 | `schema_divergent_v2.sql` | 10% |
| 概念退化机制设计 | ⚠️ 草案 | 发散层 v0.1 第 8.7 节 | 60% |
| 自引用三层架构 | ⚠️ BLOCKED | `DESIGN-v5.2b` | 30% |

---

## 二、设计完备性逐项评估

### 2.1 概念退化机制

**已有设计（发散层 v0.1 第 8.7 节）：**

| 设计要素 | 完备度 | 说明 |
|---------|--------|------|
| 哲学定义（退化 ≠ 遗忘） | ✅ 完整 | 形式化定义 + 示例 |
| 退化策略（4类） | ✅ 完整 | 复合算法/派生定理/工程实现/跨域类比 |
| 触发条件 | ⚠️ 部分 | `activation < θ_forget` + `access_count 连续N周期零增长` |
| 退化操作 (Decompose) | ❌ 缺失 | 只有伪代码，无具体算法 |
| 语义属性分配 | ❌ 缺失 | "C的语义属性分配到A和B中"怎么分？无设计 |
| A/B激活度boost | ⚠️ 骨架 | 提到要给组成元素boost，无具体公式 |
| 可逆性 | ⚠️ 部分 | "部分可逆"，无恢复机制设计 |

**结论：概念退化有清晰的方向和框架，但核心操作（Decompose）的算法未设计。**

### 2.2 跨层同步

**当前状态：完全空白。**

当概念C退化后：
- 收敛层中C参与的验证结果怎么办？
- 发散层中C生成的假设怎么办？
- 对偶器中C作为锚点的匹配怎么办？
- 方向统计中C作为seed的记录怎么办？

**需要但未设计：**
- 级联更新协议
- 引用完整性保障
- 脏数据标记机制
- 同步事务边界

### 2.3 系统健康监测

**已有 (`health_monitor.py`)：**

```python
class ConceptHealthMonitor:
    def check(self, node_id) -> HealthStatus  # ✅
    def scan_all(self) -> list[HealthStatus]  # ✅
    def scan_degraded_candidates(self) -> list[HealthStatus]  # ✅
    def decay(self) -> list[HealthStatus]     # ⚠️ 骨架，无实际衰减更新
    def heartbeat(self) -> None               # ⚠️ 仅日志记录
```

**缺失：**
- 健康趋势分析（不是单次检查，是趋势）
- 预警机制（declining → degraded 的提前预警）
- 自动化响应（触发退化？通知用户？）
- 健康仪表盘 / TUI

### 2.4 记忆压缩 (Consolidation)

**当前状态：只有一句话愿景。**

> "类似人脑的睡眠 consolidation——将短期活跃模式压缩为长期结构化知识"

**需要但未设计：**
- 压缩触发条件
- 压缩算法（什么保留、什么丢弃）
- 压缩周期
- 压缩后的质量验证

### 2.5 与元认知层的交互

**当前状态：无交互协议。**

协同层和元认知层（v5.2 MetaCognitiveArbiter）应该是什么关系？

**未回答的问题：**
- 协同层退化一个概念时，是否需要通知元认知层调整预算？
- 元认知层的比例控制是否受协同层健康状态影响？
- 系统资源紧张时，元认知层和协同层谁优先？

### 2.6 自引用机制

**设计 (`DESIGN-v5.2b`)：**

| 层级 | 功能 | 状态 |
|------|------|------|
| Layer 1 元数据自指 | 统计查询 | ✅ 设计完整 |
| Layer 2 结构反思 | 层级完整性/跨域隔离/演绎闭环 | ⚠️ 设计完整，实现BLOCKED |
| Layer 3 意图生成 | 主动探索意图 | ⚠️ 设计完整，实现BLOCKED |

**BLOCKED原因：** 节点数<50 / 多视角<70% / 跨域<2

**与协同层的关系：** 未定义。自引用发现"某层级稀疏"后，协同层是否参与响应？

---

## 三、数据模型评估

### 3.1 已有表

```sql
-- 概念退化记录（v0.3+ 启用，预留）
CREATE TABLE concept_degradation (
    id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL,
    degradation_type TEXT,       -- "decompose" | "merge" | "archive"
    source_concept TEXT,
    target_concepts TEXT,        -- JSON: ["A", "B"]
    semantic_transfer TEXT,      -- JSON
    triggered_at TIMESTAMP,
    restored_at TIMESTAMP
);

-- 低效区
CREATE TABLE limbo_nodes (
    id TEXT PRIMARY KEY,
    original_node_id TEXT NOT NULL UNIQUE,
    compressed_into TEXT,        -- JSON
    compression_reason TEXT,     -- "redundant" | "underutilized" | "superseded" | "orphaned"
    limbo_at TIMESTAMP,
    access_count_in_limbo INTEGER DEFAULT 0,
    resurrection_threshold INTEGER DEFAULT 5,
    last_queried_at TIMESTAMP,
    full_content TEXT            -- 完整节点 JSON 备份
);

-- 归档区
CREATE TABLE archive_nodes (
    id TEXT PRIMARY KEY,
    original_node_id TEXT NOT NULL,
    archived_at TIMESTAMP,
    archive_reason TEXT,
    final_content TEXT
);
```

### 3.2 缺失的表

| 缺失表 | 用途 |
|--------|------|
| `cross_layer_sync_log` | 跨层同步操作记录 |
| `degradation_semantic_map` | 退化前后的语义映射关系 |
| `health_trend` | 健康趋势时序数据 |
| `consolidation_batch` | 记忆压缩批次记录 |

---

## 四、与整体架构的兼容性

| 交互方向 | 状态 | 问题 |
|---------|------|------|
| 协同层 → 收敛层 | ❌ 未定义 | 退化后如何更新验证结果？ |
| 协同层 → 发散层 | ❌ 未定义 | 退化后如何更新假设和激活？ |
| 协同层 → 元认知层 | ❌ 未定义 | 健康状态是否影响比例控制？ |
| 协同层 → 持久化层 | ⚠️ 部分 | 有表，但无完整CRUD接口 |
| 收敛层 → 协同层 | ✅ 已触发 | `touch()` 更新激活度 |
| 发散层 → 协同层 | ✅ 已触发 | `touch()` 更新激活度 |

---

## 五、风险与边界

| 风险 | 当前覆盖 | 缓解措施 |
|------|---------|---------|
| 退化误触发（活跃概念被退化） | ❌ 无 | 未设计 |
| 级联退化（A退化导致B也退化） | ❌ 无 | 未设计 |
| 退化后恢复（用户突然需要） | ⚠️ 部分 | `restored_at` 字段预留 |
| 跨层不一致 | ❌ 无 | 未设计 |
| 压缩丢失关键信息 | ❌ 无 | 未设计 |
| 僵尸概念判断阈值敏感 | ⚠️ 部分 | 可调参数，但无自动校准 |

---

## 六、综合评级

| 维度 | 评级 | 说明 |
|------|------|------|
| 架构定位 | A | 渗透层定位清晰，与收敛/发散的关系定义正确 |
| 概念退化设计 | B | 有框架和哲学，缺核心算法（Decompose） |
| 跨层同步 | F | 完全空白 |
| 系统健康监测 | C | 基础版实现，缺趋势分析和预警 |
| 记忆压缩 | F | 只有愿景，无设计 |
| 元认知交互 | F | 无交互协议 |
| 数据模型 | B | 预留了关键表，缺跨层同步相关表 |
| 降级策略 | D | 只有预留字段，无完整恢复机制 |

### 综合评级: C+

**不是"不能用"，而是"只有一个骨架，肌肉和神经系统都没长出来"。**

---

## 七、关键缺口清单

### 🔴 P0 — 阻塞性缺口

1. **跨层同步协议**
   - 退化操作后，如何同步更新收敛层/发散层的引用？
   - 影响：没有此协议，退化会破坏数据一致性

2. **Decompose 算法**
   - "将C的语义属性分配到A和B中"具体怎么分？
   - 影响：概念退化无法落地

### 🟡 P1 — 重要缺口

3. **与元认知层的交互**
   - 系统健康状态是否影响比例控制？
   - 影响：协同层和元认知层可能冲突

4. **记忆压缩设计**
   - 压缩触发条件、算法、验证
   - 影响：长期运行后知识图谱膨胀

5. **健康趋势分析**
   - 不是单次检查，是时序趋势
   - 影响：无法提前预警概念衰退

### 🟢 P2 — 改善性缺口

6. **退化恢复机制**
   - `restored_at` 字段存在，但无恢复逻辑

7. **健康监控 TUI**
   - 可视化展示系统健康状态

---

## 八、建议行动

### 立即 (本周)

**写一份独立的协同层设计文档** (`DESIGN-v5.4-coordinative-layer.md`)，包含：
1. 跨层同步协议（最核心的缺口）
2. Decompose 算法的具体设计
3. 与元认知层的交互接口

### 短期 (2周内)

1. 实现 `Decompose` 核心逻辑
2. 实现跨层同步的原子事务
3. 补齐缺失的数据表

### 中期 (1个月内)

1. 设计并实现记忆压缩机制
2. 健康趋势分析 + 预警
3. 与 v5.3 比例控制的联动

---

## 九、一句话总结

**协同层有一个清晰的"操作系统内存管理器"定位，但目前只实现了"任务管理器"——能看到哪些进程占内存，但还不能回收、整理、压缩内存。最核心的跨层同步和Decompose算法缺失，导致概念退化只能停留在理论层面。**

---

*评估版本: v1.0*
*评估日期: 2026-06-20*
*评估者: 合作 (OpenClaw)*

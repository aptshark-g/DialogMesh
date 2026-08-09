# 主题树 manager_v2 组件级深读 — 44.8KB 巨文件 + 接线核查

> 日期: 2026-08-03 | 对象: `core/agent/topic_tree/`（8 文件 78.9KB）
> 方法: 全文精读（manager_v2.py 1,091 行）+ 消费方 rg + 运行时探针（anaconda 3.9）
> 定位: GLOBAL_AUDIT_PLAN 遗留「manager_v2 组件深读」单元，挂上下文审计。

---

## 〇、结论先行

1. **manager_v2.py 不是孤儿，也不是死代码**——`context_manager/discourse_manager.py:188-196`
   真实消费（TopicTreeManagerV2 + EmbeddingEngine + BGE 补丁），用于话题切换检测；
   但这是**唯一深度消费方**，且消费方式是"参考不控制"（决策结果只记日志，不直接改树）。
2. **测试 10/17 失败**：根因 = `EmbeddingEngine._load_model()` 只 catch `ImportError`，
   当前环境 sentence-transformers→transformers→numpy 版本检查抛 `ValueError`（非 ImportError）
   → 整个 route() 在 encode 阶段崩溃。**代码健壮性 bug**（应 catch 宽异常）+ 环境问题。
3. **两个 API 断点**：
   - `context_assembly.py:145` 调 `self._topic_tree.get_current_branch()`——V2 **没有这个方法**
     （只有 get_current_node）→ AttributeError 被 except 吞掉 → topic_tree 上下文恒空（静默）。
   - `engineering_bridges.py:330` `TopicTreeBridge.get_current_branch()` 调 `get_active_path`——
     V2 也没有 → 恒返回 `[]`（静默空）。
4. **V1/V2 双轨并存**：`manager.py`（5KB，V1，CLI registry 注册）+ `manager_v2.py`（44.8KB）。
   V1 被 `cli/registry.py:276` 与 `v3_common/integration_bridge.py` 消费（旧路径）；V2 被
   discourse_manager（新路径）消费。两个实现无桥接。

---

## 一、manager_v2.py 组件结构（1,091 行精读）

| 组件 | 行区间 | 职责 | 质量评估 |
|---|---|---|---|
| EmbeddingEngine | 35-88 | sentence-transformers 优先 + hash 伪向量回退（384-dim）| 🟡 只 catch ImportError（bug）|
| CohesionCalculator | 90-210 | 多维度 cohesion = 0.4*语义 + 0.35*实体 + 0.25*意图 | 🟢 权重可配置 |
| TopicDecisionClassifier | 211-377 | Ψ 轻量分类器：continue/fork/attach/merge/new 多特征决策 | 🟢 规则可替换 sklearn |
| ForkPointLocator | 379-451 | 语义相似度 + 意图漂移定位分叉点 | 🟢 |
| MergeEngine | 453-610 | LCA + 三路合并 + 冲突检测/解决 | 🟢 冲突默认 manual |
| ReactFlowExporter | 612-685 | ReactFlow/D3 JSON 导出 | 🟢 |
| TopicTreeManagerV2 | 687-1091 | route 主循环 + 4 执行动作 + 热区/深度压缩/摘要节点 | 🟢 逻辑完整 |

### 关键阈值（硬编码，未参数化）
```
COHESION_CONTINUE = 0.55 / COHESION_FORK = 0.25 / MAX_DEPTH = 6 /
HOT_ZONE_DEPTH = 2 / ACTIVATION_THRESHOLD = 10
分类器内部阈值: continue=0.55 / fork=0.30 / attach_min=0.25 / merge_sim>0.85
意图相关映射: (ADVISOR,QUERY)=0.7 / (DIRECTIVE,TOOL)=0.8 / (COMPANION,ADVISOR)=0.6
```

---

## 二、消费矩阵（全库 rg 实锤）

| 消费方 | 用法 | 状态 |
|---|---|---|
| context_manager/discourse_manager.py:188-196 | 实例化 V2 + activate + BGE 补丁（_fast_load_model 避免 sentence-transformers）| 🟢 真消费 |
| discourse_manager.py:625-643 | route() 决策话题切换（参考，不直接控制 _topic_tree）+ get_current_node() | 🟢 真消费 |
| assembly/context_assembly.py:143-145 | `get_current_branch()`——**方法不存在** → 恒空 | 🔴 断点（静默）|
| engineering_bridges.py:324-330 | TopicTreeBridge 包装 `get_active_path`——**不存在** → 恒 [] | 🔴 断点（静默）|
| cli/registry.py:276 | 注册 V1 `TopicTreeManager`（manager.py）| 🟢 V1 路径 |
| v3_common/integration_bridge.py:27 | `from core.agent.topic_tree import TopicTreeManager, RoutingDecision`（V1）| 🟡 V1 旧路径 |
| runtime/engine.py:27+187 | `TopicTreeContextSource`（context/topic_tree_source.py，**不同类**，包 discourse 树）| 🟢 另一套 |
| persistence/graph_store + tiered_storage + wave_query | 消费 models.py 的 TopicNode/TopicEdge（数据模型复用）| 🟢 模型层复用 |

---

## 三、运行时探针（anaconda 3.9 实测）

### 3.1 直接使用（绕过 sentence-transformers 后）
```
EmbeddingEngine.encode("测试") → 384-dim hash（OK）
tt.route("帮我看看内存扫描的报错", 12, ADVISOR, [PID:1234]) → new
tt.route(同句, 13) → continue（cohesion 高）✓
tt.route("今天天气怎么样", 14, QUERY) → fork ✓
→ 算法逻辑本身工作正常（r1=new, r2=continue, r3=fork 符合预期）
```

### 3.2 直接使用（未绕过）→ 崩溃
```
route() → EmbeddingEngine.encode() → _load_model() → from sentence_transformers
  → transformers 版本检查 → ValueError: Unable to compare versions for numpy>=1.17
  （found=None）→ 异常非 ImportError → 不触发 hash 回退 → route 崩溃
```

### 3.3 DiscourseManager 初始化 → 同环境崩溃
```
DiscourseManager() → 内部依赖 chain 触发同一 numpy 版本检查 ValueError
→ 说明当前环境 transformers/numpy 版本元数据损坏（importlib.metadata 返回 None）
```

### 3.4 pytest 结果
```
test_manager_v2.py: 10 failed / 7 passed
失败全部为 TypeError/ValueError 连锁（sentence-transformers 导入链），非断言失败
```

---

## 四、问题清单

| # | 级别 | 问题 | 根因 | 方向 |
|---|---|---|---|---|
| T1 | P1 | EmbeddingEngine 只 catch ImportError → 其他导入异常直接崩 | 健壮性 | 改 catch Exception，回退 hash |
| T2 | P1 | context_assembly 调不存在的方法（get_current_branch）| API 漂移 | 改 get_current_node 或补方法 |
| T3 | P1 | engineering_bridges 调不存在的方法（get_active_path）| API 漂移 | 同上 |
| T4 | P2 | V1/V2 双实现并存无桥接 | 多代演进 | 归一拍板（V2 保留，V1 归档或桥接）|
| T5 | P2 | 阈值硬编码（0.55/0.25/0.85 等）| 参数未参数化 | 与 A18 参数自适应联动 |
| T6 | P2 | ACTIVATION_THRESHOLD=10 延迟激活 → 前 10 轮不建树 | 设计取舍 | 确认是否要更早激活 |
| T7 | P3 | hash 伪向量与 BGE 向量混用（discourse_manager 只在 BGE 可用时补丁，否则 hash）| 一致性 | 明确编码器契约 |

---

## 五、与全局拍板池的关系

- **P-2 多代演进分裂** +1: V1/V2 双轨（manager.py vs manager_v2.py）。
- **P-1 接线断裂** +1: 两个消费方调不存在的方法（静默空）。
- **P-3 测试缺失/断裂** +1: 10 失败 = 环境导入链 + 代码健壮性（同型）。
- 主题树与对话树/温度系统（A15）的关联：V2 热区（HOT_ZONE_DEPTH=2）即温度系统雏形，
  但未接 AdaptiveHeatModel（heat_model.py 6.4KB，T1/T2 ARC 模型，被 V1 消费，V2 不消费）——
  **V2 有热区无热度模型，V1 有热度模型无 V2 决策**，两部分没有合并。


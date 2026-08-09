# 意图模块审计入口 — 2026-08-03

> 状态: **阶段一资产盘点 ✅ / 阶段二实现审计 ✅（IMPLEMENTATION_AUDIT_20260803.md 含补读 §九）/ 阶段三设计文档审计 ✅（DESIGN_AUDIT_20260803.md，含接口预扫描）/ 补读完整执行 ✅（layer0 2124L 全文 + ENGINEERING 截断段 + l3_intent 全文 + v4_un_use + adaptive_threshold 两套 + engine L3 调用）/ 阶段四拍板待开工**
> 严重度: 🔴（用户核查：旧 IntentParser 仍被 8 处引用；但预扫描发现部分已过时）
> 审计方法: 与对话树同法——资产盘点（本文件）→ import/引用全查 → 实现审计 → 设计文档审计 → 拍板

---

## 一、审计对象全景（预扫描 2026-08-03）

### 1.1 活版本：`core/agent/intent/`（新包，10 文件）

| 文件 | 规模 | 引用数 | 角色 |
|---|---|---:|---|
| `models.py` | 3906B | **344 处** | 数据模型（被广泛复用）|
| `coordinator.py` | 4386B | **19 处** | 核心编排器 |
| `dual_track.py` | 6332B | 5 处 | 双轨（算法∥LLM）|
| `multi_perspective.py` | 9235B | 5 处 | 多视角分析 |
| `multi_intent_splitter.py` | 4646B | 2 处 | 多意图拆分 |
| `literal_chain.py` | 5664B | 1 处 | 字面链验证 |
| `llm_chain.py` | 3808B | 1 处 | LLM 链 |
| `ambiguity_bridge.py` | 4011B | 1 处 | 歧义桥 |
| `ambiguity_gate.py` | 5240B | **0 处** | ⚠️ 疑似死代码 |
| `fusion_decider.py` | 4725B | **0 处** | ⚠️ 疑似死代码 |

### 1.2 旧代际（un_use / shim）

| 文件 | 规模 | 状态 |
|---|---|---|
| `v3_common/intent_parser.py` | **325B shim** | DEPRECATED 文档字符串明示；`try: from ...un_use.intent_parser import IntentParser except ImportError: IntentParser = None` |
| `v3_common/un_use/intent_parser.py` | 59KB（≈3000 行旧版）| 归档 |
| `v4/un_use/intent_parser.py` | 5KB（旧版精简）| 归档 |
| `v4/tiered/` | **空壳**（66B `__init__.py` + tests）| 内容已搬走？|

### 1.3 周边（非 intent/ 但意图相关）

| 文件 | 角色 |
|---|---|
| `llm_providers/llm_instances/intent_llm.py` | 意图 LLM 实例 |
| `prompts/intent_classifier.py` | 意图分类 prompt |
| `association/l3_intent.py` | 关联链 L3 意图验证 |
| `cli/commands/pcr_intent_cmd.py` | CLI 入口 |
| `pcr/tests/intent_trace_cli.py` | 旧意图追踪 CLI 测试 |
| `compiler/topic_quick_match.py` | 主题快匹配（BM25，对话树周边）|
| `v3_common/blueprints.py` / `gates.py` | 旧管线引用 IntentParser 处 |

### 1.4 测试

```
（未找到独立 tests/test_intent*.py——待确认：intent/ 新包是否有专属测试）
tests/test_data_multi_intent.json     ← 多意图测试数据
tests/test_data_l3_intent.json        ← L3 意图测试数据
```

---

## 二、设计文档资产（15 篇）

| 文档 | 规模 | 内容 |
|---|---|---|
| `docs/v3.0/design_layer0_pcr_and_layer1_intent_parser.md` | 110KB | PCR+Intent 原始设计（8 原则）|
| `docs/v3.0/design_layer1_intent_parser.md` | 31KB | Intent Parser v1.0（532 行）|
| `docs/v3.0/ENGINEERING_INTENT_PARSER.md` | 50KB | 工程实现（端点/接线）|
| `docs/BUSINESS_CHAIN_01_INTENT.md` | 11.7KB | 链 01 意图（8 阶段 Pipeline）|
| `docs/BUSINESS_CHAIN_01_UNIFIED_INTENT.md` | 4.8KB | 统一意图（T0/T1/T2 + 5 层漏斗）|
| `docs/v5/DESIGN_UNIFIED_INTENT_ASSOCIATION.md` | 5.4KB | 意图×关联统一 |
| `docs/v5/DESIGN_MULTI_SIGNAL_INTENT.md` | 6.7KB | 5 路弱信号贝叶斯融合 |
| `docs/v5/INTENT_MULTI_TIER.md` | 2.5KB | 意图多层级 |
| `docs/v5/INTENT_RECURSIVE_CONVERGENCE.md` | 2.2KB | 递归收敛快匹配 |
| `docs/v5/ENGINEERING_MULTI_INTENT_SPLIT.md` | 34KB | 多意图拆分工程 |
| `docs/v5/DESIGN_AGENT_NATIVE_INTENT.md` | 5.6KB | Agent-Native 意图 |
| `docs/v5/DESIGN_V3.2_ROUTING_MATRIX.md` | 6.9KB | 3D 路由矩阵（STC）|
| `docs/v3.0/DESIGN_TIERED_ACTION_RESOLVER.md` | 11.3KB | 共享分类内核 |
| `docs/v3.0/DESIGN_TIERED_PARSER.md` | 5.1KB | 三层递进解析 |
| `docs/v3.0/DESIGN_UNIFIED_PERSISTENCE.md` | 10.6KB | 统一持久化（部分相关）|

---

## 三、预扫描关键发现

1. **"旧 IntentParser 仍被 8 处引用"已部分过时**：`v3_common/intent_parser.py` 已是 325B shim（DEPRECATED），原 3000 行在 `un_use/`。需确认引用方用的是 shim 还是活包。
2. **活包核心 = `coordinator`（19 处引用）+ `models`（344 处）**；`ambiguity_gate`/`fusion_decider` 零引用（疑似死代码，待确认）。
3. **`v4/tiered` 空壳**：只剩 `__init__.py`(66B) + tests——需确认内容搬去哪（intent/ 新包？）。
4. **意图↔对话树耦合**（对话树拍板 #6 卡点）：`primary_intent` 来源悬空；话题切换信号="意图类别突变"；域选择矩阵意图类别决定域 C 权重。
5. **PCR 调控**：链01 INTENT 说 PCR 调控 8 阶段 0% 接入——需确认活包是否已接。

---

## 四、审计计划

```
阶段一: 资产盘点 ✅（2026-08-03，本文件）
阶段二: 实现审计 ✅ —— intent/ 10 文件全读 + shim/un_use 对比 + import 探针 → IMPLEMENTATION_AUDIT_20260803.md
阶段三: 设计文档审计 ✅ —— 15 篇全读 → DESIGN_AUDIT_20260803.md
阶段四: 意图↔对话树接口预扫描 ✅ —— primary_intent / 话题切换 / 域选择 / compass 四接口（DESIGN_AUDIT §五）
阶段五: 内核拍板 + 待办清单（待开工，DESIGN_AUDIT §六 8 项 + IMPLEMENTATION_AUDIT §九 补读发现）
```

---

## 五、待查清单（审计开工问题）

1. `coordinator.py` 是什么 API？被 19 处引用，是主入口吗？
2. `models.py` 344 处引用的数据模型——是意图类型体系（C/CR/QUERY/...）还是新结构？
3. `ambiguity_gate`/`fusion_decider` 零引用——死代码 or 待接线？
4. shim 的 `IntentParser = None` 分支——引用方是否防御了 None？
5. `v4/tiered` 空壳内容去向——新包是它的后继？
6. PCR 调控：活包读不读 PCR 输出（expectation/noise/complexity）？
7. 意图↔对话树：`primary_intent` 现在实际由谁产出？话题切换用什么信号？
8. 测试缺失：intent/ 新包 10 文件是否有专属测试？

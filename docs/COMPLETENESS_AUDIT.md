# DialogMesh v6 — 业务流完备性审计

> 日期: 2026-07-20

---

## 一、10 条业务链覆盖

| # | 链 | 文档 | API | 代码 | 评级 |
|:---:|------|:---:|:---:|:---:|:---:|
| 01 | 对话树主线 | ✅ | ✅ event+context | ✅ 3,400行 | ⭐⭐⭐⭐ |
| 02 | LLM回复侧 | ✅ | 间接 | ✅ 快匹配 | ⭐⭐⭐ |
| 03 | 用户修改对话树 | ✅ | ✅ PUT edit | ✅ adapter | ⭐⭐⭐⭐ |
| 04 | 元认知+持久化 | ✅ | ✅ meta/stats | ✅ persist | ⭐⭐⭐⭐ |
| 05 | 行为链预测+发现 | ✅ | ✅ behavior/* | ⚠️ 引擎未接入 | ⭐⭐⭐ |
| 06 | 关联链五层漏斗 | ✅ | ✅ relations | ⚠️ L1.5/L2.5 独立 | ⭐⭐⭐ |
| 07 | 工程链约束推理 | ✅ | ✅ engineering/* | ✅ 递归地图 | ⭐⭐⭐ |
| 08 | 画像惯性权重图 | ✅ | ✅ profile+inertia | ✅ | ⭐⭐⭐⭐ |
| 09 | 元认知第二大脑 | ✅ | ✅ meta/* | ✅ | ⭐⭐⭐ |
| 10 | 子图跨链织物 | ✅ | ✅ subgraph | ✅ | ⭐⭐⭐ |

---

## 二、数据流闭环

```
✅ 用户输入 → [链01 对话树] → [链10 子图] → LLM 回复
✅ LLM 回复 → [链02 标注] → [链06 关联] + [链05 行为]
✅ 行为变化 → [链05 行为链] → [链08 画像] → 参数反哺
✅ 画像变化 → [链08 惯性] → [链09 元认知审核] → 反馈全部链
✅ 约束违反 → [链07 工程链] → [链09 元认知] → 警报
✅ 用户修改 → [链03 编辑] + [Git版本控制] → [链04 持久化]
⚠️ L4→L5 因果晋升: 模块已有, 引擎未调用
⚠️ 关联链 L1.5 补全: 模块已有, 未接入子图编译器
```

---

## 三、缺失识别

### 3.1 引擎接入缺失 (已有模块, 未连线)

| 模块 | 引擎调用位置 | 影响 |
|------|:---:|------|
| CausalPromoter (L4→L5) | _feed_profile 未调用 | 因果晋升从不触发 |
| TTLManager (HCWA) | _feed_profile 未调用 | 温度从不迁移 |
| BehaviorDiscovery.submit_to_meta | _feed_profile 未调用 | 行为模式发现后不送审 |
| MetaSelfRepair.record_accuracy | 元认知从不调用 | 自检修复从不触发 |

### 3.2 设计文档未覆盖 (30/39 设计文档未在业务链引用)

```
核心缺失:
  DESIGN_COGNITIVE_WORKSPACE.md     → 四空间模型, 链10子图已引用但未完整映射
  DESIGN_COGNITIVE_DYNAMICS_V6.md   → 状态转移, 链08惯性图已引用
  DESIGN_RELATION_SUBSTRATE.md      → 关联基座, 链06已引用
  DESIGN_HYPOTHESIS_ENGINE.md       → 假设验证, 无业务链覆盖
  DESIGN_OBSERVATION_COMPILER.md    → 观察编译, 无业务链覆盖
  DESIGN_STATE_EVOLUTION_SYSTEM.md  → 状态演化, 链08已引用
  DESIGN_SKILL_LAYER.md             → 技能层, 无业务链覆盖
  DESIGN_ENGINEERING_CHAIN.md       → 工程链, 链07已引用 ✅
  DESIGN_ENGINEERING_ONTOLOGY.md    → 工程本体, 链07已引用 ✅
  DESIGN_TIERED_PARSER.md           → 分层解析, 链02已引用
```

### 3.3 架构设计缺口

| 缺口 | 优先级 | 说明 |
|------|:---:|------|
| 三层共识理论 (信息溯源→置信度→共识) | P2 | 设计讨论过, 未实现 |
| 多用户/多租户 | P3 | 当前单用户 |
| 存算分离 | P3 | ObservationPool+State 全内存 |
| 因果链完整闭环 | P2 | L4→L5 算法有, 未接入 |

---

## 四、总结

```
业务链覆盖: 10/10 ✅
数据流闭环: 5/7 ✅ (2个半闭环)
API覆盖:    10/10 ✅
引擎接入:   14/18 ✅ (4个模块孤岛)
设计引用:    9/39 ⚠️ (仅23%设计文档被业务链引用)

判定: 业务流设计完备, 代码接入有 4 个模块孤岛待连线
```

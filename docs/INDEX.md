# DialogMesh v6 — 业务链索引 · 完整状态

> 日期: 2026-07-19 | 总链数: 10 + 2 补充 + 1 审计 = 13 篇 | 总行数: 3,841 行

---

## 一、业务链总览 (10 链)

| # | 链名 | 文件 | 行数 | 核心内容 |
|:---:|------|------|:---:|------|
| 01 | **对话树主线** | `BUSINESS_CHAIN_01_CONVERSATION_TREE.md` | 222 | 用户输入→LLM, 四路径调度, 水波展开 |
| 02 | **LLM回复侧** | `BUSINESS_CHAIN_02_LLM_RESPONSE_SIDE.md` | 284 | 标注+快匹配, 主题绑定可延后, 重复加权 |
| 02+ | **递归收敛快匹配** | `BUSINESS_CHAIN_02_APPENDIX_TOPIC_MATCH.md` | 321 | SVO+BM25+画像+锚点, 子查询生成器 |
| 03 | **用户修改对话树** | `BUSINESS_CHAIN_03_USER_EDIT_TREE.md` | 305 | 4种修改+区块链记录+四级摘要级联 |
| 04 | **元认知+持久化** | `BUSINESS_CHAIN_04_META_PERSIST.md` | 364 | 内部修改器+修正网关(对话树专用) |
| 05 | **行为链预测** | `BUSINESS_CHAIN_05_BEHAVIOR.md` | 253 | 四层决策树+ε-greedy+RL奖励 |
| 05+ | **行为发现闭环** | `BUSINESS_CHAIN_05_SUPPLEMENT_DISCOVERY.md` | 247 | 统计发现→前端展示→元认知审核→关联链吸收 |
| 06 | **关联链五层漏斗** | `BUSINESS_CHAIN_06_ASSOCIATION.md` | 205 | L1句法→L1.5补全→L2语义→L2.5信念→L3意图→L4时序→L5因果 |
| 07 | **工程链约束推理** | `BUSINESS_CHAIN_07_ENGINEERING.md` | 208 | 7类节点+7类边+递归地图+文件绑定 |
| 08 | **画像即惯性权重图** | `BUSINESS_CHAIN_08_PROFILE_FEEDBACK.md` | 214 | 多视角共识+惯性生命周期+打破=信号+设计约束投射 |
| 09 | **元认知第二大脑** | `BUSINESS_CHAIN_09_METACOGNITION.md` | 277 | Git版本控制+复盘引擎+双模式决策+预留接口 |
| 10 | **子图跨链织物** | `BUSINESS_CHAIN_10_SUBGRAPH.md` | 195 | 对话树子图+元认知子图+双视角编译器 |
| — | **对话树审计** | `BUSINESS_CHAIN_AUDIT_DIALOGUE_TREE.md` | 195 | 5个设计缺口→已全部修补 |

---

## 二、交叉引用矩阵

```
链间依赖 (谁消费谁的数据):

链 01 ← 链02(快匹配),链05(行为信号),链06(关联),链07(约束),链08(偏好),链10(子图)
链 02 ← 链01(对话树),链06(关联链补全)
链 03 ← 链01(对话树结构),链04(元认知审核)
链 04 ← 链01-03(全部对话树数据),链08(惯性)
链 05 ← 链01(行为序列),链06(关联强度),链08(OCEAN→ε)
链 06 ← 链01(对话树),链05(行为模式),链07(约束),链08(偏好)
链 07 ← 链06(关联关系→约束)
链 08 ← 全部链 (多视角共识) → 反馈全部链 (设计约束)
链 09 ← 全部链 (审核/复盘) → 反馈全部链 (版本控制/回滚)
链 10 ← 全部链 (子图编译) → 链01(回复) + 链09(审核)
```

---

## 三、网关业务 (独立项目)

| 文档 | 项目 | 内容 |
|------|------|------|
| `switch/docs/BUSINESS_CHAIN_01_GATEWAY.md` | switch | v2.0 工业级网关设计 (4轮迭代) |
| `switch/docs/BUSINESS_FLOW_GATEWAY.md` | switch | 管理员配置+用户对话+监控运维 三主线 |
| `switch/docs/BINDING_DIALOGMESH.md` | switch | DialogMesh ↔ switch 协议绑定 |
| `docs/GATEWAY_DESIGN.md` | DialogMesh | Python 网关 API 业务设计 |

---

## 四、配套文档

| 文档 | 内容 |
|------|------|
| `docs/GUI_API.md` | 60 端点 + 8 业务域 + 前端组件映射 |
| `docs/DESIGN_AUDIT.md` | 白盒化+高自由度 100% 达标审计 |
| `docs/CLI_REFERENCE.md` | 8 CLI 命令完整用法 (历史) |
| `docs/DESIGN_CLI.md` | **CLI v2**: 40+ 命令，全模块引擎直连 Unix 管道 |
| `docs/DESIGN_SPECIFICATION.md` | 设计规范 |
| `docs/ARCHITECTURE_INDEX.md` | 架构索引 |

---

## 五、实现状态

### 已完成

| 模块 | 状态 | 说明 |
|------|:---:|------|
| P0: Mind + InteractionGraph | ✅ | 引擎接入 |
| P1: Builder+Compiler+View+6域+ABC | ✅ | 全接入 |
| P2: AnnotationStore+UnifiedStore | ✅ | 持久化层 |
| P3: v3桥接修复 | ✅ | RuleEngine等4模块 |
| OCEAN 10维 + BFI校准 | ✅ | EMA+BFT优先 |
| 修正日志 (correction journal) | ✅ | 漂移检测+LLM回顾 |
| CLI (8命令) | ✅ | chat/test/ab/profile/... |
| API (60端点) | ✅ | REST + 8业务域 |
| switch gateway (4迭代) | ✅ | Go实现, 断路器+Gradient2+... |
| switch ↔ DialogMesh 绑定 | ✅ | SwitchGatewayProvider |

### 待实现

| 模块 | 优先级 | 说明 |
|------|:---:|------|
| MetaCognition 核心 | P0 | 审核队列+复盘引擎+双模式决策 |
| SubgraphCompiler 双视角 | P0 | 对话树子图+元认知子图 |
| InertiaWeightGraph | P0 | 画像 v2: 惯性权重图 |
| 行为发现三阶段 | P1 | 统计→展示→审核→吸收 |
| 关联链 L1.5 补全器 | P1 | 快慢双通道 |
| 关联链 L2.5 信念凝聚 | P1 | 贝叶斯序贯后验 |
| 工程链递归地图 | P1 | 颗粒度+水波展开 |
| Git 版本控制 | P1 | 8类数据不可变日志 |
| A/B 测试验证 | P0 | bench_ab_ocean.py |

---

## 六、统计

```
业务链文档:   13 篇 (10 链 + 2 补充 + 1 审计)
配套文档:      5 篇 (GUI_API, DESIGN_AUDIT, CLI_REF, ...)
网关文档:      3 篇 (switch 侧)
─────────────────────────────
总计:         21 篇设计文档

业务链总行数:  3,841 行
对话树四链:    链01-04 = 1,175 行
行为预测+发现:  链05 = 500 行
关联链:        链06 = 205 行
工程链:        链07 = 208 行
画像:          链08 = 214 行
元认知:        链09 = 277 行
子图:          链10 = 195 行
```

---

## 七、待补充 (识别到的缺口)

| 缺口 | 说明 | 优先级 |
|------|------|:---:|
| 因果链三层共识理论 | 信息溯源→置信度→共识 (未做) | P2 |
| 外部能力实现 | web_search/env_validate/literature (预留接口) | P3 |
| 关联链 L4→L5 晋升算法 | 伪因果→实因果的转化条件 | P1 |
| 元认知自检修复 | 操作准确率 < 0.7 → 自动调整 | P2 |
| 多用户/多租户 | 当前仅单用户设计 | P3 |

# DialogMesh v6 — 白盒化 & 高自由度设计审计

## 设计愿景

> 白盒化哲学: 每一个模块可探索,用户通过理解而成长。
> 高自由度: 用户可修改任何中间状态,修改被记录并纳入系统学习。

---

## 一、可达性审计 (CAN I SEE IT?)

| 模块 | 可读端点 | 数据内容 | 状态 |
|------|---------|---------|------|
| LLM 画像 | GET /v6/profile | OCEAN 10维 + MBTI + BFI校准 | ✅ |
| Trace 信号 | GET /v6/trace | S/W/R 实时信号 + confidence | ✅ |
| ABC 决策层 | GET /v6/abc | C/B/A 命中率 + 规则统计 | ✅ |
| Mind 心智空间 | GET /v6/mind + /mind/full | 关系/锚点/错误模式 | ✅ |
| InteractionGraph | GET /v6/graph | 节点 + 边 + 权重 | ✅ |
| DiscourseTree | GET /v6/discourse-tree | 对话块 + 温度 + fork | ✅ |
| SemanticObjects | GET /v6/objects | 概念节点 + 关系 | ✅ |
| RelationSubstrate | GET /v6/relations | 类型化边 (kind/strength/evidence) | ✅ |
| Causal chains | GET /v6/causal | 因果依赖链 | ✅ |
| Behavior graph | GET /v6/behavior | 行为边 + 冷却统计 | ✅ |
| Engineering knowledge | GET /v6/engineering | 约束 + 模式 | ✅ |
| Pipeline tiers | GET /v6/pipeline | 通过率 + 延迟 + 修正率 | ✅ |
| Extraction blueprint | GET /v6/extraction | 4-tier provider chain | ✅ |
| Perspective planner | GET /v6/perspectives | horizon + active view | ✅ |
| Parameters | GET /v6/parameters | 19+ 可调参数 | ✅ |
| Context assembly | GET /v6/context | 域分配 + 条目置信度 | ✅ |
| Rules | GET /v6/rules | 前提/结论/置信度/hits/misses | ✅ |
| Gateway providers | GET /v6/gateway/providers | 厂商+模型+健康+key | ✅ |
| Router modes | GET /v6/router/modes | 3模式+复杂度+降级链 | ✅ |
| Usage | GET /v6/gateway/usage | Token + 费用 | ✅ |
| Metrics | GET /v6/metrics | uptime/延迟/错误率 | ✅ |
| Sessions | GET /v6/sessions + /session/{f} | 历史列表 + 逐轮数据 | ✅ |
| Annotations | GET /v6/annotate | 用户注释 + LLM解读 | ✅ |
| Corrections | GET /v6/profile/corrections | 修正日志 before/after | ✅ |

**可达性: 24/24 模块 100% ✅**

---

## 二、可编辑性审计 (CAN I CHANGE IT?)

| 编辑对象 | 端点 | 操作 | 状态 |
|----------|------|------|------|
| OCEAN 维度 | PUT /v6/profile | 逐维修改值 | ✅ |
| MBTI 类型 | PUT /v6/profile | 直接设置类型 | ✅ |
| InteractionGraph 边 | PUT /v6/edit/graph | 修改权重/类型 | ✅ |
| InteractionGraph 节点 | PUT /v6/edit/graph | 设置节点状态 | ✅ |
| DiscourseTree 块 | PUT /v6/edit/discourse-tree | 重分类/重命名/合并 | ✅ |
| SemanticObjects | PUT /v6/edit/objects | 增减关系 | ✅ |
| RelationSubstrate | PUT /v6/edit/relations | 修改边强度/类型 | ✅ |
| IR 上下文 | PUT /v6/edit/ir | 直接注入 LLM 所见 | ✅ |
| 规则 | PUT /v6/rules | 编辑前提/结论/置信度 | ✅ |
| 参数 | PUT /v6/parameters | 修改任何阈值 | ✅ |
| 上下文配置 | PUT /v6/context/config | 调整预算+域权重 | ✅ |
| 提供商配置 | PUT /v6/gateway/providers/{n} | 修改 API key/URL | ✅ |
| 当前模型 | PUT /v6/gateway/active | 热切换 provider/model | ✅ |
| 路由模式 | PUT /v6/router/modes | 强制模式/禁用模型/预算 | ✅ |
| 降级链配置 | PUT /v6/gateway/config | 故障转移链+重试+超时 | ✅ |
| 注释 | POST /v6/annotate | 对任何数据点加注释+LLM深度分析 | ✅ |
| 回复反馈 | POST /v6/feedback | 点赞/踩 → 规则置信度更新 | ✅ |

**可编辑性: 17/17 编辑点 100% ✅**

---

## 三、学习闭环审计 (DOES IT LEARN?)

| 学习信号 | 来源 | 去向 | 状态 |
|----------|------|------|------|
| 用户修正 OCEAN | PUT /v6/profile | → ABC 规则 (user_feedback, conf=0.9) | ✅ |
| 用户修正 MBTI | PUT /v6/profile | → ABC 规则 + correction_journal | ✅ |
| 用户编辑图结构 | PUT /v6/edit/* | → correction_journal + Mind 行为记录 | ✅ |
| 用户注释数据 | POST /v6/annotate | → LLM 深度解读 + correction_journal | ✅ |
| 用户反馈回复 | POST /v6/feedback | → ABC rule.hits/misses ±1 | ✅ |
| 用户编辑规则 | PUT /v6/rules | → 直接修改规则库 | ✅ |
| 系统漂移检测 | engine._feed_profile | → LLM retrospective review | ✅ |
| BFI 校准 | OCEAN x BFI | → divergence>0.25→BFI覆盖 | ✅ |
| Mind 学习 | engine _mind.learn | → 每5轮学习关系/锚点/错误 | ✅ |

**学习闭环: 9/9 信号通路 100% ✅**

---

## 四、持久化审计 (IS IT PERSISTENT?)

| 数据 | 路径 | 保存时机 | 状态 |
|------|------|---------|------|
| OCEAN 画像 | data/profile/ocean_profile.json | 每5轮 + 启动自动加载 | ✅ |
| BFI 校准 | data/profile/bfi_history.json | 每次 BFI 评分 | ✅ |
| 修正日志 | data/profile/corrections.jsonl | 每次用户修改 | ✅ |
| ABC 规则 | data/neuro_symbolic_rules.json | 每10轮 + 用户编辑触发 | ✅ |
| Mind 关系 | data/mind_relation.json | 每5轮 Mind.learn | ✅ |
| Mind 锚点 | data/mind_attention.json | 每5轮 | ✅ |
| Mind 错误 | data/mind_mistakes.json | 每5轮 | ✅ |
| 网关配置 | data/gateway/{config,providers/*}.json | 保存+切换时 | ✅ |
| 用户注释 | data/annotations/user_notes.jsonl | 每次注释 | ✅ |
| 会话日志 | data/monitor/chat_*.jsonl | 每轮+session end | ✅ |
| AnnotationStore | data/annotations/* | 引擎自动 | ✅ |

**持久化: 11/11 数据源 100% ✅**

---

## 五、高自由度检查清单

| 自由度维度 | 实现 | 状态 |
|-----------|------|------|
| 选模型厂商 | 3 built-in + 自定义 key/url + 模型拉取 + 热切换 | ✅ |
| 选处理层级 | 3 mode router (rule/small_model/remote_llm) + force override | ✅ |
| 调参数 | 19+ parameters GET/PUT | ✅ |
| 改规则 | rules GET/PUT/feedback 置信度 | ✅ |
| 编上下文 | context config PUT + IR direct edit | ✅ |
| 改图结构 | graph/tree/objects/relations 全可编辑 | ✅ |
| 注释数据 | 任意数据点 → LLM 深度解读 | ✅ |
| 跨会话 | OCEAN/Mind/ABC/Gateway 全部跨 session 持久化 | ✅ |
| 导出 | export JSON/CSV | ✅ |
| 命令行 | chat/test/ab/profile/monitor/export/config/clean | ✅ |

---

## 六、差距与待办

| 差距 | 优先级 | 说明 |
|------|--------|------|
| OCEAN dims 不能从 GUI 锁定 | P1 | 用户设定后应可选"锁定此维度不再自动更新" |
| 注释无批量导出 | P2 | 注释应可导出为训练数据集 |
| 无 A/B 实验结果对比可视化 | P2 | 多次 A/B 结果应可对比趋势 |
| LMStudio 模型列表需手动输入 | P2 | 无法自动 fetch 本地模型列表 |
| 无模型版本管理 | P3 | API key 历史、模型切换记录 |

---

## 七、综合结论

```
═══════════════════════════════════════════
  白盒化 + 高自由度 设计达标率
═══════════════════════════════════════════

可达性:    24/24 = 100%  ✅
可编辑性:  17/17 = 100%  ✅
学习闭环:   9/9  = 100%  ✅
持久化:    11/11 = 100%  ✅
自由度:    10/10 = 100%  ✅

总端点:    60
总模块:    24 (0 孤岛)
总文档:    4 (CLI_REFERENCE, GUI_API, GATEWAY_DESIGN, DESIGN_AUDIT)
───────────────────────────────────────────
结论: 设计愿景已达成。
剩余 A/B 测试验证 → 完成全部闭环。
═══════════════════════════════════════════
```

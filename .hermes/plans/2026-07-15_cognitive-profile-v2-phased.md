# Cognitive Profile v2 — 分阶段实现方案

> **设计锚点:** `design_cognitive_profile_v2.md` + `ENGINEERING_COGNITIVE_PROFILE_V2.md`
> **用户要求:** 冷启动快速收敛 → 后验修正长链 → 稳定判断 → 波动预警 → SQLite持久化 → 会话内权重优先

---

## Phase 1: 数据模型 + 记忆衰减（基础设施）

### T1.1 数据模型 `models.py`
- `UserTag`: name, value, confidence, source(L1-L4), verification_count, is_sensitive
- `MemoryPoint`: 情绪冲击点，幂律衰减 W_c = W_m / (1+T_m)^d
- `MemoryChunk`: hot/warm/cool/cold 阶梯跃迁，双指数衰减
- `CognitiveDynamics`: Track A 9维 + 平稳性标记

### T1.2 记忆衰减 `memory_decay.py`
- 双指数衰减: W(t) = W₀ * [0.7*exp(-t/24) + 0.3*exp(-t/720)]
- 阶梯跃迁: hot(<24h)→warm(<7d)→cool(<30d)→cold
- MemoryPoint 幂律衰减
- 重要性保护: importance>0.8 时衰减减慢 1.5x

---

## Phase 2: 收敛机制 + 持久化

### T2.1 后验收敛引擎 `convergence.py`
- EMA: value_new = α*observation + (1-α)*value_old
- 动态 α: max(0.05, 1.0 / (1+√turns)) → 早期快速收敛，后期稳定
- 波动检测: |obs - value| > 2*σ 时标记为异常，触发 LLM 审核
- 冻结判断: turns>50 且 σ<0.05 → 维度冻结（仅记录不更新）

### T2.2 SQLite 持久化 `persistence.py`
- schema: profile_id, user_id, session_id, track_a_json, track_b_json, updated_at
- 会话权重: 当前会话 1.0，跨会话 0.35（参考但不主导）
- save/load/merge 接口

---

## Phase 3: 认知动力学 Track A

### T3.1 认知惯性 `dynamics/cognitive_inertia.py`
- 风格偏好（简洁/详细/结构化/自由）的皮尔逊自相关系数

### T3.2 信任度 + 情绪 + 注意力 `dynamics/trust_emotion_attention.py`
- T(S,O) = 系统承诺兑现率
- M_Em = 情绪极性信息熵
- P = TF-IDF 话题权重分布

### T3.3 预期偏差 + 记忆点 + 自我价值 `dynamics/expectation_memory_self.py`
- ΔE = 满意度偏差运行均值
- M 点集 = 高情绪事件收集+衰减
- V(S) = 自我肯定语言频率

### T3.4 认知资源 + 行为惯性 `dynamics/resource_behavior.py`
- C_max = 从回复速度+问题复杂度推断
- 行为惯性 = 接受率/质疑率/澄清率

---

## Phase 4: 标签层 Track B + g 因子

### T4.1 标签模型 + L1获取 `tag_layer/l1_passive.py`
- L1 被动观测: 语言偏好、设备类型、emoji使用、时段
- UserTag 置信度门控

### T4.2 L2 隐式推断 `tag_layer/l2_inference.py`
- 职业/领域/教育/技术深度从对话模式推断
- 关键词+话题频率+概念复杂度 → 贝叶斯置信度更新

### T4.3 g 因子推断 `tag_layer/g_factor.py`
- LLM 基于对话历史评估认知能力等级 (low/medium/high/expert)
- 评分维度: 抽象推理、领域迁移、问题复杂度、学习速度
- 每次对话结束时异步评估（不阻塞当前轮）

---

## Phase 5: 融合 + 接入引擎

### T5.1 融合层 `fusion.py`
- Track A 动态权重 × Track B 先验 → ContextItem 列表
- 风格提示: 高 divergence → 广度回复，低 divergence → 深度聚焦
- 信任度提示: trust<0.3 → 多论证，trust>0.7 → 可直接建议

### T5.2 ProfileContextSource 升级
- 替换当前简单包装，使用 CognitiveProfileV2
- 注入: 收敛状态 + 波动警告 + g因子 + 风格偏好

### T5.3 引擎接入
- `on_event()` 后更新 profile
- g 因子异步评估

---

## Phase 6: 测试 + 验证

### T6.1 单元测试
- 衰减公式正确性
- EMA 收敛速度验证
- 波动检测阈值
- g 因子评分一致性

### T6.2 端到端
- 多轮对话后 profile 演化
- 跨会话恢复
- ProfileContextSource 输出格式

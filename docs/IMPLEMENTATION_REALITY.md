# DialogMesh v6 — 实现现状 · 代码 vs 业务链

> 日期: 2026-07-19 | 对比: 10 条业务链 vs CAPABILITY_GAP vs 实际代码

---

## 一、已实现 (链 01-04 对话树主线)

| 业务链内容 | 代码实现 | 代码量 | 质量 |
|-----------|---------|:---:|:---:|
| **EventIR 解构** | `event_ir.py` | ✅ | 成熟 |
| **HeaderInjector 代词消解** | `header_injector.py` (479行) | ⭐⭐⭐⭐ | 5级消解, KB为空 |
| **9维粘合度 (CohesionScorer)** | `macro_micro_quantizer.py` (314行) | ⭐⭐⭐⭐⭐ | 真实BGE, 批量优化 |
| **SyntacticDecomposer SVO** | `syntactic_decomposer.py` (391行) | ⭐⭐⭐⭐ | 开放域NER, 短词区分度不足 |
| **DiscourseBlockTree** | `manager.py`+`segmenter.py`+`models.py` (934行) | ⭐⭐⭐⭐ | 阈值经验值, 未校准 |
| **四级摘要** | `summary_engine.py` (221行) | ⭐⭐⭐ | v3规则生成, 非LLM |
| **上下文构建** | `context_builder.py` (151行) | ⭐⭐⭐⭐ | token预算未精确 |
| **ABC 神经符号** | `neuro_symbolic.py`+`abc_orchestrator.py` | ✅ | C层5种子规则, B层LLM |
| **OCEAN 10维+BFI** | `ocean_profile.py`+`bfi_calibrator.py` | ✅ | EMA+BFI优先, CoT提示 |
| **修正日志** | `correction_journal.py` | ✅ | 漂移检测+LLM回顾 |
| **NodeAnnotationStore** | `dialogue_tree_adapter.py` | ✅ | 持久化修正网关 |
| **UnifiedGraphStore** | `unified_store.py` | ✅ | HCWA分层 |

**链 01-04 实现率: ~80%** (温度模型未实现, 摘要v3为规则生成, 元认知=0)

---

## 二、半实现 (链 05-08)

| 业务链内容 | 代码实现 | 状态 |
|-----------|---------|:---:|
| **行为链预测** (链05) | 设计文档完整, 代码=0 | ❌ 0行 |
| **行为发现** (链05+) | 设计完整, 代码=0 | ❌ 0行 |
| **关联链五层** (链06) | `relation_substrate.py`+BGE → 仅有 L1+L2 | ⚠️ 1.5/2.5层缺失 |
| **工程链约束** (链07) | `engineering_chain/` 原型, 无Document Ingestor集成 | ⚠️ 单体, 未管线化 |
| **画像惯性权重图** (链08) | OCEAN 10维已实现, 惯性图=0 | ⚠️ v1实现, v2=0 |

**链 05-08 实现率: ~25%** (设计→代码的鸿沟)

---

## 三、未实现 (链 09-10)

| 业务链内容 | 状态 | 说明 |
|-----------|:---:|------|
| **元认知** (链09) | ❌ 0行 | 设计完整, CAPABILITY_GAP P1 |
| **子图编译器** (链10) | ❌ 0行 | 双视角未实现 |
| **行为链预测引擎** | ❌ 0行 | 四层决策树 |
| **关联链 L1.5 补全器** | ❌ 0行 | 快慢双通道 |
| **关联链 L2.5 信念凝聚** | ❌ 0行 | 贝叶斯序贯后验 |
| **Git 版本控制** | ❌ 0行 | 8类数据不可变日志 |
| **因果链** | ❌ 0行 | 0/5000边有因果解释 |

**链 09-10 实现率: 0%**

---

## 四、已实现的完整模块

```
✅ DiscourseBlockTree         3,400行 (12模块 + 179测试)
✅ 语义提取 (4层)             jieba+stanza+lmstudio+deepseek
✅ OCEAN 10维 + BFI校准       EMA+CoT+BFI优先
✅ ABC 神经符号               三层决策, C层80%主导
✅ 对话树持久化               修正网关+HCWA分层
✅ switch gateway             4轮工业级迭代 (断路器+Gradient2+...)
✅ Python Gateway API         60端点, 代理switch
✅ switch ↔ DialogMesh 绑定   SwitchGatewayProvider
✅ CLI (8命令)                chat/test/ab/profile/...
✅ 修正日志                   correction_journal+漂移检测
✅ P0-P3 20/20模块接入        全孤岛解决
✅ AnnotationStore            P2持久化层
✅ 文档摄入                   88篇MD→9.8K SemanticObject
```

---

## 五、关键差距

```
设计文档量 vs 代码实现量:

  业务链文档:   3,841 行
  已实现代码:   ~15,000 行 (对话树+OCEAN+API+网关+...)
  设计覆盖:     10 链 + 2 补充 + 1 审计
  代码覆盖:     ~4.5 链 (01-04 完整, 05-08 部分, 09-10 零)
  
  差距: 业务链设计超前代码实现 ~2x
  瓶颈: 链 05-10 的核心逻辑需要从文档转化为代码
```

---

## 六、优先实现路线

| 优先级 | 内容 | 影响链 | 估时 |
|:---:|------|--------|:---:|
| P0 | **元认知核心** (审核队列+复盘引擎) | 链09→全部 | 5d |
| P0 | **子图编译器** (对话树+元认知双视角) | 链10→链01,09 | 3d |
| P0 | **画像 v2** (惯性权重图) | 链08→全部 | 3d |
| P1 | **行为发现三阶段** (统计→展示→审核) | 链05 | 3d |
| P1 | **关联链 L1.5 补全器** | 链06 | 2d |
| P1 | **Git 版本控制** | 链09 | 2d |
| P2 | **关联链 L2.5 信念凝聚** | 链06 | 2d |
| P2 | **工程链递归地图** | 链07 | 3d |

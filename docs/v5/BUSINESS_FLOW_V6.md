# DialogMesh v6 — 端到端业务流

> 2026-07-24 · 当前实现 · 全链路

---

## 用户输入 → 全链路处理

```
用户: "先定位延迟，然后修复，顺便评估影响范围"

═══════════════════════════════════════════════════════════════
Layer 0: 信号采集 (<10ms)
═══════════════════════════════════════════════════════════════

  InputSanitizer → 安全过滤
  HeaderInjector → 指代消解 (SyntacticDecomposer 语法检测)
  SyntacticDecomposer → SVO拆解
  MacroMicroQuantizer → 9D cohesion

═══════════════════════════════════════════════════════════════
Layer 1: 认知路由 PCR V2 (<50ms, 可选LLM+200ms)
═══════════════════════════════════════════════════════════════

  StructuralFeatures → entity_count, verb_count
  X轴: nomic(S,O)cosine + IDF → 认知距离
  Y轴: STC syntactic complexity → 操作粒度
  Z轴: nomic 768d mood → 反馈期望
  Zone: EXPLORE (远+浅+探索)
  
  LLMReview (可选): nemotron 3 二进制信号检验
  LLMEntityGapFill: "延迟"→entity, "影响范围"→entity
  
  ExecutionMode: react (EXPLORE zone)
  
  ↓ 路由结果 → Orchestrator

═══════════════════════════════════════════════════════════════
Layer 2: 意图解析 MultiIntent (~1.2s DeepSeek)
═══════════════════════════════════════════════════════════════

  热路径 MultiIntentSplitter (~800ms):
    LLM: "三个独立意图: 定位延迟 + 修复 + 评估影响"
    → multi=True, segments=["定位延迟","修复","评估影响"]

  冷路径 MultiPerspectiveAnalyzer (后台, ~3s):
    4视角并行:
      literal:    accept 0.95 "三个独立动宾语"
      profile:    accept 0.85 "高C倾向结构化"
      association: accept 0.85 "实体在不同关系簇"
      discourse:  accept 0.95 "话题延续"
    → MASTER合成: multi=True, 0.92
  
  如死锁(2:2) → AmbiguityBridge → L2.5信念累积

═══════════════════════════════════════════════════════════════
Layer 3: 关联链 L1→L4
═══════════════════════════════════════════════════════════════

  L1 Modifier: Stanza提取修饰语, deprel_config驱动
  L1.5 Completer: syntax ∩ LLM 共识融合
  L2 RelationSubstrate: 9种边+EntityNode+2跳遍历
  L2.5 BeliefAccumulator: 贝叶斯多源累积+7D belief
  L3 Intent: 4视角投票+LLM死锁解决
  L4 Temporal:
    T-BN: P(修复|诊断)=0.8, P(评估|修复)=0.6
    JS漂移检测: JSD=0.15 → 无异常
    LLM协同: 验证转移合理性, 调整阈值

═══════════════════════════════════════════════════════════════
Layer 4: 对话树 DiscourseBlockTree
═══════════════════════════════════════════════════════════════

  DiscourseBlockTreeManager.feed():
    → segment_turn (cohesion断崖切分)
    → route_block (continue/attach/fork/merge)
    → update_summary (v1→v2→v3→v4 渐进式)

  BM25 TopicQuickMatch (~5ms):
    jieba分词 → BM25匹配 → "延迟"→"性能故障" 2.75

  BM25→LLM 双轨 (可选):
    LLM验证匹配 → 漂移检测 → 3次后迁移

  SummaryEngine.build_context():
    温度分级:
      Hot blocks: 全文 [Hot·★★★·Near]
      Warm blocks: entity摘要 [Warm·★★·Mid]
      Cold blocks: milestone保留
      Frozen: 索引检索

  ThreeParadigmContext.build():
    温度×价值×距离 排序 → 结构化标签
    → "[Hot·★★★·Near] 定位延迟... [Cold·★·Far] 上月例行部署..."

  PosteriorCorrector: 漂移证据累积→节点重新隶属

═══════════════════════════════════════════════════════════════
Layer 5: 行为链 Behavior
═══════════════════════════════════════════════════════════════

  BehaviorEdge.record_observation():
    → 自适应阈值: success_threshold = old*0.9 + rate*0.1
    → 稳定性判定: rate > threshold AND inst < threshold

  BehaviorLLMCollaborator:
    explain_drift: LLM解释行为变化
    discover_patterns: LLM发现异常模式
    suggest_and_apply: LLM调参→回写edge (70%统计+30%LLM)

═══════════════════════════════════════════════════════════════
Layer 6: 工程链 Engineering
═══════════════════════════════════════════════════════════════

  EngineeringChain.snapshot():
    MCP ClientManager → 可用工具列表
    ToolRegistry → 注册工具
    env: {os, python, cwd}

  check_feasibility("定位延迟"):
    → matching_tools: [gdb, perf, strace]
    → feasible: True

═══════════════════════════════════════════════════════════════
Layer 7: 编排 + 规划 Orchestrator + Planner
═══════════════════════════════════════════════════════════════

  AgentOrchestrator.process():
    全链路协调: PCR → MultiIntent → L4 → Behavior → Engineering
    → LLM合成执行计划
    
  LLMPlanner.plan():
    LLM任务分解:
    {
      "steps": [
        {"task": "定位延迟", "tool": "perf", "parallel": false},
        {"task": "修复", "tool": "gdb", "parallel": false, "depends_on": 0},
        {"task": "评估影响", "tool": "strace", "parallel": true, "depends_on": 1}
      ],
      "confidence": 0.85
    }

═══════════════════════════════════════════════════════════════
Layer 8: 认知层 V4/Cognitive (桥接，待激活)
═══════════════════════════════════════════════════════════════

  Bridge 1: PCR → OceanProfile (route调制OCEAN权重)
  Bridge 2: Behavior → PatternLearner (不稳定边→模式学习)
  Bridge 3: Discourse → MemoryExtractor + TagLayer
  Bridge 4: L4 → BeliefMap (转移→信念)
  Bridge 5: 全信号 → Fusion (TrackA+B → LLM上下文)
  Bridge 6: Trigger → Metacognition (事件→回顾审查)

═══════════════════════════════════════════════════════════════
Layer 9: 监控 + 元认知扳机
═══════════════════════════════════════════════════════════════

  MetacognitiveTriggerEngine.check(signals):
    belief_entropy > 0.5 → compressor_ingest
    intent_drift > 0.3 → l4_explain_drift
    cold_blocks > 20 → compress_cold_blocks
    llm_error_rate > 10% → llm_degraded
    correction_rate > 0.4 → behavior_llm_review

═══════════════════════════════════════════════════════════════
最终输出
═══════════════════════════════════════════════════════════════

  给LLM的上下文:
    [Hot·★★★·Near] 先定位延迟，然后修复，顺便评估影响范围
    [Warm·★★·Mid]   昨天发现AES密钥硬编码→已修复
    [Cold·★·Far]    上月v2.3部署→日常

  LLM回答:
    "好的，我帮你分三步: (1)先定位延迟 (工具:perf)
     (2)根据定位结果修复 (工具:gdb)
     (3)评估影响范围 (工具:strace)
     是否需要我开始第一步？"
```

---

## 模块状态总览

| 层 | 模块 | 状态 | LLM协同 | 延迟 |
|----|------|------|---------|------|
| 0 | 信号采集 | ✅ | 语法检测 | <10ms |
| 1 | PCR V2 | ✅ | nemotron审查+实体补全 | 50-250ms |
| 2 | MultiIntent | ✅ | DeepSeek 4视角 | 0.8-3s |
| 3 | 关联链 L1-L4 | ✅ | L4 LLM协同 | ~200ms |
| 4 | DiscourseTree | ✅ | Summary+BM25双轨 | ~500ms |
| 5 | Behavior | ✅ | 自适应+LLM协同 | ~200ms |
| 6 | Engineering | ✅ | MCP桥接 | ~100ms |
| 7 | Orchestrator+Planner | ✅ | LLM任务分解 | ~500ms |
| 8 | V4 Cognitive | 🔗 桥接就绪 | 待激活 | — |
| 9 | Metacognitive Trigger | ✅ | 7规则监控 | <1ms |

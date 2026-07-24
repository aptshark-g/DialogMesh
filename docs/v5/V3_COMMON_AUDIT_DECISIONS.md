v3_common 剩余模块核查记录
========================

保留 (架构稳定后适配):

  models.py (964L, 18ref, 79类/函数)
    v3.0全量Pydantic数据模型: Intent_v3, TaskGraph_v3, SessionState_v3等
    → 保留, 是8个模块的公共数据契约

  gates.py (421L, 10ref, 21类/函数)
    三层门控+双轨策略: Hot/Cold path routing
    → 保留, 门控逻辑与当前双轨设计兼容

  blueprints.py (207L, 7ref, 7类/函数)
    Blueprint定义+默认库+启动校验
    → 保留, orchestrator.py的依赖

  orchestrator.py (260L, 5ref)
    异步Blueprint执行引擎: 状态传递+幂等+回滚+trace
    → 保留, 与agent_native.py互补(同步调度vs异步执行)

  discourse_integration.py (288L, 4ref, 9类/函数)
    对话集成桥接: 接收原始输入+历史→生成DiscourseBlock
    → 保留, DiscourseTree对接

  integration_bridge.py (534L, 2ref, 18类/函数)
    五层新模块组装器: PCR→Gates→IntentParser→引擎
    → 保留, 全链路组装逻辑

  health_check.py (235L, 1ref, 15类/函数)
    系统健康检查: ComponentHealth, DependencyGraph
    → 保留, 运维工具

  serialization.py (370L, 1ref, 24类/函数)
    序列化/反序列化工具: JSON, MessagePack, 压缩
    → 保留, 通用工具

  adaptive_threshold.py (632L, 1ref, 32类/函数)
    贝叶斯自适应阈值: 已部分被L2.5 BeliefAccumulator替代
    → 保留, 当参考

  intent_parser.py (10L, 13ref)
    兼容shim: 指向PCR V2
    → 保留, 向后兼容

已移往 un_use (已处理):
  system_bootstrap.py (836L)  → v3_0/__init__.py import已清理
  orchestrator.py (668L)      → v3_legacy版, agent_native替代
  expertise_probe.py (703L)   → pcr/llm_expertise.py替代
  intent_rule_registry.py (304L) → PCR V2替代
  metrics.py (221L)           → 合并入observability/
  plugin_system.py (210L)     → 归位discourse_block_tree/
  structured_logger.py (108L) → observability/logger.py覆盖
  alert_manager.py (119L)     → 升级为metacognitive_trigger.py

# 蓝图接线待办清单（2026-08-13）

> 触发: 用户"蓝图就是一堆问题…实现的很糟蹋" — 设计骨架（宏观蓝图+微观
> 执行+元认知监控）成立, 但大量模块存在未接线。逐项补, 每项带验收。

## 已确认的接线缺口（按优先级）

| # | 缺口 | 现状 | 验收 |
|---|------|------|------|
| W1 | **意图→召回策略映射未接** | intent 参数死参数; PCR zone→intent_category 兜底表在生产未走通 | 意图分类后 recall 按意图选路 |
| W2 | **普通对话分支无召回/深度触发** | v3 非 task 分支直接发网关, 无 recall、无子图编译 | 深度信号(query/discussion/详细/深入) → 锚点+compile_from_anchors 注入 |
| W3 | **recall 本体无图扩展** | recall() 只有 _diffuse(内存树); ConceptGraph/cross_ref 扩展只在编译器 | recall 可选 expand_graph（内容边限定） |
| W4 | **bench 无树结构** | FakeBlock parent/child 空 → 评测中扩散空转 | build_service 按 session 建链 |
| W5 | **task 类 query 走执行层轨未接全** | v3 Phase 4 tool_loop 分支有锚点注入; 意图路由未把 task 类 query 统一送执行层 | intent=task → TaskRunner 轨 |
| W6 | **蓝图模板覆盖薄** | 只有 recall_pipeline 等少数模板; 大批业务流未注册 | 业务流集合 ↔ 模板注册表比对, 缺口补齐 |
| W7 | **行为链学习深度偏好未做** | 用户频繁深挖的话题 → 扩展深度自适应（设计有, 实现无） | 行为链信号 → 扩展深度调节 |

> 施工顺序: W4 → W2 → W5 → W1 → W3 → W6 → W7（W4/W2 本轮做）

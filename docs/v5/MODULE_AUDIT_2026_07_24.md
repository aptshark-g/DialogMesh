# DialogMesh v6 模块审计报告

> 2026-07-24 · 全模块完成度与方案评估

---

## 一、已完成模块 (LLM 协同 + 零硬编码)

| 模块 | 行数 | 方案 | LLM协同 |
|------|------|------|---------|
| association/l4_temporal.py | 241 | T-BN转移预测 + JS漂移检测 | ✅ 漂移解释 + 转移验证 |
| association/l4_collaborative.py | 183 | 双轨反馈闭环 | ✅ 结构上下文→LLM→修正阈值 |
| association/l2_5_belief.py | 286 | 贝叶斯多源累积 | ✅ LLM触发 + 阈值自适应 |
| association/l3_intent.py | 218 | 4视角投票 | ✅ LLM死锁解决 |
| association/l1_5_completer.py | 305 | 语法+LLM协同补全 | ✅ DeepSeek始终协同 |
| behavior/llm_collaborative.py | 202 | LLM协同行为分析 | ✅ 解释+模式发现+调参 |
| behavior/models.py | 152 | 自适应阈值学习 | ✅ 统计70%+LLM30%融合 |
| compiler/discourse_block_tree.py | 917 | 对话树核心 | ✅ 温度摘要 + context注入 |
| compiler/topic_quick_match.py | 216 | BM25+jieba + LLM双轨 | ✅ 快匹配→慢验证→漂移迁移 |
| compiler/three_paradigm_context.py | 173 | 三范式罗盘 | ✅ 温度×距离×信息价值 |
| compiler/posterior_corrector.py | 141 | 后验修正 | ✅ 证据累积→节点重新隶属 |
| compiler/summary_engine.py | 137 | 渐进式摘要 v1→v4 | ✅ 算法提取结构→LLM压缩 |
| intent/multi_intent_splitter.py | 118 | LLM-first 拆分 | ✅ 零硬编码分割标记 |
| intent/multi_perspective.py | 211 | 4视角分析 | ✅ DeepSeek 5次LLM |
| intent/dual_track.py | 156 | 热/冷双轨 | ✅ 热路径<1s 冷路径后台 |
| intent/ambiguity_bridge.py | 101 | 死锁→L2.5桥接 | ✅ 贝叶斯证据流 |
| pcr_router_v2.py | 600 | 3D坐标路由 | ✅ LLM审查 + 实体补全 |
| engineering/chain.py | 136 | MCP工具桥接 | ✅ 工具可行性分析 |
| llm_config.py | 47 | 全局参数配置 | ✅ 11处硬编码→config |

---

## 二、已有但未集成 LLM (核心模块)

| 模块 | 行数 | 当前方案 | 缺口 |
|------|------|----------|------|
| cognitive/derivation_compressor.py | 274 | 发散→收敛压缩 | 未接入引擎event流 |
| topic_tree/manager_v2.py | 1092 | 话题树路由 | 未用三范式标签 |
| orchestrator/orchestrator.py | 999 | 任务编排 | LLM已有, 未全链路 |
| planner/planner.py | 794 | 任务规划 | 无LLM参与 |
| context/manager.py | 725 | 上下文管理 | 未用温度×价值 |
| runtime/engine.py | 3520 | 全局引擎 | 已接入discourse+compass ✅ |

---

## 三、历史遗留 (待清理/标记)

| 目录/模块 | 行数 | 状态 |
|----|------|------|
| v3_legacy/ | 2400+ | 旧V3架构, 等待废弃 |
| v3_common/ | 1900+ | V3公共模块, 等待迁移 |
| v3_0/cognitive_tree/ | 2600+ | 旧认知树, 等待废弃 |
| v4/cognitive/ | 2500+ | V4认知(behavior_discovery等已集成) |
| router/router_v4.py | 117 | ✅ 已标DEPRECATED |
| classifier/ | 159 | 旧分类器 |
| tiered/ | 500+ | 分层处理(部分有用) |

---

## 四、未完成(设计存在但未实现)

| 设计 | 状态 |
|------|------|
| L5 长期记忆 | 设计存在, 0代码 |
| ReactFlow 可视化 | 前端任务, 待 |
| compress_cold_blocks 后台 | 接口在, 未定时触发 |
| segment_turn 测试 | 代码在, 缺测试 |
| Engine → DerivationCompressor 接线 | 待接 |

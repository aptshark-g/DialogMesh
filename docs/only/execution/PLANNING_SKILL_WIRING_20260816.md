# PlanningSkill 第二规划通道接线（2026-08-16）

> 状态: 施工完成 ✅ | 触发: 用户"继续完成2"（接 PlanningSkill 第二规划通道）
> 前置: planner/ 六策略规划器实现完整但从未接生产——核查发现其
> IntentCategory 枚举与规则模板全部是旧项目（游戏逆向/内存修改）残留,
> 直接接线 = 接错器官。做法: 适配层 + 通用模板 + 生产接入。

## 一、适配层（planner/ 领域适配）

### 1. 通用任务模板（_plan_rule_based 扩展, 零 LLM）
- `intent.metadata["intent_label"]` 驱动: task_planning / code_analysis /
  data_search / recall 各给真实骨架（read→plan→implement→verify→report 等）
- 原逆向模板（SCAN_MEMORY 等）保留不动; 其余走通用模板/兜底

### 2. LLM prompt 通用化（planner/models.py）
- `llm_system_prompt`: reverse-engineering assistant → 中文通用任务规划器

## 二、生产接入（v3_session_api.py）

- `_PlanningGatewayProvider`: PlanningSkill.generate_async → switch 网关
  （deepseek-v4-flash, thinking 关, 15s 预算）
- `_plan_with_skill(text, intent_label)`: Intent_v3 → PlanningSkill.plan
  （HYBRID: 规则骨架 + LLM 细化; 网关不可用 → 骨架兜底）→ 拓扑步骤 +
  前端 task_graph; 全失败 → (None, None) 静默回退
- Phase 4: 无用户确认任务图时调用 → steps 注入 TaskRunner（复用 08-15
  步骤级接线）+ `_seed_task_graph` 落盘前端图

## 三、顺带修复（实测发现的真问题）

1. **双重 LLM 调用卡死（180s+）**: run_dag 的 llm_reply 节点触发
   handle_llm 再调一次 LLM → Phase 4 又调 → `defer_llm=True`（生产跳过）
2. **async 段阻塞 19s**: behavior 节点 BehaviorBrain 初始化/学习同步阻塞
   → `defer_async=True`（生产跳过 priority>=9 段; post-LLM 管线/事件
   订阅仍完成写入）
3. **tool_loop 预算感知**: _call_gateway 固定 90s × 3 重试 + deadline 仅
   轮间检查 → 单轮最长 270s。改: 每轮按剩余预算截断, 预算 <30s 不重试
4. **空回复兜底**: TaskRunner 预算内未完成但有工具产出 → 生成摘要内容
5. **意图分类强化**: casual 收紧 + 示例（写代码/做程序 → 代码分析）
6. **超时预算压缩**: classify 60→20s, 规划 provider 25→15s, TaskRunner
   120→100s

## 四、验证

- 新增测试 8 项（转换纯函数/规则骨架/全链路 mock）; 相关回归 210 全绿
- **真实端到端**（API 重启后, UTF-8 脚本）:
  - 请求 17.9s 返回（此前 180s+ 卡死）
  - intent 分类正确（代码分析 → code_analysis 模板）
  - PlanningSkill 落盘 task_graph = [read_code, analyze, modify, test,
    report]（version=1）
  - 执行树 root steps 与规划一致; 5 节点（1 plan + 4 工具步骤）

## 五、边界

- PlanningSkill 只在无用户确认任务图时生效（用户图优先, 不覆盖）
- HYBRID 的 LLM 细化实测常解析失败（回退骨架）——骨架已足够指导执行,
    LLM 细化质量提升留后续（结构化输出 + 重试）
- 响应里的 task_graph 字段显示 Phase 5 的 fallback 模板节点, 落盘才是
  PlanningSkill 图——前端展示对齐留后续

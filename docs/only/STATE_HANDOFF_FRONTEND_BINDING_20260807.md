# 压缩交接 — 启发管道全链 + 归档审计 + 前端绑定准备（2026-08-07）

> 状态: 压缩恢复唯一入口 | 触发: 用户确认开始前端绑定（B5）前压缩
> 恢复路径: 读本文档 → GLOBAL_PHILOSOPHY_FILTER_FINAL（拍板依据）→
> IMPLEMENTATION_PLAN → 开工 B5（13 页绑定 smoke）

---

## 一、本轮终态（2026-08-07 实测）

### 完成（全部有测试）
1. **二阶抽象提炼管道全链**（A24 / blog chapter3）:
   - `heuristic_inventory.py`（四元组链模型 + 示范种子 ×2 + 库存/检索/注入/
     持久化 + 结构模板）
   - `heuristic_distiller.py`（发散变体家族/收敛/反事实/LLM 反推 60-80%/
     规则兜底 P×I 路由 + information_value LLM 语义价值）
   - 生产接线: engine 挂载 + llm_reply 注入 [决策依据] + 失败/纠正变化触发
     （节流）+ 白盒视图（CLI dm heu + /v6/heuristics + RightDock「启发」tab）
2. **归档审计**（UN_USE_AUDIT_20260807）: 2 处高价值断线已接入 —
   memory_strategy_federation（恢复 + distiller P×I 聚类）+
   TieredNegativeKB（恢复 + executor 工具校验 HARD_BLOCK 拦截）
3. **GAP-5 taint**（executor 回合污染 + [不可信] 标注）+
   **GAP-O4 world 归位**（compiler._ensure_backbone 接线, importance 7 策略
   从零消费变活跃）+
   **启发活性监测**（coverage 阈值 → deactivate + 事件）+ **反推成本**
   （采样 20→12 + 护栏）
4. **GAP-F1 变更日志视图**（/v6/changelog + intervene + RightDock「变更日志」
   tab, git log + PR review 语义）
5. **博客校准**（chapter3 两处实现校准: 变化驱动触发 / 种子≠公理清单）

### 测试状态
各套件全绿: 启发 33 / taint 5 / tiered 5 / world importance 3 / changelog 4 /
回归（kernel_dispatch 49 / tool_batch 8 / learning_bridge 12 / production 3 /
learn_template 4）; 前端 tsc 归零 + build 成功

### 环境状态
- **服务未监听**（8000/8080/5173 均无）— 用户以为已启动, 实际 start.bat
  需重新运行（启动: 双击 start.bat 或命令行）
- 网关 Switch 8080; `DEEPSEEK_API_KEY` 新 shell 需重设
- git 未提交（按惯例）: 真实改动 530 条（M1-M9 起累积, pycache 噪音已滤）

## 二、B5 前端绑定计划（下一步）

目标: 13 页 × 真数据端点 smoke 验证（页面→API 全链路, 无 stub 假数据）
方法（TROUBLESHOOTING §7 方法论）:
1. 页面清单: Chat/ChatOverlay/ConversationGraph/Gateway/Pipeline/MetaCenter/
   Behavior/DeepChain/Engineering/Dashboard/Sessions/Settings/TaskPlanning
2. 每页: 挂载真数据 → 控制台无 404/TypeError → 关键交互（编辑/提交）可用
3. 端点抽查: /v6/* 内核 dispatch 真数据（stubs 已消假）
4. 重点: 图谱页 ReactFlow 鼠标交互（TROUBLESHOOTING §10 遗留验证）、
   白盒编辑（B1 版本化已就绪）、RightDock 各 tab（启发/变更日志/上下文/
   工程链真数据）

## 三、恢复三步
1. 读本文档（终态 + B5 计划）
2. 读 RECOVERY_PLAN_20260803.md（顶部已指向本文档）
3. 启动 start.bat（8000 + 8080 + 前端）→ 开工 B5

## 四、关键文件索引（docs/only/）
- 启发: wise/HEURISTIC_DISTILLATION_DESIGN_20260806.md（定案含种子理论/
  P×I 修正）+ wise/HEURISTIC_DISTILLATION_IMPL_20260807.md +
  wise/MEMORY_FEDERATION_CLUSTERING_20260807.md +
  wise/TIERED_NEGATIVE_KB_IMPL_20260807.md
- 审计: UN_USE_AUDIT_20260807.md
- 前端: frontend/FE_DEEP_AUDIT_ROUND2_20260806.md +
  frontend/FE_CONTRACT_REGISTRY_20260806.md + frontend/B1_B6_IMPL_20260806.md +
  frontend/GAPF1_CHANGELOG_20260807.md
- P2: blueprint/P2_TAINT_WORLD_HEALTH_COST_20260807.md +
  blueprint/GAP34_IMPL_20260806.md

# 阶段 B P0 施工 — task_graph 版本化（内存态 + 冲突检测）

> 日期: 2026-08-06 | 状态: 完成 ✅
> 触发: 用户报告"LLM 规划图 → 后端直接落盘 → 前端编辑被状态刷新吞掉"
> （无内存态工作区 + 无版本冲突检测）。登记于 TROUBLESHOOTING 状态核查
> "新增问题" + FE_CONTRACT_REGISTRY §5。

---

## 一、问题根因（实测）

`core/agent/api/v3_session_api.py` 原实现:
- LLM 规划 → `json.dump` 直落 `task_graphs/{sid}.json`（L399-407）
- GET 每次读文件; PUT 无条件覆盖（L493-502）
- 保护 = "文件存在性" 而非版本号 → 前端画布编辑态与后端文件之间无协议
- 竞态: LLM 新规划 / 后台刷新 / 多窗口并发 → 用户编辑被覆盖或"看起来被吞"

## 二、施工内容（前后端闭环）

### 后端（v3_session_api.py）
1. **内存态工作区** `_TASK_GRAPH_WORKSPACES`（热, 线程锁保护）+
   落盘兜底（温, 含 version 字段, 临时文件原子替换）
2. 辅助函数:
   - `_get_task_graph_ws(sid)` — 内存优先, 盘兜底, 返回 `{nodes, edges, version}`
   - `_put_task_graph(sid, nodes, edges, version)` — 冲突检测 + 覆盖 + version+1
   - `_persist_task_graph(sid, ws)` — 写盘（原子）
   - `_seed_task_graph(sid, nodes)` — LLM 规划仅在 version==0 时写入（不覆盖用户版本）
3. `GET /task-graph` → `{nodes, edges, version}`（内存优先）
4. `PUT /task-graph` → 请求带 `version: Optional[int]`:
   - 不带 version = 强制覆盖（向后兼容旧前端）
   - 带 version 且 < 当前 → **409** `{error: version_conflict, current_version, nodes, edges}`
5. 消息处理落盘处改用 `_seed_task_graph`（保留"不覆盖用户确认版本"语义,
   从"文件存在性"升级为"version==0"判断, 含内存态）

### 前端
1. `api/session.ts`:
   - `TaskGraphData`（nodes/edges/version）
   - `TaskGraphConflictError`（409 → 携带 current_version + 服务端内容）
   - `saveTaskGraph(sid, nodes, edges, version?)` — 带 version=乐观更新,
     不带=强制覆盖; 409 抛冲突错误
   - `getTaskGraph` 返回 version
2. `pages/TaskPlanningPage.tsx`:
   - `versionRef` 跟踪当前版本（加载时初始化, 保存成功后更新）
   - 自动保存（2s 节流）带 version → 409 静默置冲突标志（保留本地编辑）
   - 冲突提示条（amber）: "服务端规划已更新（vX）, 本地编辑保留中"
     - **覆盖服务端** → 强制保存（不带 version）
     - **放弃本地** → 重新加载服务端版本
   - 确认按钮: 冲突未解决时确认 = 强制覆盖

## 三、验证

- 后端新增测试 `core/agent/api/tests/test_task_graph_versions.py` **8/8 全绿**:
  GET 空 version=0 / 无 version 强制覆盖 / version 递增 / 过期 version→409 /
  seed 不覆盖用户版本 / seed 空版本写入 / 重启（清内存）盘兜底带 version /
  盘文件含 version 字段
- api 目录回归: `test_kernel_dispatch` + `test_task_graph_versions` +
  `test_viz_edit` = **86/86 全绿**
- 前端: `tsc` 归零 + `vite build` 成功（2.18s）

## 四、对齐哲学

- 内存态=热 / 落盘=温: 与 tiered_storage 分层一致
- 不覆盖用户确认版本: 与 B5-3（用户控制权）/ A19（白盒）一致
- 冲突显式呈现给用户: 与"用户介入决策"设计一致（覆盖/放弃由用户选择）
- 向后兼容（无 version = 强制）: 旧调用不破, 符合 A17 记录不可删

## 五、遗留/后续

- ConversationGraphPage 图谱编辑（/v6/edit/*）同型问题: api_viz_edit 直接改
  引擎对象无版本 — 列为阶段 B P1（同方案推广: workspace + version + 409）
- 蓝图 DAG 视图（LLM 每次现构建）: 无持久视图 — 后续结合 B1-8 认知容器
  决策后再定
- TaskPlanningPage 自动保存 409 只置标志（不弹窗）, 符合"编辑中不打扰"。

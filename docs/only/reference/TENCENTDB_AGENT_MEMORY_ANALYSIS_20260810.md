# TencentDB Agent Memory 参考分析（2026-08-10）

> 项目: https://github.com/TencentCloud/tencentdb-agent-memory
> 定位: OpenClaw/Hermes 的记忆插件（Memory-as-a-Plugin）, MIT, Node/TS
> 评测: token -61.38% / pass rate +51.52% / PersonaMem 48%→76%

---

## 一、核心架构（与我们高度同构, 验证了方向）

### 1. L0-L3 语义金字塔（长期记忆分层）
```
L3 Persona    persona.md      —— 用户画像/偏好（顶层, 高密度, 人可读）
L2 Scenario   scene_blocks/*.md —— 场景块（工作流/SOP 模式）
L1 Atom       原子事实（LLM 提取 + 去重）
L0 Conversation 原始对话
```
- 提炼管道: L0 捕获 → L1 提取(dedup) → L2 场景聚合 → L3 画像
- **checkpoint 增量**: 只处理 changed scenes（last_persona_time 之后更新的）
- **progressive disclosure**: 上下文只注入顶层, 出错时 drill-down 到低层

### 2. 符号记忆（Symbolic Memory, 短期上下文压缩）
- 底层: refs/*.md 存原始工具日志（全量 offload）
- 中层: jsonl 步骤摘要
- 顶层: **Mermaid Canvas**（高密度符号图, 带 node_id）
- 注入机制: mmd-injector 把 MMD 作为标记消息注入 messages, token 计数,
  L3 压缩时用历史 MMD 替换丢失上下文
- node_id 追踪: LLM 在符号图上推理, 要细节就 grep node_id 取原文

### 3. 存储后端（factory 可插拔）
- "sqlite"（默认）: SQLite + sqlite-vec + FTS5(BM25) —— 零服务进程
- "tcvdb": 腾讯云向量库（服务端 embedding + hybridSearch）
- BM25 本地编码器独立组件

### 4. 安全设计
- SceneExtractor 的 LLM 沙箱: workspaceDir=scene_blocks/, 系统文件
  （checkpoint/persona）对 LLM 物理不可见 —— LLM 自主读写信件文件

---

## 二、与我们的映射（方向验证 ✅）

| TencentDB | DialogMesh | 状态 |
|---|---|---|
| L0-L3 金字塔 | 对话树分层（Hot/Warm/Cold）+ 画像 profile | ✅ 已有 |
| scene 场景提炼 | 二阶抽象/启发蒸馏/行为链 DPO | ✅ 已有 |
| L3 Persona | 画像（track A/B）| ✅ 已有 |
| 符号记忆 MMD | 蓝图任务图 + 前端 Mermaid 可视化 | ⚠️ 部分（注入上下文未做）|
| 渐进披露 drill-down | 召回锚点 → 执行层精确查阅 | ✅ 已有 |
| sqlite-vec + FTS5 | UnifiedStore(BGE+LSH) + BM25 + SPO | ✅ 已有（更复杂）|
| checkpoint 增量 | 需核查（可能全量重复提炼）| ⚠️ 待查 |
| LLM 沙箱写文件 | 蓝图编辑/权限门 | ✅ 已有（PermissionEngine）|

---

## 三、可借鉴点（真正的增量价值）

1. **MMD 符号注入 LLM 上下文**（最大差距）
   - 我们把蓝图/执行迹存在内部结构, 但没以高密度符号形式注入 LLM 上下文
   - TencentDB 的 mmd-injector 有完整机制: 注入位置/标记/token 计数/L3 替换
   - 我们 exec 层 tool_loop 的上下文注入可以学: 用紧凑符号图代替 verbose 日志
   - 这与我们"蓝图=任务地图"定案直接呼应（执行时把图符号注入上下文）

2. **checkpoint 增量提炼**
   - 我们的二阶抽象/蒸馏是否每次全量? 若全量则改增量（changed 信号）
   - 他们的 CheckpointManager + scene_index.updated 时间戳

3. **LLM 沙箱工作目录**
   - SceneExtractor 把 LLM 限制在 scene_blocks/ 目录写文件
   - 我们蓝图 subgraph 编辑可以让 LLM 只写子图文件（权限收窄）

4. **评测方法论**
   - SWE-bench 连续 50 任务模拟长会话上下文压力
   - PersonaMem 48%→76% 的长期个性化评测
   - 我们的 DOC_RECALL_BENCH 是文档召回, 可加"连续会话压力"维度

5. **存储后端抽象验证**
   - 他们 factory: sqlite/tcvdb 切换 —— 印证我们 GraphBackend Protocol 方向
   - sqlite-vec 是轻量首选（我们 G10 阶段 2 保守替代, 现在可用）

---

## 四、差异（他们没做而我们有的）

- 元认知仲裁（异步介入/双向归因/偏差即养分）
- 蓝图宏观控制（任务地图/重规划/约束注入）
- 行为链 DPO / 因果链 C1-C5 / 二阶抽象公理
- 混合锚点召回（BGE+BM25+SPO+HyDE+扩散, 溯源置信度）
- 写即索引 + G0 记忆闭环（产出内容跨重启可召回）
- 时序约束召回（文档版本新旧降权）
- 多工具执行层（tool_loop + 权限门 + OS 工具）

---

## 五、结论

- **方向验证**: 分层记忆 + 符号化 + 渐进披露 + 异构存储 —— 与我们的
  设计哲学高度一致, 说明之前拍板正确
- **最大可学**: MMD 符号注入 LLM 上下文（token 省 61% 的实证）——
  我们的 exec 上下文注入可借鉴; 这也是"蓝图=任务地图"的执行侧落地
- **待决策**: 是否把"执行迹 → 紧凑符号图注入 tool_loop 上下文"列为
  下一施工项（对应我们 EXECUTION_LAYER_ARCHITECTURE 的上下文管理）

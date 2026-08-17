# 压缩交接 — 前端治理白盒绑定完成 + B 类后端需求待开工（2026-08-17）

> 状态: 压缩恢复唯一入口（本轮）
> 前置: docs/only/STATE_HANDOFF_RECALL_ABLATION_20260816.md
> 恢复三步: 读本文档 → 读 RECOVERY_PLAN（顶部已指向）→ 读 AGENTS.md +
>  追踪矩阵 + docs/only/frontend/UI_REFACTOR_PLAN.md（B1-B16 登记表）
> 环境: 8000 API 在跑（本会话启动, PID 42040, 含治理端点）; 网关 8080 /
>  前端 4173 未起（需要时 start.bat 或单独起）; 工作区剩 4 个临时 py
>  （fibonacci/hello_world/sum_*.py, agent 测试残留, 未提交）

## 〇、提交线（均本地, 未推 GitHub; 8aeb070 后工作区基本干净）

```
8aeb070 前端治理白盒绑定（8 端点 → GovernancePanel + MetaCenter 治理 tab）
        + 用户并行 UI 重构 P1-E~P1-O/P2/P3 收尾 + 截图记录（108 文件, 一起交）
e656f70 HyDE 方向收尾: 域门控（_hot_is_doc）+ DM_SPO_LLM_JUDGE 隔离 →
        K3 干净对照 = 基线无增益; HyDE→BM25 词项扩展实测负（默认关）
8cf3199 真 HyDE 进评测: eval_100 --hyde + 多假设 RRF + 门控 + 3 个真 bug
        （encoder 联网挂起 / SPO 谓词 LLM 爆炸 / generate 兼容）
6cf5727 召回消融矩阵 12+ 组（基线局部最优）+ q059 地面真相修正（C 类 1→0）
```

## 一、前端绑定现状（本轮完成, 全部验证）

### 已绑定
- **治理白盒 8 端点**（新, 2026-08-17）: `frontend/src/components/meta/
  GovernancePanel.tsx` + MetaCenterPage「治理」tab:
  `/v6/governor`（熔断 scope 状态/连败/在飞/治理动作）· `/v6/diagnosis`
  （异步诊断报告）· `/v6/repairs`（自修复包 + 应用/验证通过/验证失败）·
  `/v6/probe`（主动体检 + 立即巡检）· `/v6/warmup`（预热 + 触发）·
  `/v6/system-profile`（自画像）· `/v6/blueprint/suggestions`（蓝图建议）·
  `/v6/llm-calls`（LLM 观测含 trace_id）; 30s 轮询; 类型加在
  `frontend/src/types/api.ts`、封装在 `frontend/src/api/v6.ts`。
- 既有: GatewayPage 真实计费/统计/错误目录; MetaCenter 概览/队列/版本/七树;
  会话切换器（P3 getHistory 真实历史）; 上下文工作台（P1-B /v6/context）;
  顶栏画像状态点。
- 验证: `npx tsc --noEmit -p tsconfig.app.json` 零错误; `npm run build` 成功;
  后端 8 端点全部 200 且返回形状与组件一致（governor{breakers,in_flight,
  recent_actions} / diagnosis{pending,repairs,reports} / system-profile
  {ts,modules,tests,git_history,weak_spots} 等）。

### 未绑定 = B 类后端需求（UI_REFACTOR_PLAN §2 登记表, 下一轮主线）

| # | 需求 | 触发场景 | 前端临时方案 |
|---|---|---|---|
| B1 | `project_id` 实体: session/task/graph-node 挂项目 | 项目组真实过滤 | localStorage 映射 |
| B2 | ContextCompiler 检索加 project 范围 | 项目=认知边界 | 无（等 B1） |
| B3 | 上下文钉住/移除接口（记忆片段级, 作用下轮编译） | 工作台记忆卡三态 | 本地状态 |
| B4 | 画像健康度聚合值（一个数）供顶栏状态点 | 监控撤出右栏 | 复用画像端点取首值 |
| B5 | 会话标题摘要 + 相对时间（替代裸 session id） | 会话列表人性化 | 前端截断 |
| B6 | 画像成功/风险状态指标数据源 | 画像健康度与风险 | 空态 |
| B7 | 画像冷启动语义: turn_count=0 空对象 vs 基线 | 首用画像呈现 | 空态 hasDims |
| B8 | 槽位配对偏好持久化（用户偏好端点） | 跨设备同步 | localStorage |
| B9 | 自动化视口配对协议（远期） | 虚拟机场景 | 无 |
| B10 | /v6/context 补 total_tokens/budget + 稳定 ID | 注入条预算水位 | 求和/指纹键 |
| B11 | 上下文条目↔图谱节点映射 + 图结构选择接口 | 图结构模式 | 占位 |
| B12 | 最终注入上下文编译快照（读+分段级覆写写） | 精调模式 | 占位 |
| B13 | 全局内容搜索端点（会话/上下文/图谱节点） | 万能搜索栏 | 占位 |
| B14 | 元认知代操作协议（NL→规划→GUI/系统操作, checkpoint 审批） | 万能搜索栏"帮我操作" | 无 |
| B15 | 项目 CRUD + 会话归属服务端持久化（/v6/projects + 归属写） | P2 项目组 | localStorage 全量 |
| B16 | 新建会话携带 project_id | 项目内工作流闭环 | 等端点 |

**建议开工顺序**（依赖 + 价值）:
1. **B15+B1+B16**（项目实体闭环: /v6/projects CRUD → session 挂 project_id →
   新建会话携带; P2 前端已可用, 后端补齐是最高价值闭环）
2. **B5**（会话标题摘要+相对时间, 列表人性化, 低风险）
3. **B4+B6**（画像健康度聚合, 顶栏状态点真数据）
4. **B10**（/v6/context 补字段, 工作台预算水位）
5. **B3**（上下文钉住/移除写接口）
6. B8 / B2 / B7（B7 需产品决策: 空态 vs 全 50 基线）
7. B13 / B11 / B12 / B14（大工程, 需设计）; B9 远期

## 二、召回/HyDE 收尾结论（勿重蹈）

- **融合管线局部最优**: 12+ 组消融（route_unique/vec_gate/PRF/CE 三口径/
  指令前缀）全负或中性 → 不再无依据改融合权重。
- **HyDE 本语料无可靠增益**: K1 全负; K3 干净对照（域门控+SPO 隔离）=
  基线（doc 50.8% / dialogue 76.9%）; HyDE→BM25 扩展也负（假设文档缺
  内部词汇）→ DM_HYDE 默认关。若再试 HyDE, 唯一路径 = Query2Doc 用真实
  语料 few-shot 引导生成。
- **评测语料自污染**: docs/ 新增评测主题文档会漂移基线（54.1→50.8）;
  基线锚定当前语料, 换语料重定基线。
- **SPO 谓词 LLM 判定有 50 次进程预算**（DM_SPO_LLM_JUDGE=0 可关）;
  评测注入 LLM 时必须隔离它（否则 dialogue 假回归）。

## 三、环境坑（续用）

- 8000 必须 .venv 起（anaconda torch 死锁）; start.bat 带 pause 会阻塞,
  单独起用 `Start-Process .venv\Scripts\python.exe scripts\start_server.py
  --no-gateway -WindowStyle Hidden`。
- 沙箱 .git 只读 → git add/commit 需提权; 沙箱进程无出网 → 网关需提权。
- PowerShell 管道 GBK 乱码 → 中文脚本写 UTF-8 文件执行。
- 前端验证: `npx tsc --noEmit -p tsconfig.app.json` + `npm run build`;
  改动前确认工作区（本项目有并行会话扫提交先例）。
- 全量 pytest: `.venv\Scripts\python.exe -m pytest core/agent -q --tb=short
  -p no:cacheprovider`（~4min, 2068 绿基线）。

## 四、关键文档

- docs/only/frontend/UI_REFACTOR_PLAN.md（B1-B16 登记表 + P1 分期 + 变更日志）
- docs/only/frontend/DESIGN.md（液体玻璃设计语言 v2）
- docs/only/recall/HYDE_EVAL_20260817.md（HyDE 泛化+研究+负结果）
- docs/only/recall/RECALL_FUSION_ABLATION_20260816.md（融合消融全记录）
- docs/test/EVAL_100_20260817.md（当前语料基线: doc 50.8% / dialogue 76.9%）

## 五、B15+B1+B16 施工状态（2026-08-17 续, 已单测绿, 全量待跑）

> 用户"先补 B 类后端" → 从项目闭环（B15+B1+B16）开工。

### 已实现（5 个文件, 未提交）
- **新增 `core/agent/api/projects_api.py`**（`/v6/projects` CRUD + 会话归属）:
  GET /v6/projects → `{projects, session_project}`（结构对齐前端
  Project{id,name,color,created_at} + sessionProject 映射）; POST 建项目;
  PATCH 改名/改色; DELETE 删项目（归属自动清除）; PUT /v6/sessions/{id}/
  project 归属写（B1）。持久化 `data/projects.json`, RLock 保护。
- **`v3_session_api.py`**: `POST /v3/session` 支持 body `{project_id}`（B16,
  无 body 兼容旧前端）; session dict 挂 project_id; 创建时同步归属映射。
- **`stubs_api.py`**: `/v6/sessions` 列表项补 `id`/`project_id`（B1）;
  前端过滤可用 `/v6/projects` 的 session_project（无需改 /v6/sessions）。
- **`v6_app.py`**: `_try_include projects_api` 注册路由。
- **新增测试 `core/agent/api/tests/test_projects_api.py`（9 项）**:
  CRUD/持久化重载/归属写与清除/删除清归属/端点/404/POST /v3/session 带
  project_id。**9/9 绿**; kernel_dispatch 回归 49 绿（合计 58 passed）。

### 关键 bug（已修, 记录防重蹈）
- **threading.Lock 不可重入死锁**: `create_project` 等 `with _PROJECTS_LOCK:`
  后调 `_save()`（内部再 `with _PROJECTS_LOCK:`）→ 同线程二次 acquire 永久
  阻塞（pytest 卡 5min+ 真因）。改 `RLock`。**凡"持锁函数内部再调持锁
  函数"必须用 RLock**。

### 待办
- **全量 pytest 待跑**: 当前 8000/8080/4173 服务占用 ~4.6GB 内存,
  全量 pytest 再加载模型 → OOM 被系统杀（aborted）。跑全量前先停服务
  或确认内存充足。
- B15 前端切换（projectStore 从 localStorage → /v6/projects）下一轮做;
  B1 的 task/graph-node 挂 project 未做（先 session 层闭环）。
- 上线迁移: 前端本地 dm_projects 数据 → 初始导入后端。

## 六、前端基础治理 + 项目工作区 P0（2026-08-17 续, 已提交本地）

### 本轮完成（全部验证）
- **总览页动态加载**: DashboardPage 会话列表加关键词搜索 + IntersectionObserver
  滚动增量加载（20/批）; 移除无上限逐项动画延迟（防大列表卡死, 电商式懒加载）。
- **会话页同款**: SessionsPage 会话列表搜索 + 增量加载（30/批, 按项目过滤生效）。
- **v6.0 品牌移除**（未发正式版, 研发代号不再外显）: `frontend/index.html`
  title → DialogMesh; Sidebar 徽标删除; DashboardPage 副标题去掉版本前缀。
- **顶部 5 状态卡可读化**: PersistenceOverview 改为中文标签 + 一句用途说明
  （记忆批注/统一记忆/用户画像/规则库/知识图谱）, 去掉 status/records 原始字段。
- **项目=工作区 P0**（方向见 PROJECT_WORKSPACE_20260817.md）:
  项目模型加 `path`; 创建后弹「选择工作区文件夹」（新建自动建 data/projects/{slug} /
  已有浏览选择或手动路径）; `GET /v6/projects/browse` 只读目录浏览（A21: 仅读不创建,
  目录不存在返回空列表非 404）; projectStore 加 setProjectPath。
- **任务页大工程立项**: TASK_EXECUTION_VIEW_20260817.md（完成度/执行轨迹/回放 +
  GitHub 调研清单: flyte/prefect/n8n/langgraph studio）。

### 验证
- `test_projects_api` 13 绿（含 path/create_dir/browse 只读/空目录）;
  `test_gateway_price_sync` 4 绿; tsc 零错误; build 成功（4173 已服务新构建）。
- 实测: POST /v6/projects {path, create_dir:true} 落盘目录 + browse 可见（已清理测试数据）。

### 待办（下一轮）
- 项目页视图（点项目 → 该项目会话/任务/图, 而非全局过滤）; 项目内新建会话（B16 已有）。
- 元认知项目级经验总结（/v6/projects/{id}/digest）。
- 会话 fork/分支 + git 式版本回滚（PROJECT_WORKSPACE 设计稿）。
- 任务完成度: ExecutionTree → 只读聚合端点 + 画布状态着色（TASK_EXECUTION_VIEW P0）。
- B5 会话标题摘要 / 画像健康度（B4+B6）等 B 类未动。

### 环境（现状）
- 8000 API（PID 12652, 含本轮 projects/browse + 价格同步）/ 8080 网关 / 4173 前端均在跑。
- 全量 pytest 前需停服务防 OOM（约 4.6GB 占用）。

## 七、项目页视图 + 设计元信息（2026-08-17 续, 已提交本地）

### 完成（全部实测）
- **项目页视图** `/projects/:id`（`ProjectPage.tsx`, 懒加载）: 侧栏点项目进入专属页
  （不再只是全局会话过滤）; 概览（名称/颜色/文件夹/创建时间/会话数）+ 项目会话列表
  （搜索+进入聊天）+ 设计元信息编辑与凝练。
- **项目设计元信息（二阶抽象）**: 项目模型 `design{philosophy, axioms, goals, source,
  updated_at}`; `GET/PUT /v6/projects/{id}/design` + `POST .../design/digest`
  （LLM 从项目会话实践凝练, 失败降级模板; 开关 DM_PROJECT_DESIGN_LLM, 默认开）。
  实测 digest 真实 LLM 凝练成功（source=llm_digest）。
- **测试**: test_projects_api 17 绿（含 design CRUD + 模板兜底 + 缺项目 404）;
  kernel_dispatch 回归 78 绿; tsc/build 绿; 4173 服务新构建; API 已重启。

### 说明
- digest 会覆盖手动编辑（本就是"再生成"语义）; 手动保存走 PUT source=manual。
- 该轮对用户既有项目跑过一次 LLM 凝练（真实产出, 非垃圾数据）; 可手动编辑覆盖。

### 待办（下一轮）
- 项目页补任务/图数据聚合; 元认知项目级经验总结（P1）; 会话 fork/分支（P2）。
- B 类后端续（B5 会话标题 / B4+B6 画像健康度）。

## 八、项目页小修 + 环境信息面板 + git 只读端点（2026-08-17 续, 已提交本地）

### 完成（全部实测）
- **项目页「新建会话」**: 概览卡右侧加按钮, `createSession(projectId)`
  （B16 创建即归属本项目）→ 直接进入该会话, 无需建后归档。
- **创建时间 bug 修复**: `created_at` 为 epoch 秒而前端按毫秒 `new Date` →
  1970/1/22 假象; store `toProject` 统一转毫秒 + 页面防御转换（>1e12 视为 ms）。
- **工程链副屏 → 环境信息**（DockContents `EnvironmentDockContent`, 原
  raw dump 占位替换）: Git 工作区卡（分支/领先落后/变更数/远端/最近提交/
  变更文件清单）+ 已启动 Skills + 项目关系约束（chapter2 案例引用）+
  项目图关系（节点/边/子图锚点）+ 刷新。
- **git 只读端点** `GET /v6/git/status`（`git_api.py`, 只读无写, A21）;
  工程页模块点击 → 副屏切「节点详情」摘要（默认副屏=环境信息）。
- **文档**: `GIT_VISUALIZATION_20260817.md`（内置 git 可视化 + VS 联动
  方案: 建议先做文件系统/CLI 桥, 再做 VSIX）。

### 验证
- test_git_api 2 + test_projects_api 17 = 19 绿; tsc 零错误; build 成功;
  4173 服务新构建; `/v6/git/status` 实测（main / 11 变更文件 / 最近提交正确）。

### 待办
- 内置 git 可视化（/v6/git/log 提交图 + diff 摘要）; VS 联动（先文件系统桥）。
- 项目页补任务/图聚合; 元认知项目经验总结 P1; 会话 fork/分支 P2; B 类续。

## 九、工程链多模块副屏 + git 写操作 + 后台进程（2026-08-18, 已提交本地）

### 完成（全部实测）
- **工程链副屏多模块化**: 分区可折叠（环境信息/连接/Git 分支/后台进程/Skills）。
- **环境信息（Codex 式）**: 变更 `+N/-N`（numstat 行数统计）、本地、当前分支、
  提交（信息输入 → add -A + commit）、推送（无远端报错）、比较分支/PR 占位;
  最近提交 + 变更文件清单。
- **Git 分支可切换**: `POST /v6/git/branch`（switch / switch -c 新建）;
  git 写操作仅显式触发, 限仓库根, 错误诚实返回; 测试用临时独立仓库。
- **后台进程**: `GET /v6/system/processes`（线程枚举, 已知工作者中文标注）。
- **连接占位**: 本地 / 连接机器 / 手机控制 / 飞书 / 微信（待接入）。
- **Skills**: 关键词搜索 + 滚动列表 + github 下载渠道占位。

### 验证
- test_git_api 3（含临时仓库切分支/提交/推送）+ test_system_api 2 + projects 17
  = 22 绿; tsc 零错误; build 成功; 4173 服务新构建; 端点实测
  （变更 +583/-133、分支 2、进程 6）。

### 待办
- 提交图可视化（/v6/git/log --graph）+ diff 摘要; VS 联动文件系统桥。
- 连接模块协议设计（远程/手机/飞书/微信）; 联网下载 skill（github 渠道）。
- 项目页补任务/图聚合; 元认知项目经验总结 P1; 会话 fork/分支 P2; B 类续。

## 十、前端反人类治理（第一轮, 2026-08-18, 已提交本地）

### 完成（全部实测）
- 副屏滚动修复（flex min-h-0）+ 圆角修正; 玻璃材质确认存在。
- 图谱意图过滤 → 现行分类（后端 kernel_graph 归一化 + 前端新 INTENT_COLOR_MAP,
  中文标签）; 页面用 node.intent。
- 画像 OCEAN → 中文标签（开放性/尽责性/外向性/宜人性/神经质）。
- 工程链重排（递归地图 → 工具技能 → 约束编辑 → 摘要 → 工程模块最底）+
  工程模块滚动增量加载 + 编辑态圆角按钮。
- 网关路由模式可点击切换（setRouterModes）; 用量页 Token 柱状图（按模型
  输入/输出, recharts）。

### 验证
- 61 测绿（kernel_dispatch）+ tsc 零错误 + build 成功 + 4173 服务新构建;
  /v6/graph 实测意图归一化输出（unknown 兜底正确）。

### 待办（详见 FRONTEND_OVERHAUL_20260818.md）
- Mind 空间 / 元认知内页 / 图谱注释与子 tab / 管道页（参数详情+图表+自适应）/
  深层链（解释） / 网关日期范围+命中率 / 递归地图可视化 / 工程模块编辑做实。

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

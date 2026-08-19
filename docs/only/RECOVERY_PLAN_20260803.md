# 压缩恢复规划 — 2026-08-03（2026-08-03 更新）

> 目的: 压缩后按此文档顺序恢复上下文，避免丢状态。
> ****2026-08-19 仓库可上手性: 依赖清单 + 一键安装（最新）:
> 压缩恢复唯一入口 = `docs/only/STATE_HANDOFF_FRONTEND_BINDING_20260817.md`
> （§十三 本轮新增）。根因: gateway.exe / models 未入库, README 缺环境安装。
> 完成: docs/SETUP.md 依赖清单表 + scripts/setup_env.py 一键安装（仅标准库,
> venv/依赖/前端/网关二进制/配置复制, 支持分段） + setup.bat/sh + README
> 快速开始改造。验证: --check 实测（venv 3.13 识别）+ 语法编译通过。
> 提交 8040f5c 后新增本地提交（均未推）。待办: 网关 release 发布后填
> DM_GATEWAY_BIN_URL; 继续 FRONTEND_OVERHAUL 清单。
> ****2026-08-18 前端治理第二轮 + 管道/深层链可读化（最新）:
> ****2026-08-18 前端治理第二轮 + 管道/深层链可读化（最新）:
> 压缩恢复唯一入口 = `docs/only/STATE_HANDOFF_FRONTEND_BINDING_20260817.md`
> （§十一 本轮新增）。完成: 画像单字母维度中文映射（10 维, 上轮未生效根因）;
> 路由切换后端补 PUT + 持久化（上轮 405 根因）; 网关用量时间轴
> （usage_log.jsonl 按日期, X=日期堆叠图, 实测 6 天真实数据）; 管道页
> 说明+运行模式+参数变更记录; 深层链逐 tab 解释。验证: 83 测绿 + tsc/build
> 绿 + 端点实测。提交 7ff4d5d 后新增本地提交（均未推）。环境: 8000/8080/4173
> 在跑。下一轮: Mind 空间 / 元认知内页 / 管道副屏参数详情模块 / 网关命中率。
> ****2026-08-18 前端反人类治理第一轮（最新）:
> ****2026-08-18 前端反人类治理第一轮（最新）:
> 压缩恢复唯一入口 = `docs/only/STATE_HANDOFF_FRONTEND_BINDING_20260817.md`
> （§十 本轮新增）。完成: 副屏滚动/圆角; 图谱意图过滤换现行分类
> （kernel_graph 归一化 + 前端新映射）; OCEAN 中文标签; 工程链重排+增量加载;
> 网关路由可点 + Token 柱状图。验证: 61 测绿 + tsc/build 绿 + /v6/graph 实测。
> 提交 32e100d 后新增本地提交（均未推）。环境: 8000/8080/4173 在跑。
> 下一轮: FRONTEND_OVERHAUL_20260818.md（管道/深层链/Mind/元认知内页等）。
> ****2026-08-18 工程链多模块副屏 + git 写操作 + 后台进程（最新）:
> ****2026-08-18 工程链多模块副屏 + git 写操作 + 后台进程（最新）:
> 压缩恢复唯一入口 = `docs/only/STATE_HANDOFF_FRONTEND_BINDING_20260817.md`
> （§九 本轮新增）。完成: 工程链副屏分区折叠（环境信息 Codex 式变更+N/-N/
> 提交/推送 + Git 分支可切换 + 后台进程 + 连接占位 + Skills 搜索/滚动/下载占位）;
> 后端 /v6/git/branch·commit·push（写操作显式触发限仓库根）+ /v6/system/processes。
> 验证: 22 测绿 + tsc/build 绿 + 端点实测（+583/-133, 分支 2, 进程 6）。
> 提交 2273d99 后新增本地提交（均未推）。环境: 8000/8080/4173 在跑。
> 下一轮: 提交图可视化 / VS 联动 / 连接模块协议 / 联网下载 skill。
> ****2026-08-17 环境信息面板 + git 只读端点 + 项目页小修（最新）:
> ****2026-08-17 环境信息面板 + git 只读端点 + 项目页小修（最新）:
> 压缩恢复唯一入口 = `docs/only/STATE_HANDOFF_FRONTEND_BINDING_20260817.md`
> （§八 本轮新增）。完成: 工程链副屏改环境信息（git/skills/约束/图关系,
> 原占位替换）; `/v6/git/status` 只读端点; 项目页新建会话（B16 创建即归属）;
> 创建时间 epoch 秒 bug 修复。验证: 19 测绿 + tsc/build 绿 + 端点实测。
> 提交 b9b177f 后新增本地提交（均未推）。环境: 8000/8080/4173 在跑。
> 下一轮: 内置 git 可视化（/v6/git/log） / VS 联动（文件系统桥） / B 类续。
> ****2026-08-17 项目页视图 + 设计元信息（最新）:
> ****2026-08-17 项目页视图 + 设计元信息（最新）:
> 压缩恢复唯一入口 = `docs/only/STATE_HANDOFF_FRONTEND_BINDING_20260817.md`
> （§七 本轮新增）。完成: `/projects/:id` 项目页（概览+项目会话+设计元信息编辑/
> LLM 凝练）; 后端 design{philosophy,axioms,goals} CRUD + digest 二阶抽象
> （实测 llm_digest 真实产出）。验证: 78 测绿 + tsc/build 绿 + API 已重启实测。
> 提交 5ad3ddb 后新增本地提交（均未推）。环境: 8000/8080/4173 在跑。
> 下一轮: 项目页补任务/图聚合 / 元认知项目经验总结 P1 / B 类续。
> ****2026-08-17 前端基础治理 + 项目工作区 P0（最新）:
> ****2026-08-17 前端基础治理 + 项目工作区 P0（最新）:
> 压缩恢复唯一入口 = `docs/only/STATE_HANDOFF_FRONTEND_BINDING_20260817.md`
> （§六 本轮新增）。完成: 总览/会话页搜索+滚动增量加载; v6.0 品牌移除;
> 顶部 5 状态卡可读化; 项目=工作区 P0（path + 只读目录浏览 + 创建后选文件夹）;
> 任务页大工程立项（TASK_EXECUTION_VIEW + PROJECT_WORKSPACE 两份设计稿）。
> 验证: 17 测绿 + tsc/build 绿 + 端点实测。提交 9362fcd + 本轮新提交（均未推）。
> 环境: 8000/8080/4173 在跑。下一轮: 项目页视图 / 任务完成度 P0 / B 类续。
> ****2026-08-17 前端治理绑定完成 + B 类后端待开工（最新）:
> ****2026-08-17 前端治理绑定完成 + B 类后端待开工（最新）:
> 压缩恢复唯一入口 = `docs/only/STATE_HANDOFF_FRONTEND_BINDING_20260817.md`。
> 完成: 治理白盒 8 端点前端绑定（GovernancePanel + MetaCenter「治理」tab,
> tsc/build 绿 + 后端 200 验证）+ 用户并行 UI 重构 P1-E~P1-O/P2/P3 一起
> 提交（8aeb070, 108 文件, 均未推）。召回/HyDE 收尾结论见交接 §二
> （融合局部最优; HyDE 默认关; 评测语料自污染）。下一轮主线: B 类后端
> 需求（UI_REFACTOR_PLAN §2 登记表 B1-B16）, 建议顺序 B15+B1+B16 →
> B5 → B4+B6 → B10 → B3。环境: 8000 API 在跑（治理端点可用）; 网关/前端
> 未起。工作区剩 4 个临时 py 未提交。
> （新施工前必读: AGENTS.md + 追踪矩阵 + UI_REFACTOR_PLAN §2）
> ****2026-08-17 HyDE 方向收尾（最新）:
> 压缩恢复唯一入口 = `docs/only/STATE_HANDOFF_RECALL_ABLATION_20260816.md`
> （延续）。完成: 域门控（_hot_is_doc query 级, 会话域完全禁用 HyDE）+
> DM_SPO_LLM_JUDGE 隔离（修 SPO LLM 判定测量混淆）→ HyDE K=3 干净对照
> = 基线（doc 50.8% / dialogue 76.9%, 无增益, 早期 +3.3pp 是假设方差）;
> HyDE→BM25 词项扩展（Rocchio 近似）实测负（§四.5, 假设文档缺内部词汇）;
> DM_HYDE 默认 0 维持。全量 2068 绿。待办: Query2Doc 语料引导生成（若
> 再试 HyDE）/ 前端绑定（用户 UI 改完后）。未推 GitHub。
> （新施工前必读: AGENTS.md + 追踪矩阵 + HYDE_EVAL_20260817.md）
> ****2026-08-17 真 HyDE 进评测（最新）:
> 压缩恢复唯一入口 = `docs/only/STATE_HANDOFF_RECALL_ABLATION_20260816.md`
> （延续）。完成: eval_100 --hyde（真网关 LLM）+ 多假设 RRF（K=3）+
> 向量置信门控 + 泛化性设计（docs/only/recall/HYDE_EVAL_20260817.md,
> 研究对照: HyDE 2212.10496 / RAG-Fusion / Rocchio+HyDE 2511.19349）;
> 同语料实测 K1 全负、K3 doc+3.3pp 但 dialogue-7.7pp → DM_HYDE 默认关;
> 顺带修 3 个真 bug（encoder 联网挂起 local_files_only / SPO 谓词 LLM
> 判定爆炸 50 次预算 / generate 返回约定兼容）; 发现评测语料自污染
> （自加文档漂移基线 doc top1 54.1→50.8, 非代码回归）。全量 2068 绿。
> 待办 P1: HyDE→BM25 词项扩展（2511.19349 正解）/ 域门控（仅冷池）。
> （新施工前必读: AGENTS.md + 追踪矩阵 + HYDE_EVAL_20260817.md）
> ****2026-08-16 第一版稳定化（最新）:
> 压缩恢复唯一入口 = `docs/only/STATE_HANDOFF_V1_STABILIZE_20260816.md`。
> ****2026-08-16 融合消融 + doc 域 miss 根因（最新）:
> 压缩恢复唯一入口 = `docs/only/STATE_HANDOFF_RECALL_ABLATION_20260816.md`。
> 完成: doc 域 29 条 miss 全量归因（A/B/C）+ 12+ 组融合消融矩阵
> （route_unique/vec_gate/PRF/CE 三种候选口径/BGE 指令前缀全净负 →
> 基线局部最优, 证据: RECALL_FUSION_ABLATION_20260816.md）+ q059
> 地面真相修正（doc top1 52.5→54.1%, C 类 1→0）+ 三个实验开关
> （默认关）+ eval_100 setdefault 化。全量 2068 绿。待办: 真 HyDE
> 进评测 / goldset 文档级粒度 / CE 路线并集+段落级打分。
> （新施工前必读: AGENTS.md + 追踪矩阵 + 消融文档）
> 完成: 全量 2068 绿 / 4:21 / 峰值 3.3GB（内存根因 = SemanticEncoder 非单例
> ×8 + stanza 联网挂起 ×6 + HF ×4 + pytest-asyncio 缺失）; 学习闭环持久化
> （LEARNED_TEMPLATES 落盘 + 二阶抽象测试）; 经验 RAG（0.45 语义阈值）;
> 孤儿糅合（suggest_blueprints 接线 + 归档 7 处）; trace_id 传播（§11.2,
> thread-local 跨线程透传）; response.intent 修复。提交: 99e6b0e→40e1f3e
> （9 个, 均未推）。待办: 跨域召回 25% / 贝叶斯概率加权 / 约束空间化（设计
> 要点见交接 §四）+ 前端绑定（用户 UI 改完后）。
> 环境: 8000+8080+4173 在跑; 全量 pytest ~5min 可复跑。
> （新施工前必读: AGENTS.md + 追踪矩阵 + 交接 §六关键文档）
> ****2026-08-15 召回加固 + 空回复根治 + 设计过程基建（最新）:
> ****2026-08-16 执行链路高可用 + 元认知治理/自修自迭代（最新）:
> 压缩恢复唯一入口 = `docs/only/STATE_HANDOFF_SELFREPAIR_20260816.md`。
> 完成: 请求级预算+LLM 观测（call_recorder /v6/llm-calls）+ ExecutionGovernor
> （熔断/定向重试/幂等/自调节）+ AsyncDiagnoser（A10 大环, 网关挂→自动
> 诊断报告）+ SelfIntrospection（系统自画像 /v6/system-profile）+
> SelfRepair P1（git apply+白名单验证+失败回滚 /v6/repairs）+ 自愈经验库
> （贝叶斯 prior, 诊断注入设计约束+既往经验, 凝练回写）。用户判断:
> 对内自修 vs 多 agent —— 外部修缺 a 设计约束=无先验无演进; 元认知
> 持 a 视角=贝叶斯共识根本。提交: 713b27c→dde499c→9b8ab82（均未推）。
> 待办: 主动体检 / Phase1-2 预算 / LLM 凝练教训 / 约束空间化 / 前端绑定。
> 环境: 8000+8080 跑; 重启后首次请求先 /v6/health 预热。
> （新施工前必读: AGENTS.md + 追踪矩阵 + 4 份新设计文档）
压缩恢复唯一入口 = `docs/only/STATE_HANDOFF_20260815.md`。
完成: 语料卫生(50.8%) + 四精排试点全输 fused(cap=4 唯一正收益) +
P9 全文加固(真幻觉率 0.175→0.000) + claim 三分口径 + 空回复根治
（NameError/网关流式聚合/随机空重试/doom 止损/project_map 粗视图）+
AGENTS.md 施工约束 + 承诺级双向追踪矩阵 + 颗粒度变体契约 +
API 改 .venv(anaconda torch 卡死根因)。提交: DialogMesh 5 个 /
switch 3 个（均未推）。P1: claim 复跑 / 蓝图任务形态约束映射 /
多次采样校准。**（新施工前必读: AGENTS.md + 追踪矩阵）
2026-08-13 深夜 网关全套升级 + 前端绑定（最新）:
> 压缩恢复唯一入口 = `docs/only/STATE_HANDOFF_GATEWAY_FRONTEND_20260813.md`。
> 完成: 召回终态(69.2%/31.1%/C=0) + Faithfulness 机制(0.80) + 文档语料
> 入生产池 + HyDE + 意图分类 + 执行轨迹落树(P0) + 网关全套（流式聚合/
> 超时重试/自适应熔断/健康缓存/错误码目录/计费持久化/配额/admin/
> 热更新69ms/压测 3.4K-22.8K req/s） + 前端真实计费绑定。
> 提交: DialogMesh ahead 20 / switch ahead 5（均未推）。
> P1: 意图自适应融合 / 重排层 / HyDE 默认 / task 轨 / 图扩展。**
> **2026-08-13 召回终测 + Faithfulness 机制修复（最新）:
> 压缩恢复唯一入口 = `docs/only/STATE_HANDOFF_RECALL_FINAL_20260813.md`。
> 完成: eval_100 全量 95s（原 919s）/ BM25 Rust 250x / 语料结构切分全覆盖 /
> 多文件期望修复 / C 类归零 / vector_primary 融合（doc top1 31.1%,
> dialogue 69.2%）/ 确定性双跑 / Faithfulness 机制验证（simple 0.80,
> 总 0.29; 根因: deepseek-v4 思维链写进 content → 网关 thinking 开关
> {"type":"disabled"}）/ 蓝图 recall 节点消费 / 网关 health 并行。
> P0 全清; P1: 意图感知自适应融合 / 重排层 / HyDE / task 轨 / 图扩展。
> 环境坑: 沙箱进程无出站网络（网关需 start.bat/提权启动）。**
> **2026-08-12 召回体系完整化（最新）:
> 压缩恢复唯一入口 = `docs/only/STATE_HANDOFF_RECALL_COMPLETE_20260812.md`。
> 完成: 评测集清理(39+61=100)/量化指标(top1 69.2% R@5 94.9% MRR 0.797)/
> StructurePreSplitter 切分/两级粒度/claim 级 Context Recall(0.562)/
> 内容→图(vault 110 节点 159 边 + 图导航 + 隐式边核验)/子图扩展 5 设计/
> Rust 内核(PyBuffer 零拷贝 2ms + 缓存持久化 bug 修复)/
> 蓝图 recall_pipeline 模板。待办 P0: eval_100 全量/Faithfulness/
> BM25 接 Rust/RRF 通用块降权。环境坑 9 条已记录。**
> **2026-08-11 评测面板 + 缓存竞态修复（最新）:
> 压缩恢复唯一入口 = `docs/only/STATE_HANDOFF_20260809.md`（§十二续）。
> 完成: ① G0 索引缓存竞态修复（default/global 分文件落盘, 指纹+维度
> 校验防旧缓存污染, 360/360 块完整落盘, 4 项新测试）; ② 评测面板
> `docs/test/EVAL_DASHBOARD.md|.json`（scripts/eval_dashboard.py, 统一
> 6 类评测产物参数/指标/缺失）; ③ 新缺口 GAP-R11~R14 已记录
> （COMPLETENESS_GAP_INVENTORY §六: 蓝图 recall 未接线 / 锚点硬截断 /
> 孤立标题残块）。goldset 重建后干净基线: 82 query / 360 块,
> rrf top1 29.3%（随机 5.8%）/ CP@5 0.375。待办: Context Recall /
> Faithfulness 未实现; REFINE_CHAIN_DUMP 可重跑（网关缓存 bug 已修）。**
> **2026-08-10 符号注入 + 跨语言召回完成（最新）:
> 压缩恢复唯一入口 = `docs/only/STATE_HANDOFF_20260809.md`（§十/§十一）。
> 完成: 符号注入（trace→Mermaid 状态图 + tool_loop 上下文压缩,
> 端到端 3 步工具链验证 + 回归 42/42）; 跨语言召回（bge-m3 统一
> 1024 维, en top1 0%→24%, BM25 跨语言保护 + 向量粗筛）。
> 决策: 保 bge-m3 统一（中文 -10pp 换跨语言）; 符号注入=下一施工项已完成。
> 施工记录 = docs/only/execution/SYMBOL_INJECTION_IMPL_20260810.md;
> 决策 = docs/only/recall/RECALL_CROSSLINGUAL_DECISION_20260810.md。
> 开放项: 提炼器升级/token 阈值/原文落盘 refs/统一提炼调度层。**
> **2026-08-10 chromadb 环境修复完成（最新）:
> 压缩恢复唯一入口 = `docs/only/STATE_HANDOFF_20260809.md`（§八）。
> chromadb 1.5.9 装入 .venv（清华镜像）+ 三处 chromadb 入口离线化
> （ChunkStore/ChromaBridge/ChromaStore, 本地 embedding 零下载）+
> UnifiedStore 持久化接线（unified_persist, DM_CHUNK_BACKEND=unified
> 自动开启）。测试: .venv 119/3（3 failed 预存在环境差异）+ anaconda
> 116/1 skipped。施工记录 = docs/only/storage/CHROMADB_ENV_FIX_20260810.md。
> 剩余待办: 博客 chapter4 / 前端 B / 层3 变体 / 跨域召回 / trace_id §11.2。**
> **2026-08-09 深夜 召回体系完成（最新）:
> 压缩恢复唯一入口 = `docs/only/STATE_HANDOFF_20260809.md`（§七）。
> 完成: 量化评测体系（50 查询/2444 块/GPU/基线 44%）+ 时序约束(+6pp,
> cross 0→25%) + recall→subgraph 桥 + 情景再现端到端三支全通（真实
> LLM）+ 写即索引 + G0 记忆闭环（跨重启可召回）。提交线: v1 已推,
> 本地 5 个未推（dd1ef66→35a96f2）。待办: chromadb 环境修复 / 博客
> chapter4 / 前端 B / 层3 变体 / 跨域召回 / trace_id 传播 §11.2。
> 环境: 8000/8080 跑, .venv torch GPU, clash 7877 可出网。**
> **2026-08-09 v2 执行层施工完成（最新）:
> 压缩恢复唯一入口 = `docs/only/STATE_HANDOFF_20260809.md`。
> v2 执行层分层落地: tool_loop 增强（约束注入/工具白名单/超时/步钩子/
> trace）+ ExecutionMonitor 三层监控（Hot/Warm/Cold, 确定性裁决）+
> TaskRunner 蓝图节点执行壳（重规划循环 + 三层介入 + 复盘回流）+
> 接线（statemachine agentic 工具节点 / v3 Phase 4 任务图约束注入 /
> GET /v6/execution/{sid} 白盒视图）。验证: 新测试 22 + 回归 150 全绿 +
> 真 LLM 端到端冒烟（自主 write_file→run_shell→总结, 3.8s）。
> 施工记录 = docs/only/execution/V2_EXECUTION_LAYER_IMPL_20260809.md。
> 下一步: ①第一版收尾（README/commit+push GitHub）或 ②前端执行迹绑定
> （阶段 B）, 用户定优先级。**
> **2026-08-09 压缩交接（最新）:
> 压缩恢复唯一入口 = `docs/only/STATE_HANDOFF_20260809.md`
> （召回第二批 + OS 工具 + function calling + 第一版核对终态）。
> 本轮完成: 黄金集+RRF(+12.5pp top1)/G0 索引缓存/2 个 vector bug 修复/
> OS 工具集(run_shell/run_python/run_session/dir_list/grep)/tool_loop
> function calling 端到端(LLM 自主写文件+运行)/执行层分层架构定案/
> 第一版核对全绿(1856 测试+前端 19/19)。
> 恢复三步: 读交接文档 → RECOVERY_PLAN → 下一步 v2 执行层施工或
> 第一版收尾(README/commit+push GitHub), 用户定优先级。**
> **2026-08-07 晚压缩交接（最新）:
> 压缩恢复唯一入口 = `docs/only/STATE_HANDOFF_UI_TEST_ROUND_20260807.md`
> （B5 UI 测试基建 + OCR skill + 环境修复终态）。
> 本轮完成: OCR skill（Windows 自带引擎）/ Playwright 基建（chromium 内核 +
> webServer）/ vite dev+preview 同源代理 / 图谱页 fitView+Provider 重构 /
> nats_bridge 协程警告修复 / task_graph GBK 解码修复。
> 未决: 图谱页 ReactFlow 鼠标交互仍失效（节点渲染正常但拖拽/平移/右键全失败,
> 备选: 切纯 SVG 画布——TROUBLESHOOTING §10）+ 测试脚本需加延时防 429。
> 恢复三步: 读交接文档 → RECOVERY_PLAN → 攻图谱页交互。**
> **2026-08-07 压缩交接（最新）:
> 压缩恢复唯一入口 = `docs/only/STATE_HANDOFF_FRONTEND_BINDING_20260807.md`
> （启发管道全链 + 归档审计 2 候选接入 + GAP-5/O4/活性/成本 + GAP-F1 +
> B5 前端绑定计划 + 环境: 服务需重新启动 start.bat）。
> 测试: 各套件全绿（启发 33 / taint 5 / tiered 5 / changelog 4 /
> world 3 + 回归 82/36）; 前端 tsc 归零 + build 成功。
> 下一步: 启动 start.bat → B5 13 页真数据绑定 smoke。**
> **2026-08-06 压缩交接（最新）:
> 压缩恢复唯一入口 = `docs/only/STATE_HANDOFF_COMPLETENESS_20260806.md`
> （三批完备性施工 + 外部对标结论 + 差距清单 + 环境坑）。
> 全量 1782 passed / 0 failed / 16 skipped。对标结论: 核心认知引擎已赶上/
> 领先三款产品; 未赶上 = 多渠道/多媒体/部署形态 + 4 个 P2 机制 + 前端绑定。
> 剩余: GAP-F1/F2（前端, 阶段 B）+ P2 项（GAP-3/4/5/O4/P2/P3）。**
> **2026-08-06 第三批施工完成（最新）:
> GAP-O1/O2/O3 + GAP-P1 已处理（COMPLETENESS_GAP_INVENTORY 第三批）——
> memory/ 归档（A17 保留）/ coordinator 判定修正（已接线, 非孤儿）/
> PCR 模型统一（SemanticEncoder 优先）/ 控制面板参数化
> （build strictness/depth/breadth/decision_mode）。
> 施工记录 = `docs/only/blueprint/THIRD_BATCH_IMPL_20260806.md`。
> 全量 1782 passed / 0 failed / 16 skipped。
> 下一步: 第四批 GAP-F1/F2（前端变更日志 + 139 文件绑定, 阶段 B）+ P2 项。**
> **2026-08-06 第二批施工完成（最新）:
> GAP-E1/E2 / GAP-1 / GAP-2 已修复（COMPLETENESS_GAP_INVENTORY 第二批）——
> executor meta/behavior 占位真接线（_run_meta_consume/_run_behavior_brain）/
> 权限引擎细化（permission_engine.py, OpenWorker RiskClass/Mode/standing rules）/
> 定时自动化持久实体（automation.py, AutomationTask/TaskRun/Scheduler）。
> 施工记录 = `docs/only/blueprint/SECOND_BATCH_IMPL_20260806.md`。
> 全量 1776 passed / 0 failed / 16 skipped（净增 32 项）。
> 下一步: 第三批 GAP-O1/O2（memory/coordinator 归位）+ GAP-O3（PCR 模型统一）
> + GAP-P1（控制面板参数化）; 第四批 = 前端（阶段 B）。**
> **2026-08-06 学习闭环批次完成（最新）:
> GAP-D2/D1/D5 已修复（COMPLETENESS_GAP_INVENTORY 第一批）——
> learn_blueprint 生产注入（v3_session_api run_dag 后 +
> 共享 registry）/ 蒸馏原料管道（ExecutionTraceStore → distill_once →
> A24 验证 → 沉淀）/ 技能生命周期（SkillLifecycle 活性状态机）。
> 施工记录 = `docs/only/blueprint/LEARNING_CLOSED_LOOP_IMPL_20260806.md`。
> 全量 1744 passed / 0 failed / 16 skipped（净增 12 项）。
> 下一步: 第二批 GAP-E1/E2（executor meta/behavior 占位真接线）+
> GAP-1（权限引擎细化）+ GAP-2（定时自动化持久实体）。**
> **2026-08-06 完备性盘点更新（最新）:
> 系统级外部对标完成: `docs/only/benchmark/BENCHMARK_EXTERNAL_20260806.md`
> （OpenClaw × Hermes × OpenWorker 能力矩阵 + GAP-1~7 + E2 技能蒸馏自查）。
> 完备性缺口总清单: `docs/only/COMPLETENESS_GAP_INVENTORY_20260806.md`
> （三轮代码探针实测, 非文档复读; 含真缺口 GAP-D1~O4/F1~F3 +
> 修正记录防重复施工 + 施工顺序四批）。
> 核心结论: 测试绿掩盖接线断裂 —— learn_hook 生产零注入（LEARNED_TEMPLATES
> 只在测试沉淀）、蒸馏原料管道断（DistillationEngine 零数据流）、
> executor 四链仍占位（meta/behavior/discourse/engineering）。
> 下一步: 按清单第一批施工（GAP-D2 learn_blueprint 生产注入 → D1 蒸馏管道
> → D5 技能生命周期）。**
> **2026-08-06 P1 批次更新（最新）:
> 后端 P1 全部完成 — G3 四保护 / E5-E6 错误反思 / P1-4 availability /
> P1-5 MCP 接入+并行 / P1-2 三层介入。
> 施工记录 = `docs/only/blueprint/P1_PROTECTION_REFLECTION_IMPL_20260806.md`。
> 全量 core/agent 1732 passed / 0 failed / 16 skipped（净增 55 项）。
> 压缩恢复唯一入口仍为 STATE_HANDOFF_BACKEND_BLUEPRINT_20260806.md
> （顶部已补 P1 批次更新）。剩余: P1-1 前端变更日志 / P1-3 热路径监视 /
> P1-6 前端绑定（阶段 B）。**
> **2026-08-06 压缩交接（最新）:
> 压缩恢复唯一入口 = `docs/only/STATE_HANDOFF_BACKEND_BLUEPRINT_20260806.md`
> （后端完备 + 蓝图自增长闭环终态, 含已知内容/待办/环境坑）。
> 全量 1677/1677 绿 + 真 LLM 全链通。本批设计定案 4 份:
>   META_ARBITER_ASYNC_INTERVENTION / FLOW_SELF_GROWTH /
>   ERROR_META_REFLECTION / BIDIRECTIONAL_ATTRIBUTION（均在 blueprint/）
> 施工完成: 决策事件 / RECOVERY 执行期 / Meta 副作用 / tool 节点 /
>   text_utils / ReAct 子循环 / 归因闭环 / LEARNED_TEMPLATES。
> 剩余 P1: G3 四保护 / E5-E6 错误反思 / 前端变更日志 / availability /
>   MCP 工具 / 前端绑定。恢复三步见交接文档 §八。**
> **2026-08-06 后端完备性 + 蓝图并行 + 真 LLM 验证更新:
> 1. 全量收集 0 错误（execution/meta __init__ / testing_utils 路径 / pcr 归档副本）
> 2. 蓝图模板重构为订阅表语义（同 Tick 并行）+ run_dag 并行改造
>    （statemachine 13/13, 蓝图 10/10, kernel/cli 77/77）
> 3. 真实缺陷修复: PCRRouterV2.warm_up / PathState 三处归一 /
>    stats str.value / document 参数提取+parse 降级 / gateway 异常降级 /
>    engine._persist_state / telemetry 日志隔离 / DPO loop 迁移
> 4. pcr 测试迁移 DualTrack 38/38, compiler 迁移 M3 语义 11/11
> 5. 真 LLM 全链验证: linkage_quality_v2 1/1 (239s), v3_session_api 端到端通
> 6. 全量 core/agent: 1624 passed / 1 flaky（stress 时限, 已放宽 60s）
> 7. 新设计定案: docs/only/blueprint/META_ARBITER_ASYNC_INTERVENTION_20260806.md
>    （蓝图=任务地图/执行=复杂网络/元认知仲裁/异步介入）
> 8. 下一批施工: P0 决策变更事件 schema → RECOVERY 执行期切换 →
>    check_degradations 副作用化 → 前端变更日志视图
> 依赖: pytest-timeout 2.4.0 已装; chromadb/websockets 因 numpy dist-info
> 损坏未装（UnifiedStore/EventBus 内存版覆盖同等能力）。
> 网关: Switch 8080, DEEPSEEK_API_KEY=sk-a471...（环境变量, 不入库）。**
> **2026-08-05 SD 批次更新: 模块级补全第九批完成
> （SD-1 FileSandbox.review 接 AST 语义约束（SemanticDiffer + SemanticConstraint）
> 真实写路径生效 / bootstrap_v6 注入 differ+constraint / SandboxIntegration 透传；
> SD-3 execution/tests/test_semantic_diff.py 19 项；SD-2 索引补录。
> SD 19/19 + 回归 88/88 + import 探针 6/6。
> 施工记录 = `docs/only/execution/SD_IMPL_PROGRESS_20260805.md`。
> 模块级补全 9 批全部完成 → 下一批: 阶段 B 前端绑定 / 全量 LLM 测试。**
> **2026-08-05 规划批次更新: 模块级补全第八批完成
> （PL-1 planner/models.py git d993553 完整恢复（34 规划模型 + 5 skill 模型
> 并入唯一内核）/ PL-2 v4/skill_layer 门面化（re-export 自 planner）/
> PL-3 三套归一验证（planner 内核 + v3_0/planning 门面 + v4/skill_layer 门面）。
> 顺带修复 event/pluggable.py NATS connect 硬超时（原无限挂起卡死 event 套件）。
> planner 27/27 + CLI 28/28 + topic_tree/meta/context/intent 121/121 +
> event 63/64（预存在）+ runtime 14/14 + causal/behavior 37/37。
> PCR test_integration 8 失败 = 预存在（旧 IntentParser 弃用 shim a984c79）。
> 施工记录 = `docs/only/planner/PL_IMPL_PROGRESS_20260805.md`。
> 下一批模块级补全建议: SD-1/2/3 / 阶段 B 前端绑定 / 全量 LLM 测试。**
> **2026-08-05 元认知批次更新: 模块级补全第七批完成
> （M5 写路径接线: FeedbackBridge 写回 / MetaSubscriber 订阅 / engine 每5轮闭环；
> M8 三套归一: v4 唯一内核 + MetaConsumer 组件 + v3 归档；M9: cognitive_loop
> 归档 + TriggerEngine 保留组件资产）。meta 16/16 + event 63/64 +
> v4/cognitive 32/33 + runtime 14/14 + CLI 28/28。
> 施工记录 = `docs/only/meta/META_IMPL_PROGRESS_20260805.md`。
> 下一批模块级补全建议: 规划 PL-1/2/3 / SD-1/2/3 / 阶段 B 前端绑定 /
> 全量 LLM 测试。**
> **2026-08-05 主题树批次更新: 模块级补全第六批完成
> （T1 EmbeddingEngine 宽异常兜底 / T2-T3 get_current_branch·get_active_path
> 断点修复 / T4 V1V2 归一（V2 唯一内核 + 门面 + 归档）/ T5 阈值参数化 /
> T6 auto_activate / T7 编码器契约）。主题树 40/40 + 上下文 46/46 +
> CLI 28/28 + 综合回归 266 passed。
> 施工记录 = `docs/only/topic_tree/TOPIC_TREE_IMPL_PROGRESS_20260805.md`。
> 下一批模块级补全建议: 元认知 M5/M8/M9 / 规划 PL-1/2/3 / SD-1/2/3。**
> **2026-08-05 causal 批次更新: 模块级补全第五批完成
> （C1 CausalPlanner 挂载+slow_path / C2 CognitionHub 喂数据 / C3 UnifiedContext
> 裁决注释 / C4 discourse 符号 / C5 行为链核对）。causal 11/11 + 跨模块 99/99。
> 施工记录 = `docs/only/causal/CAUSAL_IMPL_PROGRESS_20260805.md`。
> 下一批模块级补全建议: 主题树 T1-T7 / 元认知 M5/M8/M9 / 规划 PL-1/2/3 /
> SD-1/2/3。**
> **2026-08-04 行为链 DPO 批次更新: 模块级补全第四批完成
> （3.1a 可观测 kind 门控 / 3.1b no_response 自对丢弃 / 3.1c 归一化匹配 /
> 3.2 test_dpo_learner 18 项 / 3.3 承诺持久化 + B7 PCR 视角 + B5 回退重模拟）。
> DPO 18/18 + 行为链 36/36 + 跨模块 81/81。
> 施工记录 = `docs/only/behavior/DPO_IMPL_PROGRESS_20260804.md`。
> 下一批模块级补全建议: causal C1-C5 / 主题树 T1-T7 / 元认知 M5/M8/M9 /
> 规划 PL-1/2/3 / SD-1/2/3。**
> **2026-08-04 画像模块级补全更新: 模块级补全第三批完成
> （P2 Track A 复活 / P4 L3 视角固化 / P5 认知状态→对话树 / P6 双向先验 /
> P7 inertia 喂数据 / P8 ProfileContextSource / P9 死代码归档 /
> P10 g 因子领域化 / P11 CLI+双名修复 / P12 19 项新测试 / P3 PROFILE_GAP 修正 /
> H2 写入规范）。画像 19/19 + 画像回归 39/39 + 跨模块 116/116 + 104/104。
> 施工记录 = `docs/only/profile/PROFILE_IMPL_PROGRESS_20260804.md`。
> 下一批模块级补全建议: 关联链 Phase 6（蓝图 §7.3 Event Sourcing M→1 通道）/
> 行为链 DPO / causal C1-C5 / 主题树 T1-T7 / 元认知 M5/M8/M9 / 规划 PL-1/2/3 /
> SD-1/2/3。**
> **2026-08-04 意图模块级补全更新: 模块级补全第二批完成
> （I3 engine 主路径接 Agent-Native 意图管线 / I4 registry 切新包 /
> I8 mcp shim 引用防御 / I9 新增 fusion+ambiguity 11 项测试）。
> intent 19/19 + statemachine 10/10 + CLI+kernel 77/77 + MCP 26/26。
> 施工记录 = `docs/only/intent/I_IMPL_PROGRESS_20260804.md`。
> mcp 包已装 .venv（Python 3.13, mcp 1.29 + fastmcp 3.4.5）。
> 下一批模块级补全建议: 画像 P2-P12 / 关联链 Phase 6 / 行为链 DPO。**
> **2026-08-04 对话树模块级补全更新: 模块级补全第一批完成
> （D-14 CohesionScore 字段 bug 修复 + M1-P12 直连 1234 移除 +
> D3 内核组装: CLI registry 切 B 内核 + B 补 A 兼容写操作面 +
> CLI 门面适配）。对话树+CLI 71/71 + 新增 13/13 + 核心回归 70/70 +
> 跨模块回归全绿。施工记录 = `docs/only/discourse_tree/D_IMPL_PROGRESS_20260804.md`。
> 压缩后第一恢复入口仍为 `docs/only/STATE_HANDOFF_IMPLEMENTATION_20260804.md`
> （顶部已更新为含对话树补全的完成态）。下一批模块级补全建议: 意图 I3-I12 /
> 画像 P2-P12 / 关联链 Phase 6 / 行为链 DPO。**
> **2026-08-04 M9 完成更新（M1-M9 清单全完成）: 阶段 A 施工进度
> M1 ✅ / M2 ✅ / M3 ✅ / M4 ✅ / M5 ✅ / M6 ✅（存储接线）/
> M7 ✅（服务层薄中间件 B4-1）/ M8 ✅（CLI/REST 对齐 B4-5: 命令内核 +
> CLI 消假执行 + REST 消假数据 + 前端 86 路径全覆盖）/
> M9 ✅（子图编辑层2/3 B5-3: serializer 四形态 json/xml/markdown/natural +
> 编辑行为回流行为链；11/11 测试 + 回归 89/89）。
> 压缩后第一恢复入口 = `docs/only/STATE_HANDOFF_IMPLEMENTATION_20260804.md`
> （M1-M9 完成态），施工总计划 = `docs/only/IMPLEMENTATION_PLAN_20260804.md`。
> M9 施工记录 = `docs/only/viz_edit/M9_SERIALIZER_IMPL_PROGRESS_20260804.md`。
> 下一阶段 = 模块级补全（意图/画像/对话树/关联链/行为链/causal/主题树/
> 元认知/规划/SD）+ 阶段 B 前端绑定。**
> **2026-08-04 M8 完成更新: 阶段 A 施工进度 M1 ✅ / M2 ✅ / M3 ✅ / M4 ✅ / M5 ✅ /
> M6 ✅（存储接线）/ M7 ✅（服务层薄中间件 B4-1）/ M8 ✅（CLI/REST 对齐 B4-5:
> 命令内核 core/agent/kernel/ 新建 + CLI 消假执行 + REST 消 stubs 假数据 +
> 前端 86 路径 100% 覆盖；内核 49/49 测试 + 回归 127/127）。
> 压缩后第一恢复入口 = `docs/only/STATE_HANDOFF_IMPLEMENTATION_20260804.md`
> （M1-M8 完成态），施工总计划 = `docs/only/IMPLEMENTATION_PLAN_20260804.md`。
> M8 施工记录 = `docs/only/cli_rest/CLI_REST_IMPL_PROGRESS_20260804.md`。**
> **2026-08-04 M7 完成更新: 阶段 A 施工进度 M1 ✅ / M2 ✅ / M3 ✅ / M4 ✅ / M5 ✅ /
> M6 ✅（存储接线）/ M7 ✅（服务层薄中间件 B4-1: v6_app 挂 rate_limiter/queue/
> session + core/service/v3_0 归档 + service 壳归档；8/8 测试 + 全栈 10/10 +
> 回归 91/91）。
> 压缩后第一恢复入口 = `docs/only/STATE_HANDOFF_IMPLEMENTATION_20260804.md`
> （M1-M7 完成态），施工总计划 = `docs/only/IMPLEMENTATION_PLAN_20260804.md`。
> M7 施工记录 = `docs/only/service/SERVICE_IMPL_PROGRESS_20260804.md`。**
> **2026-08-04 M6 完成更新: 阶段 A 施工进度 M1 ✅ / M2 ✅ / M3 ✅ / M4 ✅ / M5 ✅ /
> M6 ✅（存储接线 G10: UnifiedStore→ChunkStore 向量后端 + TieredStorage→主存储
> 分层 + unified_graph_store 半实现完成 + FactStore 批量写修复；22/22 测试 +
> 回归 78/78 + M5 核心 71/71）。
> 压缩后第一恢复入口 = `docs/only/STATE_HANDOFF_IMPLEMENTATION_20260804.md`
> （M1-M6 完成态 + M7 待开工），施工总计划 = `docs/only/IMPLEMENTATION_PLAN_20260804.md`。
> M6 施工记录 = `docs/only/storage/STORAGE_IMPL_PROGRESS_20260804.md`。
> 开工下一步 = M7 服务层薄中间件（B4-1）: rate_limiter/queue/session 挂 FastAPI /
> core/service/v3_0 归档（先迁移 test_fullstack）。**
> **2026-08-04 M5 完成更新: 阶段 A 施工进度 M1 ✅ / M2 ✅ / M3 ✅ / M4 ✅ / M5 ✅
> （EventBus 生命周期 G2，12/12 测试 + 回归 110/110 + 压测 3 项全绿）。
> 压缩后第一恢复入口 = `docs/only/STATE_HANDOFF_IMPLEMENTATION_20260804.md`
> （M1-M5 完成态 + M6 待开工），施工总计划 = `docs/only/IMPLEMENTATION_PLAN_20260804.md`。
> 开工第一步 = M6 存储接线（G10）: 先重新核查存储层现状（G10 文档经勘误:
> tiered_storage/unified_store 是真实实现非壳、faiss 三环境不一致），
> 再按 G10-P1（UnifiedStore→ChunkStore）/ P2（TieredStorageManager→主存储）/
> P3（孤儿后端归档）/ PE-3（FactStore 批量写修复）顺序施工。
> M5 施工记录 = `docs/only/event/EVENTBUS_IMPL_PROGRESS_20260804.md`。**
> **2026-08-04 最新: 拍板全部完成（10 大项定案），阶段 A 后端施工中。
> M1 网关 ✅ / M2 白盒编辑 ✅ / M3 认知层 ✅ / M4 执行层 ✅。
> 压缩后第一恢复入口 =
> `docs/only/STATE_HANDOFF_IMPLEMENTATION_20260804.md`（M1-M4 完成态 + M5 待开工），
> 施工总计划 = `docs/only/IMPLEMENTATION_PLAN_20260804.md`（M1-M9 清单）。
> 开工第一步 = M5 EventBus 生命周期（G2）。**
> **2026-08-03 终态更新: 三模块（意图/画像/对话树）拍板+施工完成（R1-R6），深度修复完成；
> 工程链（07）+ 上下文（02）四轮审计完成（盘点/设计对照/设计精读/运行验证），待拍板待施工。
> 压缩后第一恢复入口 = `docs/only/STATE_HANDOFF_20260803_FINAL.md`（改动清单/待办/测试数字/环境坑）。
> 工程链/上下文恢复入口 = `docs/only/STATE_HANDOFF_ENGINEERING_CONTEXT_20260803.md`（审计终态+待讨论清单）。
> **2026-08-03 追加: 工程链/上下文待讨论 17 项已用 PARADIGM 哲学消解 → 12 项施工/清理 + 5 项核心讨论
> （`docs/only/wise/PARADIGM_FILTER_ENGINEERING_CONTEXT_20260803.md`）。
> **全局审计规划已定（`docs/only/GLOBAL_AUDIT_PLAN_20260803.md`）: 全部剩余 8 模块审计完
> 再统一讨论/拍板/施工（局部冲突多为伪问题，全貌下哲学消解）。
> 剩余 8 模块: StateMachine / 主题树 / 规划 / 因果基板 L5 / 元认知 / 持久化层 / LLM 回复侧 / 用户编辑树。
> 审计顺序: ① StateMachine+主题树 ② 规划+因果基板 ③ 元认知+持久化 ④ LLM 回复侧+用户编辑树。**
> 当前待办: ① FactStore 批量写缺陷修复（压测失败根因）② 存储架构拍板（SQLite 拓展/redis 热层）
> ③ Phase 4.5 LLM 全量测试 ④ 工程链/上下文拍板与施工。**
> **2026-08-03 四查后更新: 用户核查新增清单（执行层多树图 / 主题树 manager_v2 / causal+
> cognition+assembly+discourse / 外围 11 域）已全部落盘 → 全局审计全覆盖（23 项）。
> 压缩后第一恢复入口改为 `docs/only/STATE_HANDOFF_GLOBAL_AUDIT_FINAL_20260803.md`
> （四查终态 + 全局拍板池 + 索引）。**
> **2026-08-03 追加: 设计全貌 ↔ 审计内容对应关系核查完成
> （`docs/only/DOCS_LANDSCAPE_MAPPING_20260803.md`）——105 个未引用设计文档分 5 类
> （A 33 真缺口 / B 4 合并 / C 25 历史 / D 8 总览 / E 8 独立），重构可行性已评估。**
> **2026-08-03 再追加: A 类 33 缺口批量精读全部完成（8/8 批，42 篇，落盘
> `docs/only/landscape_read/`，含 51 项冲突登记聚类）——冲突只记录不拍板，
> 下一步建议哲学消解（PARADIGM 对照）→ 全局拍板。**
> **2026-08-03 三追加: 前端实现审计完成（`docs/only/frontend/FRONTEND_IMPL_AUDIT`
> ——FE-1 P0 白盒编辑 API 后端未注册 404 / FE-2 死代码 / FE-3 四套 WS）+ SemanticDiff
> 补盲（`landscape_read/SEMANTIC_DIFF_AUDIT`——SD-1 注入零调用）+ 映射归类修正
> （9 历史元文档确认非真缺口）。**
> **2026-08-04 最新: 全局哲学消解轮完成（61 项冲突 → 真决策 13→8；G1+G3/G10/B2-3/B4-1/
> B4-5 六项已定案）。压缩后第一恢复入口 = `docs/only/STATE_HANDOFF_PHILOSOPHY_ROUND_20260804.md`
> （本轮终态 + 定案 + 剩余 8 项 + 施工前置 + 恢复路径）。拍板依据 =
> `GLOBAL_PHILOSOPHY_FILTER_FINAL_20260803.md` + `G10_STORAGE_DECISION_20260803.md`。**

---

## 一、恢复顺序（文档 → 提供什么）

```
第 1 步  读 docs/only/STATE_SNAPSHOT_ROUND2_20260802.md
         → 第二轮冻结快照：行为链质量深挖 + DPO 完成情况 + 待办清单（§三）

第 2 步  读 docs/only/STATE_HANDOFF_20260802.md
         → 唯一恢复入口：§十三/§十四/§十五（关联链终态 / 行为链施工完成态 / 压缩前状态）
         → §八 蓝图 P1 待办 + §九 测试命令

第 3 步  读 docs/only/behavior/BEHAVIOR_IMPL_PROGRESS_20260802.md
         → 行为链 P0-P3+CLI 全量施工记录（改动文件/验证/环境坑）

第 4 步  读 docs/only/intent/AUDIT_ENTRY_20260803.md
         → 意图审计入口：三代分裂（旧 8 阶段断链/v4_tiered 空壳/新包未接线）+ 资产盘点
         → 配套 IMPLEMENTATION_AUDIT_20260803.md（含补读 §九）+ DESIGN_AUDIT_20260803.md（含意图↔对话树接口预扫描）

第 5 步  读 docs/only/discourse_tree/AUDIT_ENTRY_20260802.md
         → 对话树审计入口：5 套实现 + 30 篇设计文档 + 内核草案（KERNEL_ABSORPTION §八/§九 公理）

第 6 步  读 docs/only/association/DECISIONS_20260802.md（如做关联链后续）
         → D-1~D-16 拍板（Phase 6 已完成，一般不再需要）

第 7 步  读 docs/only/STATE_HANDOFF_ENGINEERING_CONTEXT_20260803.md（工程链/上下文专项）
         → 四轮审计完成态 + 关键实锤缺陷（E1-E6/C1-C6）+ 待讨论清单（A/B/C 共 17 项）
         → 配套: docs/only/engineering/{AUDIT_ENTRY, DESIGN_IMPL_AUDIT, DESIGN_FULL_READ, IMPL_VERIFY}_20260803.md
         → 配套: docs/only/context/{AUDIT_ENTRY, DESIGN_IMPL_AUDIT, DESIGN_FULL_READ, IMPL_VERIFY}_20260803.md

第 8 步  读 docs/only/GLOBAL_AUDIT_PLAN_20260803.md（全局审计规划）
         → 审计总进度（10 完成 / 8 剩余）+ 剩余模块清单（代码位置/已知线索）+ 审计顺序
         → 策略: 全部审计完再统一讨论（全局哲学消解 + 元规则裁决）
```

## 二、意图审计成果（已完成，2026-08-03）

```
核心结论（三句话）:
1. 旧 8 阶段 IntentParser 断链（intent_rule_registry 文件丢失）→ shim IntentParser=None → 11 引用方（含 MCP/Service）静默降级
2. 新包 intent/（Agent-Native LLM-first）几乎未接线；但 fusion_decider/ambiguity_gate 是金矿（设计完备、零引用）
3. engine 真正接线的意图链 = 关联链 L3 MultiPerspectiveValidator（4 视角投票 + D-14 PCR zone 播种）

意图↔对话树接口（DESIGN_AUDIT §五/§九）:
- primary_intent 来源未定（四套类别体系并存）
- 认知刷新三维模型（layer0 §4.3）= 对话树组块边界判据的最精确实现（时间/指代/描述 + 双豁免）
- L3 tree_annotation（{topic, action}）= 现成的意图→对话树反馈通道
- D-14 PCR zone→intent 先验已通

待拍板（DESIGN_AUDIT §六 8 项 + IMPLEMENTATION_AUDIT §九）:
范式（确定性 vs LLM-first vs 认知双工）/ 四套类别归一 / 新包接线 / 5 链验证补全 / PCR 调控 / 意图↔对话树 4 接口 / 测试补全
```

## 二.5 对话树审计阶段二（已完成，下一步拍板）

```
✅ 全部完成 → docs/only/discourse_tree/IMPLEMENTATION_AUDIT_20260803.md（24/26 测试 + 10 项契约断裂 + 内核组装建议）
阶段四内核拍板待开工（状态机/决策函数/温度驱动/输入源/摘要边界/验证集）
```

## 三、行为链 DPO 待办（压缩前冻结，勿丢）

```
3.1 DPO 粗糙点审计（STATE_SNAPSHOT §1.2 四项）:
    top1==summary 判定不可靠 / no_response 污染 / LLM 蒸馏对齐率低
    正确方向: 仅对可观测行为事件（ui/tool/api/config/document kind）记录
3.2 补 tests/test_dpo_learner.py（反馈映射/阈值触发/图权重应用/白盒）
3.3 行为链剩余: B5 回退重模拟 engine 接线 / B7 多视角识别 / 显式承诺持久化挂载
```

## 四、全局剩余（非主线）

```
- 蓝图 P1 清单（STATE_HANDOFF §八）：PlanGate / expand_from_dag_trace / route_mode / PCR 模型统一
- 模块审计排队（7/12）：画像（🟡 双 ocean_profile）← 下一步 / 上下文（🟡）/ 工程链（🟡）
  / 元认知（🟡）/ 规划（🔴）/ StateMachine（从未审计）
- 已审计 5/12：PCR ✅ / 行为 ✅ / 关联 ✅ / 子图 ✅ / 蓝图 ✅ / 对话树 ✅（专项）/ 意图 ✅（专项）
```

## 四.5 画像（Profile）审计预告（下一步主线）

> 用户判断："画像实际上和对话树关系很深，因为我们是模拟用户的记忆组块，不仅仅只有记忆组块，还有用户，而用户画像则是用户的缩影。"

> **2026-08-03 更新：画像审计已完成（阶段一/二/三/四）→ `docs/only/profile/`（AUDIT_ENTRY + IMPLEMENTATION_AUDIT + DESIGN_AUDIT）。**
> **预告修正：`meta/ocean_profile.py` 不存在（原预告"双类"错误）——实际是三套体系：OCEAN（v4/cognitive/ocean_profile.py，CLI 路径活）/ 行为侧（predictor/cognitive_profile.py，brain 已接）/ user_engine（v3 规则）。**
> **核心发现：`_cognitive_profile`（CognitiveProfileV2）生产路径从未实例化（全纸面）；PROFILE_GAP 声称 95% 实为 30-40%；L3 `_profile_vote` 因 engine 不传 profile_traits 永远 ABSTAIN；inertia_graph（链08 v2）挂载未喂数据。**
> **待拍板：画像本体三套归一（OCEAN 人格层 + 惯性图行为模式层 + Track A 认知状态层）/ P4 双向先验落地 / L3 profile 视角接线 / 对话树组块边界接认知状态。**

> **2026-08-03 追加：外部参考完成 → `docs/only/profile/EXTERNAL_REFERENCE_20260803.md`（Hermes/Pi/snips-nlu 三方源码精读）。**
> **核心吸收：① Hermes 画像 = USER.md 事实列表 + 1375 chars 预算 + LLM 自 consolidation + declarative-facts 写入规范 + background_review fork 后验 + consent-gated 冷启动（比 OCEAN 浮点更可操作）；② Hermes/Pi 意图均走 LLM 原生无显式层（snips-nlu 证明规则优先+概率兜底两段式有效）；③ who-vs-how 分工语义（画像=who，技能=how）可直接化解画像/行为链边界。**
> **建议：画像内核 = 事实条目列表（bounded）+ OCEAN 投影层（维度可换），吸收 H1-H6/S1-S2/P1 清单后再拍板。**

```
画像 ↔ 对话树/意图的关系（预扫描）:
- VerifyContext.profile（OCEAN）+ SubIntent.chain_votes[profile]（意图新包）
- l3_intent._profile_vote（OCEAN C 阈值 → 意图 accept/reject）
- DESIGN_MULTI_SIGNAL_INTENT S3/S5（用户状态 OCEAN+DMN / 画像后验先验）
- 3D 路由矩阵用户偏置层（attention_anchor/expertise/cog_resource）
- 对话树组块边界（方向性假设）← 用户认知状态（疲劳/注意力/惯性）

待审计代码:
- v4/cognitive/ocean_profile.py + meta/ocean_profile.py（双类）
- profile/ 目录（若有）+ ENGINEERING_COGNITIVE_PROFILE_V2.md（2034L）+ DESIGN_COGNITIVE_PROFILE_V2
- 画像↔PCR 双向先验（P4 公理要求）
```

## 五、环境坑（回查）

```
- anaconda 3.9: pytest 可用，numpy/transformers 坏 → 全管线偶发 0xC000013D（brain.shutdown 已防御）
- stderr "State save failed PermissionError ~/.dialogmesh/state.json" = 环境噪音
- PowerShell stdin 传 python 中文乱码 → UTF-8 文档用 apply_patch 写
- 测试命令模板: C:\Users\APTShark\anaconda3\python.exe -m pytest <files> -q --tb=short
```

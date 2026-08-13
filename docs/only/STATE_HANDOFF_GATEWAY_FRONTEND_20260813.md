# 压缩交接 — 召回终态 + 网关全套升级 + 前端绑定（2026-08-13 深夜）

> 状态: 压缩恢复唯一入口（本轮）
> 前置: STATE_HANDOFF_RECALL_FINAL_20260813.md（§六 续）
> 恢复三步: 读本文档 → 读 RECOVERY_PLAN → 按待办优先级开工

## 一、召回/幻觉（前段已完成, 详见 STATE_HANDOFF_RECALL_FINAL §一/§二/§六）

- eval_100 全量 95s; dialogue top1 69.2% / doc 31.1% / C 类归零 / 确定性双跑
- Faithfulness 机制验证: simple F=0.80（关思考 + 全文上下文 + 按任务选池）;
  根因 = deepseek-v4 思维链写进 content → 网关 thinking 开关
  （{"type":"disabled"}）
- 五维评测首跑: 相关 4.25 / 一致 4.00 / 忠实 3.75 / 流畅 5.00 / 连贯 4.75
- 文档语料入生产池（DM_DOC_CORPUS=1, 10787 块）; HyDE 查询向量
  （DM_HYDE=1）; LLM 意图分类接通（W1 前半）

## 二、执行轨迹落树（P0, 已完成）

- TaskRunner(execution_tree=): create_task → 每步 spawn_sub_agent →
  complete_node（淘宝 PES 全链路可回放对齐）; llm_loop 异常转 error
  结果（树节点不卡 ACTIVE）; step 字段对齐 tool_loop 真实 payload（name）
- v3_session_api + statemachine agentic 节点接线（per-session 树 +
  run_dag context 传 discourse_tree）
- 正式测试 test_execution_trace_lands_in_tree（task_runner 8/8 绿）

## 三、网关全套升级（switch 仓库, 对标 one-api/LiteLLM）

### 核心转发
- 流式聚合（上游恒流式, 非流式客户端网关内聚合; 修复 stream&&req.Stream
  聚合恒空 bug）— 长生成 6s/833 字 finish=stop usage 正常
- 超时: 默认 30s→120s + 连接 5s 分离（DialContext）; 连接阶段重试
  （退避+jitter, max_retries 默认 2）
- 熔断: **自适应**（近 12s 失败率滑动 — unstable>15%: 3 次/40% 快开;
  stable: 5 次/60% 宽容; 3-5 区间用户拍板）; 半开渐进恢复
- fallback: gracefulDegradation（可重试错误自动切换候选 provider）

### 可观测/运维
- 健康缓存: Prober 全量并行（启动首探 + 30s 周期, 跳过无 key）→
  /v1/health 即时返回（cached=true, ?live=1 实时）
- 错误目录: 稳定 code（AUTH_FAILED/RATE_LIMITED/UPSTREAM_TIMEOUT/
  CONTEXT_WINDOW_EXCEEDED/CONTENT_POLICY/PERMISSION_DENIED/MODEL_NOT_FOUND/
  BUDGET_EXCEEDED/...）+ config/error_catalog.yaml 查表 + 消息模式分类
  （对齐 LiteLLM 异常体系）; parseError 带状态码分类（上游 4xx 不再
  落 UNKNOWN）; 所有错误出口补 code
- 计费持久化: CostTracker JSONL 追加（usage_log.jsonl）+ 启动重放重建
  （重启不丢, 实测）; /v1/usage 含 cost（total/by_key/by_model）
- per-key 日配额: DM_GATEWAY_KEY_QUOTA_DAILY（token/天, 超限
  429 BUDGET_EXCEEDED 实测）; 限流默认关闭（70+ req/s 不被卡死）
- admin: /admin 零依赖仪表盘 + /v1/error-catalog 端点
- 热更新: watcher 50ms 轮询 + diff 真实现（added/updated/removed,
  此前恒 added）— 实测 69ms < 100ms

### 压测（Go 客户端 cmd/gwbench）
- 64 并发: 3434 req/s / p50 0.567ms / p99 2.998ms
- 128 并发: 22858 req/s / p50 5.8ms / p99 15.7ms / p99.9 37ms
- 一次 4.3s 尾尖峰未复现（待 pprof 观察）
- 结论: 真实上限 3.4K-22.8K req/s, 70 req/s 要求余量 48x-326x;
  **Rust 化（sbproxy 风格）不投入** — 瓶颈在上游与客户端, 非网关

## 四、前端网关绑定（已完成, DialogMesh f84de74）

- 后端: /v6/gateway/cost（透传 switch /v1/usage 真实 cost）+
  /v6/gateway/error-catalog（YAML 文本透传, 修 _switch_get 强 JSON）
- 前端: GatewayPage 用量 tab 新增"网关真实统计与计费"卡片
  （tokens/缓存命中/总费用/按 key/模型分摊, 15s 轮询）;
  V6GatewayStats 类型对齐真实字段; tsc 零错误
- **关键发现**: 原 /v6/gateway/usage 是本地 monitor 估算（非网关真实
  数据）— cost 卡片现在是真实透传（实测 67 请求/$0.00136）
- 契约文档: FE_CONTRACT_REGISTRY 补充（含 usage/cost 双源说明）

## 五、git 状态（均本地, 未推 GitHub）

- DialogMesh: ahead 20（f84de74 最新）; switch: ahead 5（16d7941 最新）
- switch 未提交: server/middleware.go（既有改动, 非本轮）
- 数据: gateway/usage_log.jsonl（运行时数据, gitignore 已加）

## 六、环境坑（必读）

1. **沙箱启动的进程无出站网络（10013）** — 网关必须 start.bat/提权启动;
   shell 内 curl 直连测试被挡, 勿据此判断网络
2. **deepseek-v4 推理模型**: 思维链写进 content 且共享 max_tokens →
   提取/分类/判定类调用必须带 thinking:{"type":"disabled"}
   （网关三层开关: 请求级 > provider.yaml > 默认开）
3. .venv 已补 fastapi/uvicorn（API 可用 .venv 起）; anaconda numpy 坏
4. 8000 端口进程沙箱看不到（Get-NetTCPConnection 空）— 用
   netstat -ano + taskkill 强杀
5. gateway.exe 源码在 C:\Users\APTShark\PycharmProjects\switch;
   编译需提权 + GOCACHE 本地 + GOPROXY=off
6. PowerShell 管道传中文变 ? — 中文脚本写文件执行

## 七、待办（优先级）

- **P1**: 意图感知自适应融合（per-intent profile, W1 后半）; 重排层
  （doc top1 31%→40%+）; HyDE 上线默认; task 轨（W5）; recall 图扩展
  （W3）; 执行迹落树后的行为链/元认知消费（读 ExecutionTree）
- **P2**: Faithfulness 生成型任务锚定任务图/执行迹; 行为链深度偏好
  （W7）; 五维评测多次采样校准; 蓝图模板覆盖（W6）; 网关尾尖峰
  pprof 观察; 多实例部署（99.9%）; 博客 chapter4; C-MTEB/BEIR

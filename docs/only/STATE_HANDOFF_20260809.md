# 压缩交接 — 召回探索 + OS 工具 + function calling + 第一版核对（2026-08-09）

> 状态: 压缩恢复唯一入口（本轮）
> 前置: STATE_HANDOFF_UI_TEST_ROUND_20260807（树图化+召回第一批）
> **2026-08-10 追加: chromadb 环境修复完成**（见 §八）— 离线化 + 持久化 + 锁释放
> **2026-08-09 追加: v2 执行层分层施工完成**（见 §六）— 下一步:
> ①第一版收尾（README/commit+push GitHub）或 ②前端执行迹绑定（阶段 B）

---

## 一、本轮完成（全部实测）

### 1. 统一召回第二批（黄金集 + 边界测绘）
- `data/recall_goldset.json`: 40 真实 query + 218 块（真实对话自动生成,
  非手写）; 跑分 `scripts/recall_goldset.py`
  （--mode linear|rrf|norm, --single, --scope global|session）
- **RRF 融合**: top1 42.5% vs linear 30%（+12.5pp）— 免费增益, 已接入
- **G0 索引缓存**: 磁盘持久化 SPO+向量（data/recall_index/）, 76s→15s
- **🔴 修复 2 个 vector 全 0 bug**: 语言检测过严（混合文本→384 维零向量）+
  嵌套向量（(1,512) tolist 成 [[...]]）
- **边界测绘结论**: 关系类型映射 top3/top5 +5pp（词面重叠场景有效）;
  词面不相干场景 SPO 单路 0/5（主宾语义是词典盲区）; GLiNER multi-v2.1
  对中文 SPO 无效（英文实体抽取可用）; LLM 三种用法（HyDE 扩展/挑编号/
  打分）全受粗召回天花板限制（5/7）→ **蒸馏该做"主宾语义归一"**
- 设计: SPO_MODEL_STRATEGY + SPO_BILINGUAL_TWOSTAGE + DYNAMIC_TIERING_PREFETCH
  （docs/only/recall/）

### 2. 第一版功能核对（V1_FUNCTION_CHECKLIST）
- E1 服务栈 ✅ / E2 核心链路 ✅（真实 LLM 端到端）/ E3 白盒 ✅
  （修 entry.py 漏 recall 分发）/ E4 前端 ✅（pages-smoke 15/15 + 图谱 4/4）/
  E5 回归 ✅（1856 passed 0 failed）
- C1-C4 权限: 对标后已实现（shell 操作符/写根限制/standing rules/
  RiskClass 4 级, 12/12 测试）— 复核确认并挂接生产路径（decider/gates）

### 3. OS 控制工具（参考 OpenClaw + OpenWorker 源码）
- `core/agent/tools/os_tools.py`: run_shell（平台 shell+超时+结构化）/
  run_python / run_session（后台会话 new/poll/kill/list）/
  dir_list / grep + write_file 别名 — 11 测试
- `tools/__init__.py` 接线（此前 list_all 只有 2 工具 → 13 个）
- 权限门: run_shell/run_python 归 EXEC, 链式 shell/出根目录被拒
- 参考落盘: docs/only/reference/OPENCLAW_OS_TOOLS + OPENWORKER_CODE_AGENT

### 4. 执行链路 + function calling（"实现软件"）
- Statemachine `_run_node` 加 tool 分支（权限门 + ToolRegistry）
- 代码执行后处理（检测 ```python 块自动执行）— 权宜之计
- **tool_loop**（core/agent/llm/tool_loop.py）: function calling 循环
  （注入 tools → LLM tool_calls → 权限门执行 → 回灌 → 循环）— 5 测试
- v3 主流程接入: 编码类请求（is_code_request）走 tool_loop
- **端到端实测**: "写 hello world 并运行" → LLM 自主 write_file +
  run_shell（处理 Windows python3 占位符 → 用 anaconda）→ 总结 → 主动建议
- 端点: POST /v6/task/{sid}/execute（读已确认图 → Decider）

### 5. 执行层分层架构（用户拍板）
- `docs/only/blueprint/EXECUTION_LAYER_ARCHITECTURE_20260809.md`
- tool_loop = 微观执行引擎（普通 ReAct 级）; 蓝图宏观约束 + 元认知树图
  监控是壳（v2 施工: 蓝图→执行接线 / 元认知监控 / 用户可见变更日志）

## 二、测试与验证
- tool_loop 5/5 + os_tools 11 + permission 12 + statemachine 67 +
  code_postprocess 3 + recall 9 + topic_tree 23 — 本批全绿
- 全量回归: 1856 passed / 16 skipped / 0 failed
- 前端: pages-smoke 15/15 + graph-interaction 4/4 + tsc 0 错误 + build OK

## 三、环境
- 8000 API ✅（新代码: tool_loop/os_tools/执行端点）/ 8080 网关 ✅
  （deepseek active）/ 4173 preview ✅
- 模型: models/gliner_multi-v2.1（1.1GB, 中文 SPO 无效, 英文实体可用）+
  models/mdeberta-v3-base（GLiNER tokenizer）
- git 未提交（按惯例）; 临时文件已清

## 四、恢复三步
1. 读本文档（终态 + 待办）
2. 读 RECOVERY_PLAN（顶部已指向本文档）
3. 下一步: ①第一版收尾（README/commit+push GitHub）或
  ②前端执行迹绑定（阶段 B）— 用户定优先级

## 六、v2 执行层分层施工（2026-08-09 追加, 完成 ✅）

- 施工记录: docs/only/execution/V2_EXECUTION_LAYER_IMPL_20260809.md
- 四壳补全: tool_loop 增强（allowed_tools/system_inject/on_step/timeout/
  trace）+ ExecutionMonitor（Hot/Warm/Cold 三层）+ TaskRunner（蓝图节点
  执行壳, 重规划循环 + 三层介入 + 复盘回流）+ 接线（statemachine agentic
  分支 / v3 Phase 4 任务图约束注入 / GET /v6/execution/{sid} 白盒视图）
- 验证: 新测试 22 项 + 回归 150 项全绿 + 真 LLM 端到端冒烟通过
  （LLM 自主 write_file → run_shell → 总结, 3.8s, 约束内无越界）
- 事件进 engine 决策总线 → /v6/changelog 可回看可介入（approve/reject）
- 遗留: Warm 单次 LLM 评估（P2）; 前端执行迹展示（阶段 B）

## 七、召回体系完成态（2026-08-09 深夜追加）

### 完成（全部实测）
1. **量化评测体系**: docs/test/recall_queries.json（50 人工查询, 8 域）+
   scripts/doc_recall_bench.py（分级/漂移/四路/粗筛/时序）+
   GPU torch（2.6.0+cu124, RTX3080, 2444 块编码 8.3s）+
   首轮基线: bm25 28% → linear 38% → linear+时序 44% top1（MRR 0.534）
2. **时序约束**（评测驱动发现）: time_half_life_days + 块 created_at,
   cross 0%→25%
3. **recall→subgraph 桥**: compile_from_anchors（锚点 seed + 事件溯源 +
   代码轨迹 + 图扩展）
4. **情景再现端到端**（真实 LLM 非 mock）: 写文稿 → recall →
   reconstruct 三支全通（概念 R / 会话要求 Q / 代码轨迹 T）
5. **写即索引 + G0 记忆闭环**: write_file 产出 → chunk_store(produced) →
   recall 冷路径合并 → 向量落盘 data/recall_index/ → 跨重启可召回
6. **修复链**: TaskRunner→trace_store / v3 显式 msg_id 事件 /
   EventLog.get_event（replay_unconsumed ASC 截断 bug）/
   ChunkStore.atoms_by_tag

### 测试
write_index 4 + subgraph_anchors 6 + event_log_get 2 + recall 18 +
task_runner 7 + 回归 47+ 全绿

### 提交线（本地未推）
67d6abe(v1 已推) → dd1ef66(v2.1) → 88e32f1(评测+时序) →
4e05c30(subgraph 桥) → d47be27(情景再现闭环) → 35a96f2(G0 记忆闭环)

### 待办（记录不施工/独立任务）
- chromadb 环境修复（.venv numpy 正常 + clash → 装, 切 unified 持久后端）
- 博客 chapter4（素材齐: 定位/分层/时序/情景再现/量化数据）
- 前端 B（执行迹/情景视图展示）
- 层3 变体评测 / 跨域召回(25%) / 文档-代码同步审计 / BEIR 公开基准
- trace_id 跨模块传播（§11.2）; G 支线 ConceptGraph 数据源

### 环境
8000(新代码)/8080 在跑; .venv torch GPU; anaconda numpy 坏（测试用 anaconda,
向量/评测用 .venv）; clash 7877 可出网

### 恢复三步
1. 读本文档（§七 完成态 + 待办）
2. 读 RECOVERY_PLAN（顶部已指向）
3. 下一步候选: 博客 chapter4 / 前端 B / chromadb 环境修复 / 跨域召回

## 五、关键文档索引
- 第一版核对: docs/only/V1_FUNCTION_CHECKLIST_20260808.md
- 执行层架构: docs/only/blueprint/EXECUTION_LAYER_ARCHITECTURE_20260809.md
- 召回设计: docs/only/recall/（STRATEGY/BILINGUAL/DYNAMIC_TIERING）
- 蓝图薄点审计: docs/only/blueprint/BLUEPRINT_THIN_AUDIT_20260808.md
- 参考: docs/only/reference/（OPENCLAW_OS_TOOLS + OPENWORKER_CODE_AGENT）
- 测试数据: docs/test/RECALL_GOLDSET_20260808.md

## 八、chromadb 环境修复完成（2026-08-10）

- 施工记录: docs/only/storage/CHROMADB_ENV_FIX_20260810.md
- chromadb 1.5.9 装入 .venv（清华镜像, 无需 clash）+ .venv 补 pytest 9.1.1
- 三处 chromadb 入口离线化（本地 embedding 兜底, 不再触发默认模型下载）:
  ChunkStore chromadb 后端（PersistentClient + 冷重开重建 Atom + close()）/
  ChromaBridge（close() 从 reset 改官方 close, 修 metadata 空 dict）/
  ChromaStore（修 available 不触发 lazy init 的预存在 bug + close()）
- UnifiedStore 持久化接线: ChunkStore unified_persist=True（load 恢复 +
  节流落盘 + close flush）; DM_CHUNK_BACKEND=unified 时自动开启
- 测试: 新增 7 项（chromadb 6 + unified persist 1）; .venv 119/3 failed
  （3 failed 为 recall 环境差异预存在, recall 文件未动）; anaconda 116/1 skipped
- 环境坑: .venv 才有 chromadb（anaconda numpy 坏）; chromadb 测试只能 .venv 跑

## 九、环境坑复盘 — 中文编码反复踩坑（2026-08-10 记录, 教训级）

### 事件
层3 变体评测连网关, 中文 prompt 到 LLM 侧变 `????`/乱码, 浪费大量时间
排查。此前已多次出现（压缩交接 §环境坑 已有记录）。

### 根因（三层）
1. **恢复流程执行不彻底**: 只读交接顶部摘要, 未精读 §环境坑清单
   （BACKEND_BLUEPRINT 108 行早已写: heredoc `| python -` 中文变 ????）
2. **无条件反射**: 中文输入应一律走 apply_patch/Set-Content 写 .py 文件再执行,
   不要裸管道喂 stdin（PowerShell 管道默认编码 ≠ UTF-8）
3. **网关调用规范未集中**: dm-client 鉴权 / provider 字段 / batch 超时,
   散落在 v3_session_api.py / tool_loop.py 源码, 没有提取成文档

### 规则（防止第三次）
- 中文脚本/中文输入 → 先写文件（apply_patch 或 Set-Content UTF8）再执行,
  禁止 `@'...'@ | python -` 传中文
- 连网关前先 `rg "chat/completions" core` 看现成调用（v3_session_api.py）
- 网关规范（本地网关 8080）:
  - 鉴权: `Authorization: Bearer dm-client`（不是 provider 的 sk- key!）
  - body 必带: `provider: "deepseek"` + `model: "deepseek-v4-flash"`
  - batch ≤ 4 条/请求, max_tokens ≤ 2048, 否则 504 Gateway Timeout
  - 空 content + finish_reason=length = max_tokens 太小的网关行为
- 测试后清临时文件（本批 smoke 已清）

## 十、符号注入施工完成（2026-08-10）

- 施工记录: docs/only/execution/SYMBOL_INJECTION_IMPL_20260810.md
- 新增 core/agent/llm/symbol_injector.py: trace → Mermaid 状态图 +
  上下文压缩（早期轮次符号化, 保留最近轮原文, node_id 可追溯）
- tool_loop 加 symbol_interval（默认关）; TaskRunner 接线（TaskConstraint 字段）
- 端到端（真实 LLM）: 3 步工具链符号图正确生成; 回归 42/42 全绿
- 开放项: LLM 提炼升级 / token 阈值触发 / 原文落盘 refs / 统一提炼调度层

## 十一、跨语言召回决策（2026-08-10）

- 决策文档: docs/only/recall/RECALL_CROSSLINGUAL_DECISION_20260810.md
- 拍板: 保 bge-m3 统一（1024 维, 接受中文 -10pp 换跨语言统一空间）
- en top1 0% → 24%（MRR 0.063→0.355）: BGE-M3 + 向量粗筛 + BM25 跨语言保护
- 评测报告: docs/test/DOC_RECALL_VARIANT_BENCH_20260810.md
- 参考分析: docs/only/reference/TENCENTDB_AGENT_MEMORY_ANALYSIS_20260810.md

## 十二、结构化切分修复 + 量化评测推进（2026-08-11）

### 1. 网关缓存污染 bug 修复（LLM 空返回真根因）
- 现象: LLM 偶发返回空 content（agent_bench code#2 / refine LLM 全空）
- 根因: switch 网关缓存键 = messages+model, **不含 max_tokens/temperature**
  → max_tokens=16 的截断空响应被缓存, 同 messages 的 128 请求命中坏缓存
- 修复: server/api.go requestCacheKey 加入生成参数（已编译 gateway.exe）
- 验证: mt=16 坏缓存不再污染 mt=128（content 恢复）

### 2. goldset 切块质量问题（用户: 硬切太乱来）
- 根因: goldset 生成器绕过生产注册链路, 私有 chunk_text 按句硬切
  → markdown 结构（---/###/代码块）被吞, 块语义残缺
- 修复: 新增 chunk_document 工具（ToolRegistry, category=parse）
  → MarkdownParser 树（heading 层级 + code/list 独立）+ 噪音过滤
  → 结构节点独立成块, 段落合并; select 修复（header/semantic 优先
  fixed_size, 不再按 quality/latency 让 fixed_size 胜出）
- goldset 重建: 714 块 → 360 块, 异常 184 → 0（4 个为代码注释误报）
- 脚本修复: _build_goldset.py 加 ROOT 到 sys.path（core 导入失败曾全 fallback）

### 3. 量化评测数据（本轮）
- Agent 任务: 成功率 100%（10/10）, 延迟 avg 24.7s（LLM 生成主导）,
  token ~4.7K/任务, ¥0.009/任务
- 记忆评测（RAGAS 口径）: rrf top1 52.5%（随机 11.3%）, CP@5 0.603
- 消融: L0 粗召回 top1 53.3% / L1 子图覆盖 93.3%（goldset 无图数据,
  实为 top-10 透传）/ L2 LLM 精排 20% → **LLM 简单挑选负增益,
  粗召回 RRF 排序是主力**（LLM 空返回修复后结论稳定）
- 评测脚本: agent_bench.py / memory_bench.py / refine_bench.py /
  refine_ablation.py / dump_refine_chain.py / gen_recall_variants.py /
  recall_variant_bench.py

### 4. 待办（压缩后）
- goldset 重建后重跑记忆评测基线（top1/CP 应变化, 块质量提升）
- 精细化正解: 子图内容直接注入执行层（不做 LLM 中间过滤）——设计待落地
- Rust 重构（RECALL_RUST_DESIGN_20260810.md）: 余弦/BM25 计算核心
- 评测体系补齐: Faithfulness（claim 级）/ Context Recall / 并发吞吐

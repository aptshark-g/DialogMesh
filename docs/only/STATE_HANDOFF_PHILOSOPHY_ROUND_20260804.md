# 压缩交接 — 全局哲学消解轮（2026-08-04）

> 压缩后唯一恢复入口（本批）。恢复顺序: 本文档 → `GLOBAL_PHILOSOPHY_FILTER_FINAL_20260803.md`
> → `G10_STORAGE_DECISION_20260803.md` → `GLOBAL_PENDING_DECISIONS_20260803.md`。
> 状态: **61 项冲突哲学消解完成，真决策 13 → 8 项；6 大项已定案；进入剩余拍板 + 施工阶段**。

---

## 一、本轮完成（2026-08-03 晚 ~ 08-04）

### 1.1 审计补盲（3 项）
```
docs/only/frontend/FRONTEND_IMPL_AUDIT_20260803.md   （新目录）
  前端真实代码审计（src 约 136 源文件）:
  FE-1 P0  白盒编辑 API（/v6/edit/* 5 端点）后端未注册 → 图编辑/对话树编辑 404
  FE-2 P1  12+ 组件/hook/lib 死代码
  FE-3 P1  四套 WebSocket 实现并存
  FE-4 P2  stubs_api 假数据（前端读到 stub 响应）
  FE-5 P2  前端 15 页"有 UI 需接管线"
  FE-6 P3  GraphEditPanel 提交失败静默

docs/only/landscape_read/SEMANTIC_DIFF_AUDIT_20260803.md
  DESIGN_SEMANTIC_DIFF 设计↔实现对照: 10 分类/5 级风险一致；
  SD-1 P1 SemanticDiffer 注入后零调用（AST 约束从未生效）

DOCS_LANDSCAPE_MAPPING 修正: 9 个历史元文档确认非真缺口（BUSINESS_CHAIN_REMAINING/
  REMAINING_CHAINS_GAP/FRONTEND_AUDIT/implementation_assessment/architecture_gaps×2/
  reviews×2/IMPROVEMENTS）
```

### 1.2 全局哲学消解（核心产出）
```
G6_PHILOSOPHY_FILTER_20260803.md          （61 项消解表初版）
ROUND1_G1_G6_EXECUTION_20260803.md        （G1 四层方案 + 51 项预筛 + 精度修正）
GLOBAL_PHILOSOPHY_FILTER_FINAL_20260803.md（糅合 FINAL = 唯一拍板依据）
G10_STORAGE_DECISION_20260803.md          （存储选型定案）
GLOBAL_PENDING_DECISIONS_20260803.md      （全局待拍板清单，已同步）
```

---

## 二、已定案 6 大项（施工依据，不再讨论）

| 项 | 定案 | 文档 |
|---|---|---|
| G1+G3 | 决策/双路径归一: 蓝图退视图(DAG 构建/校验/编辑) → StateMachine 执行引擎（消费 DAG, 拓扑序）→ GlobalDecider 状态底座（registry 实例注入）→ CognitiveScheduler 未来；agent_native 退数据容器或删（装配归 bootstrap_v6）；v3_session_api L125 换真引擎（P0）| FINAL §6/§7 |
| G10 | 存储分层+触发: 阶段1 零新依赖（sqlite_store+graph_store+UnifiedStore 向量首选+TieredStorageManager 分层启用）+ 2 接线；阶段2 Kuzu（Protocol 新后端）；阶段3 Neo4j/Milvus（与 G5 同触发）| G10_STORAGE_DECISION |
| B2-3 | 锚点能力底座: 持久化持锚点+扩散+RAG 适配（所有模块可消费），子图只做编译（召回→组装）；主控走子图/子 agent 直连持久化 | FINAL §8 |
| B4-1 | 服务层降级: 组件保留（rate_limiter/session_manager/request_queue）+ 协议保留（service/protocol）+ 层归档（v3_0 先迁移 test_fullstack）+ v6_app 薄中间件层（轻服务层）| FINAL §9 |
| B4-5 | CLI/RPC: 内核唯一（dispatch 函数集）+ 传输可插拔；顺序 = CLI 补全（消假执行）→ REST 对齐（消 stubs）→ MCP 标准化 → 多 agent 直连 | FINAL §10 |
| G6 | 61 项预筛本身（消解率 74%）| FINAL |

---

## 三、剩余真决策 8 项（拍板池）

```
🔴 待拍板（按顺序）:
  B8-4  网关 vs 进程内 provider（归 LLM-2, 含 I1-8 双套 Provider）
  B1-8  CognitiveWorkspace 容器（归 LLM-1）
  B5-3  子图编辑 = 用户控制权（A19 落地）
  G4    FE-1 白盒编辑 API 未注册（P0，方向已明待施工）
🟡 待确认（方向已定）:
  G2    EventBus 生命周期层（NEVER drop + 热/温/冷 + GAP-1~3）
  G5    分布式触发条件（含 B8-1）
  G7-9  归档/索引/处置策略
```

---

## 四、施工前置汇总（定案项落地时用）

```
G1+G3-P1  修 StateMachine（X3 补 3 handler + X4 输出传递 + X5 result 兜底）P0
G1+G3-P2  StateMachine 支持 DAG 拓扑序执行 P0
G1+G3-P3  v3_session_api L125 归一（orch.process → get_engine().on_event）P0
G1+G3-P4  agent_native 处置（装配归 bootstrap_v6，退容器或删）P1
G1+G3-P5  GlobalDecider 注入 StateMachine（复用 registry 实例）P1
G10-P1    UnifiedStore → ChunkStore backend（向量接线）P1
G10-P2    TieredStorageManager → 主存储路径（分层接线）P1
G10-P3    4 孤儿后端（faiss/milvus/hnsw/lsm）归档或吸收 P2
B2-3-P1   持久化层建召回能力接口（锚点+扩散+RAG 适配）P1
B2-3-P2   子图 compile_dialogue 从持久化取数（替换 11+ getattr）P2
B4-1-P1   v6_app 薄中间件层（rate_limiter/queue/session 挂 FastAPI）P1
B4-5-P1   CLI 补全（消假执行）+ REST 对齐（消 stubs）P1
FE-1      白盒编辑 API 注册（api_viz_edit 挂 v6_app + init(engine)）P0
```

---

## 五、恢复路径（压缩后）

```
1. 读本文档（本轮终态 + 定案 + 剩余 + 施工前置）
2. 读 GLOBAL_PHILOSOPHY_FILTER_FINAL_20260803.md（唯一拍板依据, 含 §6/7/8/9/10 定案细节）
3. 读 G10_STORAGE_DECISION_20260803.md（存储定案）
4. 读 GLOBAL_PENDING_DECISIONS_20260803.md（全模块待拍板清单）
5. 按需读: landscape_read/README_INDEX（51 项冲突）/ frontend/FRONTEND_IMPL_AUDIT /
   landscape_read/SEMANTIC_DIFF_AUDIT / ROUND1_G1_G6_EXECUTION（过程记录）
```

---

## 六、环境与测试备忘（沿用）

```
- pytest 用 anaconda3（C:\Users\APTShark\anaconda3\python.exe -m pytest）
- 避免直接跑 event/tests/test_pluggable.py 与 test_e2e.py（NATS 无限重连）
- start_engine 会卡 NATS（X1 P0）——探针时注意超时
- 环境差异: anaconda3 有 faiss / .venv 无 / hermes 无
- 中文写入用 apply_patch（PowerShell 管道写 Python 会 GBK 乱码）
```


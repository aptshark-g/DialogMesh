# DialogMesh v6 — 设计文档

> 2026-07-27 · 当前运行时状态
> 前端: React 19 + TS + Vite + Zustand | 后端: Python FastAPI | 网关: Go switch
> 嵌入: LM Studio nomic-embed-text 768d | LLM: DeepSeek v4 via switch gateway

---

## 一、架构总览

```
用户输入 → v3_session_api
              │
              ├── Phase 1: AgentOrchestrator 认知分析 (PCR + Intent + Context)
              ├── Phase 2: 用户画像注入 (OCEAN/MBTI/BFI)
              ├── Phase 3: BlueprintEngine → BlueprintDAG
              │              ├── SkillRegistry.match(intent) → 策略选择
              │              ├── TEMPLATE → 直接模板
              │              ├── HYBRID → 模板 + LLM 节点调整
              │              └── LLM_DRIVEN → 发散→学习→收束
              ├── Phase 3.5: Decider → 3 Tick 并行执行
              │              Tick 0: pcr + intent
              │              Tick 1: context + subgraph + profile
              │              Tick 2: llm_reply (依赖全部完成)
              ├── Phase 4: switch Gateway → LLM 回复
              └── Phase 5: task_graph 返回前端
```

**10 条业务链接入状态**:

| 链 | 状态 | 说明 |
|------|:---:|------|
| 00 PCR | ✅ | 路由分析 |
| 01 Discourse | ✅ | 对话结构 |
| 02 Context | ⚠️ | 存在但空跑 |
| 03 Intent | ✅ | 意图拆分 |
| 04 MetaP | ✅ | EventLog |
| 05 Behavior | ⚠️ | 基础接入 |
| 06 Association | ⚠️ | 部分接入 |
| 07 Engineering | ❌ | 未接 |
| 08 Profile | ✅ | 画像注入 |
| 09 Meta | ⚠️ | 异步审计 |
| 10 Subgraph | ❌ | 未接 |
| 11 Blueprint | ✅ | 编排引擎 |

---

## 二、Blueprint 编排引擎

### 三策略

| 策略 | 说明 | 延迟 |
|------|------|:---:|
| TEMPLATE | 确定性模板(代码分析/数据搜索) | <10ms |
| HYBRID | 模板 floor + LLM 调整节点 (通用对话/任务规划) | ~500ms |
| LLM_DRIVEN | 发散→学习→收束, PlanGate 人工审核 (因果推理) | ~2s |

### Decider Tick 执行

```
BlueprintDAG → Decider (EventBus 模式)
  Tick 0: [pcr, intent]         ← 并行
  Tick 1: [context, subgraph, profile]  ← 并行
  Tick 2: [llm_reply]           ← 依赖全部完成
```

### 约束检查

- 节点数 ≤ 7, 深度 ≤ 18
- 拓扑排序, 无环检测
- data_key 解析验证
- 必须含 PCR 入口 + LLM 出口

---

## 三、学习摄入管线

### 搜索源 (5源, 可扩展)

| 源 | API | 权威 | 状态 |
|------|-----|:---:|:---:|
| ArxivSource | arxiv API | 0.95 | ✅ |
| DuckDuckGoSource | duckduckgo_search 库 | 0.55 | ✅ |
| ScholarSource | Semantic Scholar API | 0.90 | ✅ |
| GitHubSource | GitHub API | 0.85 | ✅ |
| TavilySource | Tavily API (需Key) | 0.92 | ✅ |

扩展新源: `class MySource(SearchSource)` → `SourceRegistry.register()`。

### 内容提取三层层

```
L1: trafilatura (精确, 去导航/广告)
L2: newspaper3k (NLP摘要)
L3: bs4 (兜底, 仅去标签)
```

PDF: pymupdf 原生 → 扫描件检测(文本 <50 chars) → PaddleOCR。

### 存储两仓

```
外部 (ChromaDB)             内部 (HybridIndex)
网页/论文/代码               Sessions/Events/Relations
HNSW 向量索引               SHA256 链 EventLog
k-means 聚类 → LLM 压缩       Meta 审计验证
    ↓ (单向)
  规则 → EventLog
```

### 可信度 (SelfCheckGPT 三层)

```
L1: domain_authority (查表, 25%)
L2: freshness + citations (计算, 35%)
L3: SelfCheck LLM (内容一致性, 40%)
→ credibility 0-1

Meta 学习回写: 正确 +0.02 / 错误 -0.05
```

---

## 四、前端

### 页面地图

| 页面 | 路径 | 状态 |
|------|------|:---:|
| Dashboard | / | ✅ |
| Chat | /chat | ✅ |
| Gateway | /gateway | ✅ |
| Cognitive Profile | /profile | ✅ |
| Behavior | /behavior | ✅ |
| Task Planning | /tasks | ⚠️ DAG 数据已通, 渲染待更新 |
| Meta Center | /meta | ✅ |
| Deep Chain | /chains | ✅ |
| Sessions | /sessions | ✅ |
| Conversation Graph | /graph | ✅ |
| Pipeline | /pipeline | ✅ |
| Engineering | /engineering | ✅ |
| Settings | /settings | ✅ |

### 技术栈

- React 19 + TypeScript + Vite
- Zustand (状态管理)
- Framer Motion (动画)
- ReactFlow (DAG可视化)
- Recharts (图表)

### TaskGraphNode (前后端统一)

```typescript
interface TaskGraphNode {
  id: string;
  name: string;
  type: string;  // pcr|intent|context|subgraph|profile|llm_reply|scan|read|write|...
  status: 'pending' | 'running' | 'completed' | 'failed';
  dependencies: string[];
  params?: Record<string, any>;  // Blueprint 专属
  checkpoint?: boolean;
}
```

---

## 五、持久化

| 存储 | 用途 | 状态 |
|------|------|:---:|
| HybridIndex (FTS5+Vector) | 内部 sessions/events/relations | ✅ |
| ChromaDB (HNSW+聚类) | 外部学习内容 | ✅ |
| EventLog (SHA256链) | 审计/回溯/Meta评分 | ✅ |
| GraphStore | 实体关联 | ✅ |
| SQLiteSessionStore | 会话持久化 | ✅ |
| JSON文件 | v3会话备份 | ✅ |

---

## 六、监控

- `PipelineTracer` → `data/pipeline_traces.jsonl` (每条请求自动记录)
- `PipelineTracer.summary()` → 链健康/延迟/错误率 → Meta 消费
- `MetaFeedback` → 策略降级/升级/学习
- 前端 Debug Monitor → `data/frontend_debug.jsonl`

---

## 七、代码结构

```
core/agent/
  api/              v3_session_api, v6_app, chat_api, stubs, gateway
  blueprint/        编排引擎 (~1,500L, 7 模块)
    models, skill_registry, llm_dag_builder, engine, executor, decider, meta_feedback, tracer
  learning/         学习管线 (~1,300L, 7 模块)
    sources, source_registry, content_fetcher, embedder, credibility, ingestion, chroma_store
  orchestrator/     agent_native (认知管线 + process_dag 桥接)
  persistence/      HybridIndex, FTS5, VectorStore, EventLog, GraphStore
  event/            EventBus (NATS 模式 pub/sub)
  execution/        sandbox, permissions, semantic_diff, closure (17 模块)
  compiler/         子图编译, 语法分解
  planning/         Blueprint 模板, checkpoint
  state/            Decider 状态机
  memory/           RAGraph, 压缩路由器

frontend/src/
  pages/            13 页面
  components/       MessageBubble, ErrorBoundary, TaskGraphView, ...
  hooks/            useV6Gateway, useV6TaskWS, useChat, ...
  stores/           Zustand stores
  types/api.ts      TypeScript 类型 (TaskGraphNode 支持 Blueprint)
```

---

## 八、设计文档索引

| 文档 | 内容 |
|------|------|
| `docs/DESIGN_BLUEPRINT_ORCHESTRATION.md` | Blueprint 15节 (理念→前沿→四段协议→统一可视化) |
| `docs/DESIGN_LEARNING_INGESTION.md` | 学习管线 8节 (搜索→抓取→可信度→RAG→双仓) |
| `docs/GAP_ANALYSIS.md` | 10链差距分析 |
| `docs/TROUBLESHOOTING.md` | 8节 已知问题+修复 |
| `docs/BUSINESS_CHAIN_11_BLUEPRINT.md` | Blueprint 业务链 |
| `docs/ENGINEERING_BLUEPRINT.md` | 工程规格 |
| `.hermes/plans/` | 实施计划 |

# MemoryGraph 项目清单

> 本文档记录 `memorygraph/` 目录下所有核心文件及其职责。
> 生成时间：2025-06-30

---

## 目录总览

```
memorygraph/
├── config/              # 配置文件
├── core/                # 核心代码
│   ├── agent/           # 对话管理引擎
│   └── infrastructure/  # 基础设施（P0-P2）
├── gui/                 # NiceGUI 可视化面板
├── data/                # 运行时数据（SQLite, GraphML）
├── docs/                # 设计文档
├── requirements.txt     # Python 依赖
├── pyproject.toml       # 项目配置
├── README.md            # 项目说明
└── MANIFEST.md          # 本文件
```

---

## 配置文件（config/）

| 文件 | 职责 | 是否纳入版本控制 |
|------|------|------------------|
| `agent_config.yaml` | 默认配置（阈值、窗口大小、模型路径） | ✅ |
| `user_config.yaml` | 用户配置（API Key、模型名、偏好） | ❌（含密钥） |
| `user_config.yaml.example` | 用户配置示例（带注释） | ✅ |

---

## 基础设施（core/infrastructure/）

P0-P2 落地的核心基础设施模块。

| 文件 | 职责 | 状态 |
|------|------|------|
| `model_service.py` | BGE 单例常驻 + 批量编码 + 缓存 | ✅ P0-1 |
| `sqlite_store.py` | SQLite 持久化（会话/轮次/话题/用户/向量） | ✅ P0-2 |
| `token_manager.py` | Token 计数（tiktoken/字符近似）+ 智能截断 | ✅ P0-3 |
| `cache_layer.py` | LLM 响应缓存（L1 内存 + L2 SQLite） | ✅ P0-5 |
| `graph_store.py` | NetworkX 有向图（话题/轮次/实体/关系） | ✅ P2 |
| `test_runner.py` | 自动化测试套件（5 项测试） | ✅ P2 |

---

## 对话管理核心（core/agent/）

### 上下文管理（context_manager/）

| 文件 | 职责 |
|------|------|
| `discourse_manager.py` | 统一入口：话题检测 + 上下文组装 + 持久化 + 恢复 |
| `semantic_index.py` | BGE 向量索引 + 语义搜索 + 批量编码 |
| `turn.py` | Turn 数据模型（原始查询 + 话语块 + 元数据） |
| `context_layer.py` | 上下文注入层（用户画像 → ContextBlock） |

### 多级 LLM 客户端（coordinator/）

| 文件 | 职责 |
|------|------|
| `multi_tier_llm_client.py` | Tier 1/2 路由 + 自动回退 + 缓存集成 |
| `mode_router.py` | 复杂度评估 + 模式选择（rule/small/remote） |
| `small_model_client.py` | LMStudio 本地模型连接 |
| `adaptive_threshold.py` | 自适应阈值 + 贝叶斯反馈 |
| `bayesian_engine.py` | 贝叶斯后验推断（模式偏好/满意度） |
| `complexity_evaluator.py` | 查询复杂度评分（长度/领域/意图） |

### 话题树（topic_tree/）

| 文件 | 职责 |
|------|------|
| `manager_v2.py` | TopicTreeManagerV2：Embedding + 实体 + 意图三维 cohesion |
| `manager.py` | 旧版话题树（兼容） |
| `models.py` | 话题节点/边数据模型 |

### 用户引擎（user_engine/）

| 文件 | 职责 |
|------|------|
| `user_profile.py` | 用户画像数据模型（技术等级/领域/风格） |
| `user_extractor.py` | 单轮特征提取（技术词/领域/意图） |
| `user_manager.py` | 画像持久化 + 统计更新 |
| `consistency_checker.py` | 跨轮一致性校验（行为 vs 声明） |

### 任务引擎（task_engine/）

| 文件 | 职责 |
|------|------|
| `task_manager.py` | 任务生命周期管理（检测/创建/更新/完成） |
| `task_detector.py` | 任务类型检测（code/analyze/learn/compare） |
| `task.py` | 任务数据模型 |

### 话语块管道（discourse_block_tree/）

| 文件 | 职责 |
|------|------|
| `manager.py` | 话语块管理（创建/索引/查询） |
| `segmenter.py` | 话语分割（标点/语义/长度） |
| `summary_engine.py` | 三级摘要（V1 原文 → V2 压缩 → V3 标签） |
| `models.py` | 话语块/锚点/意图数据模型 |

### 其他模块

| 文件/目录 | 职责 |
|-----------|------|
| `discourse_integration.py` | 话语块管道整合入口 |
| `intent_parser.py` | 意图解析（query → intent_label） |
| `intent_rule_registry.py` | 意图规则注册表 |
| `expertise_probe.py` | 技术水平探测 |
| `cognitive_compiler/` | 认知编译器（语义编码/分解/注入） |
| `compiler/` | 编译器层（header_injector, semantic_encoder, macro_micro_quantizer） |
| `config/` | 配置加载（discourse_config, logging_setup, prompt_config） |
| `context_window/` | 上下文窗口管理（compressor, window_manager） |
| `frontend/` | 前端组件（澄清 FSM, 多模态, WebSocket, 任务图可视化） |
| `llm_providers/` | LLM 提供商抽象（base, local, openai, mock, failover, hybrid） |
| `mcp/` | MCP 协议客户端/服务器 |
| `observability/` | 可观测性（日志/指标/追踪/告警） |
| `onboarding/` | 引导系统 |
| `orchestrator.py` | 编排器 |
| `pcr/` | 协议兼容层（PCR） |
| `persistence/` | 持久化层（旧版，与 infrastructure 并存） |
| `prompts/` | 提示词模板（意图/任务/边界/摘要/用户画像） |
| `security/` | 输入消毒 |
| `service/` | 服务层（API, 会话管理, 限流, 分布式锁） |
| `tools/` | 认知工具 |
| `window/` | 窗口管理（旧版） |
| `tests/` | 单元测试（adaptive_threshold, expertise_probe, integration） |

---

## 可视化面板（gui/）

| 文件 | 职责 | 状态 |
|------|------|------|
| `dashboard.py` | 主面板：仪表盘/对话树/任务看板/贝叶斯监控/实时对话 | ✅ |
| `streaming.py` | 流式响应组件（thinking → 完成） | ✅ P0-4 |
| `server.py` | 服务器启动 |
| `mcp_routes.py` | MCP 路由 |
| `static/` | CSS/JS 静态资源 |
| `templates/` | HTML 模板 |

---

## 运行时数据（data/）

| 路径 | 说明 | 是否纳入版本控制 |
|------|------|------------------|
| `data/memorygraph.db` | 主 SQLite 数据库 | ❌ |
| `data/graphs/` | GraphML 话题图 | ❌ |
| `data/test_*.db` | 测试数据库 | ❌ |

---

## 依赖文件

| 文件 | 说明 |
|------|------|
| `deploy/requirements.txt` | Python 依赖列表 |
| `deploy/pyproject.toml`   | 项目配置（ Poetry / setuptools） |
| `deploy/Dockerfile`       | Docker 构建 |
| `deploy/docker-compose.yml`| Docker Compose 配置 |

---

## 测试状态

| 测试 | 文件 | 结果 |
|------|------|------|
| model_service | `core/infrastructure/test_runner.py` | ✅ pass |
| persistence | `core/infrastructure/test_runner.py` | ✅ pass |
| graph_store | `core/infrastructure/test_runner.py` | ✅ pass |
| topic_detection | `core/infrastructure/test_runner.py` | ✅ 80% accuracy |
| semantic_search | `core/infrastructure/test_runner.py` | ✅ 100% top-3 recall |

---

## 变更日志

| 日期 | 变更 |
|------|------|
| 2025-06-30 | 项目独立化：创建 `memorygraph/` 子目录，整理核心文件 |
| 2025-06-30 | P0-1: ModelService 单例常驻 |
| 2025-06-30 | P0-2: SQLiteStore 持久化 |
| 2025-06-30 | P0-3: TokenManager 计数与截断 |
| 2025-06-30 | P0-4: StreamingResponse 流式输出 |
| 2025-06-30 | P0-5: ResponseCache 缓存层 |
| 2025-06-30 | P1: 自动持久化 + 启动恢复 |
| 2025-06-30 | P2: GraphStore + 自动化测试 |

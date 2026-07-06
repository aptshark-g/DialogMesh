# DialogMesh v3.0

> 多层 LLM 认知架构的对话代理系统 —— 6 个 LLM 实例协同，认知双工融合，双树结构驱动

---

## 项目简介

**DialogMesh** 是一个基于多层 LLM 认知架构的工业级对话代理系统。v3.0 版本引入六层 LLM 协同认知引擎，通过 **认知双工（Cognitive Duplex）** 架构将算法引擎与 LLM 引擎并行运行，由 Fusion Engine 加权融合输出；同时以 **认知树（Cognitive Tree）** 与 **主题树（Topic Tree）** 构成双树结构，实现对话状态的精确建模与用户话题的持久追踪。

DialogMesh 专为复杂多轮对话场景设计，支持动态规划、工具注册与绑定、可观测性全链路监控，以及 FastAPI + WebSocket 异步服务层。

---

## 核心特性

### 1. 六层 LLM 认知架构

| LLM 实例 | 职责 | 关键输出 |
|----------|------|----------|
| **PCR-LLM** | Protocol Compatible Router — 协议兼容路由与意图初分 | 路由决策、协议兼容性判断 |
| **Intent-LLM** | 意图解析 — 从用户查询提取结构化意图 | IntentLabel、置信度、槽位填充 |
| **Planning-LLM** | 规划生成 — 任务分解与策略选择 | 规划图、Skill 选择、依赖关系 |
| **Meta-Cognitive-LLM** | 元认知监控 — 认知状态评估与资源调度 | 认知负荷、策略调整建议 |
| **Reflective-LLM** | 反思校验 — 输出质量评估与自我修正 | 一致性评分、修正建议 |
| **Answer-LLM** | 答案生成 — 最终响应合成与格式化 | 结构化响应、多格式输出 |

六层 LLM 通过 **Cognitive Compiler** 统一编排，支持级联激活与短路优化。

### 2. 认知双工融合引擎（Cognitive Duplex）

```
┌─────────────────┐     ┌─────────────────┐
│  算法引擎 (Algo)  │     │  LLM 引擎      │
│  • 规则路由      │  ║  │  • 语义理解    │
│  • 向量检索      │  ║  │  • 推理规划    │
│  • 模式匹配      │  ║  │  • 生成合成    │
│  • 统计决策      │  ║  │  • 反思校验    │
└────────┬────────┘  ║  └────────┬────────┘
         │           ║            │
         └───────────╫────────────┘
                     ║
              ┌──────┴──────┐
              │ Fusion Engine │
              │  加权融合决策   │
              └──────┬──────┘
                     ↓
              最终响应输出
```

算法引擎与 LLM 引擎并行执行，Fusion Engine 根据置信度、延迟、成本多维评分进行动态加权融合，实现"快思考 + 慢思考"的协同决策。

### 3. 双树结构

#### 认知树（Cognitive Tree）
- **节点/边模型**：节点承载认知状态，边表示认知转换关系
- **生命周期管理**：ACTIVE → COOLING → COLD → ARCHIVED 状态机
- **访问控制**：基于角色的节点读写权限（RBAC）
- **事务性写入**：ACID 保证的认知状态持久化
- **跨引用（Cross-Ref）**：支持节点间语义关联与导航

#### 主题树（Topic Tree）
- 用户话题追踪与层次化组织
- 与认知树形成正交双树：主题树关注"用户说了什么话题"，认知树关注"系统如何理解"
- 支持话题延续、切换、回溯、子话题嵌套

### 4. 规划 Skill 层（Planning Skill Layer）

**5 核心原语**：

| 原语 | 说明 | 适用场景 |
|------|------|----------|
| **DivideConquer** | 分而治之 — 递归分解复杂任务 | 多步骤分析、批量处理 |
| **ConditionalBranch** | 条件分支 — 动态路径选择 | 决策树、用户意图分流 |
| **LoopUntil** | 循环直至 — 迭代优化直到满足条件 | 数据检索、验证收敛 |
| **SearchVerifyExecute** | 搜索-验证-执行 — 外部知识增强 | RAG、工具调用、事实校验 |
| **TreeOfThought** | 思维树 — 多路径探索与回溯 | 复杂推理、创意生成 |

**三级 SkillLevel**：
- `HIGH` — 仅输出规划名称与参数
- `MEDIUM` — 输出规划名称 + 简要说明 + 参数
- `DETAIL` — 完整规划图、依赖关系、执行步骤

**模式回退链**：规划失败时自动降级（ToT → DivideConquer → 单步执行），确保系统鲁棒性。

### 5. 工具注册与绑定（Tool Registry）

- **SchemaGuard**：参数 Schema 校验与兼容性检查
- **ToolBindingEngine**：运行时参数绑定与类型转换
- **权限控制**：工具级别访问权限（`tool_registry/permission.py`）
- **发现与短列表**：自动工具发现 + 相关性排序

### 6. 异步服务层

- **FastAPI** + **WebSocket** 双通道支持
- **4 种响应格式**：
  - `BRIEF` — 极简摘要
  - `BALANCED` — 平衡信息密度
  - `EXPLANATORY` — 详细解释
  - `TUTORIAL` — 教学式引导
- **会话管理**：多会话并发、状态隔离、持久化恢复
- **响应合成器**：基于格式的动态内容组装

### 7. 可观测性全链路

| 维度 | 组件 | 能力 |
|------|------|------|
| **Metrics** | `metrics.py` | Prometheus 兼容指标采集 |
| **Logging** | `logger.py` | 结构化日志 + 多级过滤 |
| **Tracing** | `tracer.py` | 分布式追踪，调用链可视化 |
| **Alerting** | `alert.py` | 阈值告警 + 通知通道 |
| **Dashboard** | `dashboard.py` | 实时诊断面板 |
| **Telemetry** | `telemetry.py` | 遥测数据聚合与导出 |

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                        用户层                                │
│  CLI / WebSocket / HTTP API / 第三方集成                      │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                   服务层 (Service Layer)                     │
│  ┌────────────┐ ┌──────────────┐ ┌──────────────────────┐   │
│  │   api.py   │ │ agent_service│ │  session_manager     │   │
│  │  (FastAPI) │ │   (业务逻辑)  │ │   (会话生命周期)      │   │
│  └────────────┘ └──────────────┘ └──────────────────────┘   │
│  ┌────────────┐ ┌──────────────┐ ┌──────────────────────┐   │
│  │websocket_  │ │response_compo│ │   middleware         │   │
│  │  manager   │ │   ser.py     │ │   (中间件)            │   │
│  └────────────┘ └──────────────┘ └──────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              app_factory.py (应用工厂)                  │  │
│  └──────────────────────────────────────────────────────┘  │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                  编排层 (Orchestrator)                        │
│  ┌────────────┐ ┌──────────────┐ ┌──────────────────────┐   │
│  │ orchestrator│ │  bootstrap   │ │   system_bootstrap    │   │
│  │   .py      │ │   (运行时)    │ │   (系统启动)          │   │
│  └────────────┘ └──────────────┘ └──────────────────────┘   │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                   认知层 (Agent Core)                        │
│  ┌────────────┐ ┌──────────────┐ ┌──────────────────────┐   │
│  │cognitive_  │ │  cognitive_  │ │   context_manager    │   │
│  │  tree/     │ │  compiler/   │ │   (上下文管理)         │   │
│  │  (双树)     │ │  (编译器)     │ │                       │   │
│  └────────────┘ └──────────────┘ └──────────────────────┘   │
│  ┌────────────┐ ┌──────────────┐ ┌──────────────────────┐   │
│  │  planning/ │ │ llm_providers│ │   tool_registry      │   │
│  │  (规划Skill)│ │   (LLM适配)   │ │   (工具注册)          │   │
│  └────────────┘ └──────────────┘ └──────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              observability/ (可观测性)                 │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                     基础设施层                                │
│  配置系统 (config/) / 数据模型 (data_models.py) / 测试套件       │
└─────────────────────────────────────────────────────────────┘
```

---

## 快速开始

### 环境要求

- Python 3.11+
- PyTorch 2.0+（CPU 即可，GPU 可选）
- 内存：建议 8GB+
- 磁盘：~500MB（模型 + 依赖）

### 安装

```bash
# 克隆仓库
git clone https://github.com/yourusername/DialogMesh.git
cd DialogMesh

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
# 或开发模式
pip install -e ".[dev]"
```

### 配置

```bash
# 复制示例配置
cp config/user_config.yaml.example config/user_config.yaml

# 编辑 config/user_config.yaml，填入 LLM API Key
# 支持：OpenAI / DeepSeek / 本地 LMStudio / Ollama
```

### 运行测试

```bash
# 运行全部测试（327 个）
pytest core/agent/v3_0/ core/service/v3_0/ -v

# 运行特定模块测试
pytest core/agent/v3_0/planning/tests/ -v
pytest core/agent/v3_0/cognitive_tree/tests/ -v
pytest core/agent/v3_0/tool_registry/tests/ -v

# 带覆盖率报告
pytest core/agent/v3_0/ core/service/v3_0/ --cov=core --cov-report=term-missing
```

### 启动服务

```bash
# 启动主服务（FastAPI + WebSocket）
python main_v3.py

# 默认端口：8000
# API 文档：http://localhost:8000/docs
# WebSocket：ws://localhost:8000/ws
```

---

## 项目结构

```
DialogMesh/
├── main_v3.py                          # 服务入口点
│
├── core/
│   ├── agent/v3_0/                     # 认知层核心（v3.0）
│   │   ├── cognitive_tree/               # 认知树 + 主题树双树结构
│   │   │   ├── manager.py                # 树管理器（节点/边/生命周期）
│   │   │   ├── models.py                 # 节点/边数据模型
│   │   │   ├── cross_ref.py              # 跨引用导航
│   │   │   └── tests/
│   │   ├── cognitive_compiler/           # 认知编译器
│   │   │   ├── compiler.py               # 编译主入口
│   │   │   ├── edge_manager.py           # 边生命周期管理
│   │   │   ├── access_control.py         # 访问控制（RBAC）
│   │   │   ├── lifecycle.py              # 节点生命周期状态机
│   │   │   ├── event_bus.py              # 认知事件总线
│   │   │   └── querier.py                # 认知查询引擎
│   │   ├── llm_providers/                # LLM 提供商适配层
│   │   │   ├── provider_manager.py       # 统一 ProviderManager
│   │   │   ├── base.py                   # 抽象基类
│   │   │   ├── openai_provider.py        # OpenAI / DeepSeek 适配
│   │   │   ├── local_provider.py         # LMStudio / Ollama 本地适配
│   │   │   ├── failover_provider.py      # 故障转移
│   │   │   ├── hybrid_router.py          # 混合路由
│   │   │   ├── mock_provider.py          # 测试 Mock
│   │   │   ├── circuit_breaker.py        # 熔断器
│   │   │   └── streaming.py              # 流式响应处理
│   │   ├── context_manager/              # 上下文管理
│   │   │   ├── manager.py                # 上下文管理器
│   │   │   ├── window.py                 # 上下文窗口管理
│   │   │   ├── store.py                  # 上下文存储
│   │   │   └── models.py                 # 上下文数据模型
│   │   ├── planning/                     # 规划 Skill 层
│   │   │   ├── planner.py                # 规划器主入口
│   │   │   ├── skill_engine.py           # Skill 执行引擎
│   │   │   ├── skill_registry.py         # Skill 注册表
│   │   │   ├── skill_matcher.py          # Skill 匹配器
│   │   │   ├── decomposition.py          # 任务分解
│   │   │   ├── dependency_resolver.py    # 依赖解析
│   │   │   ├── scheduler.py              # 执行调度器
│   │   │   ├── optimizer.py              # 规划优化
│   │   │   ├── fallback.py               # 模式回退链
│   │   │   ├── strategy_selector.py      # 策略选择器
│   │   │   ├── agent_allocator.py        # Agent 分配
│   │   │   └── tests/
│   │   ├── tool_registry/                # 工具注册与绑定
│   │   │   ├── registry.py               # 工具注册表
│   │   │   ├── binding.py                # ToolBindingEngine
│   │   │   ├── executor.py               # 工具执行器
│   │   │   ├── permission.py             # 权限控制
│   │   │   ├── discovery.py              # 工具发现
│   │   │   ├── shortlister.py            # 工具短列表
│   │   │   └── models.py                 # 工具数据模型
│   │   ├── observability/                # 可观测性
│   │   │   ├── metrics.py                # 指标采集
│   │   │   ├── logger.py                 # 结构化日志
│   │   │   ├── tracer.py                 # 分布式追踪
│   │   │   ├── alert.py                  # 告警系统
│   │   │   ├── dashboard.py              # 诊断面板
│   │   │   ├── telemetry.py              # 遥测聚合
│   │   │   └── store.py                  # 可观测数据存储
│   │   ├── orchestrator/                 # 编排器
│   │   │   ├── orchestrator.py           # 主编排器（6 LLM 协同）
│   │   │   ├── bootstrap.py              # 运行时启动
│   │   │   └── models.py                 # 编排数据模型
│   │   ├── system_bootstrap.py           # 系统启动入口
│   │   ├── data_models.py                # 全局数据模型
│   │   └── __init__.py
│   │
│   └── service/v3_0/                     # 服务层（v3.0）
│       ├── api.py                        # FastAPI 路由
│       ├── agent_service.py              # Agent 业务逻辑
│       ├── session_manager.py            # 会话管理
│       ├── websocket_manager.py          # WebSocket 连接管理
│       ├── response_composer.py          # 响应格式合成器
│       ├── app_factory.py                # 应用工厂
│       ├── middleware.py                 # 中间件
│       ├── data_models.py                # 服务数据模型
│       ├── tests/
│       └── __init__.py
│
├── config/                               # 配置文件
│   ├── agent_config.yaml                 # 默认配置
│   ├── user_config.yaml                  # 用户配置（不提交 git）
│   ├── user_config.yaml.example          # 配置示例
│   └── expertise_lexicon.yaml            # 领域词汇表
│
├── docs/v3.0/                            # 设计文档
│   ├── DESIGN_FULL_CONCEPT.md            # 总体架构设计
│   ├── DESIGN_MULTILAYER_LLM_COGNITIVE.md # 多层 LLM 认知设计
│   ├── DESIGN_PLANNING_SKILL_LAYER.md    # 规划 Skill 层设计
│   ├── DESIGN_TASK_PLANNING_DYNAMIC.md   # 动态任务规划设计
│   ├── ENGINEERING_*.md                  # 16 份工程实现文档
│   └── ...
│
├── tests/                                # 集成测试
├── requirements.txt                      # 依赖列表
├── pyproject.toml                        # 项目配置
├── README.md                             # 本文件
├── README_EN.md                          # 英文文档
├── MANIFEST.md                           # 项目清单
├── CONTRIBUTING.md                       # 贡献指南
└── CHANGELOG.md                          # 变更日志
```

---

## 技术亮点

| 技术点 | 实现 | 优势 |
|--------|------|------|
| **六层 LLM 协同** | PCR → Intent → Planning → Meta → Reflective → Answer | 级联激活、短路优化、细粒度认知分工 |
| **认知双工** | 算法引擎 ∥ LLM 引擎 + Fusion Engine | 延迟与质量的最优权衡，支持快/慢思考切换 |
| **规则引擎重写** | AlgorithmEngine: 三维噪声检测 + 规则意图解析 + 认知快照 | 从 20 行桩升级为 280 行完整实现 |
| **融合引擎独立** | FusionEngine: 5 种策略 + 冲突检测 + 递归合并 | 从内联类提取为独立模块 |
| **元认知三层验证** | MetaCognitiveValidator: 事实性/一致性/合理性 | 规则 + LLM 双轨道验证 |
| **跨会话复盘** | ReflectiveAnalyzer: 偏见检测 + 学习策略生成 | TreeHealthAnalyzer + BiasDetector |
| **画像更新** | ProfileUpdater: EMA 加权融合 | Track A 趋势 + Track B 修正 |
| **冷启动探测** | ColdStartProbe: 5 维通用语言特征 | 不依赖领域词表，Max-based 评分 |
| **幻觉三层防御** | SchemaGuard → HallucinationDetector → BiasDetector | 实时拦截 + 跨轮检测 + 长期复盘 |
| **后处理约束** | AnswerConstraintValidator | 长度/安全/内容/置信度校验 |
| **状态映射** | FSM 外部状态映射 | 双向映射 + 转换日志 |
| **事件注册表** | WebSocket EventRegistry | Schema 校验 + 第三方扩展 |
| **分布式锁** | DistributedLock: Threading + Redis 适配 | 自动降级、上下文管理器 |
| **PCR 反馈闭环** | PcrFeedbackLoop: EMA 自适应阈值 | 滑动窗口噪声追踪 |
| **规则冲突检测** | RuleConflictDetector | 成对模式重叠 fuzz 测试 |
| **双树结构** | Cognitive Tree ⊕ Topic Tree | 正交建模：系统理解 + 用户话题分离 |
| **规划 Skill 原语** | 5 核心原语 × 3 级详细度 × 模式回退链 | 复杂任务自动分解、鲁棒执行 |
| **SchemaGuard** | 参数 Schema 校验 + ToolBindingEngine | 工具调用类型安全、运行时兼容 |
| **可观测性** | 指标/日志/追踪/告警/面板/遥测六维覆盖 | 生产级监控与诊断 |
| **异步服务** | FastAPI + WebSocket + 4 种响应格式 | 高并发、低延迟、多场景适配 |
| **LLM 适配层** | ProviderManager + 熔断 + 故障转移 | 多模型无缝切换、高可用 |

---

## 性能基准

| 指标 | 数值 |
|------|------|
| 测试用例总数 | **392**（v3.0 新增 65） |
| 测试通过率 | **100%** |
| 核心代码文件 | **109**（v3.0: 87 + 新增 22） |
| 代码总行数 | **~34,516**（v3.0 新增 ~2,800） |
| 工程文档 | **16** 份 |
| 设计文档 | **4** 份 |

### 测试覆盖模块

- `cognitive_tree/tests/` — 认知树/主题树生命周期、事务写入、访问控制
- `cognitive_compiler/tests/` — 编译器、边管理、事件总线
- `llm_providers/tests/` — ProviderManager、熔断、故障转移、流式
- `context_manager/tests/` — 上下文管理、窗口管理、存储
- `planning/tests/` — 规划器、Skill 引擎、分解、调度、回退
- `tool_registry/tests/` — 注册、绑定、执行、权限、发现
- `observability/tests/` — 指标、日志、追踪、告警
- `orchestrator/tests/` — 编排器、六层 LLM 协同
- `service/v3_0/tests/` — FastAPI、WebSocket、会话、响应合成

---

## 路线图

- [x] **v3.0** — 多层 LLM 认知架构（6 个 LLM 实例、认知双工、双树结构、规划 Skill、327 测试）
- [ ] **v3.1** — 认知树可视化面板、主题树自动修剪优化
- [ ] **v3.2** — 多模态输入支持（图像、语音、文档）
- [ ] **v3.3** — 分布式部署（多实例编排、负载均衡、状态共享）
- [ ] **v4.0** — 自主学习与进化（在线 Skill 学习、认知树自优化）

---

## 许可证

MIT License

---

## 相关文档
## v3.2 行为认知引擎（新增模块，2026.07）

11 模块管线: HybridCompiler → BehaviorGraph → Predictor → CausalDiscovery → NegativeKB → CausalSubstrate → FoA → L1Summary → Rewarder → FusionEngine (4-track)

| 指标 | 值 |
|------|-----|
| 测试 | 217 passing |
| 规则库 | 98 (63 EN + 35 CN) |
| 可靠性 | 95%+ (真实 LLM) |
| 压力测试 | 57/57 轮零崩溃零降级 |
| 图边数 | 52 per session |

快速开始: `python scripts/test_v32_run.py` (需 DEEPSEEK_API_KEY)

- [英文文档](README_EN.md)
- [项目清单](MANIFEST.md)
- [变更日志](CHANGELOG.md)
- [贡献指南](CONTRIBUTING.md)
- [设计文档](docs/v3.0/)

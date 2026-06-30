# DiscourseBlock Tree 工业级评估报告

> **评估前提**：本项目是工业级开源项目，不是学术原型。评估标准基于可部署性、可维护性、可扩展性、可靠性。

---

## 一、工业级标准定义

| 维度 | 标准 | 不达标的表现 |
|------|------|-------------|
| **开箱可用** | `pip install` 后直接运行，无需手动配置 | 需要手动下载模型、配置路径、安装额外依赖 |
| **配置驱动** | 所有行为参数可通过配置文件/环境变量调整 | 阈值、模型路径、知识库全部硬编码 |
| **优雅降级** | 任何组件失败，系统继续运行，功能降级而非崩溃 | `try/except: pass`，无降级策略，无日志 |
| **性能可控** | 延迟可预测，冷启动 < 100ms，内存占用明确 | 冷启动 729ms，内存 526MB，无性能预算 |
| **可观测** | 结构化日志、关键指标暴露、可追踪 | 零日志，无法知道系统运行状态 |
| **可扩展** | 新领域通过配置接入，无需改代码 | 知识库 `_ENTITY_CANDIDATES_BASE` 写死在代码里 |
| **跨平台** | Windows/Linux/macOS 一致运行 | Windows 测试输出乱码，路径处理未统一 |
| **文档完善** | README、API 文档、部署指南、示例 | 无 README，无使用文档 |

---

## 二、当前实现工业级差距分析

### 2.1 开箱可用：❌ 严重不达标

**问题清单**：
1. **BGE 模型需手动下载**：用户需要执行 `python -m modelscope download BAAI/bge-small-zh`，没有自动下载机制
2. **NER 模型依赖链未解决**：`addict`、`datasets` 等依赖未声明，首次运行才发现缺失
3. **jieba 词典首次加载 681ms**：无预加载机制，首次请求阻塞
4. **无 `requirements.txt` / `pyproject.toml` 依赖声明**：discourse 系统的依赖（torch, transformers, modelscope, jieba, numpy）未在包级别声明

**工业级要求**：
- `pip install memorygraph-discourse` 后，首次运行自动下载所需模型（或提供 `python -m memorygraph_discourse download-models` 命令）
- 所有依赖在 `pyproject.toml` 中声明，安装时自动解决
- 提供 Docker 镜像，开箱即用

### 2.2 配置驱动：❌ 完全缺失

**硬编码参数清单**（直接搜索）：

```python
# 阈值（全部无法配置）
COMPLEX_CLAUSE_LENGTH = 30       # SyntacticDecomposer
MAX_CLAUSES_PER_INPUT = 5         # SyntacticDecomposer
DEFAULT_THRESHOLD = 0.5           # Segmenter
V3_TRIGGER_TURN_COUNT = 5         # SummaryEngine
DEFAULT_HOT_TURNS = 5             # ContextBuilder
hot_turns = 5                     # DiscoursePipeline

# 模型路径（硬编码）
DEFAULT_MODEL_PATH = "models/BAAI/bge-small-zh"  # SemanticEncoder
model_id = "damo/nlp_raner_named-entity-recognition_chinese-base-news"  # SemanticParser

# 权重（硬编码）
macro_weight = 0.6                  # MacroMicroQuantizer
micro_weight = 0.4                  # MacroMicroQuantizer
TEMPORAL_DECAY_LAMBDA = 0.6        # MacroMicroQuantizer

# 知识库（硬编码在代码中）
_DEFAULT_KB = {...}                 # HeaderInjector（~50 条规则）
_ENTITY_CANDIDATES_BASE = {...}     # SyntacticDecomposer（已移除，但 NER 回退仍硬编码）

# 设备选择（自动，但无法覆盖）
device = "cuda" if torch.cuda.is_available() else "cpu"  # SemanticEncoder
```

**工业级要求**：
- 所有参数支持 `YAML` / `JSON` / `TOML` 配置文件
- 环境变量覆盖（如 `MEMORYGRAPH_BGE_MODEL_PATH`）
- 配置热加载（不重启服务即可更新参数）

### 2.3 优雅降级：⚠️ 形式有，实质无

**当前模式**：
```python
try:
    self._encoder = get_encoder()
except Exception:
    self._encoder = None  # 静默降级，无日志
```

**问题**：
1. **无日志记录**：`get_encoder()` 失败的原因是什么？模型文件缺失？内存不足？CUDA 不可用？无从知道
2. **无降级策略文档**：`None` 降级后，哪些功能失效？`MacroMicroQuantizer` 用 SHA256 伪向量，但用户不知道精度下降了
3. **无健康检查接口**：无法查询"当前 BGE 模型是否可用"
4. **NER 模型加载失败导致 1500ms 超时**：`ModelScope` pipeline 加载超时阻塞主线程，没有超时控制

**工业级要求**：
- 每个组件有 `HealthCheck` 接口，返回状态 + 降级信息
- 所有异常记录结构化日志（`WARNING` 级别：降级；`ERROR` 级别：失败）
- 降级策略可配置（如"BGE 不可用时是否拒绝服务" vs "使用伪向量继续运行"）

### 2.4 性能可控：⚠️ 冷启动不可接受

**实测数据**：

| 指标 | 实测值 | 工业级目标 | 差距 |
|------|--------|----------|------|
| 冷启动（模型加载） | **729ms** | < 100ms | 7.3× |
| 内存占用（RSS） | **526MB** | < 200MB | 2.6× |
| 单轮处理延迟 | 20ms（稳定后） | < 10ms | 2× |
| 并发 10 线程 | 未测试 | 延迟增加 < 50% | 未知 |

**问题根因**：
1. **BGE 模型首次加载 729ms**：模型文件 91MB，从磁盘读取 + 反序列化耗时。应提供服务化模式（模型常驻内存，多进程共享）或 ONNX 量化版本
2. **内存 526MB**：BGE 模型约 100MB，但 Python 进程 + torch 开销 + 可能的其他模型缓存导致。工业环境中每个用户/会话一个实例，需要内存预算控制
3. **无性能预算**：没有定义"最大延迟"、"最大内存"、"最大并发"等 SLA 指标

**工业级要求**：
- 提供预加载模式（服务启动时加载模型，而非首次请求时）
- 提供 ONNX / INT8 量化版本，模型体积 < 30MB，加载 < 50ms
- 内存预算控制：每个会话最大内存、全局内存上限
- 性能指标暴露：延迟 P99、吞吐量 QPS、内存使用

### 2.5 可观测：❌ 完全缺失

**当前状态**：
- 零日志（discourse 模块没有 `import logging`）
- 零指标（没有 Prometheus / StatsD 指标）
- 零追踪（没有 OpenTelemetry / Jaeger 追踪）

**工业级要求**：
- 结构化日志（JSON 格式）：每个请求记录输入、处理时间、块数量、状态变化
- 关键指标：
  - `discourse_block_created_total`（块创建计数）
  - `discourse_edu_processed_total`（EDU 处理计数）
  - `discourse_latency_seconds`（处理延迟 Histogram）
  - `discourse_model_loaded`（模型加载状态 Gauge）
- 健康检查端点：`/health` 返回各组件状态

### 2.6 可扩展：❌ 知识库不可扩展

**当前问题**：
1. **知识库硬编码**：`HeaderInjector` 的 `_DEFAULT_KB` 包含 ~50 条规则，用户无法添加新领域（如医疗、法律、金融）
2. **实体类型硬编码**：`SemanticParser` 的 `POS_ENTITY_MAP` 固定映射词性到实体类型
3. **意图标签硬编码**：`SyntacticDecomposer` 的 `intent_label="analyze" if clause.predicate else "statement"`，只有两种意图

**工业级要求**：
- 知识库支持外部文件（YAML/JSON）热加载
- 领域插件机制：用户可以通过配置文件定义新领域的实体、谓语、意图
- 意图扩展：支持自定义意图类型（如 `intent: medical_diagnosis`）

### 2.7 跨平台：⚠️ Windows 有编码问题

**实测问题**：
1. **测试输出乱码**：`tests/test_50_rounds.py` 在 Windows Git Bash 中输出为乱码，说明 `sys.stdout` 编码未正确处理
2. **路径分隔符**：代码中使用 `models/BAAI/bge-small-zh`（Unix 风格），在 Windows 上 `os.path.exists()` 通常能处理，但最好使用 `os.path.join`
3. **模型缓存路径**：`C:\Users\APTShark\AppData\Local\Temp\jieba.cache` 是用户级路径，在 Linux 容器环境中可能无权限

### 2.8 文档：❌ 完全缺失

**当前状态**：
- 无 README.md
- 无 API 文档
- 无部署指南
- 无使用示例
- 无架构图

---

## 三、按优先级排序的问题清单

### 🔴 P0 — 阻塞发布（必须先解决）

| # | 问题 | 影响 | 工作量 |
|---|------|------|--------|
| 1 | **配置系统缺失** | 无法部署到不同环境，无法扩展 | 8h |
| 2 | **冷启动 729ms** | 用户首次请求体验极差，可能导致服务超时 | 8h |
| 3 | **日志完全缺失** | 故障排查 impossible，无法运维 | 6h |
| 4 | **模型自动下载** | 用户需手动下载，无法 `pip install` 即用 | 4h |

### 🟡 P1 — 严重影响可用性（应尽快解决）

| # | 问题 | 影响 | 工作量 |
|---|------|------|--------|
| 5 | **知识库硬编码** | 无法扩展新领域，每次改代码需重新部署 | 6h |
| 6 | **错误处理只有 pass** | 故障无日志，降级无感知 | 4h |
| 7 | **内存占用 526MB** | 高并发场景下内存爆炸 | 8h |
| 8 | **Windows 编码问题** | 影响 Windows 用户 | 2h |
| 9 | **无文档** | 无法吸引用户，无法贡献 | 8h |

### 🟢 P2 — 影响体验（可延后）

| # | 问题 | 影响 | 工作量 |
|---|------|------|--------|
| 10 | **线程安全缓存** | 高并发下数据竞争 | 4h |
| 11 | **性能指标暴露** | 无法监控运行状态 | 6h |
| 12 | **持久化存储** | 会话重启丢失 | 8h |
| 13 | **Docker 镜像** | 部署复杂 | 4h |

---

## 四、精进路线图

### 阶段 1：基础工业改造（2-3 周，P0 + P1 核心）

目标：让系统达到"可部署、可运维、可扩展"的最小工业级。

#### Week 1: 配置系统 + 日志 + 模型管理

**Day 1-2: 配置系统**
- 引入 `pydantic-settings` 或自研配置系统
- 配置文件：`~/.config/memorygraph/discourse.yaml`
- 环境变量覆盖：`MEMORYGRAPH_*`
- 所有硬编码参数迁移到配置：
  ```yaml
  discourse:
    encoder:
      model_path: "models/BAAI/bge-small-zh"
      device: "auto"  # auto/cpu/cuda
      cache_size: 10000
    segmenter:
      threshold: 0.5
      macro_weight: 0.6
      micro_weight: 0.4
    manager:
      hot_turns: 5
    summary:
      v3_trigger_turns: 5
  ```

**Day 3-4: 日志系统**
- 所有模块引入 `import logging`
- 关键操作记录：
  - `INFO`: 块创建/合并、状态变化、模型加载成功
  - `WARNING`: 组件降级（如 BGE 不可用 → 伪向量）、配置热加载
  - `ERROR`: 模型加载失败、内存不足、超时
- 提供日志格式配置（JSON / 文本）

**Day 5: 模型自动下载**
- 提供 `python -m memorygraph_discourse download-models` 命令
- 安装时检测模型缺失，提示用户下载
- 支持 ModelScope / HuggingFace 镜像切换

#### Week 2: 冷启动优化 + 错误处理

**Day 1-2: 冷启动优化**
- 提供 `DiscoursePipeline.preload()` 方法，服务启动时调用
- 模型加载放入后台线程，不阻塞主流程
- 提供 ONNX 量化版本（模型 < 30MB，加载 < 50ms）

**Day 3: 错误处理改造**
- 所有 `try/except: pass` 替换为结构化错误处理：
  ```python
  except ModelLoadError as e:
      logger.warning(f"BGE model unavailable: {e}, falling back to SHA256 pseudo-vectors")
      self._encoder = None
      self._health.mark_degraded("encoder", reason=str(e))
  ```
- 每个组件提供 `HealthCheck` 接口

**Day 4-5: 知识库可扩展**
- 知识库从代码迁移到 YAML 文件
- 支持热加载（运行时更新）
- 提供默认知识库 + 用户扩展知识库合并机制

#### Week 3: 文档 + 测试 + 质量

**Day 1-2: 文档**
- README.md：安装、快速开始、配置、API 概览
- `docs/architecture.md`：架构图、数据流、设计决策
- `docs/configuration.md`：所有配置参数说明
- `docs/deployment.md`：部署指南（pip / Docker / 源码）

**Day 3: 编码修复**
- Windows 输出乱码修复（设置 `PYTHONIOENCODING=utf-8` 或处理 stdout 编码）
- 统一路径处理（`os.path.join` / `pathlib.Path`）

**Day 4-5: 测试强化**
- 50 轮测试加入断言（检查块数量、状态变化、实体数量）
- 压力测试（100+ 轮、并发测试）
- 错误注入测试（模型缺失、内存不足、超时）

### 阶段 2：性能优化 + 可观测（3-4 周，P1 剩余 + P2）

**Week 4-5: 性能优化**
- ONNX 量化 BGE 模型
- 内存预算控制（限制缓存大小、会话内存上限）
- 批量处理优化（多轮请求合并编码）

**Week 6: 可观测**
- Prometheus 指标暴露（`discourse_*` 前缀）
- OpenTelemetry 追踪（请求链路追踪）
- 健康检查端点 `/health`

**Week 7: 持久化**
- SQLite / Redis 持久化话语块树
- 会话恢复机制

### 阶段 3：生态建设（持续）

- Docker 镜像 + Docker Compose 示例
- 示例应用（Chatbot 集成、客服系统、知识问答）
- 社区贡献指南（CONTRIBUTING.md）
- CI/CD（GitHub Actions 自动化测试、发布）

---

## 五、核心结论

### 当前状态：学术原型 → 工业级 的距离 = 60-70%

| 维度 | 学术原型评分 | 工业级评分 | 差距 |
|------|------------|----------|------|
| 功能完整性 | 90% | 90% | ✅ 无差距 |
| 架构设计 | 85% | 85% | ✅ 无差距 |
| 开箱可用 | 20% | 90% | ❌ 70% 差距 |
| 配置驱动 | 0% | 90% | ❌ 90% 差距 |
| 优雅降级 | 30% | 90% | ❌ 60% 差距 |
| 性能可控 | 40% | 85% | ❌ 45% 差距 |
| 可观测 | 0% | 85% | ❌ 85% 差距 |
| 可扩展 | 10% | 80% | ❌ 70% 差距 |
| 文档 | 0% | 90% | ❌ 90% 差距 |

### 继续精进？**必须**

从工业开源角度，当前系统处于**"可运行但不可部署"**的状态。核心算法和架构是合格的，但外围工程（配置、日志、部署、文档）是空白。

**建议**：
- **先不做算法优化**（如 v3 用 LLM 生成、接入 LTP 依存句法等）—— 这些在工业环境中是可选增强，不是阻塞项
- **先补工程基础**（配置、日志、冷启动、文档）—— 这些是阻塞项，没有它们无法发布

**最小可发布版本（MVP for OSS）**：
- 配置系统 ✅
- 日志系统 ✅
- 模型自动下载 ✅
- 冷启动优化（预加载模式）✅
- README + 部署文档 ✅
- 基本错误处理（不 crash）✅

达到这 6 项，系统就可以发布 v0.1.0，然后迭代优化。

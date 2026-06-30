# MemoryGraph 智能对话上下文管理系统

> 基于语义向量 + 自适应话题树 + 多级 LLM 协同的下一代对话记忆引擎

---

## 核心特性

| 特性 | 说明 |
|------|------|
| **语义话题树** | BGE 向量驱动的话题检测，自动聚合/切换/回溯 |
| **三级 LLM 协同** | Tier 1 快速本地 → Tier 2 LLM 仲裁 → Tier 3 后台审查 |
| **自动持久化** | SQLite 存储会话、话题、用户画像、语义向量，重启即恢复 |
| **实时流式响应** | "思考中..." 动画 + 后台异步处理，UI 不卡死 |
| **BGE 单例服务** | 模型只加载一次，进程级共享，缓存命中率 >50% |
| **图数据库** | NetworkX 有向图建模话题关系（延续/切换/回溯/子话题） |
| **智能截断** | TokenManager 精确计数 + 优先级截断，适配 8K~256K 上下文 |

---

## 快速开始

### 环境要求

- Python 3.10+
- PyTorch（CPU 即可）
- LMStudio（本地小模型，可选）
- DeepSeek API Key（高端模型，可选）

### 安装依赖

```bash
pip install -r requirements.txt
```

### 下载 BGE 模型

```bash
python -m modelscope download BAAI/bge-small-zh
# 或手动下载到 models/BAAI/bge-small-zh
```

### 配置 API Key

```bash
# 复制示例配置
cp config/user_config.yaml.example config/user_config.yaml

# 编辑 config/user_config.yaml，填入 DeepSeek API Key
```

### 启动 GUI

```bash
python -m gui.dashboard
```

### 运行测试

```bash
python -m core.infrastructure.test_runner
```

---

## 项目结构

```
memorygraph/
├── config/                  # 配置文件
│   ├── agent_config.yaml    # 默认配置
│   ├── user_config.yaml     # 用户配置（含 API Key，不提交 git）
│   └── user_config.yaml.example
├── core/
│   ├── agent/              # 对话管理核心
│   │   ├── context_manager/    # 上下文管理（DiscourseManager, Turn, SemanticIndex）
│   │   ├── coordinator/        # 多级 LLM 客户端 + 路由
│   │   ├── topic_tree/         # 话题树 V1/V2
│   │   ├── user_engine/        # 用户画像 + 一致性校验
│   │   ├── task_engine/        # 任务检测
│   │   ├── discourse_block_tree/   # 话语块管道
│   │   ├── pcr/                # 协议兼容层
│   │   ├── service/            # 服务层 API
│   │   └── ...
│   └── infrastructure/     # 基础设施（P0-P2）
│       ├── model_service.py      # BGE 单例常驻
│       ├── sqlite_store.py       # SQLite 持久化
│       ├── token_manager.py      # Token 计数与截断
│       ├── cache_layer.py        # 响应缓存
│       ├── graph_store.py        # NetworkX 图数据库
│       └── test_runner.py       # 自动化测试
├── gui/                    # NiceGUI 可视化面板
│   ├── dashboard.py        # 主面板（仪表盘/对话树/任务/贝叶斯/对话）
│   └── streaming.py        # 流式响应组件
├── data/                   # 运行时数据（SQLite DB、GraphML，不提交 git）
├── docs/                   # 设计文档
├── requirements.txt
├── pyproject.toml
└── README.md
```

---

## 关键技术

### 话题切换检测（三级协同）

1. **Tier 1（本地）**：BGE 语义相似度 + 语法连贯 + 关键词 Jaccard + 话语标记
2. **Tier 2（LLM 仲裁）**：模糊区 [0.15, 0.65] 触发 DeepSeek 语义判断
3. **Tier 3（后台审查）**：每 5 轮异步 LLM 审查话题树质量

### 上下文组装（热/温/冷）

- **热缓存**：最近 5 轮（High Priority）
- **温缓存**：话题语义摘要（Medium Priority）
- **冷缓存**：语义搜索（Low Priority）

### 自适应阈值

贝叶斯引擎根据用户行为动态调整话题切换阈值，从"一刀切 0.45"进化为"个性化阈值"。

---

## 性能基准

| 指标 | 数值 |
|------|------|
| 话题检测准确率 | 80%（Tier 1）→ 目标 90%+（+ Tier 2） |
| 语义搜索 top-3 召回 | 100% |
| BGE 编码延迟 | ~8ms/文本（缓存后） |
| 模型加载时间 | ~678ms（首次）→ 0ms（后续） |
| 测试通过率 | 5/5（100%） |

---

## 配置

### 环境变量

```bash
export DEEPSEEK_API_KEY="sk-..."
export LMSTUDIO_BASE_URL="http://localhost:1234/v1"
```

### 配置文件优先级

环境变量 > `~/.memorygraph/config.yaml` > `config/user_config.yaml` > `config/agent_config.yaml`

---

## 许可证

MIT License

---

## 路线图

- [x] P0：基础设施（模型服务、持久化、Token、流式、缓存）
- [x] P1：自动持久化与启动恢复
- [x] P2：图数据库 + 自动化测试
- [ ] P3：端到端对话验证 + 用户体验打磨
- [ ] P4：Benchmark 数据集 + 准确率优化
- [ ] P5：Docker 部署 + 生产级配置

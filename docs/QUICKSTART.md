# MemoryGraph Agent — 快速开始指南

> 从零到运行交互式 Agent 的完整步骤。

---

## 目录

1. [环境准备](#环境准备)
2. [安装依赖](#安装依赖)
3. [配置 LLM Backend](#配置-llm-backend)
   - [LM Studio（推荐）](#lm-studio推荐)
   - [Ollama](#ollama)
   - [OpenAI / Kimi / DeepSeek](#openai--kimi--deepseek)
4. [运行交互式 Agent](#运行交互式-agent)
5. [运行测试](#运行测试)
6. [常见问题](#常见问题)

---

## 环境准备

- **Python**: 3.10+
- **OS**: Windows 10/11 / macOS / Linux
- **内存**: 8GB+（本地模型建议 16GB+）
- **GPU**: 可选，CPU 也可运行（速度较慢）

---

## 安装依赖

```bash
# 1. 克隆仓库
git clone https://github.com/yourusername/memorygraph-agent.git
cd memorygraph-agent

# 2. 创建虚拟环境（推荐）
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# 3. 安装核心依赖
pip install -e .

# 4. 可选：安装完整功能
pip install -e ".[local,chinese,config]"
```

---

## 配置 LLM Backend

### LM Studio（推荐）

**最适合本地测试，无需 API Key，隐私完全可控。**

1. **下载并安装** [LM Studio](https://lmstudio.ai/)
2. **下载模型**：
   - 推荐：`qwen2.5-7b-instruct`（中文好、速度快、非 thinking 模式）
   - 备选：`qwen2.5-14b-instruct`（质量更高，需更多显存）
   - 避免：`qwen3.5-9b`（thinking 模式会消耗大量 token 在自我审查上，导致回复被截断或过度保守）
3. **启动 Local Server**：
   - 左侧栏 → "Local Server" → 开启
   - 默认端口：`1234`
   - 确认模型已加载（界面显示绿色状态）

4. **验证连接**（无需修改代码，默认配置已匹配）：
   ```python
   # interactive_test.py 默认配置
   LMSTUDIO_CONFIG = {
       "type": "openai",
       "name": "lmstudio-local",
       "api_key": "lm-studio",
       "model": "qwen/qwen2.5-7b",  # 根据实际模型名修改
       "base_url": "http://localhost:1234/v1",
       "timeout_s": 300,
   }
   ```

**模型名格式**：LM Studio 使用 `vendor/model-id` 格式（如 `qwen/qwen2.5-7b`）。在 LM Studio 界面 "Model" 下拉框中查看完整名称。

### Ollama

```bash
# 1. 安装 Ollama
# https://ollama.com/download

# 2. 拉取模型
ollama pull qwen2.5:7b

# 3. 确认运行
curl http://localhost:11434/api/tags
# 应返回模型列表
```

Ollama 配置需修改 `interactive_test.py`：
```python
OLLAMA_CONFIG = {
    "type": "local",
    "name": "ollama-local",
    "base_url": "http://localhost:11434",
    "model": "qwen2.5:7b",
}
```

### OpenAI / Kimi / DeepSeek

```bash
# 设置环境变量
export OPENAI_API_KEY=sk-xxx
export OPENAI_BASE_URL=https://api.moonshot.cn/v1  # Kimi
# 或 export OPENAI_BASE_URL=https://api.deepseek.com/v1
```

修改配置：
```python
CLOUD_CONFIG = {
    "type": "openai",
    "name": "kimi-cloud",
    "api_key": os.getenv("OPENAI_API_KEY"),
    "model": "kimi-latest",
    "base_url": os.getenv("OPENAI_BASE_URL"),
    "timeout_s": 60,
}
```

---

## 运行交互式 Agent

```bash
python interactive_test.py
```

输出示例：
```
======================================================================
  MemoryGraph Agent — Interactive Mode
  LLM-backed conversation with full pipeline tracing
  Type /exit to quit, /help for commands
======================================================================
  ✅ LLM connected: qwen/qwen2.5-7b

  Agent ready. Start typing...

👤 你是谁

  ──────────────────────────────────────────────────────────────────
  [Turn #1] User: 你是谁
  ──────────────────────────────────────────────────────────────────
  [PCR (Layer 0)]
    expectation: COMPANION
    confidence: 0.320
    noise: 0.200
    complexity: 0.072
    latency_ms: 3.000
  [Intent Parser (Layer 1)]
    category: chitchat
    confidence: 0.480
    entities: 0
    ambiguities: 0
    actionable: ✅
    latency_ms: 2.000
  [Expertise Probe]
    raw_score: 0.140
    is_llm: ❌
    reason: rule_based_cold_start
  [Adaptive Threshold]
    threshold: 0.400
    mean: 0.000
    variance: 1.000
  [LLM Response] 45 tokens generated

🤖 我是 MemoryGraph Agent，一个智能助手。我可以帮你进行意图识别、任务分析、代码调试等。请问有什么可以帮你的？

👤 我们的第一个对话是什么

🤖 你刚才问的是"你是谁"。
```

**内置命令**：
| 命令 | 作用 |
|------|------|
| `/exit`, `/quit`, `/q` | 退出 |
| `/status` | 显示会话状态（轮数、GP 观测数） |
| `/history` | 显示对话历史 |
| `/reset` | 清空会话（历史、ParseContext、AdaptiveThreshold） |
| `/pipeline` | 开关 pipeline 调试显示 |
| `/save` | 保存对话日志到 JSON |

---

## 运行测试

```bash
# 核心测试（Layer 0-1）
python -m pytest core/agent -v

# 特定模块
python -m pytest core/agent/pcr/tests -v
python -m pytest core/agent/tests/test_expertise_probe.py -v
python -m pytest core/agent/tests/test_adaptive_threshold.py -v
python -m pytest core/agent/tests/test_intent_rule_registry.py -v

# 预期：700+ passed, 0 failed
```

---

## 常见问题

### Q: 模型回复 "抱歉，我无法访问之前的对话历史"

**A**: 这是 thinking 模型（如 qwen3.5-9b）的**自我审查**行为。解决方案：
1. 切换到非 thinking 模型（`qwen2.5-7b` / `qwen2.5-14b`）
2. 在 LM Studio 的 "Chat Settings" 中调整：
   - Temperature: 0.3-0.6
   - Repeat Penalty: 1.05-1.15（抑制自我审查循环）

### Q: 回复被截断（显示 "[回复被截断]"）

**A**: 
1. 增加 `max_tokens`（如 `4096`）
2. 或切换非 thinking 模型（thinking 模型的 `reasoning_tokens` 与 `content` 共享 token 预算）

### Q: "timeout" 错误

**A**: 
1. 检查 LM Studio 是否已启动 Local Server
2. 检查模型是否已加载（绿色状态）
3. 增加 `timeout_s`（默认 300 秒，thinking 模型可能需要更久）

### Q: 连接成功但无响应

**A**: 
1. 检查模型名是否带 `vendor/` 前缀（如 `qwen/qwen2.5-7b` 而非 `qwen2.5-7b`）
2. 检查 LM Studio 的 "Chat Settings" 中 "Context Length" 是否足够（建议 4096+）

### Q: 中文分词慢（"Loading model cost 0.6 seconds"）

**A**: 正常现象，jieba 首次加载词典。后续调用复用缓存。可在 `~/.jieba` 查看缓存文件。

---

## 下一步

- [docs/LLM_PROVIDER_GUIDE.md](LLM_PROVIDER_GUIDE.md) — 深入了解所有 Provider 配置
- [docs/architecture/ARCHITECTURE.md](architecture/ARCHITECTURE.md) — 理解内部架构和数据流
- `examples/minimal_agent.py` — 3 行代码集成到自己的项目

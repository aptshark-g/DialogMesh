# LLM Provider 配置指南

> 所有支持的 LLM Provider 配置参数、使用场景和故障排查。

---

## 支持的 Provider

| Provider | 类型 | 适用场景 | 速度 | 质量 | 隐私 |
|----------|------|----------|------|------|------|
| **OpenAIProvider** | 云端 API | 生产环境、高可用 | 快 | 高 | 低（数据出域） |
| **LocalProvider** | 本地 HTTP | 本地测试、隐私敏感 | 中 | 中 | 高（完全本地） |
| **HybridRouter** | 路由层 | 成本优化、降级保障 | 自适应 | 自适应 | 混合 |
| **MockProvider** | 本地 Mock | 单元测试、离线开发 | 极快 | 固定 | 最高 |

---

## OpenAIProvider（云端 + 兼容端点）

支持：OpenAI、Kimi（Moonshot）、DeepSeek、Qwen API、AnyScale、LM Studio Local Server 等所有兼容 OpenAI SDK 的端点。

### 配置参数

```python
{
    "type": "openai",          # 固定
    "name": "my-provider",     # 自定义名称（用于日志和指标）
    "api_key": "sk-xxx",       # API Key（LM Studio 可填任意字符串）
    "model": "gpt-4o-mini",    # 模型 ID
    "base_url": "https://api.openai.com/v1",  # 自定义 Base URL
    "max_retries": 2,          # 最大重试次数（默认 2）
    "timeout_s": 30,          # HTTP 连接/读取超时（默认 30s）
}
```

### 常见端点配置

```python
# OpenAI
openai_config = {
    "type": "openai", "name": "openai",
    "api_key": os.getenv("OPENAI_API_KEY"),
    "model": "gpt-4o-mini",
    "base_url": "https://api.openai.com/v1",
}

# Kimi (Moonshot)
kimi_config = {
    "type": "openai", "name": "kimi",
    "api_key": os.getenv("KIMI_API_KEY"),
    "model": "kimi-latest",
    "base_url": "https://api.moonshot.cn/v1",
}

# DeepSeek
deepseek_config = {
    "type": "openai", "name": "deepseek",
    "api_key": os.getenv("DEEPSEEK_API_KEY"),
    "model": "deepseek-chat",
    "base_url": "https://api.deepseek.com/v1",
}

# LM Studio（本地）
lmstudio_config = {
    "type": "openai", "name": "lmstudio",
    "api_key": "lm-studio",  # 任意字符串
    "model": "qwen/qwen2.5-7b",  # 必须带 vendor/ 前缀
    "base_url": "http://localhost:1234/v1",
    "timeout_s": 300,  # 本地模型慢，需要更长超时
}
```

### 特性：Thinking 模型兼容

OpenAIProvider 自动检测 `reasoning_content` 字段（Qwen 3.5、DeepSeek-R1 等 thinking 模型）：

- 如果 `content` 为空但 `reasoning_content` 有内容，自动从 reasoning 中提取最终回复
- 支持多种标记："Final Response:", "最终回复：", "Step 6", 等
- 如果 `finish_reason == "length"` 且 reasoning 占用大部分 token，提示用户切换非 thinking 模型或增加 max_tokens

**注意**：Thinking 模型会共享 `max_tokens` 预算（reasoning + content）。建议：
- 非 thinking 模型：`max_tokens=512`（足够）
- Thinking 模型：`max_tokens=2048+`（预留 reasoning 空间）

---

## LocalProvider（Ollama / llama.cpp）

原生异步实现，支持流式响应（SSE）。

### 配置参数

```python
{
    "type": "local",           # 固定
    "name": "ollama-local",    # 自定义名称
    "base_url": "http://localhost:11434",  # Ollama 默认端口
    "model": "qwen2.5:7b",     # Ollama 模型名
}
```

### 流式响应

```python
# LocalProvider 原生支持 async 流式
result = await provider.generate_async(request, stream=True)
# 逐 token 返回，适合前端实时显示
```

---

## HybridRouter（延迟/成本感知路由）

根据输入特征自动选择最优 Provider：

```python
from core.agent.llm_providers.hybrid_router import HybridRouter

router = HybridRouter([
    openai_provider,    # 云端：高质量、高成本
    local_provider,    # 本地：低成本、高延迟
    mock_provider,     # Mock：零成本、用于测试
])

# 自动决策：
# - 简单查询（<20 字符）→ Mock（固定回复）
# - 标准查询 → Local（成本优先）
# - 复杂查询 / Local 超时 → OpenAI（质量优先）
result = router.generate(request)
```

---

## MockProvider（测试/离线）

```python
from core.agent.llm_providers.mock_provider import MockProvider

mock = MockProvider("mock", {})
mock.set_response("默认回复")

# 测试中：
# - 零延迟
# - 固定输出（可配置）
# - 不消耗 API Key
```

---

## ProviderFactory（统一入口）

```python
from core.agent.llm_providers.provider_factory import ProviderFactory

# 从配置字典自动创建对应 Provider
provider = ProviderFactory.from_config({
    "type": "openai",
    "name": "lmstudio-local",
    "api_key": "lm-studio",
    "model": "qwen/qwen2.5-7b",
    "base_url": "http://localhost:1234/v1",
    "timeout_s": 300,
})

# 返回类型：OpenAIProvider / LocalProvider / MockProvider
```

---

## GenerateRequest 参数

```python
from core.agent.llm_providers.base import GenerateRequest

req = GenerateRequest(
    prompt="用户输入...",              # 单条消息内容（如果 messages 为空）
    system_prompt="你是 AI 助手...",  # 系统提示词（可选）
    messages=[                        # 标准 OpenAI Chat messages 列表（优先）
        {"role": "system", "content": "你是 AI 助手..."},
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好！"},
        {"role": "user", "content": "你是谁"},
    ],
    max_tokens=512,                   # 最大输出 token（含 reasoning）
    temperature=0.3,                   # 0=确定性，1=创意性
    timeout_ms=30000,                  # 调用超时（ms）
    response_format="json",           # "json" | "text"（默认）
)
```

**注意**：`messages` 和 `prompt` 二选一。如果 `messages` 非空，使用标准 Chat 格式；否则用 `prompt` 构建单条 `user` 消息。

---

## 故障排查

| 现象 | 可能原因 | 解决方案 |
|------|----------|----------|
| `timeout` | 模型未加载 / 端点错误 | 检查 LM Studio/Ollama 状态，确认端口 |
| `connection refused` | 服务端未启动 | 启动 Local Server 或 Ollama |
| `model not found` | 模型名错误 | 确认带 `vendor/` 前缀（如 `qwen/qwen2.5-7b`） |
| `bad request` / `invalid` | `response_format=json` 不支持 | OpenAIProvider 会自动重试（去掉 response_format） |
| 回复被截断 | max_tokens 不足 | 增加 max_tokens（thinking 模型需 2048+） |
| 思考过程泄露 | thinking 模型标记提取失败 | 检查模型是否支持 `reasoning_content` 字段 |
| 中文乱码 | 终端编码问题 | Windows 用 `chcp 65001`，或重定向到文件 |

---

## 性能调优

| 场景 | 推荐配置 |
|------|----------|
| 本地测试（LM Studio） | `temperature=0.3`, `max_tokens=2048`, `timeout_s=300` |
| 生产环境（OpenAI） | `temperature=0.3`, `max_tokens=512`, `timeout_s=30` |
| 意图分类（轻量） | `temperature=0.0`, `max_tokens=128`, `timeout_s=10` |
| 中文对话 | `temperature=0.3-0.6`, `Repeat Penalty=1.05-1.15`（LM Studio） |
| 代码生成 | `temperature=0.2`, `max_tokens=1024` |

---

## 下一步

- [QUICKSTART.md](QUICKSTART.md) — 从零到运行
- [ARCHITECTURE.md](ARCHITECTURE.md) — 理解内部架构

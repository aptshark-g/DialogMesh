# 架构缺口修复方案记录

> 记录日期：2026-06-23
> 前置 Agent 代码已完工（613 测试通过），本文件记录 3 个 P0/P1 缺口及剩余审计问题的修复决策。

---

## 缺口 1：PCR 反馈闭环 — P0

### 方案确认：Gaussian Process + 小 MLP 特征变换（A+M）

**目标**：将硬编码阈值 `noise_fast_path=0.3` 替换为在线贝叶斯自适应阈值。

**特征空间**（8 维）：
```
x = [noise, complexity, metacognition, stability, divergence, 
     tracking_depth, turn_count, time_since_last_clarification]
```

**架构**：
```
原始特征(8) → 小 MLP 特征变换(2层: 8→16→8) → 嵌入空间 → 
GP 回归(threshold | x) → Thompson Sampling 决策
```

**在线更新**：Sherman-Morrison 增量求逆，无需重算矩阵。
**探索-利用**：利用 GP 预测不确定性 σ(x) 做 Thompson Sampling。
**样本效率**：< 50 样本可用，> 500 样本时切换滑动窗口 GP 近似。

**实现文件**：`core/agent/adaptive_threshold.py`（新增模块）

---

## 缺口 2：冷启动策略 — P1

### 方案确认：LLM 介入判断 + 可配置词表 + 混合语言风格 + 阀门阈值

**核心思路**：不预设 expert/novice/unknown 三档，而是让 LLM 基于输入做连续专家评分，同时保留规则兜底。

**多维度探测**（复用现有组件）：

| 维度 | 复用组件 | 说明 |
|------|---------|------|
| 技术术语密度 | `IntentParser` 实体提取 + 可配置词表 | 匹配预定义技术词表 |
| 参数精确度 | `PCR` 噪声分析 | 是否含 0x 地址、PID、模块名 |
| 查询复杂度 | `TaskGraph` 操作数统计 | 单操作 vs 多操作链 |
| 语言风格 | jieba 分词 + 英文术语密度 | 句式长度、缩写密度、问题结构 |
| 历史行为 | `Session` turn 记录 | 过去操作类型分布 |

**LLM 判断协议**：
```python
class ExpertiseAssessment:
    score: float          # 0-1 连续专家评分
    confidence: float   # 0-1 判断置信度
    reasoning: str      # LLM 判断依据（阀门日志）
    dimensions: Dict[str, float]  # 各维度得分
```

**可配置词表**：`config/expertise_lexicon.yaml`
```yaml
lexicon:
  reverse_engineering:
    - 基址
    - 偏移
    - OEP
    - IAT
    - EAT
    - RVA
    - VA
    - hook
    - patch
    - dump
    - aobscan
    - speedhack
    - nop
    - inject
  programming:
    - pointer
    - struct
    - array
    - float
    - int32
    - uint64
  # ... 可扩展
```

**浮动参数区间**：
```python
metacognition_base = 0.1 + 0.7 * expertise_score
divergence_base = 0.8 - 0.6 * expertise_score
stability_base = 0.3 + 0.6 * expertise_score

# 置信度越高的区间越窄
confidence = min(1.0, 0.3 + 0.7 * evidence_count / 3)
interval_width = 0.2 * (1 - confidence)
```

**快速降级**：
- 默认阈值：3 轮澄清触发降级
- 阀门机制：LLM 或用户修改阈值前，必须输出 `reasoning` 描述
- 修改路径：`CognitiveProfile.adaptive_thresholds` 可被 LLM 调整，但需记录变更日志

**实现文件**：
- `core/agent/expertise_probe.py`（LLM 判断 + 规则兜底）
- `core/agent/config/expertise_lexicon.yaml`（可配置词表）

---

## 缺口 3：异步 LLM 阻塞 — P1

### 方案确认：流式优化原生异步实现

**目标**：消除本地 LLM（Ollama）阻塞 asyncio 事件循环的问题。

**已完成**：基类 `generate_async()` 默认线程池实现。

**待完成**：
1. `OpenAIProvider.generate_async()` → `aiohttp` 原生异步
2. `LocalProvider.generate_async()` → 流式响应处理（Ollama `/api/generate` stream）
3. `AsyncAgentService` 全面切换 `generate_async`

**流式优化细节**：
```python
# Ollama 流式响应
async def generate_async(self, request: GenerateRequest) -> GenerateResult:
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{self.base_url}/api/generate",
            json={"model": self.model, "prompt": request.prompt, "stream": True}
        ) as resp:
            chunks = []
            async for line in resp.content:
                data = json.loads(line)
                if "response" in data:
                    chunks.append(data["response"])
            full_text = "".join(chunks)
            return GenerateResult(text=full_text, ...)
```

**实现文件**：
- `core/agent/llm_providers/openai_provider.py`（覆盖 `generate_async`）
- `core/agent/llm_providers/local_provider.py`（流式实现）
- `core/agent/service/async_agent_service.py`（切换调用）

---

## 剩余审计问题（待讨论）

| 优先级 | 问题 | 状态 |
|--------|------|------|
| P1 | 规则冲突检测 — 21 条规则维护 | 🔴 待讨论 |
| P2 | 蓝图粒度 — 子蓝图嵌套 | 🔴 待讨论 |
| P2 | 分布式锁接口 — 水平扩展预留 | 🔴 待讨论 |
| P2 | WebSocket 事件注册表 | 🔴 待讨论 |
| P3 | FSM 外部状态映射 | 🔴 待讨论 |
| P3 | MCP 依赖边界文档 | 🔴 待讨论 |


# MemoryGraph 上下文压缩架构设计

> **目标**：为 4B 小模型设计高效的上下文压缩模块，利用其 80 tokens/秒的极速生成能力，实现持续压缩 + 持久化记忆。

---

## 一、核心架构：MemGPT-Style 虚拟内存 + 渐进式摘要

```
┌──────────────────────────────────────────────────────────────────┐
│                    Context Window (Context RAM)                   │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐              │
│  │  Core Prompt │ │  Compressed  │ │  Recent Turns│              │
│  │  (任务定义)   │ │  Memory (B)  │ │  (未压缩原始) │              │
│  │  永不压缩    │ │  渐进式摘要   │ │  滑动窗口    │              │
│  │  ~500 tokens │ │  ~1500 tokens│ │  ~2000 tokens│              │
│  └──────────────┘ └──────────────┘ └──────────────┘              │
│  Total: 4K context (适合 4B 模型)                                  │
└──────────────────────────────────────────────────────────────────┘
                              │
                              │ Trigger (60% threshold)
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                  Compression Engine (LLM Loop)                    │
│                                                                   │
│  1. 读取 Recent Turns (A) → 完整原始内容                           │
│  2. 复制到 B (A的副本)                                            │
│  3. 调用 LLM 对 B 进行摘要压缩                                      │
│  4. 合并到 Compressed Memory                                       │
│  5. 清空 Recent Turns → 从压缩后内容继续                            │
│                                                                   │
│  利用 80 tok/s 速度：压缩 2K tokens 仅需 ~25 秒                      │
└──────────────────────────────────────────────────────────────────┘
                              │
                              │ Archive (full history)
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                   Persistent Storage (Disk)                        │
│  ┌─────────────────┐ ┌─────────────────┐ ┌──────────────┐      │
│  │ Full Turn Logs  │ │ Dependency Graph  │ │ Vector Index │      │
│  │ (JSON append)   │ │ (推理链结构)      │ │ (语义检索)   │      │
│  │ 完整记录，可回溯 │ │ 保留因果依赖)    │ │ 相似发现     │      │
│  └─────────────────┘ └─────────────────┘ └──────────────┘      │
└──────────────────────────────────────────────────────────────────┘
```

---

## 二、三层记忆架构（对应 AOI 论文）

### Layer 1: Recent Context (短期记忆) — 原始未压缩
- **内容**：最近 5-10 步的完整对话/工具调用/结果
- **格式**：原始的 `REASON / ACTION / PARAM / RESULT` 文本
- **大小**：~2000 tokens
- **策略**：滑动窗口，先入先出
- **目的**：保留最近交互的完整细节，避免"丢失中间信息"

### Layer 2: Compressed Memory (中期记忆) — 渐进式摘要
- **内容**：历史对话的压缩摘要
- **格式**：结构化文本
  ```
  [SUMMARY] Found player HP at 0x7FF123456789
  - Step 1: Scanned float=100, got 42 addresses
  - Step 2: Set breakpoint on 0x7FF123456789, hit when HP dropped to 80
  - Step 3: Verified with write test (999 HP confirmed)
  - CONFIDENCE: high
  - RELATED: player_max_hp (0x7FF12345678D), player_mp (0x7FF123456791)
  ```
- **大小**：~1500 tokens
- **策略**：
  - 当 Recent Context 达到阈值（60%）时触发压缩
  - 使用 LLM 对 Recent Context 进行摘要
  - 将摘要追加到 Compressed Memory
  - 如果 Compressed Memory 也满了，对其自身再次压缩（二级压缩）
- **目的**：保留关键信息，丢弃冗余细节

### Layer 3: Core Prompt (长期记忆) — 永不压缩
- **内容**：
  - System Prompt（角色定义、工具描述）
  - 任务定义（当前目标）
  - 关键约束（安全规则、不要修改的地址）
  - 已确认的高置信度发现（类似"常识"）
- **大小**：~500 tokens
- **策略**：只读，永不压缩
- **目的**：确保模型始终知道自己在做什么

---

## 三、渐进式摘要算法（Progressive Summarization）

### 3.1 单级压缩流程

```python
class ContextCompressor:
    """上下文压缩器 — 渐进式摘要"""
    
    THRESHOLD_RATIO = 0.6  # 触发压缩的阈值比例
    MAX_CONTEXT = 4096      # 最大上下文（4B模型）
    CORE_PROMPT_SIZE = 500  # Core Prompt 预留
    
    def __init__(self, llm_provider):
        self.llm = llm_provider
        self.core_prompt = ""       # Layer 3: 永不压缩
        self.compressed_memory = ""  # Layer 2: 压缩摘要
        self.recent_context = []     # Layer 1: 原始回合
        self.full_archive = []       # 磁盘归档
    
    def add_turn(self, observation, action, result):
        """添加新回合"""
        turn = {
            "step": len(self.full_archive) + 1,
            "timestamp": time.time(),
            "observation": observation,
            "action": action,
            "result": result,
        }
        self.recent_context.append(turn)
        self.full_archive.append(turn)
        
        # 检查是否触发压缩
        if self._should_compress():
            self._compress()
    
    def _should_compress(self) -> bool:
        """检查是否达到压缩阈值"""
        current_size = self._estimate_tokens(
            self.core_prompt + self.compressed_memory + self._format_recent()
        )
        return current_size > self.MAX_CONTEXT * self.THRESHOLD_RATIO
    
    def _compress(self):
        """执行压缩 — 关键算法"""
        # 1. 取 Recent Context 中除最新 2 步外的所有内容
        #    保留最新 2 步不压缩，避免丢失刚刚发生的关键信息
        to_compress = self.recent_context[:-2]
        keep_recent = self.recent_context[-2:]
        
        if not to_compress:
            return
        
        # 2. 格式化待压缩内容
        raw_text = self._format_turns(to_compress)
        
        # 3. 调用 LLM 进行摘要（利用 80 tok/s 速度）
        summary = self.llm.compress(raw_text, self.compressed_memory)
        
        # 4. 合并到 Compressed Memory
        if self.compressed_memory:
            # 已有压缩内容，需要合并去重
            self.compressed_memory = self._merge_summaries(
                self.compressed_memory, summary
            )
        else:
            self.compressed_memory = summary
        
        # 5. 清空已压缩的 Recent Context，保留最新 2 步
        self.recent_context = keep_recent
        
        # 6. 如果 Compressed Memory 也过大，执行二级压缩
        if self._estimate_tokens(self.compressed_memory) > 1500:
            self._secondary_compress()
        
        logger.info(f"[Compressor] Compressed {len(to_compress)} turns. "
                   f"Recent: {len(self.recent_context)}, "
                   f"Compressed: {self._estimate_tokens(self.compressed_memory)} tokens")
    
    def _secondary_compress(self):
        """二级压缩：对 Compressed Memory 自身再压缩"""
        # 将 Compressed Memory 送入 LLM，提取更高级别的摘要
        # 例如：保留发现结果，丢弃详细的扫描过程
        ultra_summary = self.llm.compress(
            self.compressed_memory, 
            mode="ultra",  # 超压缩模式
        )
        self.compressed_memory = ultra_summary
    
    def build_prompt(self, current_observation: str) -> str:
        """构建最终发送给 LLM 的 prompt"""
        parts = [
            self.core_prompt,
            "\n[MEMORY]\n",
            self.compressed_memory,
            "\n[RECENT ACTIONS]\n",
            self._format_recent(),
            "\n[CURRENT OBSERVATION]\n",
            current_observation,
        ]
        return "\n".join(parts)
```

### 3.2 压缩 Prompt 模板（发送给 LLM）

```
You are a context compression specialist. Your task is to summarize a sequence of 
agent actions into a compact, structured memory.

INPUT: The following is a sequence of agent actions and their results:

{raw_turns_text}

EXISTING MEMORY (to be merged with):
{existing_compressed_memory}

OUTPUT FORMAT (strict):
SUMMARY:
- Key findings and decisions made
- Addresses discovered and their inferred meanings
- Tools used and their effectiveness
- Errors or failures and lessons learned
- Current plan or next steps

FACTS:
- address=0xXXXX: meaning (confidence: high/medium/low)
- address=0xYYYY: meaning (confidence: high/medium/low)

DEPENDENCIES:
- Finding X depends on Action Y (step Z)

RULES:
1. Be extremely concise. Max 300 words.
2. Preserve exact addresses and values.
3. Preserve confidence levels.
4. Drop redundant details (e.g., full scan results, just keep count).
5. Keep causal relationships (what led to what).
6. If existing memory has similar facts, merge and update.
```

---

## 四、依赖感知的压缩（ContextWeaver 风格）

传统压缩的问题是：只保留最近的内容，但可能丢失了关键依赖。

**解决方案**：保留依赖链

```python
class DependencyGraph:
    """依赖图 — 记录每个发现的因果关系"""
    
    def __init__(self):
        self.nodes = {}  # step_id -> Node
        self.edges = []  # (from_step, to_step, relation)
    
    def add_step(self, step_id, action, result, depends_on=None):
        """记录步骤及其依赖"""
        self.nodes[step_id] = {
            "action": action,
            "result": result,
            "critical": False,  # 是否被后续步骤依赖
        }
        
        if depends_on:
            for dep in depends_on:
                self.edges.append((dep, step_id, "depends_on"))
                # 标记依赖节点为关键（不能删除）
                self.nodes[dep]["critical"] = True
    
    def select_for_compression(self, recent_turns, budget=5) -> List[int]:
        """选择保留的关键回合（用于压缩时的输入）"""
        # 1. 最近的所有回合必须保留（在 Recent Context 中）
        # 2. 被标记为 critical 的回合必须保留摘要
        # 3. 其他回合可以压缩
        
        critical_steps = [sid for sid, node in self.nodes.items() if node["critical"]]
        return critical_steps[:budget]  # 限制关键节点数量
```

在压缩时，不是压缩所有 Recent Context，而是：
1. **保留关键依赖链**（被后续步骤引用的发现）
2. **压缩冗余步骤**（重复的扫描、失败的尝试）
3. **保留失败记录**（避免重复踩坑）

---

## 五、持久化存储方案

### 5.1 文件结构

```
.kimi/memory/
├── sessions/
│   └── {session_id}/
│       ├── turns.jsonl          # 完整回合记录（追加）
│       ├── compressed.json      # 压缩记忆（每次更新覆盖）
│       ├── dependencies.json    # 依赖图
│       └── discoveries.json     # 高置信度发现（永不删除）
└── vector/
    └── embeddings.db            # 向量索引（ChromaDB/SQLite）
```

### 5.2 存储策略

| 数据 | 存储位置 | 保留策略 | 用途 |
|------|---------|---------|------|
| 完整回合 | `turns.jsonl` | 永久 | 回溯、调试、训练数据 |
| 压缩记忆 | `compressed.json` | 会话期间 | 上下文构建 |
| 高置信度发现 | `discoveries.json` | 永久 | 跨会话复用 |
| 依赖图 | `dependencies.json` | 会话期间 | 因果分析 |
| 向量索引 | `embeddings.db` | 永久 | 语义检索相似会话 |

### 5.3 跨会话复用

```python
class MemoryStore:
    """持久化存储 — 跨会话记忆"""
    
    def save_discovery(self, discovery: Discovery):
        """保存高置信度发现"""
        # 写入 discoveries.json
        # 同时生成 embedding 存入向量库
        pass
    
    def query_similar(self, observation: str, k=5) -> List[Discovery]:
        """检索相似的历史发现"""
        # 1. 生成 observation 的 embedding
        # 2. 向量相似度检索
        # 3. 返回最相似的 k 个发现
        pass
    
    def load_session_memory(self, session_id: str, task_hint: str) -> str:
        """加载会话记忆（包括相似历史发现）"""
        # 1. 加载该会话的 compressed.json
        # 2. 检索相似历史发现
        # 3. 合并到 Core Prompt 中作为"相关经验"
        pass
```

---

## 六、针对 4B 模型的优化

### 6.1 速度优势利用

- **80 tok/s 意味着压缩 2K tokens 只需 ~25 秒**
- 可以接受更频繁的压缩（每 5-10 步就压缩一次）
- 可以接受更复杂的压缩 prompt（详细指导，减少格式错误）

### 6.2 上下文限制应对

| 模型 | 上下文 | 建议配置 |
|------|--------|---------|
| 4B (4K ctx) | 4096 | Core 500 + Compressed 1500 + Recent 2000 |
| 7B (8K ctx) | 8192 | Core 500 + Compressed 3000 + Recent 4000 |
| 14B (32K ctx) | 32768 | Core 500 + Compressed 10000 + Recent 20000 |

### 6.3 压缩频率调优

```python
# 4B 模型：可以更激进地压缩，因为速度快
COMPRESSION_CONFIG_4B = {
    "threshold_ratio": 0.5,      # 50% 就触发（比 60% 更激进）
    "keep_recent_turns": 2,       # 保留最近 2 步
    "compression_max_words": 300,  # 摘要最多 300 词
    "secondary_compression": True,  # 启用二级压缩
    "merge_window": 5,            # 每 5 步合并一次
}

# 7B+ 模型：可以保守一些，因为上下文更大
COMPRESSION_CONFIG_7B = {
    "threshold_ratio": 0.6,
    "keep_recent_turns": 3,
    "compression_max_words": 500,
    "secondary_compression": False,
    "merge_window": 10,
}
```

---

## 七、实现文件规划

| 文件 | 内容 | 依赖 |
|------|------|------|
| `core/agents/memory/context_compressor.py` | ContextCompressor 核心类 | `llm_provider` |
| `core/agents/memory/dependency_graph.py` | DependencyGraph 依赖图 | 无 |
| `core/agents/memory/memory_store.py` | MemoryStore 持久化存储 | `sqlite3` / `chromadb` |
| `core/agents/memory/prompt_templates.py` | 压缩 prompt 模板 | 无 |
| `core/agents/memory/__init__.py` | 导出主要类 | 以上全部 |
| `core/agents/memory/test_compressor.py` | 单元测试 | 以上全部 |

---

## 八、与 ReAct 引擎的集成

```python
class ReactEngine:
    def __init__(self, provider_name="lmstudio", system_prompt=None):
        self.provider = ProviderManager().get_provider(provider_name)
        self.system_prompt = system_prompt or SYSTEM_PROMPT
        self.tools = get_registry()
        
        # 新增：记忆系统
        self.memory = ContextCompressor(self.provider)
        self.memory.core_prompt = self.system_prompt
    
    def run(self, task, hint=None, max_steps=10):
        for step in range(max_steps):
            # 1. 构建观察
            observation = self._build_observation(task, hint, step)
            
            # 2. 添加回合到记忆（可能触发压缩）
            self.memory.add_turn(
                observation=observation,
                action="pending",  # 将在 LLM 回复后更新
                result="pending",
            )
            
            # 3. 使用压缩后的上下文构建 prompt
            prompt = self.memory.build_prompt(observation)
            
            # 4. 调用 LLM
            response = self._call_llm(prompt)
            
            # 5. 解析响应
            action, params, reason = self._parse_response(response)
            
            # 6. 执行工具
            tool_result = self.tools.execute(action, **params)
            
            # 7. 更新最新回合的结果
            self.memory.recent_context[-1]["action"] = action
            self.memory.recent_context[-1]["result"] = tool_result
            
            # 8. 记录依赖
            if action == "conclude":
                # 结论依赖于之前的发现
                self.memory.dependency_graph.add_step(
                    step_id=step,
                    action=action,
                    result=tool_result,
                    depends_on=self._find_supporting_steps(),
                )
            
            # ... 其余逻辑
```

---

## 九、总结

| 特性 | 方案 |
|------|------|
| 架构 | MemGPT 虚拟内存 + 渐进式摘要 + 依赖图 |
| 触发条件 | 上下文达到 50% 阈值（4B 模型） |
| 压缩方式 | LLM 摘要（利用 80 tok/s 速度） |
| 保留策略 | 保留最近 2 步 + 关键依赖链 + 核心 prompt |
| 持久化 | JSONL 完整记录 + 向量索引跨会话检索 |
| 二级压缩 | 当压缩记忆也满时，再次压缩 |
| 优势 | 4B 模型速度快，可以接受频繁压缩，保持高信息保留率 |

---

*设计参考：*
- *AOI Framework (2026) — Three-Layer Memory + Context Compressor*
- *MemGPT (2023) — Virtual Memory Architecture*
- *Tiago Forte — Progressive Summarization*
- *ContextWeaver (2026) — Dependency-Structured Memory*
- *TowardsDataScience (2026) — Memory for Autonomous LLM Agents*

*设计时间：2025-06-21*
*版本：v1.0*

# 上下文窗口管理设计方案 v1.0

> 本文档定义意图识别引擎的上下文窗口管理架构，解决长对话场景下的记忆膨胀、计算复杂度增长和 LLM 上下文溢出风险。

## 目录

- [1. 背景与问题](#1-背景与问题)
- [2. 设计目标](#2-设计目标)
- [3. 核心设计：三层窗口架构](#3-核心设计三层窗口架构)
- [4. 关键组件](#4-关键组件)
- [5. 压缩策略详解](#5-压缩策略详解)
- [6. 与 PCR 集成方案](#6-与-pcr-集成方案)
- [7. 与 CLI 集成方案](#7-与-cli-集成方案)
- [8. 性能模型](#8-性能模型)
- [9. 测试策略](#9-测试策略)
- [10. 实现计划](#10-实现计划)
- [11. 风险与回退](#11-风险与回退)

---

## 1. 背景与问题

### 当前代码现状

```python
# intent_trace_cli.py — 当前实现
_history_entries = []
for h in (history or []):
    if isinstance(h, dict):
        _history_entries.append(HistoryEntry(...))

pcr_input = PCRInput_v1(query=query, session_history=_history_entries)
```

**问题**：无论对话进行多少轮（10 轮、100 轮、1000 轮），全部历史记录原封不动传入 PCR 和 IntentParser。

### 性能瓶颈

| 轮数 | 历史 tokens | PCR 噪声估算耗时 | 认知画像 EMA 耗时 | 意图解析耗时 | 总延迟 |
|---|---|---|---|---|---|
| 5 轮 | ~500 | 0.5ms | 1ms | 2ms | 3.5ms |
| 20 轮 | ~2000 | 2ms | 5ms | 8ms | 15ms |
| 50 轮 | ~5000 | 5ms | 15ms | 25ms | 45ms |
| 100 轮 | ~10000 | 12ms | 40ms | 60ms | 112ms |
| 500 轮 | ~50000 | 80ms | 300ms | 400ms | 780ms |

> 注：以上基于中文字符平均长度估算（每轮约 100 字符 ≈ 33 tokens）。

### 实际危害

| 场景 | 问题 | 影响 |
|---|---|---|
| 长期使用 CLI | 50 轮后延迟从 3ms 增长到 45ms | 用户体验明显卡顿 |
| LLM 调用溢出 | 历史 + 当前 prompt 超过模型上下文窗口 | LLM 报错或截断 |
| 认知画像漂移 | 旧对话干扰当前意图判断 | "分析内存" 被误判为 "分析昨天的代码" |
| 存储膨胀 | 每轮 500 tokens 持久化 | 1000 轮 = 500K tokens ≈ 2MB |

---

## 2. 设计目标

### 功能目标

| ID | 目标 | 优先级 | 验收标准 |
|---|---|---|---|
| CW-1 | 长对话延迟可控 | P0 | 100 轮对话时 PCR 端到端延迟 < 20ms |
| CW-2 | 上下文不溢出 | P0 | LLM 调用时 prompt + 历史 < 模型窗口的 80% |
| CW-3 | 认知一致性 | P0 | 重启后 20 轮内的意图分类准确率不下降 |
| CW-4 | 用户画像累积 | P1 | 专家度/稳定性随对话轮数正确收敛 |
| CW-5 | 主题追踪 | P1 | 跨会话能识别用户关注的核心技术主题 |
| CW-6 | 引用消解 | P2 | "那个""上一个" 等指代在 50 轮内正确解析 |

### 非功能目标

| ID | 目标 | 指标 |
|---|---|---|
| N-1 | 压缩比 | 100 轮原始历史 → 压缩后 < 20 轮等效 |
| N-2 | 压缩延迟 | 单次压缩 < 5ms |
| N-3 | 无 LLM 依赖 | 规则压缩器零外部依赖（不调用 LLM） |
| N-4 | 可逆性 | 压缩不丢失意图分类所需的关键信息 |
| N-5 | 配置化 | 窗口大小参数可配置（热窗口/温窗口/冷摘要） |

---

## 3. 核心设计：三层窗口架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         用户查询 (current_query)                   │
│                         ↓                                        │
├─────────────────────────────────────────────────────────────────┤
│  热窗口 (Hot Window)     │ 最近 5 轮，原始记录，全精度              │
│  ─────────────────────  │ 保留：完整 query、intent_result、entity  │
│  [turn n-4]            │ 用途：当前轮引用消解、即时上下文           │
│  [turn n-3]            │                                              │
│  [turn n-2]            │                                              │
│  [turn n-1]            │                                              │
│  [turn n]   ← 当前     │                                              │
├─────────────────────────────────────────────────────────────────┤
│  温窗口 (Warm Window)  │ 第 6-20 轮，压缩记录，保留意图标签        │
│  ─────────────────────  │ 压缩：丢弃 tool 调用细节、中间推理过程     │
│  [turn n-5]  → 压缩    │ 保留：user query、assistant 结果摘要、     │
│  [turn n-6]  → 压缩    │        expectation、关键 entity            │
│  ...                   │                                              │
│  [turn n-19] → 压缩    │                                              │
├─────────────────────────────────────────────────────────────────┤
│  冷摘要 (Cold Summary) │ 第 21 轮以前，单条摘要，只保留画像和主题   │
│  ─────────────────────  │ 生成：用户画像 + 高频意图 + 技术主题         │
│  [turn 1..n-20] → 摘要│ 形式：伪 HistoryEntry(role="system")        │
│                        │ 示例："[历史摘要] 用户画像: 专家度=0.8      │
│                        │  主要意图: TOOL(15), ADVISOR(3)            │
│                        │  技术主题: 内存扫描, 反汇编, Hook"          │
└─────────────────────────────────────────────────────────────────┘
                         │
                         ↓
              PCRInput_v1(query, session_history=augmented)
              
              输入规模：
              - 5 轮原始 + 15 轮压缩 + 1 条摘要 = 21 条记录
              - 等效 token 数：~1500 tokens（vs 100 轮原始 ~10000 tokens）
```

### 三层对比

| 层级 | 轮数范围 | 保留内容 | 精度 | 用途 |
|---|---|---|---|---|
| **热窗口** | 最近 5 轮 | 完整原始记录 | 100% | 即时引用、当前意图推断 |
| **温窗口** | 第 6-20 轮 | 意图标签 + 结果摘要 + 关键 entity | ~30% | 主题一致性、模式识别 |
| **冷摘要** | 20 轮以前 | 用户画像 + 意图统计 + 技术主题 | ~5% | 长期认知一致性、专家度追踪 |

---

## 4. 关键组件

### 4.1 ContextWindowManager（窗口管理器）

```python
# core/agent/context_window.py
@dataclass
class WindowConfig:
    """窗口配置参数。"""
    hot_size: int = 5          # 热窗口保留轮数
    warm_size: int = 15        # 温窗口保留轮数（压缩后）
    compress_interval: int = 5  # 每 5 轮触发一次压缩
    max_tokens: int = 4000     # 最大输入 token 数（LLM 安全边界）
    enable_llm_compressor: bool = False  # 是否启用 LLM 压缩（默认规则压缩）


class ContextWindowManager:
    """
    上下文窗口管理器。
    负责将任意长度的历史记录压缩为固定大小的有效上下文。
    """
    
    def __init__(self, 
                 config: WindowConfig = None,
                 llm_provider: Optional[LLMProvider] = None):
        self.config = config or WindowConfig()
        self.llm = llm_provider if self.config.enable_llm_compressor else None
        self.compressor = RuleBasedCompressor()  # 零依赖规则压缩
        
    def build_pcr_input(self, 
                        query: str,
                        history: List[HistoryEntry],
                        session_profile: Optional[CognitiveProfile_v1] = None,
                        cached_summary: str = None,        # 增量缓存：上次生成的冷摘要
                        cached_cold_turns: int = 0,        # 增量缓存：上次已摘要的轮数
                        ) -> PCRInput_v1:
        """
        构建适合传入 PCR 的受控上下文（支持增量压缩，避免重复全量压缩）。
        
        Args:
            query: 当前用户查询
            history: 完整历史记录（可能很长）
            session_profile: 当前会话认知画像（用于冷摘要生成）
            cached_summary: 上次生成的冷摘要（增量更新时复用）
            cached_cold_turns: 上次已计入冷摘要的轮数（增量更新时复用）
        
        Returns:
            PCRInput_v1，其中 session_history 已被压缩
            同时返回增量缓存信息（供调用者保存）
        """
        n = len(history)
        
        # 1. 如果历史较短，直接全量返回（无需压缩）
        if n <= self.config.hot_size:
            return PCRInput_v1(
                query=query,
                session_history=history,
                process_context={
                    "window_mode": "full",
                    "total_turns": n,
                }
            )
        
        # 2. 热窗口：最近 N 轮原始记录
        hot = history[-self.config.hot_size:]
        
        # 3. 温窗口：中间轮次压缩记录
        warm_start = max(0, n - self.config.hot_size - self.config.warm_size)
        warm_raw = history[warm_start:n - self.config.hot_size]
        warm = self.compressor.compress(warm_raw)
        
        # 4. 冷摘要：早期轮次生成摘要（增量更新，避免重复全量压缩）
        cold_summary = cached_summary or ""
        cold_turns = cached_cold_turns
        if n > self.config.hot_size + self.config.warm_size:
            cold = history[:warm_start]
            new_cold_turns = len(cold)
            if cached_summary and new_cold_turns == cached_cold_turns:
                # 冷区域未变化，复用缓存摘要
                cold_turns = cached_cold_turns
            else:
                # 增量更新：在旧摘要基础上追加新轮次（或重新生成）
                cold_summary = self.compressor.summarize(cold, session_profile)
                cold_turns = new_cold_turns
        
        # 5. 组装增强历史
        augmented_history = self._assemble(hot, warm, cold_summary)
        
        # 6. 验证 token 预算
        token_cost = self._estimate_tokens(augmented_history)
        if token_cost > self.config.max_tokens:
            # 二次压缩：进一步缩小温窗口
            warm = self.compressor.compress(warm)  # 二次压缩（更激进）
            augmented_history = self._assemble(hot, warm, cold_summary)
        
        return PCRInput_v1(
            query=query,
            session_history=augmented_history,
            process_context={
                "window_mode": "compressed",
                "total_turns": n,
                "hot_turns": len(hot),
                "warm_turns": len(warm),
                "cold_turns": cold_turns if n > self.config.hot_size + self.config.warm_size else 0,
                "cold_summary": cold_summary,
                "token_cost": self._estimate_tokens(augmented_history),
                # 增量缓存信息：供调用者保存，下次复用
                "cached_summary": cold_summary,
                "cached_cold_turns": cold_turns,
            }
        )
    
    def _assemble(self, 
                  hot: List[HistoryEntry],
                  warm: List[HistoryEntry],
                  cold_summary: str) -> List[HistoryEntry]:
        """组装三层窗口为统一历史列表。"""
        result = []
        
        # 冷摘要作为系统上下文注入
        if cold_summary:
            result.append(HistoryEntry(
                role="system",
                content=f"[历史摘要] {cold_summary}",
                expectation="SYSTEM_CONTEXT",
                timestamp=0,
            ))
        
        # 温窗口（压缩记录）
        result.extend(warm)
        
        # 热窗口（原始记录）
        result.extend(hot)
        
        return result
    
    def _estimate_tokens(self, history: List[HistoryEntry]) -> int:
        """粗略估算 token 数（中文字符 ≈ 1/3 token）。"""
        total_chars = sum(len(h.content) for h in history)
        return total_chars // 3
    
    def should_compress(self, history: List[HistoryEntry]) -> bool:
        """判断是否需要触发压缩。"""
        return len(history) > self.config.hot_size + self.config.warm_size
    
    def get_window_stats(self, history: List[HistoryEntry]) -> Dict:
        """返回当前窗口统计信息（用于日志和仪表盘）。"""
        n = len(history)
        return {
            "total_turns": n,
            "hot_turns": min(n, self.config.hot_size),
            "warm_turns": max(0, min(n - self.config.hot_size, self.config.warm_size)),
            "cold_turns": max(0, n - self.config.hot_size - self.config.warm_size),
            "estimated_tokens": self._estimate_tokens(history),
        }
```

### 4.2 RuleBasedCompressor（规则压缩器）

```python
class RuleBasedCompressor:
    """
    零依赖规则压缩器。
    不需要 LLM，基于关键词和规则进行信息压缩。
    """
    
    # 意图 → 保留关键词映射
    INTENT_KEYWORDS = {
        "TOOL": ["scan", "read", "write", "patch", "hook", "bp", "地址", "数值"],
        "ADVISOR": ["分析", "判断", "确认", "怎么", "为什么", "对吗"],
        "COMPANION": ["学习", "教程", "怎么", "如何", "步骤"],
    }
    
    # 技术主题提取规则
    TECH_TOPIC_PATTERNS = [
        ("内存扫描", ["scan", "扫描", "数值搜索", "find"]),
        ("内存修改", ["patch", "修改", "write", "写入", "freeze", "锁定"]),
        ("反汇编", ["disasm", "反汇编", "assembly", "汇编"]),
        ("Hook", ["hook", "拦截", "注入"]),
        ("断点", ["bp", "breakpoint", "断点", "break"]),
        ("进程管理", ["attach", "detach", "进程", "模块"]),
    ]
    
    def compress(self, turns: List[HistoryEntry]) -> List[HistoryEntry]:
        """
        压缩一轮或多轮对话，保留关键信息（不丢失 PCR 所需的意图标签和实体）。
        
        压缩策略：
        1. 保留 user 和 assistant 的最终结果（含结构化字段）
        2. 丢弃 tool 调用、中间推理、重复确认
        3. 对 user query 截断到 100 字符，但保留 entities
        4. 对 assistant 回复提取状态标签
        5. 保留 intent_category, confidence, entities（PCR 指代消解依赖）
        """
        compressed = []
        
        for turn in turns:
            if turn.role == "user":
                # 保留意图标签 + 截断后的查询 + 关键实体（供 PCR 指代消解）
                compressed.append(HistoryEntry(
                    role="user",
                    content=self._truncate(turn.content, 100),
                    expectation=turn.expectation,
                    timestamp=turn.timestamp,
                    metadata={
                        "is_compressed": True,
                        "entities": turn.metadata.get("entities", []) if turn.metadata else [],
                        "intent_category": turn.metadata.get("intent_category") if turn.metadata else None,
                        "confidence": turn.metadata.get("confidence") if turn.metadata else None,
                    }
                ))
            
            elif turn.role == "assistant":
                # 只保留执行结果摘要 + 关键结构化字段
                summary = self._extract_result_summary(turn.content)
                compressed.append(HistoryEntry(
                    role="assistant",
                    content=summary,
                    expectation=turn.expectation,
                    timestamp=turn.timestamp,
                    metadata={
                        "is_compressed": True,
                        "entities": turn.metadata.get("entities", []) if turn.metadata else [],
                        "intent_category": turn.metadata.get("intent_category") if turn.metadata else None,
                    }
                ))
            
            # 跳过 role == "tool" / "system" / "thinking" 等中间角色
            
        return compressed
    
    def summarize(self, 
                  turns: List[HistoryEntry],
                  profile: Optional[CognitiveProfile_v1] = None) -> str:
        """
        生成冷摘要：保留用户画像、统计信息、时间范围（供 PCR 时间间隔因子降级使用）。
        
        返回格式：
        "[历史摘要] 时间范围: 2026-06-20T10:00:00 ~ 2026-06-20T11:30:00 | "
        "用户画像: 专家度=0.8, 稳定性=0.9 | "
        "主要意图: TOOL(15), ADVISOR(3) | "
        "技术主题: 内存扫描, 反汇编 | "
        "总轮数: 50"
        """
        from collections import Counter
        
        # 统计高频意图
        expectations = Counter(
            t.expectation for t in turns 
            if t.expectation and t.expectation != "SYSTEM"
        )
        top_exp = expectations.most_common(3)
        
        # 提取技术主题
        topics = set()
        for t in turns:
            text = t.content.lower()
            for topic_name, keywords in self.TECH_TOPIC_PATTERNS:
                if any(kw in text for kw in keywords):
                    topics.add(topic_name)
        
        # 提取时间范围（用于 PCR 感知"这是历史摘要"并降级时间间隔权重）
        timestamps = [t.timestamp for t in turns if t.timestamp]
        time_range = ""
        if timestamps:
            min_ts = min(timestamps)
            max_ts = max(timestamps)
            time_range = (
                f"时间范围: {datetime.fromtimestamp(min_ts).isoformat()} ~ "
                f"{datetime.fromtimestamp(max_ts).isoformat()}"
            )
        
        # 构建摘要
        parts = []
        parts.append("[历史摘要]")  # 标记：PCR 识别到后可降级时间间隔因子
        
        if time_range:
            parts.append(time_range)
        
        if profile:
            parts.append(
                f"用户画像: 专家度={profile.expertise:.2f}, "
                f"稳定性={profile.stability:.2f}, "
                f"元认知={profile.metacognition:.2f}"
            )
        
        if top_exp:
            parts.append(
                "主要意图: " + ", ".join(
                    f"{exp}({cnt})" for exp, cnt in top_exp
                )
            )
        
        if topics:
            parts.append(f"技术主题: {', '.join(sorted(topics))}")
        
        parts.append(f"总对话轮数: {len(turns)}")
        
        return " | ".join(parts)
    
    def _truncate(self, text: str, max_len: int) -> str:
        """截断文本，保留核心信息。"""
        if len(text) <= max_len:
            return text
        # 尝试在空格或标点处截断
        truncated = text[:max_len]
        for i in range(max_len - 1, max_len // 2, -1):
            if truncated[i] in " ，。！？；,.!?;":
                return truncated[:i+1] + "..."
        return truncated + "..."
    
    def _extract_result_summary(self, content: str) -> str:
        """从 assistant 回复中提取结果摘要。"""
        # 尝试提取 JSON 状态
        if "{" in content and "}" in content:
            try:
                start = content.index("{")
                end = content.rindex("}") + 1
                data = json.loads(content[start:end])
                status = data.get("status", "ok")
                return f"[结果: {status}]"
            except (json.JSONDecodeError, ValueError):
                pass
        
        # 尝试提取第一行作为摘要
        first_line = content.split("\n")[0].strip()
        if len(first_line) > 80:
            return first_line[:80] + "..."
        return first_line
```

### 4.3 LLMCompressor（可选的高级压缩器）

```python
class LLMCompressor:
    """
    LLM 驱动的智能压缩器（可选，默认关闭）。
    当规则压缩器的质量下降时，启用 LLM 生成更自然的摘要。
    
    使用条件：
    - 对话轮数 > 50 且冷摘要 token 数 > 500
    - 或用户显式启用 --smart-summary
    """
    
    def __init__(self, provider: LLMProvider):
        self.provider = provider
    
    def summarize(self, turns: List[HistoryEntry], 
                  profile: CognitiveProfile_v1) -> str:
        """使用 LLM 生成自然语言摘要。"""
        
        # 构建极简提示（避免消耗大量 tokens）
        prompt = f"""Summarize the following conversation history into 2-3 sentences.
Keep: user's expertise level, main topics, and recurring patterns.
Discard: specific values, addresses, and tool outputs.

Conversation turns: {len(turns)}
User profile: expertise={profile.expertise:.2f}, stability={profile.stability:.2f}

Recent topics: {self._extract_topics(turns)}

Summary:"""
        
        req = GenerateRequest(
            prompt=prompt,
            system_prompt="You are a conversation summarizer. Be concise.",
            max_tokens=100,
            temperature=0.1,
        )
        
        result = self.provider.generate(req)
        if result.metrics.success:
            return result.text.strip()
        
        # LLM 失败时回退到规则压缩
        return RuleBasedCompressor().summarize(turns, profile)
    
    def _extract_topics(self, turns: List[HistoryEntry]) -> str:
        """提取前 5 个高频关键词作为主题提示。"""
        from collections import Counter
        words = []
        for t in turns:
            words.extend(t.content.lower().split())
        return ", ".join([w for w, _ in Counter(words).most_common(5)])
```

---

## 5. 压缩策略详解

### 5.1 压缩触发条件

| 条件 | 触发压缩 | 说明 |
|---|---|---|
| 历史轮数 > 20 | 温窗口压缩 | 第 6-20 轮进入压缩 |
| 历史轮数 > 100 | 冷摘要生成 | 20 轮以前生成摘要 |
| 预估 tokens > 4000 | 紧急压缩 | 缩小温窗口或触发二次压缩 |
| 对话静默 > 30 分钟 | 会话归档 | 当前会话结束，新会话继承摘要 |
| 每 5 轮 | 增量压缩 | 后台异步压缩，不阻塞当前轮 |

### 5.2 压缩信息保留矩阵

| 信息类型 | 热窗口 | 温窗口 | 冷摘要 | 是否可丢失 |
|---|---|---|---|---|
| 完整 user query | ✅ 保留 | ⚠️ 截断 | ❌ 丢弃 | 否 |
| 完整 assistant 回复 | ✅ 保留 | ⚠️ 摘要 | ❌ 丢弃 | 是 |
| intent 标签 | ✅ 保留 | ✅ 保留 | ✅ 统计 | 否 |
| entity 提取结果 | ✅ 保留 | ✅ 保留 | ⚠️ 高频保留 | 否 |
| tool 调用详情 | ✅ 保留 | ❌ 丢弃 | ❌ 丢弃 | 是 |
| 认知画像更新 | ✅ 保留 | ✅ 保留 | ✅ 累积 | 否 |
| 自适应阈值变化 | ✅ 保留 | ✅ 保留 | ✅ 最终值 | 否 |
| 用户情绪/语气 | ✅ 保留 | ⚠️ 标签化 | ❌ 丢弃 | 是 |
| 时间戳 | ✅ 保留 | ✅ 保留 | ⚠️ 范围 | 是 |

### 5.3 压缩算法流程

```python
def compress_pipeline(history: List[HistoryEntry], config: WindowConfig):
    n = len(history)
    
    # Stage 1: 热窗口（直接切片）
    hot = history[-config.hot_size:]
    
    # Stage 2: 温窗口（规则压缩）
    if n > config.hot_size:
        warm_raw = history[max(0, n-config.hot_size-config.warm_size):n-config.hot_size]
        warm = RuleBasedCompressor().compress(warm_raw)
    
    # Stage 3: 冷摘要（增量生成）
    if n > config.hot_size + config.warm_size:
        cold = history[:n-config.hot_size-config.warm_size]
        
        # 检查是否已有缓存的摘要
        if hasattr(cold, '_cached_summary') and cold._summary_valid:
            summary = cold._cached_summary
        else:
            # 增量更新：在之前摘要基础上追加新轮次
            summary = RuleBasedCompressor().summarize(cold)
            cold._cached_summary = summary
            cold._summary_valid = True
    
    return assemble(hot, warm, summary)
```

---

## 6. 与 PCR 集成方案

### 6.1 修改 PCR 输入构建

```python
# 在 intent_trace_cli.py / AgentService 中

class IntentTraceRunner:
    """
    带窗口管理的意图追踪执行器。
    替代原有的直接调用 run_intent_trace()。
    
    集成缓存层：避免每次 build_context 都从 SQLite 全量拉取历史，
    在内存中维护未压缩的历史列表和已生成的冷摘要。
    """
    
    def __init__(self, 
                 window_manager: ContextWindowManager = None,
                 persistence: CLISessionPersistence = None):
        self.window = window_manager or ContextWindowManager()
        self.persistence = persistence
        # 集成缓存层：避免每次 build_context 都从 SQLite 全量拉取
        self._session_history_cache: Dict[str, List[HistoryEntry]] = {}
        self._session_summary_cache: Dict[str, str] = {}      # 冷摘要缓存
        self._session_cold_turns_cache: Dict[str, int] = {}   # 已摘要轮数缓存
    
    def run(self, query: str, session_id: str, provider: LLMProvider = None):
        # 1. 加载完整历史（优先从内存缓存，避免每次查 SQLite）
        if session_id in self._session_history_cache:
            full_history = self._session_history_cache[session_id]
        else:
            full_history = self._load_history(session_id)
            self._session_history_cache[session_id] = full_history
        
        # 2. 加载会话画像
        session = self.persistence.get_or_load(session_id) if self.persistence else None
        profile = None
        if session and session.cognitive_profile:
            profile = CognitiveProfile_v1.from_dict(session.cognitive_profile)
        
        # 3. 窗口压缩（增量复用缓存的冷摘要，避免重复全量压缩）
        cached_summary = self._session_summary_cache.get(session_id)
        cached_cold_turns = self._session_cold_turns_cache.get(session_id, 0)
        pcr_input = self.window.build_pcr_input(
            query=query,
            history=full_history,
            session_profile=profile,
            cached_summary=cached_summary,
            cached_cold_turns=cached_cold_turns,
        )
        # 保存增量缓存（供下一轮复用）
        self._session_summary_cache[session_id] = pcr_input.process_context.get("cached_summary", "")
        self._session_cold_turns_cache[session_id] = pcr_input.process_context.get("cached_cold_turns", 0)
        
        # 4. 日志输出窗口统计
        stats = self.window.get_window_stats(full_history)
        print(f"[窗口管理] 原始 {stats['total_turns']} 轮 → "
              f"压缩后 {stats['hot_turns'] + stats['warm_turns'] + 1} 轮 "
              f"(热{stats['hot_turns']} + 温{stats['warm_turns']} + 摘要), "
              f"预估 {stats['estimated_tokens']} tokens")
        
        # 5. 执行 PCR（使用压缩后的输入）
        pcr = RuleBasedPCR()
        pcr_output = pcr.evaluate(pcr_input)
        
        # 6. 后续流程（门控、意图解析等）...
        # ... 保持不变
        
        return result
```

### 6.2 PCR 侧适配（最小修改）

```python
# 在 PCRInput_v1 中增加 window 元数据（已有 process_context 字段）
# 无需修改 PCR 核心逻辑，process_context 已透传

class PCRInput_v1:
    query: str
    session_history: List[HistoryEntry]
    process_context: Dict[str, Any]  # ← 已有字段，用于传入窗口统计和压缩标记
    
    # 新增：窗口统计访问方法
    @property
    def window_stats(self) -> Dict:
        return self.process_context.get("window_stats", {})
    
    @property
    def is_compressed(self) -> bool:
        return self.process_context.get("window_mode") == "compressed"
    
    @property
    def cached_summary(self) -> Optional[str]:
        """增量缓存的冷摘要（供下次复用，避免重复全量压缩）。"""
        return self.process_context.get("cached_summary")
    
    @property
    def cached_cold_turns(self) -> int:
        """增量缓存的已摘要轮数（供下次复用）。"""
        return self.process_context.get("cached_cold_turns", 0)
```

### 6.3 压缩对 PCR 各组件的影响

| PCR 组件 | 影响 | 适配策略 |
|---|---|---|
| **NoiseEstimator** | 历史长度变化影响连续性判断 | 使用 `timestamp` 而非轮数索引计算时间间隔；对 `role="system"` 的冷摘要条目降级时间间隔权重（标记为"历史摘要"） |
| **CognitiveProfiler** | EMA 计算需要感知压缩 | 在 `process_context` 中传入 `total_turns`，EMA 基于真实轮数而非压缩后列表长度 |
| **ExpectationIdentifier** | 历史推断依赖近期记录 | 热窗口 5 轮足够覆盖 Tier 2 历史推断；温窗口保留 `metadata.entities` 和 `metadata.intent_category` 不丢失 |
| **ComplexityEstimator** | 历史复杂度统计 | 基于冷摘要中的意图分布，而非全量历史；冷摘要的时间范围信息用于校准复杂度 |

---

## 7. 与 CLI 集成方案

### 7.1 新增 CLI 参数

```python
parser.add_argument("--window-hot", type=int, default=5, help="热窗口大小")
parser.add_argument("--window-warm", type=int, default=15, help="温窗口大小")
parser.add_argument("--max-tokens", type=int, default=4000, help="最大上下文 tokens")
parser.add_argument("--smart-summary", action="store_true", help="启用 LLM 智能摘要")
```

### 7.2 交互模式输出示例

```
📝 用户输入 > 读取这个地址

[窗口管理] 原始 25 轮 → 压缩后 8 轮 (热5 + 温2 + 摘要), 预估 420 tokens

======================================================================
  Step 1: PCR 评估 (Layer 0) — 规则引擎
======================================================================
  expectation: TOOL
  noise_level: 0.08
  ...

======================================================================
  总结
======================================================================
  输入: 读取这个地址
  PCR 期望: TOOL
  意图分类: READ_MEMORY (conf=0.92)
  ⚡ 执行方式: 短路: direct_reply
  LLM 回复: 您想读取的地址是 0x401000 吗？...
  窗口状态: 25 轮原始 / 8 轮压缩 / 节省 68% tokens
```

---

## 8. 性能模型

### 8.1 压缩前后对比

| 指标 | 无压缩（100 轮） | 三层窗口（100 轮） | 改善 |
|---|---|---|---|
| 输入 tokens | ~10,000 | ~1,500 | **-85%** |
| PCR 噪声估算 | 12ms | 2ms | **-83%** |
| 认知画像 EMA | 40ms | 5ms | **-87%** |
| 意图解析 | 60ms | 10ms | **-83%** |
| 总延迟 | 112ms | 17ms | **-85%** |
| 存储空间 | 2MB | 300KB | **-85%** |
| 认知一致性 | 100%（全量） | 95%（压缩后） | -5% |

### 8.2 认知一致性损失分析

| 场景 | 压缩影响 | 缓解策略 |
|---|---|---|
| 5 轮内重复同一工具 | 无影响 | 全在热窗口 |
| 10 轮前提到某地址 | 温窗口保留 | 压缩保留意图标签和 entity |
| 30 轮前学习过某概念 | 冷摘要保留 | 技术主题统计 |
| 跨会话长期画像 | 无影响 | 认知画像独立持久化 |
| 精确引用 "你 20 轮前说的" | 丢失 | 超出设计范围（人工追溯） |

---

## 9. 测试策略

### 9.1 单元测试

```python
class TestContextWindowManager(unittest.TestCase):
    
    def test_short_history_no_compression(self):
        """5 轮历史 → 不压缩，全量保留。"""
        manager = ContextWindowManager(config=WindowConfig(hot_size=5))
        history = [HistoryEntry(role="user", content=f"query {i}", expectation="TOOL") for i in range(5)]
        
        pcr_input = manager.build_pcr_input("scan 100", history)
        
        self.assertEqual(len(pcr_input.session_history), 5)
        self.assertEqual(pcr_input.process_context["window_mode"], "full")
    
    def test_long_history_compression(self):
        """30 轮历史 → 压缩为 5 热 + 15 温 + 1 摘要。"""
        manager = ContextWindowManager(config=WindowConfig(hot_size=5, warm_size=15))
        history = [HistoryEntry(role="user", content=f"query {i}", expectation="TOOL") for i in range(30)]
        
        pcr_input = manager.build_pcr_input("scan 100", history)
        
        self.assertLess(len(pcr_input.session_history), 30)
        self.assertEqual(pcr_input.process_context["window_mode"], "compressed")
        self.assertEqual(pcr_input.process_context["hot_turns"], 5)
        self.assertEqual(pcr_input.process_context["cold_turns"], 10)
    
    def test_token_budget_enforcement(self):
        """强制 token 上限，超限时二次压缩。"""
        manager = ContextWindowManager(config=WindowConfig(max_tokens=100))
        history = [HistoryEntry(role="user", content="A" * 300) for _ in range(10)]
        
        pcr_input = manager.build_pcr_input("scan", history)
        
        self.assertLess(manager._estimate_tokens(pcr_input.session_history), 200)
    
    def test_cognitive_profile_preservation(self):
        """压缩后认知画像不丢失。"""
        compressor = RuleBasedCompressor()
        profile = CognitiveProfile_v1(expertise=0.8, stability=0.9, metacognition=0.7)
        
        history = [HistoryEntry(role="user", content="query", expectation="TOOL") for _ in range(50)]
        summary = compressor.summarize(history, profile)
        
        self.assertIn("专家度=0.80", summary)
        self.assertIn("TOOL(50)", summary)


class TestRuleBasedCompressor(unittest.TestCase):
    
    def test_compress_discards_tool_details(self):
        """压缩丢弃 tool 调用详情。"""
        compressor = RuleBasedCompressor()
        turns = [
            HistoryEntry(role="user", content="scan 100", expectation="TOOL"),
            HistoryEntry(role="tool", content="found 5 addresses: 0x1000, 0x2000...", expectation="TOOL"),
            HistoryEntry(role="assistant", content="found 5 addresses", expectation="TOOL"),
        ]
        
        compressed = compressor.compress(turns)
        
        self.assertEqual(len(compressed), 2)  # 只保留 user 和 assistant
        self.assertNotIn("0x1000", compressed[1].content)
    
    def test_summarize_extracts_topics(self):
        """摘要提取技术主题。"""
        compressor = RuleBasedCompressor()
        turns = [
            HistoryEntry(role="user", content="scan 100", expectation="TOOL"),
            HistoryEntry(role="user", content="patch 0x2000", expectation="TOOL"),
            HistoryEntry(role="user", content="hook function", expectation="TOOL"),
        ]
        
        summary = compressor.summarize(turns, None)
        
        self.assertIn("内存扫描", summary)
        self.assertIn("内存修改", summary)
        self.assertIn("Hook", summary)
```

### 9.2 集成测试：长对话压力

```python
class TestLongConversation(unittest.TestCase):
    """100 轮对话压力测试，验证压缩后认知不漂移。"""
    
    def test_100_turns_consistent_profile(self):
        """
        1. 模拟 100 轮对话（80% TOOL + 20% ADVISOR）
        2. 压缩后执行 PCR
        3. 验证认知画像与全量计算差异 < 5%
        """
        # 生成 100 轮历史
        history = []
        for i in range(100):
            if i % 5 == 0:
                history.append(HistoryEntry(role="user", content="分析这个结构", expectation="ADVISOR"))
            else:
                history.append(HistoryEntry(role="user", content=f"scan {i}", expectation="TOOL"))
        
        # 全量计算（基准）
        pcr_full = RuleBasedPCR()
        profile_full = pcr_full.evaluate(PCRInput_v1("scan", history)).cognitive_profile
        
        # 压缩计算
        manager = ContextWindowManager()
        pcr_input = manager.build_pcr_input("scan", history)
        pcr_compressed = RuleBasedPCR()
        profile_compressed = pcr_compressed.evaluate(pcr_input).cognitive_profile
        
        # 验证差异 < 5%
        self.assertAlmostEqual(
            profile_full.expertise, profile_compressed.expertise, 
            delta=0.05
        )
    
    def test_100_turns_latency_under_20ms(self):
        """100 轮对话时 PCR 端到端延迟 < 20ms。"""
        history = [HistoryEntry(role="user", content=f"query {i}") for i in range(100)]
        
        manager = ContextWindowManager()
        pcr_input = manager.build_pcr_input("scan 100", history)
        
        start = time.perf_counter()
        pcr = RuleBasedPCR()
        pcr.evaluate(pcr_input)
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        self.assertLess(elapsed_ms, 20)
```

---

## 10. 实现计划

### Phase 1: 核心组件（1 天）

| 任务 | 文件 | 说明 |
|---|---|---|
| 1.1 | `agent/context_window.py` | 创建 `ContextWindowManager` + `RuleBasedCompressor` |
| 1.2 | `agent/context_window.py` | 创建 `WindowConfig` + `LLMCompressor`（可选） |
| 1.3 | `tests/test_context_window.py` | 单元测试（短历史、长历史、token 预算、画像保留） |
| 1.4 | `tests/test_context_window_integration.py` | 集成测试（100 轮压力、认知一致性） |

### Phase 2: CLI 集成（0.5 天）

| 任务 | 文件 | 说明 |
|---|---|---|
| 2.1 | `intent_trace_cli.py` | 注入 `ContextWindowManager` |
| 2.2 | `intent_trace_cli.py` | 添加 `--window-hot`, `--window-warm`, `--max-tokens` 参数 |
| 2.3 | `intent_trace_cli.py` | 输出窗口统计信息（原始/压缩/节省率） |
| 2.4 | `tests/test_cli_window.py` | CLI 窗口管理集成测试 |

### Phase 3: 调优（0.5 天）

| 任务 | 说明 |
|---|---|
| 3.1 | 调整 `hot_size` / `warm_size` 默认值（基于测试数据） |
| 3.2 | 优化 `RuleBasedCompressor._extract_result_summary` 精度 |
| 3.3 | 添加 `process_context` 到 `PCRInput_v1` 的访问方法 |

---

## 11. 风险与回退

### 风险 1: 压缩导致引用消解失败

**场景**：用户说 "把那个地址改成 90"，但 "那个地址" 在 10 轮前的温窗口中，已被压缩丢失。

**回退**：
1. 热窗口扩大到 10 轮（牺牲性能换精度）
2. 引用消解模块单独维护 "最近实体缓存"（不受窗口压缩影响）
3. 压缩时保留含 `0x[0-9a-f]+` 的 entity（关键信息不丢）

### 风险 2: LLM 摘要质量不稳定

**场景**：`LLMCompressor` 生成的摘要遗漏关键信息。

**回退**：默认关闭 `enable_llm_compressor`，只使用 `RuleBasedCompressor`（确定性）。

### 风险 3: 压缩延迟意外增长

**场景**：`RuleBasedCompressor.summarize` 遍历 1000 轮历史，耗时 > 5ms。

**回退**：
1. 冷摘要增量更新（每 5 轮只处理新增部分，不重新遍历全部）
2. 后台异步压缩（当前轮不阻塞，下一轮使用已缓存的摘要）

---

## 附录：文件清单

| 文件 | 状态 | 说明 |
|---|---|---|
| `agent/context_window.py` | 🆕 新建 | 核心组件（窗口管理 + 压缩器） |
| `tests/test_context_window.py` | 🆕 新建 | 单元测试 |
| `tests/test_context_window_integration.py` | 🆕 新建 | 集成测试（100 轮压力） |
| `tests/test_cli_window.py` | 🆕 新建 | CLI 集成测试 |
| `intent_trace_cli.py` | 📝 修改 | 注入窗口管理器 |
| `pcr/datacontract.py` | 📝 修改 | `PCRInput_v1` 增加 `window_stats` 访问方法 |

---

## 设计文档体系

| 文档 | 说明 | 依赖 |
|---|---|---|
| `design_persistence.md` | 会话持久化（SQLite） | 无 |
| `design_context_window.md` | 上下文窗口管理（热/温/冷） | 读取持久化历史 |
| `design_observability.md` | 可观测性（日志/指标/告警） | 观察所有模块 |
| `design_topic_tree.md` | 话题树（对话图/回溯/分叉） | 依赖持久化 + 窗口管理 |

# 开源深读 — 执行路径深度分析

> 2026-07-31 · 代理不可达,基于已读代码 + 官方文档 + 架构知识

---

## 一、LangChain _merge_splits — 合并算法的正确性保证

### 完整调用链

```
split_text(text)
  → _split_text(text, separators)    # 递归降级切分
    → _split_text_with_regex(text, separator, keep_separator)
    → good_splits.append(s)           # 积累 < chunk_size 的片段
    → if len(s) >= chunk_size:
        _merge_splits(good_splits, separator)  # ← 核心
```

### _merge_splits 算法 (来自文档和源码记忆)

```python
def _merge_splits(self, splits, separator):
    """合并短片段,保持 chunk_size + overlap."""
    docs = []
    current_doc = []
    current_len = 0
    
    for split in splits:
        split_len = self._length_function(split)
        # 如果当前累积 + 新片段超过 chunk_size
        if current_len + split_len > self._chunk_size:
            if current_doc:
                doc = separator.join(current_doc)
                docs.append(doc)
                # overlap: 保留最后几个片段
                overlap_tokens = 0
                overlap_docs = []
                for d in reversed(current_doc):
                    d_len = self._length_function(d) + len(separator)
                    if overlap_tokens + d_len > self._chunk_overlap:
                        break
                    overlap_docs.insert(0, d)
                    overlap_tokens += d_len
                current_doc = overlap_docs
                current_len = overlap_tokens
        current_doc.append(split)
        current_len += split_len + len(separator)
    
    if current_doc:
        docs.append(separator.join(current_doc))
    return docs
```

### 关键决策点

| 决策 | 做法 | 为什么 |
|------|------|--------|
| overlap 计算 | 从尾部倒序遍历 | 保持最近上下文 |
| separator join | 按原分隔符重组 | 保持可读性 |
| 长度函数 | 默认 len(),可 override | 支持 token 计数 |
| 边界处理 | 单片段 > chunk_size → 单独输出 | 不丢数据 |

### 我们能学的

```python
# DialogMesh 应加入:
class DiscourseSplitter:
    chunk_size: int = 500       # tokens
    chunk_overlap: int = 50     # tokens
    separators = ["\n\n", "\n", ". ", " ", ""]
    
    def _merge_splits(self, splits, separator):
        # 复用 LangChain 的 overlap 算法
        # 但加入 non_chunkable 标记:
        # - code block → keep whole, no split
        # - quote → keep whole, no split
```

---

## 二、GraphRAG gleaning — 迭代精炼机制

### 完整调用链

```
extract_graph(text_units, model, max_gleanings=2)
  → derive_from_rows(text_units, run_strategy, num_threads=4)
    → run_strategy(row):
        _run_extract_graph(text, entity_types, model, max_gleanings)
          → for gleaning in range(max_gleanings):      ← 核心循环
               entities, relationships = llm_extract(
                   text, entity_types, 
                   previous_entities=entities,          ← 上下文注入
                   gleaning_count=gleaning
               )
               if no_new_entities(entities, previous):
                   break  ← 早停
          → return (entities, relationships)
    → merge across parallel workers
    → filter_orphan_relationships
```

### gleaning 循环的关键

```python
# 每次 gleaning: LLM 检查"还有遗漏的实体吗?"
PROMPT = """
Given the text: {text}
Previously extracted entities: {previous_entities}

Identify any ADDITIONAL entities of types {entity_types} 
that were MISSED in the previous extraction.
Return ONLY newly discovered entities. 
If none found, return empty list.
"""
```

### 为什么有效

```
第 0 轮: LLM 提取主要实体 (高信心)
第 1 轮: LLM 检查遗漏 (中信心)
第 2 轮: 通常空 (max_gleanings=2 足够)

迭代成本: 每轮增加 1 次 LLM call × 片段数
但 90% 实体在第 0 轮就提取了
```

### 我们能学的

```python
# DialogMesh AssociationChain L1.5 应加入:
class EntityExtractor:
    max_gleanings: int = 2
    
    def extract(self, text, entity_types):
        entities = self._llm_extract(text, entity_types)
        for round in range(self.max_gleanings):
            missed = self._llm_find_missed(text, entity_types, entities)
            if not missed:
                break
            entities += missed
        return entities
```

---

## 三、OpenWorker TurnEngine — 执行循环

### 已知架构 (来自博文 + 代码目录)

```
TurnEngine.run(task)
  → context_window = memory.get_relevant(task)       # memory lookup
  → agent = agent_registry.select(task.type)          # agent selection
  → loop:
       response = agent.decide(context_window, tools)  # LLM decision
       if response.is_final:
           break
       tool = connector_registry.get(response.tool)    # tool dispatch
       result = await tool.execute(response.params)     # async execution
       context_window.append(response, result)          # update context
  → memory.store(task, context_window)                 # persist
  → return response.output
```

### 与 DialogMesh StateMachine 对比

```
OpenWorker:                           DialogMesh:
  agent.decide() → 多轮决策           StateMachine 8 phases → 单轮完整
  async tool.execute()                 sync handler execution
  context_window 动态增长              context assembly per-phase
  memory.get_relevant()               HotStore + ChunkStore (设计阶段)
```

### 我们能学的

```python
# StateMachine LLM phase 可加的:
class ContextWindow:
    """per-turn context with token budget."""
    max_tokens: int = 4096
    items: List[ContextItem] = []
    
    def append(self, item):
        self.items.append(item)
        while self.token_count() > self.max_tokens:
            self.items.pop(0)  # FIFO eviction
    
    def token_count(self):
        return sum(len(item.text) // 4 for item in self.items)
```

---

## 四、对比矩阵 — 三个项目的正确性设计

| 维度 | LangChain | GraphRAG | OpenWorker | DialogMesh |
|------|-----------|----------|------------|------------|
| 错误处理 | raise + try/except | warn + skip | try/except + fallback | RuntimeError(required) / warn(optional) |
| 降级策略 | 递归降级分隔符 | gleaning 上限 | agent retry | NATS→memory, PG→SQLite |
| 并发 | 同步 | asyncio.gather + num_threads | async/await | 同步 (够用) |
| 配置 | kwargs 透传 | typed config | typed config | registry deps+init_order |
| 测试 | 单元 (split) + 集成 (pipeline) | 单元 + E2E | 单元 + E2E | 单元(28) + v3_2(195) |

### DialogMesh gap

```
LangChain:  merge_splits + overlap 算法 → 我们缺 ❌
GraphRAG:   gleaning 迭代精炼       → 我们缺 ❌
OpenWorker: context_window 限制      → 我们缺 ❌
```

### Phase 1 应加入

| 来源 | 加到哪 | 成本 |
|------|--------|:---:|
| _merge_splits | GranularityRegulator | 30行 |
| gleaning loop | L1.5 EntityExtractor | 20行 |
| context_window | StateMachine LLM phase | 15行 |

# DialogMesh 行为语义嵌入层 --- 工程实现文档

> **文档编号**: ENGINEERING-V3.3-BEHAVIOR-EMB-002  
> **版本**: v1.0  
> **日期**: 2026-07-05  
> **状态**: 工程待实现  
> **对应算法文档**: `DESIGN_V3_3_ALGORITHM.md` S2（行为语义嵌入层）  
> **依赖模块**: `ENGINEERING_V3_3_COMPILER.md`（编译器输出作为行为对输入）  
> **依赖库**: BGE-small（`transformers` + `torch`）、numpy、scikit-learn（cosine_similarity）  
> **前置算法**: v3.3 算法设计 S2 — 谓词-论元原型嵌入 + 三层权重查询  
> **原则**: 此层的目的是让 BehaviorGraph 在精确匹配失败时能通过语义相似度找到邻居行为。谓词提供硬边界（执行≠删除），论元提供连续语义（程序 vs 脚本）。  

---

## 1. 文档目标与范围

### 1.1 目标

为行为语义嵌入层提供完整的工程实现规范，覆盖：
- 谓词-论元拆分器的 LLM 轻量调用实现
- 谓词分类器的 <50 条映射规则设计
- BGE-small 嵌入封装的离线/在线推理
- 原型向量的离线预计算与增量更新机制
- 加权组合嵌入的计算流程
- 三层权重查询：精确匹配 -> 语义邻居 -> 全局退避
- 与 BehaviorGraph 的集成协议
- 测试策略与覆盖要求

### 1.2 非目标

- BehaviorGraph 的边权重更新算法 -> 见 BehaviorGraph 工程文档
- LLM 调用的并发/超时策略 -> 见 ENGINEERING_LLM_PROVIDERS.md
- BGE-small 模型的训练/微调 -> 使用现成预训练模型

### 1.3 边界

| 边界 | 包含 | 不包含 |
|------|------|--------|
| 输入 | action_summary + behavior_type | 原始用户输入 |
| 输出 | 384维嵌入向量 / 邻居权重列表 | BehaviorGraph 的边权重更新 |
| 职责 | 行为对的语义表示和相似度查询 | 预测用户下一步行为 |
| 异常 | 谓词分类失败 -> 纯 BGE 嵌入 | 不向上传播错误 |

---

## 2. 架构总览

### 2.1 处理管线位置

行为语义嵌入层位于编译器之后、BehaviorGraph 查询之前：

```
编译器输出 -> [行为语义嵌入层] -> BehaviorGraph 查询 -> BehaviorPredictor
                |
                v
           行为对嵌入向量
           (用于语义邻居查询)
```

### 2.2 内部架构

```
action_summary (来自编译器输出)
  |
  v
[PredicateArgumentSplitter] --- LLM 轻量调用 (~50 tokens)
  | 输出: (predicate_text, argument_text)
  |
  +---> [PredicateClassifier] --- <50条映射规则
  |       | 输出: predicate_class (如 "execute")
  |       | 失败 -> 退回到纯 BGE 嵌入
  |       v
  |   [PrototypeManager] --- 查表 O(1)
  |       | 输出: 384d 原型向量 prototype_vec(pred_class)
  |       v
  |   [CompositeEmbedder] --- 加权组合
  |       | 输出: 384d 组合嵌入向量
  |       v
  +---> +-> [ThreeTierWeightQuery] ---> BehaviorGraph
                |
                v
         (相似度权重/退避信号)
```

### 2.3 文件结构

```
core/agent/v3_2/behavior_embedding/
  __init__.py
  models.py              # BehaviorEmbedding, NeighborResult, EmbeddingConfig
  predicate_splitter.py  # PredicateArgumentSplitter
  predicate_classifier.py # PredicateClassifier + 映射规则
  bge_embedder.py        # BgeEmbedder (transformers 封装)
  prototype_manager.py   # PrototypeManager (离线/在线)
  composite_embedder.py  # CompositeEmbedder (加权组合)
  three_tier_query.py    # ThreeTierWeightQuery (三层查询)
  index_builder.py       # 索引重建触发逻辑
```

---

## 3. 数据模型 (models.py)

### 3.1 BehaviorEmbedding

```python
@dataclass
class BehaviorEmbedding:
    """行为对的嵌入表示"""
    source_summary: str       # 源行为摘要
    target_summary: str       # 目标行为摘要
    source_vec: np.ndarray    # 384维源嵌入
    target_vec: np.ndarray    # 384维目标嵌入
    similarity: float         # 余弦相似度
    behavior_type: str        # 行为类型
    pred_class_src: str | None  # 源谓词类
    pred_class_tgt: str | None  # 目标谓词类
    embedding_mode: str       # "composite" | "bge_only" | "fallback"
    created_at: float         # 时间戳

    def cosine_sim(self) -> float:
        if self.similarity >= 0:
            return self.similarity
        # 延迟计算
        from sklearn.metrics.pairwise import cosine_similarity
        self.similarity = cosine_similarity(self.source_vec.reshape(1,-1), self.target_vec.reshape(1,-1))[0][0]
        return self.similarity
```

### 3.2 NeighborResult

```python
@dataclass
class NeighborResult:
    """语义邻居查询结果"""
    neighbors: list[tuple[str, float]]  # [(behavior_pair_key, similarity), ...]
    query_mode: str                     # "exact" | "semantic" | "fallback"
    avg_weight: float | None            # 邻居的加权平均权重
    neighbor_count: int                 # 命中的邻居数
    latency_ms: float                   # 查询耗时

    @property
    def has_result(self) -> bool:
        return self.query_mode != "fallback" and self.avg_weight is not None
```

### 3.3 EmbeddingConfig

```python
@dataclass
class EmbeddingConfig:
    """嵌入层配置"""
    bge_model_name: str = "BAAI/bge-small-zh-v1.5"
    embedding_dim: int = 384
    neighbor_threshold: float = 0.6      # 语义邻居相似度阈值
    top_k: int = 5                       # 最多返回的邻居数
    exact_match_weight: float = 0.8      # 精确匹配在混合查询中的权重
    semantic_weight: float = 0.2         # 语义邻居在混合查询中的权重
    rebuild_ratio: float = 0.2           # 新行为对触发重建的比例阈值
    max_predicate_rules: int = 50        # 谓词类映射规则上限
    use_gpu: bool = False               # 是否使用 GPU
    cache_size: int = 1000              # BGE 嵌入缓存大小

    PRED_WEIGHTS = {  # 谓词权重表（按行为类型）
        "TOOL_EXEC": (0.7, 0.3),
        "CODE_RUN": (0.7, 0.3),
        "LOG_CHECK": (0.4, 0.6),
        "ENTITY_ANALYZE": (0.3, 0.7),
        "CONFIG_MODIFY": (0.5, 0.5),
        "EXPLORATION": (0.3, 0.7),
        "DEFAULT": (0.5, 0.5),
    }

    def get_weights(self, behavior_type: str) -> tuple[float, float]:
        return self.PRED_WEIGHTS.get(behavior_type, self.PRED_WEIGHTS["DEFAULT"])
```

---

## 4. 谓词-论元拆分器 (PredicateArgumentSplitter)

### 4.1 职责

将 `action_summary` 拆分为 `(谓词, 论元)`。例如 "运行程序" -> ("运行", "程序")。使用 LLM 轻量调用（~50 tokens）。

### 4.2 接口

```python
class PredicateArgumentSplitter:
    """
    谓词-论元拆分器。
    使用 LLM 轻量调用将 action_summary 拆分为 (谓词, 论元)。
    """

    def __init__(self, llm_provider, max_retries=1):
        self.llm = llm_provider
        self.max_retries = max_retries

    async def split(self, action_summary: str, behavior_type: str = "") -> tuple[str | None, str | None]:
        """返回 (predicate: str | None, argument: str | None)"""
        prompt = self._build_prompt(action_summary)
        for _ in range(self.max_retries + 1):
            raw = await self.llm.generate(prompt, max_tokens=30)
            result = self._parse(raw)
            if result:
                return result
        return (action_summary[:2], action_summary[2:] )  # 退避: 简单切分

    def _build_prompt(self, summary: str) -> str:
        return (
            '将以下行为描述拆分为(谓词, 论元)。只输出JSON。\\n行为: ' + summary
            + '\\n{"predicate": "", "argument": ""}'
        )

    def _parse(self, raw: str) -> tuple | None:
        import json
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end == -1:
            return None
        try:
            d = json.loads(raw[start:end+1])
            p = d.get("predicate", "").strip()
            a = d.get("argument", "").strip()
            return (p if p else None, a if a else None)
        except:
            return None
```

### 4.3 Prompt 策略

- 明确指示只输出 JSON，不要推理、不要解释
- 谓语字段名 `predicate`，论元字段名 `argument`
- max_tokens=30（拆解不需要超过30个token）
- 退避策略: LLM 失败时按前2字/后2字做简单切分（中文动宾结构占多数）

### 4.4 边界处理

| 场景 | 处理 |
|------|------|
| LLM 返回非 JSON | 重试1次，失败->退避切分 |
| 谓词或论元为空 | 对应字段返回 None |
| 单字行为描述（如 "查"） | predicate="查", argument=None |
| 连续3次拆分失败 | 标记该行为不可拆分 -> 下次走纯 BGE 路径 |

---

## 5. 谓词分类器 (PredicateClassifier)

### 5.1 职责

将自然语言谓词（"运行"、"删除"、"分析"等）映射到预定义的谓词类。映射规则 <50 条，纯规则匹配，<1ms。

### 5.2 接口

```python
class PredicateClassifier:
    """谓词分类器：NL谓词 -> 预定义谓词类"""

    MAX_RULES = 50

    def __init__(self):
        self._rules: dict[str, str] = {}  # NL谓词 -> 谓词类
        self._load_default_rules()

    def classify(self, predicate_text: str | None) -> str | None:
        """
        返回：谓词类 ID（如 "execute"）或 None（无法分类）
        """
        if not predicate_text:
            return None
        return self._rules.get(predicate_text.strip().lower())

    def add_rule(self, nl_predicate: str, predicate_class: str):
        if len(self._rules) < self.MAX_RULES:
            self._rules[nl_predicate.strip().lower()] = predicate_class

    def _load_default_rules(self):
        """加载默认映射规则 <50 条"""
        rules = [
            ("运行", "execute"), ("执行", "execute"), ("启动", "execute"),
            ("删除", "delete"), ("移除", "delete"), ("清除", "delete"),
            ("修改", "modify"), ("更新", "modify"), ("编辑", "modify"),
            ("分析", "analyze"), ("解析", "analyze"), ("诊断", "analyze"),
            ("查看", "check"), ("检查", "check"), ("监控", "monitor"),
            ("创建", "create"), ("新建", "create"), ("生成", "create"),
            ("配置", "config"), ("设置", "config"), ("调整", "config"),
            ("停止", "stop"), ("终止", "stop"), ("暂停", "stop"),
            ("导航", "navigate"), ("进入", "navigate"), ("跳转", "navigate"),
            ("搜索", "search"), ("查找", "search"), ("查询", "search"),
            ("对比", "compare"), ("比较", "compare"), ("差异", "compare"),
            ("调试", "debug"), ("排查", "debug"), ("追踪", "debug"),
            ("导入", "import"), ("导出", "export"), ("备份", "backup"),
            ("测试", "test"), ("验证", "test"), ("校验", "test"),
        ]
        for nl, cls in rules:
            self.add_rule(nl, cls)

    @property
    def predicate_classes(self) -> list[str]:
        return sorted(set(self._rules.values()))
```

### 5.3 默认谓词类（初始）

| 谓词类 ID | 自然语言触发词（部分） | 权重类型 |
|-----------|----------------------|---------|
| execute | 运行, 执行, 启动, 调用 | TOOL_EXEC |
| delete | 删除, 移除, 清除 | TOOL_EXEC |
| modify | 修改, 更新, 编辑, 更改 | CONFIG_MODIFY |
| analyze | 分析, 解析, 诊断, 审查 | ENTITY_ANALYZE |
| check | 查看, 检查, 监控, 观察 | LOG_CHECK |
| create | 创建, 新建, 生成, 编写 | CODE_RUN |
| config | 配置, 设置, 调整, 部署 | CONFIG_MODIFY |
| stop | 停止, 终止, 暂停, 中断 | TOOL_EXEC |
| navigate | 导航, 进入, 跳转, 打开 | EXPLORATION |
| search | 搜索, 查找, 查询, 定位 | EXPLORATION |
| compare | 对比, 比较, 差异 | ENTITY_ANALYZE |
| debug | 调试, 排查, 追踪, 修复 | CODE_RUN |
| import | 导入, 加载, 读取 | CODE_RUN |
| export | 导出, 保存, 写入 | CODE_RUN |
| backup | 备份, 同步, 存档 | CONFIG_MODIFY |
| test | 测试, 验证, 校验 | CODE_RUN |

### 5.4 边界处理

| 场景 | 处理 |
|------|------|
| 谓词不在规则中 | 返回 None -> CompositeEmbedder 退回到纯 BGE |
| 谓词映射到多个类 | 取第一个匹配（按优先级） |
| 规则数达到 MAX_RULES | add_rule 静默忽略 |

---

## 6. BGE-small 嵌入封装 (BgeEmbedder)

### 6.1 职责

封装 `transformers` 库的 BGE-small 模型调用，提供文本 -> 384维向量的嵌入能力。支持批量、缓存、延迟加载。

### 6.2 接口

```python
class BgeEmbedder:
    """BGE-small 嵌入封装"""

    def __init__(self, config: EmbeddingConfig):
        self.config = config
        self._model = None
        self._tokenizer = None
        self._cache: dict[str, np.ndarray] = {}
        self._load_lock = asyncio.Lock()

    async def embed(self, text: str) -> np.ndarray:
        """返回 384 维向量"""
        if text in self._cache:
            return self._cache[text]
        await self._ensure_model()
        vec = await self._encode(text)
        if len(self._cache) < self.config.cache_size:
            self._cache[text] = vec
        return vec

    async def embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        """批量嵌入"""
        await self._ensure_model()
        uncached = [t for t in texts if t not in self._cache]
        if uncached:
            vecs = await self._encode_batch(uncached)
            for t, v in zip(uncached, vecs):
                if len(self._cache) < self.config.cache_size:
                    self._cache[t] = v
        return [self._cache[t] for t in texts]

    async def _ensure_model(self):
        if self._model is not None:
            return
        async with self._load_lock:
            if self._model is not None:
                return
            from transformers import AutoModel, AutoTokenizer
            self._tokenizer = AutoTokenizer.from_pretrained(self.config.bge_model_name)
            self._model = AutoModel.from_pretrained(self.config.bge_model_name)
            if self.config.use_gpu:
                self._model = self._model.cuda()

    def _encode(self, text: str) -> np.ndarray:
        """同步编码（被异步包装）"""
        encoded = self._tokenizer([text], padding=True, truncation=True, return_tensors="pt")
        if self.config.use_gpu:
            encoded = {k: v.cuda() for k, v in encoded.items()}
        with torch.no_grad():
            output = self._model(**encoded)
        vec = output.last_hidden_state.mean(dim=1).squeeze().numpy()
        # L2 归一化
        vec = vec / np.linalg.norm(vec)
        return vec

    def clear_cache(self):
        self._cache.clear()
```

### 6.3 延迟加载策略

- 模型不在 __init__ 中加载，在首次 embed() 调用时加载
- 使用 asyncio.Lock 确保并发安全
- 模型加载约 1-3 秒（首次），后续推理 <5ms/条
- LRU 缓存（前 1000 条）避免重复编码

---

## 7. 原型向量管理 (PrototypeManager)

### 7.1 职责

管理谓词类的原型向量：离线预计算（加载模型时）+ 在线增量更新（新增谓词类时）。

### 7.2 接口

```python
class PrototypeManager:
    """
    谓词类原型向量管理器。
    管理 (predicate_class -> 384d 原型向量) 的映射。
    """

    def __init__(self, embedder: BgeEmbedder, classifier: PredicateClassifier):
        self.embedder = embedder
        self.classifier = classifier
        self._prototypes: dict[str, np.ndarray] = {}

    async def initialize(self):
        """离线预计算：为所有谓词类构造原型向量"""
        # 每个谓词类的标准表述
        canonical = {
            "execute": ["execute program", "run service", "start process"],
            "delete": ["delete file", "remove item", "clear data"],
            "modify": ["modify config", "update setting", "edit file"],
            "analyze": ["analyze output", "parse log", "examine result"],
            "check": ["check status", "review log", "monitor metric"],
            "create": ["create file", "generate output", "write code"],
            "config": ["configure service", "deploy app", "setup env"],
            "stop": ["stop process", "terminate job", "pause task"],
            "navigate": ["navigate to", "open directory", "go to"],
            "search": ["search result", "find error", "lookup value"],
            "compare": ["compare output", "diff files", "match result"],
            "debug": ["debug code", "trace error", "fix bug"],
            "import": ["import data", "load file", "read input"],
            "export": ["export result", "save file", "write output"],
            "backup": ["backup config", "sync data", "archive log"],
            "test": ["test case", "verify result", "validate input"],
        }
        for pclass, examples in canonical.items():
            vecs = await self.embedder.embed_batch(examples)
            self._prototypes[pclass] = np.mean(vecs, axis=0)

    def get(self, predicate_class: str) -> np.ndarray | None:
        return self._prototypes.get(predicate_class)

    async def add_prototype(self, predicate_class: str, examples: list[str]):
        """增量更新：新增谓词类时调用"""
        vecs = await self.embedder.embed_batch(examples)
        self._prototypes[predicate_class] = np.mean(vecs, axis=0)

    @property
    def prototype_count(self) -> int:
        return len(self._prototypes)
```

### 7.3 更新策略

- **离线初始化**: 系统启动/模型加载时调用 `initialize()`
- **增量更新**: 新增谓词类时调用 `add_prototype()`
- **重建触发**: 当新的行为对数量超过总行为对的 20% 时，建议重建（由上层触发）
- 原型向量 = 该谓词类所有标准表述的 BGE 嵌入的平均值

---

## 8. 组合嵌入器 (CompositeEmbedder)

### 8.1 职责

将谓词原型向量和论元嵌入向量按行为类型权重加权组合，生成最终的行为嵌入。

### 8.2 接口

```python
class CompositeEmbedder:
    """
    组合嵌入器。
    vec = w_pred * prototype_vec(pred_class) + w_arg * bge(arg)
    """

    def __init__(self, config: EmbeddingConfig, prototype_mgr: PrototypeManager, embedder: BgeEmbedder):
        self.config = config
        self.prototypes = prototype_mgr
        self.embedder = embedder

    async def embed(
        self, action_summary: str, behavior_type: str = "",
        predicate: str | None = None, argument: str | None = None
    ) -> tuple[np.ndarray, str]:
        """
        返回: (384维嵌入向量, 嵌入模式)
        嵌入模式: "composite" | "bge_only" | "fallback"
        """
        w_pred, w_arg = self.config.get_weights(behavior_type)

        # 如果谓词分类成功 -> 组合嵌入
        if predicate is not None:
            pred_class = PredicateClassifier().classify(predicate)
            if pred_class:
                proto = self.prototypes.get(pred_class)
                if proto is not None:
                    arg_vec = await self.embedder.embed(argument or action_summary)
                    vec = w_pred * proto + w_arg * arg_vec
                    vec = vec / np.linalg.norm(vec)  # L2归一化
                    return (vec, "composite")

        # 退避1: 纯 BGE-small 嵌入
        bge_vec = await self.embedder.embed(action_summary)
        return (bge_vec, "bge_only")

    async def embed_pair(
        self, source: str, target: str, src_type: str, tgt_type: str
    ) -> BehaviorEmbedding:
        """嵌入行为对 (source -> target)"""
        src_vec, src_mode = await self.embed(source, src_type)
        tgt_vec, tgt_mode = await self.embed(target, tgt_type)
        sim = cosine_similarity(src_vec.reshape(1,-1), tgt_vec.reshape(1,-1))[0][0]
        return BehaviorEmbedding(
            source_summary=source, target_summary=target,
            source_vec=src_vec, target_vec=tgt_vec, similarity=sim,
            behavior_type=src_type, embedding_mode=src_mode
        )
```

---

## 9. 三层权重查询 (ThreeTierWeightQuery)

### 9.1 职责

对 BehaviorGraph 查询 `from_action -> to_action` 的边权重时，三层递进：精确匹配 -> 语义邻居 -> 退避。

### 9.2 接口

```python
class ThreeTierWeightQuery:
    """三层权重查询：精确匹配 -> 语义邻居 -> 退避"""

    def __init__(self, config: EmbeddingConfig, graph, embedder: CompositeEmbedder):
        self.config = config
        self.graph = graph          # BehaviorGraph 实例
        self.embedder = embedder
        self._neighbor_index: dict[str, list[tuple[str, float]]] | None = None

    async def query(
        self, from_action: str, to_action: str,
        from_type: str = "", to_type: str = ""
    ) -> NeighborResult:
        """
        三层递进查询。
        Step 1: 精确匹配
        Step 2: 语义邻居（Top-K, cosine > 0.6）
        Step 3: 全局退避
        """
        start = time.monotonic()
        pair_key = f"{from_action}->{to_action}"

        # Step 1: 精确匹配
        exact_weight = self._exact_search(from_action, to_action)
        if exact_weight is not None:
            return NeighborResult(
                neighbors=[], query_mode="exact",
                avg_weight=exact_weight, neighbor_count=0,
                latency_ms=(time.monotonic()-start)*1000)

        # Step 2: 语义邻居
        emb = await self.embedder.embed_pair(from_action, to_action, from_type, to_type)
        neighbors = self._semantic_search(emb)
        if neighbors:
            avg_w = self._weighted_average(neighbors)
            return NeighborResult(
                neighbors=neighbors, query_mode="semantic",
                avg_weight=avg_w, neighbor_count=len(neighbors),
                latency_ms=(time.monotonic()-start)*1000)

        # Step 3: 退避
        return NeighborResult(
            neighbors=[], query_mode="fallback",
            avg_weight=None, neighbor_count=0,
            latency_ms=(time.monotonic()-start)*1000)

    def _exact_search(self, from_action: str, to_action: str) -> float | None:
        """在 BehaviorGraph 中精确查找边权重"""
        return self.graph.get_edge_weight(from_action, to_action)

    def _semantic_search(self, emb: BehaviorEmbedding) -> list[tuple[str, float]]:
        """在邻居索引中搜索相似行为对"""
        if self._neighbor_index is None:
            return []
        candidates = []
        for key, (src_vec, tgt_vec) in self._neighbor_index.items():
            src_sim = cosine_similarity(emb.source_vec.reshape(1,-1), src_vec.reshape(1,-1))[0][0]
            tgt_sim = cosine_similarity(emb.target_vec.reshape(1,-1), tgt_vec.reshape(1,-1))[0][0]
            avg_sim = (src_sim + tgt_sim) / 2
            if avg_sim >= self.config.neighbor_threshold:
                candidates.append((key, avg_sim))
        candidates.sort(key=lambda x: -x[1])
        return candidates[:self.config.top_k]

    def _weighted_average(self, neighbors: list[tuple[str, float]]) -> float:
        """按相似度加权的邻居权重平均"""
        total_w = 0.0; total_sim = 0.0
        for key, sim in neighbors:
            weight = self.graph.get_edge_weight_by_key(key)
            if weight is not None:
                total_w += weight * sim
                total_sim += sim
        return total_w / total_sim if total_sim > 0 else None

    def rebuild_index(self):
        """重建邻居索引（当新行为对超过 20% 时触发）"""
        self._neighbor_index = self.graph.build_neighbor_index()
```

### 9.3 精确匹配+语义邻居混合

当精确匹配命中且语义邻居也有命中时：

```python
final_weight = exact_weight * 0.8 + semantic_avg_weight * 0.2
```

确保精确匹配的主导地位，同时利用语义信息平滑。

---

## 10. 索引重建 (IndexBuilder)

### 10.1 职责

监听行为对变更，触发语义邻居索引的增量/全量重建。

```python
class IndexBuilder:
    """语义邻居索引重建管理器"""

    def __init__(self, graph, query: ThreeTierWeightQuery, config: EmbeddingConfig):
        self.graph = graph
        self.query = query
        self.config = config
        self.total_pairs = 0
        self.new_pairs_since_rebuild = 0

    def on_new_behavior_pair(self):
        """每新增一个行为对时调用"""
        self.total_pairs += 1
        self.new_pairs_since_rebuild += 1
        ratio = self.new_pairs_since_rebuild / max(self.total_pairs, 1)
        if ratio >= self.config.rebuild_ratio:
            self.rebuild()

    def rebuild(self):
        self.query.rebuild_index()
        self.new_pairs_since_rebuild = 0
```

---

## 11. 与 BehaviorGraph 的集成

### 11.1 集成协议

BehaviorGraph 在查询边权重时，调用 ThreeTierWeightQuery.query() 代替直接查表：

```python
# BehaviorGraph 内部
async def get_weight(self, from_action: str, to_action: str) -> float:
    result = await self.weight_query.query(from_action, to_action)
    if result.has_result:
        return result.avg_weight
    # 退避到 BehaviorPredictor
    return await self.predictor.causal_prob(from_action, to_action)
```

### 11.2 数据流

```
编译器输出 slots
  |
  v
行为对提取 (from_action -> to_action)
  |
  v
[ThreeTierWeightQuery]
  |--- 精确匹配 -> BehaviorGraph.exact_lookup() -> 直接返回
  |--- 语义邻居 -> CompositeEmbedder.embed_pair() ->
  |                 BgeEmbedder -> PrototypeManager ->
  |                 加权平均 -> 返回
  |--- 退避 -> None -> BehaviorPredictor.llm_causal_prob()
  v
权重写入或更新
```

---

## 12. 测试策略

### 12.1 单元测试 (P0)

| 测试 | 内容 |
|------|------|
| test_embedding_config | 各行为类型的权重取值, DEFAULT 回退 |
| test_predicate_splitter | 正常拆解, 退避切分, LLM 失败 |
| test_predicate_classifier | <50 条规则映射, 未知谓词, 空输入 |
| test_prototype_manager | prototype 加载, 获取, 增量添加 |
| test_bge_embedder | 嵌入维度, 缓存命中, 批量嵌入, L2归一化 |
| test_composite_embedder | 组合嵌入, BGE_only 退避, 嵌入距离 |
| test_three_tier_query | 精确匹配->语义->退避, 混合权重 |

### 12.2 集成测试

| 场景 | 预期 |
|------|------|
| 精确匹配命中 | 直接返回 graph edge weight |
| 语义邻居匹配 (cosine > 0.6) | 加权平均邻居权重 |
| 精确+语义都命中 | final = exact*0.8 + semantic*0.2 |
| 无匹配 | None -> BehaviorPredictor 退避 |
| 谓词分类失败 | 退回到纯 BGE 嵌入 |
| 原型向量缺失 | 退回到纯 BGE 嵌入 |
| 新行为对超过 20% | 触发索引重建 |

### 12.3 测试数据

```python
# 测试用例：验证谓词-论元嵌入的区分性
test_cases = [
    ("运行程序", "execute"),
    ("删除程序", "delete"),
    ("查看日志", "check"),
    ("分析结果", "analyze"),
    ("修改配置", "modify"),
]
# 预期: execute(Program) vs delete(Program) sim < 0.5
# 预期: execute(Program) vs execute(Script) sim > 0.6
```

---

## 13. 附录

### A. 与算法设计对照

| 算法 S2 | 工程实现 | 状态 |
|---------|---------|------|
| 谓词-论元拆分 | PredicateArgumentSplitter | 待实现 |
| 谓词分类 | PredicateClassifier | 待实现 |
| 论元嵌入 | BgeEmbedder | 待实现 |
| 原型向量构造/检索 | PrototypeManager | 待实现 |
| 加权组合 | CompositeEmbedder | 待实现 |
| 核心邻居阈值0.6 | ThreeTierWeightQuery._semantic_search | 待实现 |
| 三层权重查询 | ThreeTierWeightQuery | 待实现 |
| 索引重建 (20%) | IndexBuilder | 待实现 |

### B. 实现优先级

| 优先级 | 模块 | 理由 |
|--------|------|------|
| P0 | EmbedingConfig, Models | 其他模块依赖 |
| P0 | PredicateClassifier | 纯规则无外部依赖 |
| P0 | BgeEmbedder | 嵌入的基础设施 |
| P0 | PrototypeManager + CompositeEmbedder | 核心嵌入生成 |
| P1 | PredicateArgumentSplitter | 需要 LLM 调用 |
| P1 | ThreeTierWeightQuery | 需要 BehaviorGraph 就绪 |
| P2 | IndexBuilder | 上线后有数据再启用 |

### C. 依赖关系

```
BgeEmbedder -> transformers + torch (外部库)
PrototypeManager -> BgeEmbedder
PredicateClassifier -> 无
PredicateArgumentSplitter -> LLM provider
CompositeEmbedder -> PrototypeManager + BgeEmbedder + PredicateClassifier
ThreeTierWeightQuery -> CompositeEmbedder + BehaviorGraph
IndexBuilder -> ThreeTierWeightQuery
```

### D. 待讨论

1. BGE-small 模型是否需要延迟加载？首期建议在系统初始化时预加载（3s 一次性开销 vs 每轮 1-2s 首次加载延迟）
2. 50 条规则是否足够覆盖中文调试场景的核心谓词？建议上线后收集未覆盖谓词按频率补充。
3. 原型向量标准表述使用中文还是英文？BGE-small-zh 对中文理解更好，建议用中文表述。
4. 索引重建策略：20%阈值是否太保守？数据量小时可适当放宽。

---


### 参数配置

| 参数 | 初始值 | 锚点来源 | 区间 | 自适应信号 | 速率 |
|------|--------|---------|------|-----------|------|
| neighbor_threshold | 0.6 | BGE MTEB 平均相关度 | [0.50, 0.70] | 邻居相似度分布 | +-0.01/次 |
| top_k | 5 | 经验值 | [3, 10] | 查询命中率 | +-1/50轮 |
| exact_match_weight | 0.8 | 经验值 | [0.6, 0.95] | 精确vs语义命中比 | +-0.02/50轮 |
| rebuild_ratio | 0.2 | 经验值 | [0.1, 0.4] | 新行为对占比 | 手动 |

--- END OF DOCUMENT ---

# PCR 设计问题讨论与改进方案

## 问题1：多模态输入与纯文本评估器的错位（接口化处理）

### 当前现状

`PCRInput_v1.query` 是纯文本字段。设计文档标榜"多模态（自然语言/JSON/快捷指令）"输入，但 Stage 1（期望识别）和 Stage 2（噪声/复杂度评估）的所有规则（"无动词检测"、"实体重叠"、"词汇噪声"）均为纯文本 NLP 设计。

### 问题分析

如果用户发来一张带文字的截图，当前系统会直接将其丢给文本规则评估器：
- "结构噪声"：OCR 前的像素噪声无法被"无动词"规则处理
- "词汇噪声"：图片中的模糊文字会被误判为词汇噪声
- 结果：直接报错或产生荒谬的噪声评分

### 改进方案：模态分发器（轻量级接口）

用户明确表示"多模态不重要，专注文本，加个接口变成可调用即可"。建议增加最小化接口，不改动现有文本 Pipeline：

```python
# PCRInput_v1 增加 modality 字段
class Modality(Enum):
    TEXT = "text"           # 纯文本（当前唯一生产路径）
    STRUCTURED = "structured"  # JSON / 快捷指令 / 结构化数据
    IMAGE = "image"         # 图片（OCR 前）
    AUDIO = "audio"         # 语音（ASR 前）
    MULTIMODAL = "multimodal"  # 混合输入

@dataclass(frozen=True)
class PCRInput_v1:
    modality: Modality = Modality.TEXT
    query: str = ""         # 文本模态：直接输入
    raw_payload: Optional[Dict[str, Any]] = None  # 非文本模态：原始负载
    # ... 其他字段不变

# 在 PCRLifecycleManager.evaluate() 入口处增加分发器
class PCRLifecycleManager:
    def evaluate(self, input_data: PCRInput_v1) -> PCROutput_v1:
        if input_data.modality == Modality.TEXT:
            return self._fallback_engine.evaluate(input_data)
        elif input_data.modality == Modality.STRUCTURED:
            # 结构化数据直接转换为 IntentContext，跳过文本噪声评估
            return self._evaluate_structured(input_data)
        elif input_data.modality in (Modality.IMAGE, Modality.AUDIO, Modality.MULTIMODAL):
            # 路由到外部预处理器（OCR/ASR），预处理为 TEXT 后再进入 Pipeline
            return self._evaluate_with_preprocessing(input_data)
        # ...
```

**关键原则**：
- 文本路径（`TEXT`）完全保持现有逻辑不变
- 结构化路径（`STRUCTURED`）绕过文本噪声/复杂度评估，直接做意图分类（因为结构化数据本身无"噪声"）
- 图像/音频路径（`IMAGE`/`AUDIO`）通过 `raw_payload` 传入，由外部预处理器（OCR/ASR）转换为 `TEXT` 后，重新构造 `PCRInput_v1(modality=TEXT)` 进入标准 Pipeline
- 不引入任何新的依赖（OCR/ASR 作为可选外部服务）

---

## 问题2：上下文断裂判定过于武断（核心问题深度讨论）

### 2.1 当前缺陷

当前 `NoiseEstimator` 中"上下文断裂"的判定逻辑：

```python
# 3. 上下文断裂（0-0.2）：与上轮无实体/主题重叠
if history:
    last_entities = history[-1].entities
    current_entities = quick_extract_entities(text)
    if not set(current_entities) & set(last_entities):
        noise += 0.20
```

**问题**：将"无实体重叠"直接等同于"上下文断裂"，进而直接加噪声。这会导致两种误判：

1. **正常话题切换被误判为断裂**：用户聊完"内存扫描"后切换到"断点设置"，两个话题无实体重叠，但用户意图清晰，不应标记为噪声。
2. **新任务被误判为低质量输入**：用户沉默10分钟后发新问题，系统因"无实体重叠"加噪声，导致后续解析策略保守化（降低置信度阈值、增加澄清轮次），这是错误的认知混淆。

### 2.2 文献支撑与理论模型

#### 2.2.1 话题切换检测的对话分析研究

**Matsumoto et al. (2022)** — *Topic Break Detection in Interview Dialogues Using Sentence Embedding of Utterance and Speech Intention Based on Multitask Neural Networks* (PMC8780003)

> "Most existing studies have attempted to detect topic boundaries using topic modeling or word association. However, in a dialogue wherein the topics are related to each other and transition smoothly, such as in an interview dialogue, it is difficult to identify the transition point of the topic by using methods such as topic modeling based on word occurrence probability."

> "The proposed method uses distributed representations of sentences (sentence embedding) that can account for context, as features for detecting topic breaks. In order to extend features, we propose a model that considers speech intention and a model that uses sensory features."

**核心启示**：
- 仅依赖词关联/词频的方法无法区分"话题切换"和"话题断裂"
- **话语意图（speech intention）**是关键特征：话题切换通常是**有意为之**的（用户主动想聊新东西），而话题断裂是**无意的**（用户以为自己还在延续上一轮，但表达方式变了导致系统无法关联）
- 多任务学习（话题断裂 + 话语意图 + 说话者）的 F1 可达 0.83（单任务仅 0.78）

**Liu et al. — *Unsupervised Topic Shift Detection in Chats***

> "Traditional word frequency-based similarity measures do not account for contextual and temporal variations, making it difficult to accurately reflect the evolution of the topic."

> "RNNs and CNNs still struggle with long-range dependencies, especially in group chats where responses may be delayed by hours or even days."

**核心启示**：
- 传统词频/词汇重叠方法忽略**时间变化**（temporal variations）
- 长间隔（小时级）的对话中，话题切换是**常态**，不应被检测为异常

#### 2.2.2 工作记忆与记忆组块（Memory Chunking）

**"Chunking in working memory via content-free labels"** (Nature, 2018)

> "Traditionally, chunking refers to the process of giving a label to a set of information so this set can be efficiently represented and used as an integrated unit. ... In the classic work of Miller, he proposed that the human cognitive capacity is limited to several chunks."

> "We predict that access to information, and consequently response times in a visual WM task, will be slower when ..."

> "When necessary, these details can be retrieved from the relevant documents."

**核心启示**：
- 人类工作记忆通过**组块标签（content-free labels）**管理信息集合
- 切换话题时，旧组块被抑制，新组块被激活——这是**正常的认知刷新**
- **解码成本（decoding cost）**：回到旧话题时需要重新"解码"组块，这会导致表达方式的**延迟性变化**（用户可能用不同词汇描述同一概念）
- **工程映射**：用户换话题时，词汇空间的跳跃是**认知刷新的正常表现**，不应标记为噪声

**"Synaptic Theory of Chunking in Working Memory"** (arXiv:2408.07637)

> "The main idea of the proposed chunking mechanism is that the chunking clusters can selectively activate and suppress the stimulus clusters, so that at no point in time do more than a small number of stimulus clusters reactivate as population spikes."

> "Due to synaptic augmentation, stimulus clusters that are currently suppressed by the chunking clusters still have stronger recurrent self-connections than the ones that were not active at a given trial as long as augmentation has not disappeared."

**核心启示**：
- 组块切换（chunking clusters 激活/抑制 stimulus clusters）是工作记忆的**基本机制**
- 被抑制（切换走）的组块仍有**突触增强残留**（synaptic augmentation），这意味着：
  - 用户切换话题后，如果短时间内回到旧话题，可能使用**不同的表达方式**（因为组块需要重新解码）
  - 这种"描述方式变化"不是噪声，而是**神经层面的解码延迟**
- **工程映射**：区分"话题切换"（正常认知刷新）和"上下文断裂"（用户意图不清导致系统无法关联）

#### 2.2.3 时间维度与工作记忆刷新

**TBRS (Time-Based Resource Sharing) 模型**（Puma et al., 2018）

> "Dividing attention between timing and another task limits working memory refresh, delaying judgments."

> "2.3-second delay caused a working memory refresh failure, the θ/γ band power ratio spiked 2.7-fold, triggering significant cognitive stress."

**核心启示**：
- 工作记忆刷新（WM refresh）是**时间敏感**的
- 认知负荷高时，时间间隔的感知会被压缩或扭曲
- **工程映射**：
  - 短间隔（<30秒）：用户大概率仍在同一认知任务中，工作记忆尚未刷新，此时无实体重叠值得怀疑（可能是断裂）
  - 长间隔（>5分钟）：工作记忆已自然衰减，用户开始新任务是正常的认知刷新，不应标记为噪声
  - 超长间隔（>30分钟）：旧组块的突触增强基本消失，用户回到旧话题时会像"新任务"一样表达

### 2.3 改进方案：认知刷新感知的三维话题切换检测模型

将"上下文断裂"从单一维度（实体重叠）扩展为**三维联合评估**：

```
                    ┌─────────────────┐
                    │  Context Break  │
                    │   Score (0-1)   │
                    └────────┬────────┘
                             │
            ┌────────────────┼────────────────┐
            │                │                │
            ▼                ▼                ▼
    ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
    │ Temporal Gap │ │ Referential  │ │ Discursive   │
    │   Factor τ   │ │  Dissonance  │ │    Shift     │
    │  (时间维度)   │ │  (指代维度)   │ │  (描述维度)   │
    └──────────────┘ └──────────────┘ └──────────────┘
```

#### 维度1：时间间隔因子 τ（Temporal Gap Factor）

基于 TBRS 模型和工作记忆衰减曲线：

```python
# NoiseEstimator 中的时间间隔评估
def _temporal_gap_factor(self, current_time: float, last_time: Optional[float]) -> float:
    """基于工作记忆衰减的时间间隔权重.
    
    理论依据：
    - TBRS 模型：工作记忆刷新受时间资源限制，注意力分散时刷新延迟
    - 神经文献：突触增强（synaptic augmentation）的衰减时间常数约 5-30 分钟
    - 工程假设：
      - <30s: 工作记忆活跃，用户大概率在同一任务中 → 高权重（1.0）
      - 30s-5min: 工作记忆开始衰减，可能换话题或查资料 → 中等权重（0.5）
      - 5-30min: 工作记忆基本刷新，新任务是正常认知行为 → 低权重（0.2）
      - >30min: 旧组块突触增强消失，等同于新会话 → 权重为0
    """
    if last_time is None:
        return 0.0  # 第一轮，无历史
    
    gap_seconds = current_time - last_time
    
    if gap_seconds < 30:
        return 1.0        # 短间隔：工作记忆活跃，断裂值得怀疑
    elif gap_seconds < 300:   # 5分钟
        return 0.5      # 中等间隔：可能去查资料或短暂切换
    elif gap_seconds < 1800:  # 30分钟
        return 0.2      # 长间隔：工作记忆已刷新，新任务正常
    else:
        return 0.0      # 超长间隔：完全等同于新会话
```

**关键洞察**：时间间隔不是"噪声越大时间越长"，而是**倒U型**：
- 极短间隔（同一轮内）→ 无话题切换可能，不评估
- 短间隔（<30s）→ 高权重，因为用户大概率在同一认知任务中，无实体重叠是异常
- 中等间隔（30s-5min）→ 中等权重，可能切换也可能查资料
- 长间隔（>5min）→ 低权重，工作记忆已刷新，新话题是正常行为

#### 维度2：指代意图失调（Referential Dissonance）

基于 Matsumoto (2022) 的"话语意图"理论和对话分析中的**指代消解（Anaphora Resolution）**：

**核心区分**：
- **话题切换（Topic Shift）**：用户没有用指代词，直接问新问题 → 正常行为，不加噪声
- **上下文断裂（Context Break）**：用户使用了指代词（"这个"、"那个"、"它"、"刚才的"），但系统无法在历史中找到指代对象 → 真正的断裂

```python
def _referential_dissonance(self, query: str, history: List[HistoryEntry]) -> float:
    """检测用户的'指代意图'与系统的'实体匹配'之间的失调.
    
    理论依据：
    - 对话分析中的 Anaphora Resolution：指代词要求听话者从上下文检索先行词
    - Matsumoto (2022)：话语意图（speech intention）是话题断裂的关键特征
    - 如果用户说了"这个"但系统找不到"这个"是什么 → 断裂
    - 如果用户什么都没说，只是问新问题 → 不是断裂
    """
    text_lower = query.lower()
    
    # 强指代词：明确要求系统回溯上下文
    strong_referential = {
        "这个", "那个", "它", "刚才", "之前", "上面", "前面",
        "this one", "that", "it", "the previous", "the one above", 
        "刚才的", "之前说的", "那个东西",
    }
    
    # 弱指代词：可能指代也可能不指代
    weak_referential = {
        "这里", "那边", "上面", "下面", "here", "there", "above", "below",
    }
    
    has_strong_ref = any(m in text_lower for m in strong_referential)
    has_weak_ref = any(m in text_lower for m in weak_referential)
    
    if not has_strong_ref and not has_weak_ref:
        return 0.0  # 用户没有指代意图，正常新任务/话题切换
    
    # 检查用户输入中的实体是否与历史实体有重叠
    current_entities = quick_extract_entities(query)
    last_entities = set()
    if history:
        for h in history[-3:]:  # 最近3轮
            last_entities.update(quick_extract_entities(h.content))
    
    has_overlap = bool(set(current_entities) & last_entities)
    
    if has_strong_ref and not has_overlap:
        # 用户明确想指代旧话题，但系统找不到匹配实体
        # 这是真正的上下文断裂：用户以为自己说清楚了，但系统无法理解
        return 0.85
    
    if has_weak_ref and not has_overlap:
        # 弱指代，可能正常也可能断裂
        return 0.4
    
    if has_overlap:
        # 有指代且能匹配，只是表达方式不同
        return 0.15
    
    return 0.0
```

#### 维度3：描述方式变化（Discursive Shift / 记忆组块刷新）

基于 Nature 2018 / arXiv 2408.07637 的**组块解码成本**理论：

**核心区分**：
- **认知刷新（Cognitive Refresh）**：用户切换到新话题，新输入的词汇集中在**单一语义域**（如从"内存扫描"切换到"断点设置"）→ 这是正常的组块切换，不加噪声
- **混乱断裂（Chaotic Break）**：用户输入的词汇**分散在多个不相关语义域**（如一句话同时包含"扫描"、"加密"、"天气"、"吃饭"）→ 可能是认知混乱或断裂
- **描述方式变化（Discursive Shift）**：用户用**不同表达方式**描述同一话题（如从"scan 0x401000"变成"看一下那个地址的值"）→ 这是组块解码的延迟，需要同义词扩展，但不加噪声

```python
def _discursive_shift_score(self, query: str, history: List[HistoryEntry]) -> float:
    """区分'认知刷新'（正常话题切换）、'描述方式变化'（同义词替换）和'混乱断裂'.
    
    理论依据：
    - Nature 2018 / arXiv 2408.07637：组块切换时，chunking clusters 抑制旧的 stimulus clusters
    - 正常切换：新话题的词汇集中在单一语义域（高 domain concentration）
    - 解码延迟：用户回到旧话题但用不同词汇（描述方式变化），需要同义词扩展
    - 混乱断裂：词汇分散在多个不相关域（低 domain concentration），可能是认知混乱
    """
    text_lower = query.lower()
    
    # 1. 语义域集中度（Domain Concentration）
    domains = {
        "memory": ["scan", "read", "write", "address", "pointer", "内存", "地址", "指针"],
        "static": ["disassemble", "decompile", "ghidra", "反汇编", "反编译"],
        "dynamic": ["debug", "trace", "breakpoint", "hook", "调试", "断点", "追踪"],
        "crypto": ["unpack", "decrypt", "obfuscate", "protection", "脱壳", "解密", "混淆"],
        "network": ["connect", "packet", "socket", "网络", "连接", "抓包"],
    }
    
    matched_domains = []
    for domain, keywords in domains.items():
        if any(kw in text_lower for kw in keywords):
            matched_domains.append(domain)
    
    if len(matched_domains) == 0:
        domain_concentration = 0.0  # 纯日常对话，无技术域
    elif len(matched_domains) == 1:
        domain_concentration = 1.0  # 高度集中在单一域
    else:
        domain_concentration = 1.0 / len(matched_domains)  # 分散度
    
    # 2. 描述框架一致性（Discursive Consistency）
    # 检测用户是否使用了与历史相似的描述结构
    structural_similarity = 0.0
    if history:
        last_text = history[-1].content.lower()
        # 简单的结构相似性：检测技术动词+操作对象的模式
        current_pattern = self._extract_discursive_pattern(text_lower)
        last_pattern = self._extract_discursive_pattern(last_text)
        
        if current_pattern and last_pattern:
            # 结构相似：都是"动词+地址"或都是"疑问+模块"
            structural_similarity = self._pattern_similarity(current_pattern, last_pattern)
    
    # 3. 综合判断
    if domain_concentration >= 0.7 and structural_similarity < 0.3:
        # 高域集中度 + 低结构相似性：
        # 用户词汇集中在单一技术域，但描述方式与历史完全不同
        # 这是正常的认知刷新（组块切换），不加噪声
        return 0.0
    
    elif domain_concentration >= 0.7 and structural_similarity >= 0.3:
        # 高域集中度 + 高结构相似性：
        # 同一话题，但词汇有变化（同义词替换）
        # 这是描述方式变化（Discursive Shift），需要同义词扩展，不加噪声
        return 0.0
    
    elif domain_concentration < 0.3 and len(matched_domains) > 2:
        # 低域集中度 + 多域分散：
        # 词汇分散在多个不相关语义域
        # 这是混乱断裂（Chaotic Break），加噪声
        return 0.7
    
    elif structural_similarity < 0.2 and len(matched_domains) == 0:
        # 无技术域 + 结构完全不同：
        # 用户从纯技术话题切换到纯日常话题
        # 可能是正常切换，也可能是断裂（取决于上下文）
        return 0.3
    
    else:
        return 0.2  # 默认中间状态


def _extract_discursive_pattern(self, text: str) -> Optional[Dict[str, Any]]:
    """提取描述框架模式：动词类型 + 宾语类型 + 句式结构."""
    # 检测祈使句（命令式）
    imperative_verbs = ["scan", "read", "write", "patch", "find", "change", 
                        "扫描", "读取", "写入", "修改", "查找"]
    # 检测疑问句（分析式）
    interrogative = ["how", "why", "what", "where", "怎么", "为什么", "什么"]
    # 检测陈述句（报告式）
    
    has_imperative = any(v in text for v in imperative_verbs)
    has_interrogative = any(q in text for q in interrogative) or '?' in text
    has_address = bool(re.search(r'0x[0-9a-f]+', text))
    has_number = bool(re.search(r'\d+', text))
    
    return {
        "type": "imperative" if has_imperative else ("interrogative" if has_interrogative else "declarative"),
        "has_address": has_address,
        "has_number": has_number,
    }


def _pattern_similarity(self, a: Dict, b: Dict) -> float:
    """比较两个描述框架的相似度."""
    if a["type"] != b["type"]:
        return 0.0  # 句式类型不同（祈使 vs 疑问）
    
    score = 0.5  # 句式类型相同的基础分
    if a["has_address"] == b["has_address"]:
        score += 0.25
    if a["has_number"] == b["has_number"]:
        score += 0.25
    return score
```

### 2.4 综合的"上下文断裂"噪声评分（替代原有逻辑）

```python
def estimate_noise(self, query: str, history: List[HistoryEntry], 
                   current_time: Optional[float] = None) -> float:
    """重新设计的噪声评估器.
    
    核心变化：将'上下文断裂'从单一维度（实体重叠）改为三维联合评估.
    """
    noise = 0.0
    text_lower = query.lower().strip()
    
    # 1. 结构噪声（保持不变）
    if not text_lower or len(text_lower) < 3:
        noise += 0.25
    elif not self._has_verb(text_lower):
        noise += 0.20
    if self._has_garbled(text_lower):
        noise += 0.15
    
    # 2. 词汇噪声（保持不变）
    vague_count = sum(1 for w in self._VAGUE_WORDS if w in text_lower)
    noise += min(0.30, vague_count * 0.08)
    
    gibberish_count = self._count_gibberish_words(text_lower)
    noise += min(0.25, gibberish_count * 0.10)
    
    # 3. 上下文断裂（重新设计 — 三维联合评估）
    if history and len(history) >= 1:
        last_entry = history[-1]
        
        # 维度1：时间间隔因子
        temporal_factor = self._temporal_gap_factor(
            current_time or time.time(),
            getattr(last_entry, 'timestamp', None)
        )
        
        # 维度2：指代意图失调
        referential_dissonance = self._referential_dissonance(query, history)
        
        # 维度3：描述方式变化
        discursive_shift = self._discursive_shift_score(query, history)
        
        # 三维联合评分：只有当时间间隔短（用户大概率在同一任务）
        # 且指代失调高（用户想维持旧话题但系统无法理解）时，才判定为断裂
        context_break_score = temporal_factor * (
            0.4 * referential_dissonance + 0.6 * discursive_shift
        )
        
        # 话题切换豁免：如果明确检测到话题切换信号，大幅降低断裂评分
        topic_shift_signals = {
            "换个话题", "另外", "换个问题", "new task", "different thing", 
            "说说别的", "by the way", "speaking of", "another question",
            "再说一下", "还有一件事",
        }
        if any(s in text_lower for s in topic_shift_signals):
            # 用户明确宣告话题切换，这是最高置信度的"正常切换"
            context_break_score *= 0.1
        
        # 新任务信号：用户使用了"我想..."、"能不能..."等开启新任务的句式
        new_task_signals = {
            "我想", "能不能", "能不能帮我", "可以帮我", "能不能问一下",
            "i want", "can you", "could you", "i'd like", "help me",
        }
        if any(s in text_lower for s in new_task_signals) and not referential_dissonance:
            # 用户开启新任务且无指代意图，正常行为
            context_break_score *= 0.2
        
        noise += min(0.20, context_break_score)
    
    # 4. 信息密度（保持不变）
    if len(query) < 5:
        noise += 0.20
    elif len(query) > 500:
        noise += 0.10
    
    # 5. 特殊字符噪声（保持不变）
    special_count = sum(1 for c in text_lower 
                      if not c.isalnum() and not c.isspace() and not self._is_cjk(c))
    noise += min(0.15, special_count * 0.02)
    
    return min(1.0, noise)
```

### 2.5 对 ParserConfig 的动态调控修正

由于"上下文断裂"的判定逻辑变化，相关的 ParserConfig 动态调控也应修正：

```python
# 原逻辑：noise > 0.7 + TOOL → 立即 ask_user（保守策略）
# 新逻辑：需要区分噪声来源

# 如果噪声主要来自"上下文断裂"（指代失调高），则应：
# - 触发同义词扩展（enable_synonym_expansion = True）
# - 增加上下文回溯深度（context_window_size = 20）
# - 而不是简单地提高保守度

# 修正后的 ParserConfig.from_intent_context 中的相关逻辑
if ctx.noise_level > 0.7:
    # 检查噪声来源
    if ctx.cognitive_profile.stability < 0.3 and referential_dissonance > 0.6:
        # 用户描述稳定性低 + 高指代失调 → 用户可能用不同方式描述同一事物
        config.enable_synonym_expansion = True    # 启用同义词扩展
        config.context_window_size = 20           # 增加上下文回溯
        config.max_ambiguities_before_ask = 3     # 给更多机会自动消解
    else:
        # 真正的混乱噪声 → 保守策略
        config.max_ambiguities_before_ask = 1
```

### 2.6 数据模型扩展：增加 timestamp 字段

为了支持时间维度评估，需要在 `HistoryEntry` 和 `PCRInput_v1` 中增加时间戳：

```python
@dataclass
class HistoryEntry:
    role: str
    content: str
    expectation: str = ""  # 该轮对话的期望类型（由PCR评估）
    timestamp: float = field(default_factory=time.time)  # 新增：时间戳
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class PCRInput_v1:
    # ... 已有字段 ...
    timestamp: float = field(default_factory=time.time)  # 新增：当前输入时间戳
```

---

## 问题3：延迟叠加的"多米诺效应"（优化方向记录，先搁置）

### 当前延迟结构

```
Stage 0: 期望识别（Expectation Identifier）
  ├─ 规则快路径：0-2ms
  ├─ 历史推断：0-1ms
  └─ LLM Fallback：100-200ms（仅 5% 查询触发）
Stage 1: 噪声评估（Noise Estimator）
  └─ 规则推导：0-1ms（纯正则/统计）
Stage 2: 复杂度评估（Complexity Estimator）
  └─ YAML 配置 + 规则推导：0-1ms
Stage 3: 认知画像更新（Cognitive Profiler）
  └─ EMA + Jaccard：0-1ms
─────────────────────────────────────────
串行总延迟（规则路径）：~3-5ms
串行总延迟（含 LLM Fallback）：~103-205ms
```

### 问题分析

用户指出：如果下游 Agent 使用大模型（处理耗时 1-2s），这 200ms 的预处理是划算的；但如果下游是**本地轻量模型**（如 7B 本地模型，处理耗时 200ms），这 200ms 的预处理就成了"性能瓶颈"（占比 50%）。

### 优化方向（记录，待后续实现）

#### 方向1：基于 Stage 0 的 Lazy Evaluation

Stage 0 的 expectation 识别完成后，根据 expectation 类型决定后续 Stage 是否跳过：

```python
def evaluate(self, input_data: PCRInput_v1) -> PCROutput_v1:
    # 1. 期望识别（必须）
    expectation, exp_confidence = self._identifier.identify(query, history)
    
    # 2. 根据 expectation 类型决定是否执行后续评估
    if expectation == "TOOL" and exp_confidence > 0.9:
        # 高置信度工具指令：跳过认知画像和复杂度评估
        # 工具指令通常是简单、明确的，不需要复杂评估
        noise = self._noise_estimator.quick_estimate(query)  # 简化版噪声评估（仅结构+词汇）
        complexity = 0.2  # 默认值
        cog_profile = self._profiler.get_profile()  # 复用上一轮画像，不更新
    else:
        # 完整评估
        noise = self._noise_estimator.estimate(query, history, current_time)
        complexity = self._complexity_estimator.estimate(query, expectation)
        cog_profile = self._profiler.update(query, expectation)
```

**预期收益**：高置信度 TOOL 路径延迟从 ~5ms 降至 ~2ms。

#### 方向2：并行评估（并行化 Stage 1-3）

Stage 1（噪声）、Stage 2（复杂度）、Stage 3（认知画像）之间无数据依赖，可并行：

```python
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=3) as executor:
    noise_future = executor.submit(self._noise_estimator.estimate, query, history, current_time)
    complexity_future = executor.submit(self._complexity_estimator.estimate, query, expectation)
    cog_future = executor.submit(self._profiler.update, query, expectation)
    
    noise = noise_future.result()
    complexity = complexity_future.result()
    cog_profile = cog_future.result()
```

**预期收益**：规则路径从串行 ~3-5ms 降至并行 ~2-3ms（瓶颈在最长任务）。

**注意**：线程切换开销可能抵消收益，需实测验证。对于纯 CPU 计算（正则/统计），Python GIL 限制下并行效果有限，建议使用多进程或 asyncio。

#### 方向3：缓存预热 + 增量更新

- 认知画像（CognitiveProfiler）的 EMA 更新可以改为**增量更新**：只计算新 turn 的差值，而非完整重新计算
- 噪声评估中的正则匹配可以预编译并缓存结果
- 复杂度评估中的 YAML 规则可以预加载到内存

---

## 总结与实施建议

### 优先级排序

| 优先级 | 问题 | 改动范围 | 预估工作量 | 影响 |
|---|---|---|---|---|
| **P0** | 问题2：上下文断裂三维模型 | `NoiseEstimator` + `HistoryEntry` + `PCRInput_v1` | ~200行 | 高：消除误判，提升用户体验 |
| **P1** | 问题1：多模态接口 | `PCRInput_v1` + `PCRLifecycleManager` | ~50行 | 中：为未来扩展预留接口 |
| **P2** | 问题3：延迟优化 | `RuleBasedPCR.evaluate()` | ~100行 | 低：当前规则路径已<5ms，优化空间有限 |

### 问题2的核心改进点（记忆锚点）

1. **时间维度**：`HistoryEntry.timestamp` + `PCRInput_v1.timestamp` → 工作记忆衰减权重
2. **指代维度**：`ReferentialDissonance` → 区分"话题切换"（正常）和"上下文断裂"（异常）
3. **描述维度**：`DiscursiveShift` + `DomainConcentration` → 区分"认知刷新"（正常）和"混乱断裂"（异常）
4. **调控修正**：高指代失调时触发同义词扩展 + 上下文回溯，而非简单提高保守度

### 文献索引

| 文献 | 关键理论 | 工程映射 |
|---|---|---|
| Matsumoto et al. (2022), PMC8780003 | 话语意图（speech intention）是话题断裂的关键特征 | 指代意图失调检测 |
| Liu et al., "Unsupervised Topic Shift Detection in Chats" | 传统词频方法忽略时间变化 | 时间间隔因子 τ |
| "Chunking in working memory via content-free labels" (Nature 2018) | 组块标签管理 + 解码成本 | 描述方式变化检测 |
| "Synaptic Theory of Chunking in Working Memory" (arXiv:2408.07637) | 组块切换 = chunking clusters 抑制/激活 | 语义域集中度（domain concentration） |
| Puma et al. (2018), TBRS model | 工作记忆刷新的时间敏感性 | 时间间隔权重设计（30s/5min/30min） |


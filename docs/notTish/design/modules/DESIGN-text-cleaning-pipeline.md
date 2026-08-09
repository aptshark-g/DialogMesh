# 学术文本清洗与预处理工程方案

## 文献依据

基于以下文献的综合方法：
- Kadhim (2018), Kathuria et al. (2021): 文本预处理 surveys
- Kowsari et al. (2019): 传统 NLP pipeline 数据预处理
- ChemNLP / Materials Science LLM extraction: 学术文档清洗（正则提取实验部分，去除作者/致谢/参考文献）
- GeekFlare NLP Text Cleaning: 噪声实体移除、HTML/LaTeX 处理、正则分词

---

## 1. 问题诊断

### 1.1 当前系统问题

| 问题 | 现象 | 根因 |
|------|------|------|
| LaTeX 噪音 | 关键词 top10: alpha, cdot, frac, mathcal | 未清洗 LaTeX 命令 |
| 列表符号噪音 | TF-IDF top: `•`, `◦`, `1.`, `2.` | 未清洗列表标记 |
| 中文分词失败 | 高频词未提取 | 未使用中文分词器 |
| 评分溢出 | composite=1.508 | 未标准化 deconstruction score |
| 语义桥接失效 | 返回空 | 格式符号污染向量 |

### 1.2 学术文本的特殊性

与社交媒体/通用文本不同：
- **公式密集**: LaTeX 数学表达式需要语义保留而非简单删除
- **双语混排**: 中文学术论文常混排英文术语
- **结构化**: 有明确的元概念/定义/公理/定理/推论层级
- **引用密集**: 需要保留或标注引用关系

---

## 2. 清洗 Pipeline 设计

### Stage 1: 结构解析（Structure Extraction）

在清洗前，先提取结构性信息，避免破坏语义层级。

```python
def extract_structure(text: str) -> dict:
    """提取论文结构，保留层级关系。"""
    return {
        "sections": [...],      # 第一部分/第二部分... 或 Introduction/Method...
        "theorems": [...],     # 定理内容及编号
        "axioms": [...],       # 公理内容及编号
        "definitions": [...],  # 定义块
        "formulas": [...],     # 独立公式块
        "references": [...],   # 参考文献
    }
```

### Stage 2: LaTeX 语义化（LaTeX Semantic Normalization）

**不是删除 LaTeX，而是将其转化为可读的文本。**

| LaTeX 模式 | 处理方式 | 示例 |
|-----------|---------|------|
| `\alpha`, `\beta`, `\gamma` | 保留希腊字母名称 | `alpha` → `alpha` |
| `\frac{a}{b}` | 转换为 `a/b` | `\frac{1}{2}` → `1/2` |
| `\mathcal{F}` | 保留字母 | `\mathcal{F}` → `F` |
| `\text{xxx}` | 提取文本内容 | `\text{inertia}` → `inertia` |
| `\mathbb{I}` | 保留符号含义 | `\mathbb{I}` → `I` (indicator) |
| `\cdot` | 移除或替换为空格 | `a \cdot b` → `a b` |
| `\left(`, `\right)` | 保留括号 | `\left(a\right)` → `(a)` |
| `\begin{cases}...\end{cases}` | 提取条件文本 | 分段函数 → 文本描述 |
| `_{xxx}` 下标 | 用 `_` 连接 | `C_{inertia}` → `C_inertia` |
| `^{xxx}` 上标 | 用 `^` 连接 | `x^{2}` → `x^2` |

**实现策略：**
- 正则匹配：对于简单模式（`\alpha`, `\cdot`）
- 栈解析：对于嵌套结构（`\frac`, `\begin{cases}`）
- 白名单：只处理已知 LaTeX 命令，未知命令保留原样或标记

### Stage 3: 数学符号标准化

| 符号 | 转换 | 语义保留 |
|------|------|---------|
| `Δ` (Delta) | `Delta` | 变化量 |
| `∂` | `partial` | 偏导数 |
| `∇` | `nabla` | 梯度 |
| `∫` | `integral` | 积分 |
| `Σ` | `sum` | 求和 |
| `∈` | `in` | 属于 |
| `→` | `to` | 映射/趋向 |
| `≥`, `≤` | `>=`, `<=` | 不等式 |
| `·` | 空格 | 点乘 |
| `•`, `◦` | 移除 | 列表符号 |

### Stage 4: 列表与格式清洗

```python
# 列表标记
r'^[\s]*[•◦·▪▫○●◎◇◆□■△▲▽▼][\s]*'  → 移除
r'^[\s]*\d+[\.\)][\s]*'               → 移除编号
r'^[\s]*[\-\–\—][\s]*'                → 统一为标记

# 多余空白
r'\n{3,}'  → '\n\n'  # 最多保留2个换行
r'[ \t]+'  → ' '     # 多个空格/Tab 统一
```

### Stage 5: 中文分词（Jieba）

```python
import jieba
import jieba.posseg as pseg

# 加载自定义词典（学术术语）
jieba.add_word('公理化体系')
jieba.add_word('认知惯性')
jieba.add_word('双惯性')
jieba.add_word('惯性成本')

# 分词 + 词性标注
words = pseg.cut(text)
# 保留: 名词(n), 动词(v), 形容词(a), 英文术语(eng)
# 过滤: 标点(x), 助词(u), 副词(d), 介词(p)
```

### Stage 6: 停用词过滤

```python
# 英文停用词（学术增强版）
# 保留通常去掉的术语：system, model, method, algorithm, analysis
# 增加学术专属停用词：respectively, herein, thereof, thereof, hereinbefore

# 中文停用词（哈工大停用词表）
# 保留：未、不、无、否（否定语义重要）
```

### Stage 7: 质量验证（Quality Check）

清洗后必须验证：

```python
def validate_cleaning(original: str, cleaned: str) -> dict:
    """验证清洗质量。"""
    return {
        "retention_rate": len(cleaned) / len(original),  # 应保留 >60%
        "latex_remaining": count_latex_commands(cleaned),  # 应 <5
        "symbol_remaining": count_symbols(cleaned),  # 应 <10
        "chinese_ratio": chinese_char_ratio(cleaned),  # 中文论文应 >30%
        "avg_word_length": avg_word_length(cleaned),  # 应 >2
    }
```

---

## 3. 修复其他问题

### 3.1 Deconstruction Score 标准化

**原公式（溢出）：**
```python
dec_score = (theorems + axioms + formal_defs) / 20  # 50+56+... / 20 = 5.45
```

**修正公式（标准化到 [0,1]）：**
```python
def compute_deconstruction_score(theorems, axioms, formal_defs, has_what, has_why, has_physics, has_math, has_engineering, has_failures) -> float:
    """六层解构完整性评分，归一化到 [0,1]。"""
    # 理论丰富度 (0-0.4)
    theory_score = min((theorems + axioms) / 40, 0.4)  # 40个定理+公理 = 满分
    
    # 形式化程度 (0-0.2)
    formal_score = min(formal_defs / 20, 0.2)  # 20个形式化定义 = 满分
    
    # 六层覆盖度 (0-0.4)
    layer_coverage = sum([has_what, has_why, has_physics, has_math, has_engineering, has_failures]) / 6
    layer_score = layer_coverage * 0.4
    
    return theory_score + formal_score + layer_score  # 总范围 [0,1]
```

### 3.2 语义桥接噪声过滤

```python
def filter_noise_dimensions(vec: dict[str, float]) -> dict[str, float]:
    """过滤 TF-IDF 向量中的噪声维度。"""
    NOISE_PATTERNS = [
        r'^[•◦·▪▫○●◎◇◆□■△▲▽▼]$',  # 列表符号
        r'^\d+[\.\)]?$',  # 数字编号
        r'^[=\+\-\*/\(\)\[\]\{\}\^\_\|<>\~\;\:\,\.\?!"\'\`]+$',  # 纯标点
        r'^\\[a-zA-Z]+$',  # 残留 LaTeX 命令
        r'^[αβγδεζηθικλμνξοπρστυφχψω]$',  # 希腊单字
        r'^.$',  # 单字符
    ]
    
    filtered = {}
    for word, weight in vec.items():
        if any(re.match(p, word) for p in NOISE_PATTERNS):
            continue
        if len(word) < 2:  # 过滤单字符
            continue
        filtered[word] = weight
    
    return filtered
```

### 3.3 触发链语义验证

```python
def validate_cross_domain_trigger(domain_a_nodes, domain_b_nodes, min_semantic_sim=0.15) -> bool:
    """跨域类比信号必须基于真实语义相似度，而非单纯存在性。"""
    # 计算两个域的语义重心向量
    centroid_a = compute_centroid(domain_a_nodes)
    centroid_b = compute_centroid(domain_b_nodes)
    
    sim = cosine_similarity(centroid_a, centroid_b)
    return sim >= min_semantic_sim
```

---

## 4. 实现计划

### Phase 1: 文本清洗模块（2-3小时）

```
lcortex/analysis/text_cleaner.py
  ├── class AcademicTextCleaner
  │   ├── extract_structure()    → 结构解析
  │   ├── normalize_latex()      → LaTeX 语义化
  │   ├── normalize_math()       → 数学符号标准化
  │   ├── clean_formatting()     → 列表/格式清洗
  │   ├── tokenize_chinese()     → Jieba 分词
  │   ├── remove_stopwords()     → 停用词过滤
  │   └── validate()             → 质量验证
  └── class TextCleaningPipeline
      └── run() → 串联所有 Stage
```

### Phase 2: 评分修复（1小时）

```
lcortex/coordination/quant_eval.py
  └── compute_deconstruction_score() → 标准化公式
```

### Phase 3: 语义桥接修复（1小时）

```
lcortex/inference/divergent/semantic_bridge.py
  └── filter_noise_dimensions() → 噪声过滤
lcortex/coordination/trigger_chain.py
  └── validate_cross_domain_trigger() → 语义验证
```

---

## 5. 验证指标

| 指标 | 清洗前 | 清洗后目标 |
|------|--------|-----------|
| LaTeX 噪音占比 | ~40% | <5% |
| 列表符号噪音 | ~15% | <1% |
| 有效中文词汇提取 | ~20% | >60% |
| 语义桥接成功率 | 0% | >30% |
| Deconstruction score | 5.45 (溢出) | [0,1] |
| Composite score | 1.508 (溢出) | [0,1] |

---

*方案时间: 2026-06-21 02:15 CST*
*参考文献: Kadhim 2018, Kowsari 2019, ChemNLP, GeekFlare NLP Pipeline*

# 三问题修复方案 — 形式化转换、多级清洗、多维评分

## 问题一：形式化语义转换器（Formalization-to-Concept Translator）

### 核心思路
论文中 `Delta E = E_实 - E_内` 不是噪音，而是**被压缩的语义**。`
alpha`, `Delta`, `lambda` 等不是无意义符号，而是有明确定义的变量。我们需要一个模块将其「解压」为概念。

### 实现方案

```python
# lcortex/analysis/formalization_extractor.py

class FormalizationExtractor:
    """从数学公式中提取语义概念。
    
    输入: 清洗后的文本 + 提取的公式列表 + 定义列表
    输出: 变量→概念映射 + 公式语义描述
    """
    
    def __init__(self):
        # 变量定义模式："E_{内} 为主体对事件的默认预期"
        self.var_def_pattern = re.compile(
            r'([A-Za-z]_?\{[^}]+\}|[A-Za-z][a-zA-Z_]*)\s*[:：]\s*为\s*(.+?)(?:[；;。]|\n|$)'
        )
        # 形式化定义模式："定义 X：..."
        self.formal_def_pattern = re.compile(
            r'(?:定义|Definition)\s*[\d\.]*\s*[:：]\s*(.+?)(?=\n|$)'
        )
    
    def extract_variable_definitions(self, text: str, formulas: List[str]) -> Dict[str, str]:
        """提取变量定义映射。
        
        示例:
            E_{内} → "主体对事件的默认预期（基准预期阈值）"
            Delta E → "预期偏差 = 实际结果 - 内部基准预期"
            alpha → "曲率系数（取值 0.8-0.95）"
        """
        var_map = {}
        
        # 1. 从文本中扫描变量解释
        for m in self.var_def_pattern.finditer(text):
            var, meaning = m.group(1).strip(), m.group(2).strip()
            var_map[var] = meaning[:200]
        
        # 2. 从公式中反向推导变量含义
        for formula in formulas:
            # 提取公式左侧的被定义量
            lhs_match = re.match(r'([A-Za-z][a-zA-Z_]*(?:_\{[^}]+\})?)\s*=', formula)
            if lhs_match:
                var = lhs_match.group(1)
                if var not in var_map:
                    var_map[var] = self._infer_meaning_from_formula(formula)
        
        return var_map
    
    def _infer_meaning_from_formula(self, formula: str) -> str:
        """从公式结构推断语义。"""
        # 简单启发式
        if 'partial' in formula:
            return "偏导数/变化率"
        if 'sum' in formula or 'integral' in formula:
            return "累积量/积分量"
        if 'Delta' in formula:
            return "偏差/变化量"
        if 'sigma' in formula:
            return "标准差/波动度量"
        return "未命名变量"
    
    def translate_formula_to_concept(self, formula: str, var_map: Dict[str, str]) -> str:
        """将公式翻译为自然语言描述。
        
        示例:
            "Delta E = E_实 - E_内" 
            → "预期偏差等于实际兑现值减去基准预期阈值"
        """
        result = formula
        # 按变量长度降序替换，避免子串冲突
        for var, meaning in sorted(var_map.items(), key=lambda x: -len(x[0])):
            result = result.replace(var, meaning)
        
        # 清理残留符号
        result = result.replace('=', '等于').replace('+', '加上').replace('-', '减去')
        result = re.sub(r'[\\{}_^]', '', result)
        
        return result[:300]
    
    def build_formula_semantic_graph(self, formulas: List[str], var_map: Dict[str, str]) -> Dict:
        """构建公式语义图（变量→概念→关系）。"""
        graph = {"nodes": [], "edges": []}
        
        for formula in formulas:
            # 提取等式两边的变量
            vars_in_formula = re.findall(r'[A-Za-z][a-zA-Z_]*(?:_\{[^}]+\})?', formula)
            for var in set(vars_in_formula):
                if var in var_map:
                    graph["nodes"].append({"var": var, "concept": var_map[var]})
            
            # 如果有等号，建立关系边
            if '=' in formula:
                parts = formula.split('=', 1)
                lhs_vars = re.findall(r'[A-Za-z][a-zA-Z_]*(?:_\{[^}]+\})?', parts[0])
                rhs_vars = re.findall(r'[A-Za-z][a-zA-Z_]*(?:_\{[^}]+\})?', parts[1])
                for lv in lhs_vars:
                    for rv in rhs_vars:
                        if lv in var_map and rv in var_map:
                            graph["edges"].append({
                                "from": lv, "to": rv,
                                "relation": "defined_by",
                                "formula": formula[:100]
                            })
        
        return graph
```

### 预期效果

| 输入 | 输出 |
|------|------|
| `Delta E = E_实 - E_内` | "预期偏差 = 实际兑现值 - 基准预期阈值" |
| `alpha ≈ 0.88` | "曲率系数约等于 0.88" |
| `U = sigma(E) / (|mu(E)| + epsilon)` | "不确定性系数 = 标准差 / (绝对均值 + 小量)" |

**关键词变化：**
- 修复前 Top 3: `alpha`(35), `delta`(34), `演绎依据`(29)
- 修复后预期 Top 3: `预期偏差`, `基准预期`, `曲率系数`

---

## 问题二：多级清洗 Pipeline（Multi-Pass Cleaning）

### 核心思路
清洗不是一次性的，而是**多阶段递进 + 质量验证反馈**。

### 实现方案

```python
# lcortex/analysis/text_cleaner.py — 扩展

class AcademicTextCleaner:
    def __init__(self, ...):
        # ... 现有初始化 ...
        self.passes = 0
        self.max_passes = 3
    
    def clean(self, text: str) -> CleaningReport:
        """多级清洗，带质量反馈。"""
        report = None
        for pass_num in range(self.max_passes):
            self.passes = pass_num + 1
            report = self._clean_single_pass(text, pass_num)
            
            # 质量检查
            quality = self._assess_tokenization_quality(report.cleaned_text)
            if quality["score"] >= 0.8:
                break  # 质量达标，提前退出
            
            # 质量不达标，调整参数进行下一轮
            text = self._prepare_for_next_pass(report.cleaned_text, quality)
        
        report.pass_count = self.passes
        return report
    
    def _assess_tokenization_quality(self, text: str) -> dict:
        """评估分词质量。
        
        质量指标:
        1. 超长 token 比例（>50 字符）
        2. 中英文边界混乱比例
        3. 纯标点 token 比例
        4. 数字-字母混合 token 比例
        """
        tokens = self.tokenize(text)
        
        total = len(tokens)
        if total == 0:
            return {"score": 0.0}
        
        long_tokens = sum(1 for t in tokens if len(t) > 50)
        boundary_issues = sum(1 for t in tokens if re.search(r'[\u4e00-\u9fa5][a-zA-Z]|[a-zA-Z][\u4e00-\u9fa5]', t))
        punct_tokens = sum(1 for t in tokens if re.match(r'^[^\w\u4e00-\u9fa5]+$', t))
        
        # 扣分制
        penalties = (
            long_tokens / total * 0.4 +      # 超长 token 最多扣 0.4
            boundary_issues / total * 0.3 +   # 边界问题最多扣 0.3
            punct_tokens / total * 0.3        # 标点 token 最多扣 0.3
        )
        
        score = max(0, 1 - penalties)
        return {
            "score": score,
            "long_ratio": long_tokens / total,
            "boundary_ratio": boundary_issues / total,
            "punct_ratio": punct_tokens / total,
            "token_count": total,
        }
    
    def _prepare_for_next_pass(self, text: str, quality: dict) -> str:
        """为下一轮清洗准备文本。"""
        # 如果超长 token 多，增加空格分隔
        if quality["long_ratio"] > 0.1:
            # 在中英文交界处插入空格
            text = re.sub(r'([\u4e00-\u9fa5])([a-zA-Z])', r'\1 \2', text)
            text = re.sub(r'([a-zA-Z])([\u4e00-\u9fa5])', r'\1 \2', text)
        
        # 如果边界问题多，标准化标点
        if quality["boundary_ratio"] > 0.05:
            text = text.replace('（', ' ( ').replace('）', ' ) ')
            text = text.replace('，', ' , ').replace('。', ' . ')
        
        return text
```

### 新增 Stage 0：边界标准化

```python
def _normalize_boundaries(self, text: str) -> str:
    """Stage 0: 在中英文、数字、中文之间插入空格。"""
    # CJK + ASCII 字母
    text = re.sub(r'([\u4e00-\u9fa5])([a-zA-Z])', r'\1 \2', text)
    text = re.sub(r'([a-zA-Z])([\u4e00-\u9fa5])', r'\1 \2', text)
    # CJK + 数字
    text = re.sub(r'([\u4e00-\u9fa5])(\d)', r'\1 \2', text)
    text = re.sub(r'(\d)([\u4e00-\u9fa5])', r'\1 \2', text)
    # 连续标点拆分
    text = re.sub(r'([。，；：！？、）（])([^\s])', r'\1 \2', text)
    return text
```

### 预期效果

| 轮次 | 超长 token 比例 | 边界问题比例 | 质量分 |
|------|----------------|-------------|--------|
| Pass 1 | 15% | 8% | 0.55 → 继续 |
| Pass 2 | 3% | 2% | 0.82 → 停止 |

---

## 问题三：多维 Deconstruction Score

### 核心思路
当前公式只数「有几个」，不评估「质量如何」。引入**完成度惩罚**和**验证维度**。

### 实现方案

```python
def compute_deconstruction_score_v2(
    theorems: int = 0,
    axioms: int = 0,
    formal_defs: int = 0,
    has_what: bool = False,
    has_why: bool = False,
    has_physics: bool = False,
    has_math: bool = False,
    has_engineering: bool = False,
    has_failures: bool = False,
    # 新增参数
    completeness_ratio: float = 1.0,      # 完成度 = 1 - (待补全数 / 总条目数)
    has_proofs: bool = False,              # 是否有严格证明
    has_experiments: bool = False,         # 是否有实验/仿真验证
    has_data: bool = False,                # 是否有数据支撑
    citation_count: int = 0,               # 引用数量
    cross_ref_density: float = 0.0,        # 交叉引用密度
) -> dict:
    """六层解构完整性评分 v2，返回分数 + 维度明细。"""
    
    # 1. 理论丰富度 (0-0.30)，降低权重
    theory_score = min((theorems + axioms) / 50, 0.30)
    
    # 2. 形式化程度 (0-0.15)
    formal_score = min(formal_defs / 25, 0.15)
    
    # 3. 六层覆盖度 (0-0.20)
    layer_coverage = sum([has_what, has_why, has_physics, has_math, has_engineering, has_failures]) / 6
    layer_score = layer_coverage * 0.20
    
    # 4. 完成度惩罚 (0-0.15)
    # 如果有大量【待补全】，分数降低
    completeness_score = max(0, completeness_ratio) * 0.15
    
    # 5. 验证维度 (0-0.20)
    verification = sum([has_proofs, has_experiments, has_data]) / 3
    verification_score = verification * 0.20
    
    # 6. 学术规范 (0-0.10)
    citation_score = min(citation_count / 20, 0.05)  # 20 引用 = 满分
    cross_ref_score = min(cross_ref_density * 5, 0.05)  # 密度 0.2 = 满分
    academic_score = citation_score + cross_ref_score
    
    total = round(theory_score + formal_score + layer_score + 
                  completeness_score + verification_score + academic_score, 3)
    
    return {
        "total": total,
        "dimensions": {
            "theory": round(theory_score, 3),
            "formal": round(formal_score, 3),
            "layer_coverage": round(layer_score, 3),
            "completeness": round(completeness_score, 3),
            "verification": round(verification_score, 3),
            "academic": round(academic_score, 3),
        },
        "penalties": {
            "incomplete_markers": 1 - completeness_ratio,
            "no_experimental_validation": not has_experiments,
            "no_data": not has_data,
        }
    }
```

### 应用到认知论文

| 维度 | 值 | 得分 |
|------|-----|------|
| 理论丰富度 | 34 条目 / 50 | 0.204 |
| 形式化程度 | 17 定义 / 25 | 0.102 |
| 六层覆盖 | 6/6 | 0.200 |
| 完成度 | ~40% 【待补全】 | 0.090 |
| 验证 | 0/3（无证明/实验/数据） | 0.000 |
| 学术规范 | 引用较少 | 0.020 |
| **总计** | — | **~0.616** |

**vs 旧公式：1.000 → 新公式：0.616**

更真实反映这是一篇「理论框架草案」而非「完整论文」。

---

---

## 新增模块一：存疑系统（Uncertainty Tracker）

### 设计动机

L2 学科变量库需要不断填充，但论文可能：
1. 使用非标准变量名（如用 `zeta` 代替 `xi`）
2. 变量名拼写错误（如 `alhpa`）
3. 自定义符号无解释（如 `mathcal{G}` 未定义）
4. 公式结构无法识别为已知模式

**不能静默忽略，必须显式存疑。**

### 架构设计

```python
# lcortex/analysis/uncertainty_tracker.py

from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum

class UncertaintyLevel(Enum):
    INFO = "info"          # 提示，不影响流程
    WARNING = "warning"    # 警告，可能影响理解
    CRITICAL = "critical"  # 严重，必须人工介入

@dataclass
class UncertaintyRecord:
    id: str                    # 唯一标识
    level: UncertaintyLevel
    category: str              # 类别: variable_unknown / variable_typo / formula_unrecognized / domain_mismatch
    source: str                # 来源公式/文本片段
    context: str               # 上下文
    suggested_action: str      # 建议操作: ignore / consult_llm / manual_review
    resolved: bool = False
    resolution: Optional[str] = None  # 人工标注的解决方式
    
class UncertaintyTracker:
    """存疑追踪器：收集所有无法自动解析的问题。"""
    
    def __init__(self, auto_escalate: bool = False):
        self.records: List[UncertaintyRecord] = []
        self.auto_escalate = auto_escalate  # 是否自动上报
    
    def add(self, level: UncertaintyLevel, category: str, source: str, 
            context: str, suggested_action: str = "ignore"):
        record = UncertaintyRecord(
            id=f"U-{len(self.records)+1:04d}",
            level=level,
            category=category,
            source=source,
            context=context,
            suggested_action=suggested_action,
        )
        self.records.append(record)
        return record.id
    
    def query(self, level: Optional[UncertaintyLevel] = None, 
              category: Optional[str] = None) -> List[UncertaintyRecord]:
        """按条件查询存疑记录。"""
        results = self.records
        if level:
            results = [r for r in results if r.level == level]
        if category:
            results = [r for r in results if r.category == category]
        return results
    
    def export_for_llm(self) -> str:
        """导出为 LLM 可读的格式，用于 Claw 模式协同。"""
        critical = self.query(level=UncertaintyLevel.CRITICAL)
        if not critical:
            return "无严重存疑项。"
        
        lines = ["# 存疑清单（需人工/LLM 协助）\n"]
        for r in critical:
            lines.append(f"## {r.id}: {r.category}")
            lines.append(f"- 来源: `{r.source}`")
            lines.append(f"- 上下文: {r.context[:200]}")
            lines.append(f"- 建议: {r.suggested_action}\n")
        return "\n".join(lines)
    
    def get_summary(self) -> dict:
        """统计摘要。"""
        return {
            "total": len(self.records),
            "critical": len(self.query(level=UncertaintyLevel.CRITICAL)),
            "warning": len(self.query(level=UncertaintyLevel.WARNING)),
            "info": len(self.query(level=UncertaintyLevel.INFO)),
            "by_category": {
                cat: len(self.query(category=cat))
                for cat in set(r.category for r in self.records)
            }
        }
```

### 与 FormalizationExtractor 的集成

```python
class FormalizationExtractor:
    def __init__(self, tracker: Optional[UncertaintyTracker] = None):
        self.tracker = tracker or UncertaintyTracker()
        self.var_map: Dict[str, str] = {}
        
    def extract_with_uncertainty(self, text: str, formulas: List[str]) -> Dict[str, str]:
        """提取变量定义，同时追踪存疑项。"""
        
        # 1. L1: 显式定义提取
        for m in self.var_def_pattern.finditer(text):
            var, meaning = m.group(1).strip(), m.group(2).strip()
            self.var_map[var] = meaning
        
        # 2. L2: 学科库匹配
        for formula in formulas:
            vars_found = re.findall(r'[A-Za-z][a-zA-Z_]*(?:_\{[^}]+\})?', formula)
            for var in set(vars_found):
                if var not in self.var_map:
                    # 尝试学科库
                    concept = self._lookup_domain_variable(var)
                    if concept:
                        self.var_map[var] = concept
                    else:
                        # 存疑：未知变量
                        self.tracker.add(
                            level=UncertaintyLevel.WARNING,
                            category="variable_unknown",
                            source=formula[:100],
                            context=f"变量 {var} 在文本中无显式定义，也不在学科库中",
                            suggested_action="consult_llm"  # 建议转 LLM
                        )
        
        # 3. 拼写检查
        for var in list(self.var_map.keys()):
            typo_match = self._check_typo(var)
            if typo_match and typo_match != var:
                self.tracker.add(
                    level=UncertaintyLevel.INFO,
                    category="variable_typo",
                    source=var,
                    context=f"变量 {var} 可能是 {typo_match} 的拼写变体",
                    suggested_action="ignore"
                )
        
        return self.var_map
    
    def _lookup_domain_variable(self, var: str) -> Optional[str]:
        """查询学科库。"""
        # 按学科优先级查询
        for domain, mapping in DEFAULT_VARIABLES.items():
            if var in mapping:
                return f"[{domain}] {mapping[var]}"
        return None
    
    def _check_typo(self, var: str) -> Optional[str]:
        """简单拼写检查（编辑距离）。"""
        # 常见拼写错误映射
        TYPO_MAP = {
            "alhpa": "alpha", "aplha": "alpha",
            "lamdba": "lambda", "labmda": "lambda",
            "epislon": "epsilon", "epslion": "epsilon",
        }
        return TYPO_MAP.get(var.lower())
```

### 存疑流转路径

```
论文处理
    ↓
FormalizationExtractor.extract_with_uncertainty()
    ↓
├─ 变量已定义/已匹配 → 直接映射
├─ 变量未知 → 存疑记录(WARNING, suggested_action="consult_llm")
├─ 变量拼写错误 → 存疑记录(INFO, suggested_action="ignore")
└─ 公式无法识别 → 存疑记录(CRITICAL, suggested_action="manual_review")
    ↓
UncertaintyTracker.export_for_llm() → Claw 模式
    ↓
人工审阅 / LLM 推断 / 忽略
    ↓
记录 resolution，更新学科库（如确认有效）
```

---

## 新增模块二：外部依赖可选配置 + Claw 模式协同

### 设计原则

- **默认零外部依赖**：不装 mecab、不调用 API 也能跑
- **用户自选增强**：配置文件开启外部依赖
- **Claw 模式兜底**：无外部依赖时，转本地 Claw 协同

### 配置设计

```python
# lcortex/config/cleaner_config.py

from dataclasses import dataclass
from typing import Optional

@dataclass
class CleanerConfig:
    """清洗模块配置。"""
    
    # 基础配置（必须）
    language: str = "auto"  # auto/zh/en/ja/de
    
    # 分词器选择
    tokenizer: str = "auto"  # auto/jieba/mecab/spacy/whitespace
    
    # 外部依赖开关
    use_jieba: bool = True           # 中文分词，默认启用（纯Python）
    use_mecab: bool = False          # 日文分词，默认关闭
    use_spacy: bool = False          # 多语言NLP，默认关闭
    
    # Claw 模式
    claw_mode: bool = False          # 是否启用 Claw 协同
    claw_provider: str = "openclaw"  # openclaw / local
    
    # 多级清洗
    multi_pass: bool = True
    max_passes: int = 3
    quality_threshold: float = 0.7
    
    # 存疑系统
    uncertainty_tracking: bool = True
    auto_escalate: bool = False      # 是否自动上报严重存疑

    def validate(self):
        """验证配置合法性。"""
        if self.use_mecab and not self._check_mecab():
            raise ImportError("mecab 未安装，请 pip install mecab-python3 或关闭 use_mecab")
        if self.use_spacy and not self._check_spacy():
            raise ImportError("spacy 未安装，请 pip install spacy 或关闭 use_spacy")
    
    def _check_mecab(self) -> bool:
        try:
            import MeCab
            return True
        except ImportError:
            return False
    
    def _check_spacy(self) -> bool:
        try:
            import spacy
            return True
        except ImportError:
            return False
```

### 语言感知分词器选择逻辑

```python
def get_tokenizer(config: CleanerConfig, text: str):
    """根据配置和文本选择分词器。"""
    
    # 检测语言
    lang = detect_language(text) if config.language == "auto" else config.language
    
    # 按优先级选择分词器
    if lang == "zh":
        if config.use_jieba:
            return jieba.cut
        return lambda t: t.split()  # 降级：空格分词
    
    elif lang == "ja":
        if config.use_mecab:
            import MeCab
            tagger = MeCab.Tagger()
            return lambda t: [w.split("\t")[0] for w in tagger.parse(t).split("\n") if "\t" in w]
        return lambda t: t.split()  # 降级
    
    elif lang in ("en", "de"):
        if config.use_spacy:
            import spacy
            nlp = spacy.load("en_core_web_sm" if lang == "en" else "de_core_news_sm")
            return lambda t: [tok.text for tok in nlp(t)]
        return lambda t: t.split()  # 简单空格分词
    
    # 默认
    return lambda t: t.split()
```

### Claw 模式协同流程

```python
class ClawModeAssistant:
    """Claw 模式：本地模板匹配辅助清洗和解析。"""
    
    def __init__(self, tracker: UncertaintyTracker):
        self.tracker = tracker
        self.templates = self._load_templates()
    
    def assist_variable_inference(self, formula: str, unknown_vars: List[str]) -> Dict[str, str]:
        """协助推断未知变量含义。"""
        
        # 1. 先尝试模板匹配
        for pattern_name, pattern in self.templates.items():
            if re.search(pattern["regex"], formula):
                inferred = {}
                for var in unknown_vars:
                    if var in pattern.get("variables", {}):
                        inferred[var] = pattern["variables"][var]
                if inferred:
                    return inferred
        
        # 2. 模板失败，记录存疑
        self.tracker.add(
            level=UncertaintyLevel.CRITICAL,
            category="formula_unrecognized",
            source=formula,
            context=f"公式无法匹配已知模板，未知变量: {unknown_vars}",
            suggested_action="manual_review"
        )
        
        return {}
    
    def assist_cleaning(self, text: str, quality_report: dict) -> str:
        """Claw 辅助清洗：针对质量问题给出修复建议。"""
        
        suggestions = []
        
        if quality_report["long_ratio"] > 0.1:
            suggestions.append("建议在中英文边界插入空格")
        if quality_report["boundary_ratio"] > 0.05:
            suggestions.append("建议标准化标点符号")
        
        # 应用建议（简单启发式修复）
        for sugg in suggestions:
            if "空格" in sugg:
                text = self._insert_boundary_spaces(text)
            elif "标点" in sugg:
                text = self._normalize_punctuation(text)
        
        return text
    
    def _load_templates(self) -> dict:
        """加载公式识别模板。"""
        return {
            "lms_update": {
                "regex": r'w.*=.*w.*[\+\-].*μ.*e.*x',
                "variables": {"w": "权重向量", "μ": "步长", "e": "误差", "x": "输入向量"},
            },
            "fxlms_error": {
                "regex": r'e.*=.*d.*[\-].*y',
                "variables": {"e": "误差信号", "d": "期望信号", "y": "滤波器输出"},
            },
            "kalman_update": {
                "regex": r'x.*=.*x.*[\+\-].*K.*z',
                "variables": {"x": "状态估计", "K": "卡尔曼增益", "z": "观测值"},
            },
        }
```

---

## 完善：多维 Deconstruction Score v2

### 完整设计

```python
def compute_deconstruction_score_v2(
    # 基础参数（同 v1）
    theorems: int = 0,
    axioms: int = 0,
    formal_defs: int = 0,
    has_what: bool = False,
    has_why: bool = False,
    has_physics: bool = False,
    has_math: bool = False,
    has_engineering: bool = False,
    has_failures: bool = False,
    # 新增：完成度
    total_entries: int = 0,           # 总条目数
    incomplete_markers: int = 0,      # 【待补全】标记数
    # 新增：验证维度
    has_proofs: bool = False,         # 是否有严格证明
    has_experiments: bool = False,    # 是否有实验/仿真
    has_data: bool = False,           # 是否有数据
    # 新增：学术规范
    citations: int = 0,               # 引用数量
    cross_references: int = 0,        # 交叉引用数
    # 新增：存疑惩罚
    uncertainty_tracker: Optional[UncertaintyTracker] = None,
) -> dict:
    """六层解构完整性评分 v2。"""
    
    # 1. 理论丰富度 (0-0.25)
    theory_score = min((theorems + axioms) / 50, 0.25)
    
    # 2. 形式化程度 (0-0.15)
    formal_score = min(formal_defs / 25, 0.15)
    
    # 3. 六层覆盖度 (0-0.20)
    layer_count = sum([has_what, has_why, has_physics, has_math, has_engineering, has_failures])
    layer_score = (layer_count / 6) * 0.20
    
    # 4. 完成度 (0-0.15)
    if total_entries > 0:
        completeness_ratio = max(0, 1 - (incomplete_markers / total_entries))
    else:
        completeness_ratio = 1.0
    completeness_score = completeness_ratio * 0.15
    
    # 5. 验证维度 (0-0.15)
    verification = sum([has_proofs, has_experiments, has_data]) / 3
    verification_score = verification * 0.15
    
    # 6. 学术规范 (0-0.10)
    citation_score = min(citations / 20, 0.05)
    cross_ref_score = min(cross_references / 10, 0.05)
    academic_score = citation_score + cross_ref_score
    
    # 7. 存疑惩罚 (0 到 -0.10)
    penalty = 0.0
    if uncertainty_tracker:
        summary = uncertainty_tracker.get_summary()
        penalty -= summary["critical"] * 0.05  # 每个严重存疑扣 0.05
        penalty -= summary["warning"] * 0.02   # 每个警告扣 0.02
        penalty = max(-0.10, penalty)          # 最多扣 0.10
    
    total = round(
        theory_score + formal_score + layer_score + 
        completeness_score + verification_score + academic_score + penalty,
        3
    )
    total = max(0, min(1, total))  # 钳制到 [0,1]
    
    return {
        "total": total,
        "dimensions": {
            "theory": round(theory_score, 3),
            "formal": round(formal_score, 3),
            "layer_coverage": round(layer_score, 3),
            "completeness": round(completeness_score, 3),
            "verification": round(verification_score, 3),
            "academic": round(academic_score, 3),
            "uncertainty_penalty": round(penalty, 3),
        },
        "metadata": {
            "entries_count": total_entries,
            "incomplete_count": incomplete_markers,
            "completeness_ratio": round(completeness_ratio, 2),
            "verification_flags": {
                "has_proofs": has_proofs,
                "has_experiments": has_experiments,
                "has_data": has_data,
            }
        }
    }
```

### 应用到认知论文（v2 评分）

| 维度 | 计算 | 得分 |
|------|------|------|
| 理论丰富度 | 34/50 | 0.170 |
| 形式化程度 | 17/25 | 0.102 |
| 六层覆盖 | 6/6 | 0.200 |
| 完成度 | 1 - (20/51) ≈ 0.61 | 0.091 |
| 验证 | 0/3 | 0.000 |
| 学术规范 | 引用较少 | 0.020 |
| 存疑惩罚 | ~15 个 WARNING + 0 CRITICAL | -0.300 → 截断到 -0.10 |
| **总计** | — | **~0.583** |

**v1: 1.000 → v2: ~0.583**

更准确反映：这是一篇理论框架草案，大量待补全，无实验验证，存在未知变量需要推断。

---

## 实施路径

| 阶段 | 任务 | 文件 | 时间 |
|------|------|------|------|
| Phase 1 | 存疑系统 + UncertaintyTracker | `lcortex/analysis/uncertainty_tracker.py` | 1h |
| Phase 2 | FormalizationExtractor 集成存疑 | `lcortex/analysis/formalization_extractor.py` | 1.5h |
| Phase 3 | 可选配置 + Claw 模式 | `lcortex/config/cleaner_config.py` | 1h |
| Phase 4 | 多维评分 v2 | `lcortex/analysis/scoring_v2.py` | 0.5h |
| Phase 5 | 整合测试 | `tests/test_three_problems_fix.py` | 1h |

总计约 5 小时，可分阶段交付。

是否按此优先级实施？

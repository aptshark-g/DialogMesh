# Literature Cortex — 对外验证引擎设计文档 (v7.0-EXTERNAL)

> **文档编号:** LC-DESIGN-v7.0-EXTERNAL
> **版本:** v7.0-EXTERNAL-rev1
> **状态:** 🔄 设计阶段
> **日期:** 2026-07-10
> **核心目标:** 从"用户对话知识库"升级为"万能对外验证引擎"，支持任意输入的验证、溯源与推理

---

## 目录

1. [定位调整：从对内到对外](#1-定位调整从对内到对外)
2. [架构调整：双盘位设计](#2-架构调整双盘位设计)
3. [Layer 0：接入层（新增）](#3-layer-0接入层新增)
4. [Layer 1 扩展：数据回溯检验](#4-layer-1扩展数据回溯检验)
5. [Layer 2 扩展：通用文本→SGF](#5-layer-2扩展通用文本sgf)
6. [统一 Pipeline 入口](#6-统一-pipeline-入口)
7. [CLI 与开放接口](#7-cli-与开放接口)
8. [监控与可观测性](#8-监控与可观测性)
9. [内容类型扩展](#9-内容类型扩展)
10. [与 DialogMesh 的协同](#10-与-dialogmesh-的协同)
11. [实施路线](#11-实施路线)

---

## 1. 定位调整：从对内到对外

### 1.1 旧定位（v6.x）

Literature Cortex 最初设计为**学术文献的认知处理系统**：
- 输入：论文、专利、技术报告
- 用户：研究人员（你自己）
- 核心能力：形式化提取、跨域类比、知识图谱演化

### 1.2 新定位（v7.0）

**对外验证引擎（Universal Verification Engine）**：
- 输入：任何可文本化的信息（论文、新闻、社交媒体、评论、日志、聊天记录）
- 用户：任何需要验证信息的人（包括 DialogMesh 代理的"对外"需求）
- 核心能力：来源验证 → 逻辑推演 → 交叉校验 → 置信度输出

```
旧定位：论文 → 形式化 → 知识图谱 → 用户查询
新定位：任意输入 → 验证 → 推理 → 置信度报告 → 任意消费者
```

### 1.3 核心差异

| 维度 | 旧定位 | 新定位 |
|------|--------|--------|
| 输入范围 | 结构化学术文本 | 任意文本/半文本 |
| 处理深度 | 全层激活（CL0→CL4） | 按可信度分级处理 |
| 溯源能力 | 弱（仅引用格式识别） | 强（DNS/whois/引用链/编辑历史） |
| 输出格式 | SGF + 知识图谱 | 验证报告 + 置信度 + 溯源链 |
| 消费者 | 单用户（你自己） | DialogMesh + API + CLI |

### 1.4 不变的部分

- L0-L4 公理层：哲学约束不变
- CL Pipeline（CL0→CL4）：验证逻辑不变
- CSM 跨域类比：结构匹配能力不变
- 生命周期管理：退化/遗忘/复活不变

---

## 2. 架构调整：双盘位设计

### 2.1 对外 vs 对内

```
┌─────────────────────────────────────────────────────────────────┐
│                        对外验证引擎                              │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Layer 0: 接入层（新增）                                  │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │   │
│  │  │ 爬虫接入  │ │ API接入  │ │ Feed接入  │ │ 文件解析  │   │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                           ↓                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Layer 1: 入口解构（扩展）                                │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │   │
│  │  │ 内容分类  │ │ 来源验证  │ │ 可信度初判│ │ 准入决策  │   │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                           ↓                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Layer 2: 结构重构（扩展）                                │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │   │
│  │  │ 物理域   │ │ 通用文本 │ │ 声明解析  │ │ 数据解析  │   │   │
│  │  │ 键合图   │ │ →SGF    │ │ (CLAIM)  │ │ (DATA)   │   │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                           ↓                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Layer 3-5: 认知核心（不变）                              │   │
│  │  CSM + CL Pipeline + L5 Arbiter                         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                           ↓                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  输出层（新增）                                           │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐                │   │
│  │  │ 验证报告  │ │ 置信度   │ │ 溯源链   │                │   │
│  │  └──────────┘ └──────────┘ └──────────┘                │   │
│  └─────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│                        对内辅助（DialogMesh）                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  接口：验证结果 → DialogMesh.v32_context                  │   │
│  │  场景：用户查询事实 → Cortex 验证 → 返回置信度            │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Layer 0：接入层（新增）

### 3.1 定位

Layer 0 是系统的**"感官"**——不验证，只采集和标准化。

### 3.2 接入方式

| 接入方式 | 适用场景 | 特化处理 |
|---------|---------|---------|
| **RSS/Atom Feed** | 新闻网站、博客、 arXiv | 提取正文，去导航/广告 |
| **社交媒体 API** | 微博、Twitter、Reddit | 去话题标签、去 @、提取时间线 |
| **网页爬虫** | 任意网页 | Playwright 渲染后文本提取，去 boilerplate |
| **文件上传** | PDF、Word、Excel、图片 | OCR + 结构化提取 |
| **WebSocket** | 实时流（聊天、日志） | 时间戳对齐、会话切分 |
| **Webhook** | 第三方推送 | 签名验证、去重 |

### 3.3 统一输出格式

所有接入方式输出统一格式：

```python
@dataclass
class RawContent:
    """Layer 0 统一输出。"""
    content_id: str           # 全局唯一ID
    source_url: str           # 来源URL（如果有）
    source_type: str          # rss / social / web / file / stream
    raw_text: str             # 提取的纯文本
    raw_html: Optional[str]   # 原始HTML（保留）
    metadata: Dict[str, Any]  # 来源特定元数据
    timestamp: datetime       # 采集时间
    fetch_method: str         # 采集方式
```

### 3.4 接入层不做的

- 不验证内容真实性
- 不执行逻辑推演
- 不做语义理解
- 只做一件事：把异构输入变成同质文本

---

## 4. Layer 1 扩展：数据回溯检验

### 4.1 现状

现有 Layer 1 有：
- 内容类型分类（学术/新闻/博客/评论）
- 关键词提取（TextRank）
- 领域分类（8个工程域）
- 可信度打分（引用+公式+结构）
- 准入决策（FULL/SHALLOW/AGGREGATE/REJECT）

### 4.2 新增：来源验证模块（SourceVerifier）

**定位：** 第一层必须有"溯源"能力，否则只是文本分类器。

```python
class SourceVerifier:
    """来源验证器 — 技术溯源，不做内容判断。"""
    
    def verify(self, raw: RawContent) -> SourceReport:
        """
        返回来源的技术可信度报告。
        不判断内容对错，只判断来源是否可靠、是否被篡改。
        """
```

#### 4.2.1 验证维度

| 维度 | 方法 | 输出 |
|------|------|------|
| **域名验证** | DNS 解析 + whois | 域名注册时间、注册人、过期时间 |
| **TLS 证书** | 证书链验证 | 是否有效、是否自签名、颁发机构 |
| **网站声誉** | 接入第三方（NewsGuard/MBFC）或自建数据库 | 声誉评分、政治偏向、事实核查记录 |
| **页面完整性** | 哈希校验（如果提供） | 是否被篡改 |
| **编辑历史** | 提取网页的 Last-Modified、版本历史 | 修改频率、重大修改标记 |
| **引用链追溯** | 提取文本中的 URL/DOI，递归验证 | 引用来源是否存在、是否循环引用 |

#### 4.2.2 来源可信度分级

```python
class SourceCredibility(Enum):
    VERIFIED = 5      # 官方源、高声誉媒体、同行评审
    TRUSTED = 4       # 知名机构、长期稳定运营的媒体
    NEUTRAL = 3       # 普通网站、个人博客（无负面记录）
    SUSPICIOUS = 2    # 新域名、匿名运营、有事实核查失败记录
    UNVERIFIED = 1    # 无法验证（如私信、口头转述）
    MALICIOUS = 0     # 已知虚假信息源、钓鱼网站
```

#### 4.2.3 引用链追溯

```python
class CitationTracer:
    """引用链追溯器。
    
    输入：一段文本中提到的所有引用（URL/DOI/论文标题/人名+言论）
    输出：引用链图（谁引用了谁，是否存在循环引用，原始来源是什么）
    """
    
    def trace(self, text: str) -> CitationGraph:
        # 1. 提取所有引用 mention
        mentions = self._extract_mentions(text)
        
        # 2. 对每个 mention，尝试找到原始来源
        for mention in mentions:
            if mention.type == "URL":
                mention.resolved = self._resolve_url(mention.text)
            elif mention.type == "DOI":
                mention.resolved = self._resolve_doi(mention.text)
            elif mention.type == "QUOTE":
                mention.resolved = self._resolve_quote(mention.speaker, mention.text)
        
        # 3. 构建引用链图
        return self._build_graph(mentions)
```

**示例：**

输入："据新华社报道，某专家称……"
输出：
```json
{
  "mentions": [
    {
      "text": "新华社",
      "type": "ORG",
      "credibility": 4,
      "resolved_url": "http://xinhuanet.com/...",
      "verification": "域名匹配、TLS有效"
    },
    {
      "text": "某专家",
      "type": "PERSON",
      "credibility": 1,
      "resolved": null,
      "warning": "匿名专家，无法验证身份"
    }
  ]
}
```

### 4.3 新增：实时性验证（TimelinessChecker）

**定位：** 信息是否过时、是否被后续信息推翻。

```python
class TimelinessChecker:
    """实时性验证器。"""
    
    def check(self, raw: RawContent) -> TimelinessReport:
        """
        检查信息的时效性。
        """
```

| 检查项 | 方法 |
|--------|------|
| 发布时间 | 提取页面/meta中的发布时间 |
| 更新标记 | 检查是否有"更新"、"勘误"标记 |
| 后续报道 | 搜索同一事件的后续报道，检查是否有推翻 |
| 事实核查记录 | 搜索该内容是否被 Snopes/FactCheck 等机构核查过 |

### 4.4 Layer 1 输出扩展

```python
@dataclass
class Layer1Report:
    """Layer 1 扩展输出。"""
    # 原有字段
    content_type: ContentType
    domain: Optional[str]
    keywords: List[str]
    credibility: CredibilityAxiom
    admission: AdmissionDecision
    
    # 新增字段
    source_report: SourceReport        # 来源验证报告
    timeliness: TimelinessReport       # 实时性报告
    citation_graph: CitationGraph      # 引用链图
    
    # 综合初判
    initial_trust_score: float         # 0-1，综合来源+时效+引用链的初判
```

---

## 5. Layer 2 扩展：通用文本→SGF

### 5.1 现状

现有 Layer 2：
- 物理域：键合图元解析器（thermal/mechanical/electrical/fluid/control）
- 非物理域：LLM 结构化提取（JSON Schema 约束）
- 输出：StandardGraphFormat（SGF）

**问题：** 键合图解析器只处理物理域。面对新闻、声明、数据，无法进入第二层。

### 5.2 新增：通用声明解析器（ClaimParser）

**定位：** 将非物理文本中的"声明"提取为结构化命题。

```python
class ClaimParser:
    """声明解析器 — 将文本中的事实声明提取为结构化命题。"""
    
    def parse(self, text: str) -> List[Claim]:
        """
        输入：任意文本
        输出：结构化声明列表
        """
```

#### 5.2.1 声明类型

```python
class ClaimType(Enum):
    FACTUAL = "factual"         # 事实声明："某地发生地震"
    CAUSAL = "causal"           # 因果声明："A导致B"
    COMPARATIVE = "comparative" # 比较声明："A比B更好"
    PREDICTIVE = "predictive"   # 预测声明："明年将..."
    NORMATIVE = "normative"     # 规范声明："应该..."
    ATTRIBUTIVE = "attributive" # 归因声明："某人说..."
```

#### 5.2.2 声明结构

```python
@dataclass
class Claim:
    claim_id: str
    claim_type: ClaimType
    subject: str              # 主语
    predicate: str            # 谓语
    object: Optional[str]     # 宾语
    context: str              # 原始上下文
    source_span: Tuple[int, int]  # 在原文中的位置
    confidence: float         # 提取置信度
    supporting_text: str      # 支持该声明的原文片段
```

**示例：**

输入："据世卫组织统计，2023年全球新冠死亡人数为100万。"
输出：
```json
{
  "claim_id": "c1",
  "claim_type": "factual",
  "subject": "2023年全球新冠死亡人数",
  "predicate": "等于",
  "object": "100万",
  "context": "据世卫组织统计，2023年全球新冠死亡人数为100万。",
  "source_span": [0, 30],
  "confidence": 0.85,
  "supporting_text": "世卫组织统计"
}
```

### 5.3 新增：数据解析器（DataParser）

**定位：** 提取文本中的数据（数字、表格、时间序列）。

```python
class DataParser:
    """数据解析器 — 提取和结构化数据。"""
    
    def parse(self, text: str) -> List[DataPoint]:
        """
        提取文本中的数据点。
        """
```

```python
@dataclass
class DataPoint:
    data_id: str
    value: Union[float, str, bool]
    unit: Optional[str]
    metric: str               # 指标名称
    time_context: Optional[str]  # 时间上下文
    space_context: Optional[str]  # 空间上下文
    source_span: Tuple[int, int]
```

**示例：**

输入："2023年第三季度，该公司营收增长15%，达到5000万美元。"
输出：
```json
[
  {
    "data_id": "d1",
    "value": 15,
    "unit": "%",
    "metric": "营收增长率",
    "time_context": "2023年第三季度",
    "source_span": [15, 25]
  },
  {
    "data_id": "d2",
    "value": 50000000,
    "unit": "USD",
    "metric": "营收",
    "time_context": "2023年第三季度",
    "source_span": [30, 40]
  }
]
```

### 5.4 SGF 扩展：非物理节点

现有 SGF 主要面向物理域。需要扩展以容纳声明和数据：

```python
# 扩展现有 SGFNode
class SGFNode:
    id: str
    base_type: str            # 物理域: R/C/I/Se...
                              # 新增: CLAIM / DATA / ENTITY / EVENT
    properties: Dict[str, Any]
    
    # 新增：非物理域专用属性
    claim_type: Optional[ClaimType]     # 如果是 CLAIM 节点
    data_point: Optional[DataPoint]     # 如果是 DATA 节点
    credibility: Optional[float]        # 节点可信度
```

### 5.5 Layer 2 输出扩展

```python
@dataclass
class Layer2Report:
    """Layer 2 扩展输出。"""
    sgf: StandardGraphFormat           # 结构图
    claims: List[Claim]                # 提取的声明
    data_points: List[DataPoint]       # 提取的数据点
    entities: List[Entity]             # 提取的实体（人名、机构、地名）
    unparseable_segments: List[str]    # 无法解析的片段（需人工审核）
```

---

## 6. 统一 Pipeline 入口

### 6.1 现状

现有多个入口：
- `run_pipeline.py`：旧版端到端 pipeline（清洗→LaTeX→形式化→评分）
- `cognitive_pipeline.py`：协调层 pipeline
- `lcortex/cli.py`：命令行接口（基础）

**问题：** 没有统一的、可编排的入口。

### 6.2 设计：UnifiedPipeline

```python
class UnifiedPipeline:
    """统一 Pipeline 入口。
    
    输入：RawContent（或直接从 Layer 0 接入）
    输出：VerificationReport
    
    支持两种模式：
    - FULL: 完整验证（CL0→CL4 全管道）
    - SHALLOW: 浅层验证（仅 Layer 1）
    - AGGREGATE: 聚合验证（多条内容合并后验证）
    """
    
    def __init__(self, config: PipelineConfig):
        self.layer0 = IngressLayer()
        self.layer1 = IngressLayerExtended()  # 含 SourceVerifier
        self.layer2 = FormalizationLayerExtended()  # 含 ClaimParser + DataParser
        self.layer3 = CSMLayer()
        self.layer4 = CLPipeline()
        self.layer5 = MetaCognitiveArbiter()
        
    def verify(self, raw: RawContent, mode: VerificationMode = VerificationMode.FULL) -> VerificationReport:
        """执行完整验证流程。"""
        
        # Step 1: Layer 1（入口解构 + 来源验证）
        l1_report = self.layer1.process(raw)
        
        # 准入决策
        if l1_report.admission == AdmissionDecision.REJECT:
            return VerificationReport(
                status="rejected",
                reason="内容可信度低于阈值",
                layer1=l1_report,
            )
        
        if l1_report.admission == AdmissionDecision.SHALLOW:
            # 浅层处理：只返回 Layer 1 结果
            return VerificationReport(
                status="shallow",
                layer1=l1_report,
                summary=self._generate_shallow_summary(l1_report),
            )
        
        # Step 2: Layer 2（形式化转译）
        l2_report = self.layer2.process(raw, l1_report)
        
        # Step 3: Layer 3（CSM 跨域类比 / 声明验证）
        # 如果是物理域 → CSM 跨域类比
        # 如果是声明 → 进入声明验证流程
        if l1_report.content_type in (ContentType.ACADEMIC, ContentType.REPORT):
            l3_report = self.layer3.analogy(l2_report.sgf)
        else:
            l3_report = self.layer3.verify_claims(l2_report.claims)
        
        # Step 4: Layer 4（CL Pipeline）
        l4_report = self.layer4.execute(
            source_sgf=l2_report.sgf,
            context={"layer1": l1_report, "layer3": l3_report},
        )
        
        # Step 5: Layer 5（元认知拍板）
        l5_report = self.layer5.decide(
            cl_report=l4_report,
            l1_report=l1_report,
        )
        
        # 生成最终报告
        return VerificationReport(
            status="completed",
            mode=mode,
            layer1=l1_report,
            layer2=l2_report,
            layer3=l3_report,
            layer4=l4_report,
            layer5=l5_report,
            summary=self._generate_summary(l1_report, l4_report, l5_report),
            confidence=self._compute_confidence(l1_report, l4_report),
        )
```

### 6.3 VerificationReport 结构

```python
@dataclass
class VerificationReport:
    """统一验证报告。"""
    
    # 基本信息
    status: str                    # completed / shallow / rejected / error
    mode: VerificationMode
    content_id: str
    timestamp: datetime
    
    # 各层报告
    layer1: Optional[Layer1Report]
    layer2: Optional[Layer2Report]
    layer3: Optional[Layer3Report]
    layer4: Optional[CLPipelineReport]
    layer5: Optional[L5Report]
    
    # 综合输出
    summary: str                   # 自然语言摘要
    confidence: float              # 0-1 综合置信度
    trust_level: TrustLevel        # VERIFIED / LIKELY / UNCERTAIN / SUSPICIOUS / FALSE
    
    # 溯源链
    source_chain: List[SourceNode] # 来源追溯链
    citation_graph: Optional[CitationGraph]
    
    # 结构化数据
    claims: List[Claim]            # 提取的声明
    data_points: List[DataPoint]   # 提取的数据
    
    # 可执行建议
    recommendation: str            # "可引用" / "需进一步验证" / "建议忽略" / "疑似虚假"
    
    # 性能
    latency_ms: float
    token_usage: TokenUsage
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典（用于 API 返回）。"""
        
    def to_markdown(self) -> str:
        """生成 Markdown 格式报告（用于人工阅读）。"""
```

---

## 7. CLI 与开放接口

### 7.1 CLI 设计

```bash
# 验证单个 URL
lcortex verify https://example.com/news/article --mode=full

# 验证文本文件
lcortex verify-file ./article.txt --source-type=news

# 验证 RSS Feed（批量）
lcortex verify-feed https://example.com/rss.xml --limit=10

# 验证社交媒体帖子
lcortex verify-social "https://weibo.com/xxx/xxx" --platform=weibo

# 声明验证（直接输入文本）
lcortex verify-claim "2023年全球新冠死亡人数为100万" --source="世卫组织"

# 数据验证
lcortex verify-data "营收增长15%" --metric="营收增长率" --unit="%"

# 监控模式
lcortex monitor --feed=https://example.com/rss --interval=300 --alert-webhook=https://hooks.slack.com/...

# 导出报告
lcortex export --report-id=xxx --format=markdown
lcortex export --report-id=xxx --format=json
```

### 7.2 REST API 设计

```python
# POST /api/v1/verify
{
  "content": "文本内容或URL",
  "content_type": "auto",  # auto / url / text / file
  "mode": "full",          # full / shallow / aggregate
  "context": {
    "source_url": "https://...",
    "expected_domain": "news",
  }
}

# Response
{
  "report_id": "rpt_xxx",
  "status": "completed",
  "confidence": 0.72,
  "trust_level": "LIKELY",
  "summary": "该内容来源可信（新华社），但声明中缺少具体数据来源引用...",
  "claims": [...],
  "source_chain": [...],
  "latency_ms": 1250,
}

# GET /api/v1/reports/{report_id}
# GET /api/v1/stats
# GET /api/v1/health
# POST /api/v1/batch-verify
```

### 7.3 开放模块接口

每个核心模块提供独立调用接口：

```python
# Layer 1 接口
POST /api/v1/layer1/classify
POST /api/v1/layer1/verify-source
POST /api/v1/layer1/trace-citations

# Layer 2 接口
POST /api/v1/layer2/parse-claims
POST /api/v1/layer2/parse-data
POST /api/v1/layer2/to-sgf

# Layer 3 接口
POST /api/v1/layer3/csm-analogy
POST /api/v1/layer3/verify-claims

# Layer 4 接口
POST /api/v1/layer4/cl-pipeline

# Layer 5 接口
POST /api/v1/layer5/arbitrate
```

---

## 8. 监控与可观测性

### 8.1 现状

`lcortex/monitor/monitor.py` 已有：
- Phase 级跟踪
- Item 级跟踪
- Token 使用统计
- 错误和降级事件
- `events.jsonl` + `monitor_report.md`

### 8.2 新增：Metrics 导出

```python
class MetricsExporter:
    """Prometheus 风格的指标导出。"""
    
    # Counter
    verification_total        # 总验证次数
    verification_failed       # 失败次数
    content_rejected_total    # 拒绝次数
    
    # Histogram
    verification_latency      # 验证延迟分布
    layer_latency             # 各层延迟
    confidence_distribution   # 置信度分布
    
    # Gauge
    active_feeds              # 活跃 Feed 数
    queue_depth               # 队列深度
    token_usage_rate          # Token 消耗速率
```

### 8.3 新增：告警规则

| 告警 | 条件 | 动作 |
|------|------|------|
| 验证延迟过高 | p99 latency > 5s | Slack/钉钉告警 |
| 大量内容被拒绝 | rejection rate > 50%（持续5分钟） | 告警 + 自动降级处理深度 |
| 来源异常 | 检测到 MALICIOUS 来源 | 立即阻断 + 告警 |
| 队列积压 | queue depth > 1000 | 告警 + 自动扩容 |
| Token 耗尽 | token usage > 80% budget | 告警 + 切换低成本模式 |

### 8.4 健康检查端点

```python
# GET /health
{
  "status": "healthy",  # healthy / degraded / unhealthy
  "version": "7.0.0",
  "layers": {
    "layer0": "up",
    "layer1": "up",
    "layer2": "up",
    "layer3": "up",
    "layer4": "up",
    "layer5": "up",
  },
  "dependencies": {
    "database": "connected",
    "llm_api": "available",
    "sentence_transformers": "unavailable",  # 内存不足时标记
  },
  "metrics": {
    "verification_total": 15234,
    "avg_latency_ms": 850,
    "rejection_rate": 0.12,
  }
}
```

---

## 9. 内容类型扩展

### 9.1 现有类型

- ACADEMIC: 学术论文
- NEWS: 新闻报道
- BLOG: 博客/评论
- COMMENT: 短评论/社交媒体

### 9.2 新增类型

| 类型 | 特征 | 处理深度 |
|------|------|---------|
| **CLAIM** | 事实声明（如"某专家说某某"） | FULL（需验证声明真伪） |
| **DATA** | 原始数据（表格、CSV、日志） | FULL（需验证数据一致性） |
| **META** | 元信息（about页、作者介绍） | SHALLOW（仅提取来源信息） |
| **OPINION** | 观点/评论（带情绪倾向） | SHALLOW（仅提取立场和情绪） |
| **SATIRE** | 讽刺/幽默（可能伪装成事实） | FULL（需检测讽刺标记） |

### 9.3 类型检测增强

```python
class ContentTypeClassifierV2:
    """扩展的内容类型分类器。"""
    
    def classify(self, text: str) -> Tuple[ContentType, Dict[str, float]]:
        # 原有特征
        scores = self._classify_base(text)
        
        # 新增：声明检测
        if self._is_claim(text):
            scores["claim"] += 0.5
        
        # 新增：数据检测
        if self._contains_data(text):
            scores["data"] += 0.5
        
        # 新增：讽刺检测
        if self._is_satire(text):
            scores["satire"] += 0.8
        
        # 新增：元信息检测
        if self._is_meta(text):
            scores["meta"] += 0.9
        
        return ContentType(max(scores, key=scores.get)), scores
```

---

## 10. 与 DialogMesh 的协同

### 10.1 协同模式

Cortex 作为 DialogMesh 的**"验证后端"**：

```
用户提问（DialogMesh）
  ↓
DialogMesh Compiler 解析意图
  ↓
如果是事实查询 → 调用 Cortex.verify()
  ↓
Cortex 返回：置信度 + 溯源链 + 建议
  ↓
DialogMesh FusionEngine 综合用户画像 + Cortex 验证结果
  ↓
生成最终回答
```

### 10.2 接口契约

```python
# DialogMesh → Cortex
class CortexVerificationRequest:
    query: str                    # 用户查询
    context: str                  # 对话上下文
    user_profile: CognitiveProfile  # 用户画像（可选，用于调整阈值）
    urgency: str                  # 紧急程度（决定处理深度）

# Cortex → DialogMesh
class CortexVerificationResponse:
    verified: bool                # 是否通过验证
    confidence: float             # 置信度
    sources: List[SourceReport]   # 来源列表
    summary: str                  # 验证摘要
    recommendation: str           # 建议（确认/质疑/拒绝）
    latency_ms: float             # 响应延迟
```

### 10.3 用户画像调整

```python
# 根据用户认知风格调整验证严格度
def adjust_threshold(profile: CognitiveProfile, base_threshold: float) -> float:
    if profile.metacognition > 0.7:
        # 高元认知用户：更严格的验证
        return base_threshold * 1.2
    elif profile.divergent > 0.6:
        # 高发散性用户：容忍更多不确定性
        return base_threshold * 0.8
    return base_threshold
```

---

## 11. 多重校验与辩证引擎

### 11.1 核心洞察

单一验证路径不够。面对真实世界的信息，必须：

1. **先检索，后校验**：先搜相关内容，聚合处理，提取核心逻辑链，再校验
2. **复合验证**：同一命题从多个角度验证（来源、逻辑、数据、共识）
3. **辩证模式**：对中医、心理学、人文社科等经验性领域，不追求绝对正确，而是同时追踪多个假设，每个假设有独立置信度
4. **模糊评分**：当形式化校验失败但证据链充分时，标记为"人类经验领域"，切换验证策略

### 11.2 多重校验工作流

```
输入：命题 P（如"针灸对慢性疼痛有效"）
  ↓
Step 1: 快速检索
  - 搜索引擎检索 P 的相关内容
  - 收集 N 篇相关文档
  - 去重、排序（按来源可信度）
  ↓
Step 2: 核心逻辑链提取
  - 对每篇文档提取：Claim + 支持证据 + 数据来源
  - 构建"证据网络"：谁支持 P，谁反对 P，谁的立场中立
  ↓
Step 3: 并行验证
  ├─ 路径 A: 形式化验证（CL Pipeline）
  │   - 如果 P 可形式化（物理/数学/工程）
  │   - 运行 CL0→CL4
  │   - 输出：HARD_PASS / HARD_FAIL / UNCERTAIN
  │
  ├─ 路径 B: 共识验证（Consensus Check）
  │   - 统计支持/反对/中立的来源数量和质量
  │   - 加权：高声誉来源权重更高
  │   - 输出：consensus_score（-1 到 +1）
  │
  ├─ 路径 C: 逻辑一致性验证（Logic Check）
  │   - 检查支持 P 的论据之间是否自相矛盾
  │   - 检查反对 P 的论据是否更有力
  │   - 输出：logic_score（0 到 1）
  │
  └─ 路径 D: 数据验证（Data Check）
      - 提取 P 中引用的数据
      - 交叉比对多个来源的同一数据
      - 输出：data_consistency_score（0 到 1）
  ↓
Step 4: 综合判定
  - 融合四条路径的结果
  - 根据领域类型选择融合策略
  ↓
输出：验证报告
```

### 11.3 辩证引擎（Dialectic Engine）

**定位：** 对经验性/关联性内容，不追求二元判定，而是同时维护多个 competing hypotheses。

```python
class DialecticEngine:
    """辩证引擎 — 同时追踪正反两方的论证。"""
    
    def dialectic(self, proposition: str, evidence: List[Document]) -> DialecticReport:
        """
        输入：命题 + 证据集合
        输出：辩证报告（含正反双方论证）
        """
```

#### 11.3.1 论证提取

```python
@dataclass
class Argument:
    argument_id: str
    side: str                    # "pro" / "con" / "neutral"
    claim: str                   # 核心主张
    premises: List[str]          # 前提
    evidence: List[str]          # 证据引用
    fallacies: List[str]         # 可能的逻辑谬误
    credibility: float           # 论证可信度
```

#### 11.3.2 辩证报告结构

```python
@dataclass
class DialecticReport:
    proposition: str
    
    # 正方论证
    pro_arguments: List[Argument]
    pro_strength: float           # 正方整体强度 0-1
    
    # 反方论证
    con_arguments: List[Argument]
    con_strength: float           # 反方整体强度 0-1
    
    # 中立证据
    neutral_evidence: List[str]
    
    # 综合评估
    synthesis: str                # 综合判断（如"证据支持但机制不明"）
    confidence: float             # 综合置信度
    recommendation: str           # "支持" / "反对" / "存疑" / "需更多证据"
    
    # 特殊标记
    is_experiential_domain: bool  # 是否经验性领域（中医/心理学等）
    known_limitations: List[str]  # 已知局限性
```

**示例：**

命题："针灸对慢性腰痛有效"

```json
{
  "proposition": "针灸对慢性腰痛有效",
  "pro_arguments": [
    {
      "claim": "多项RCT显示针灸优于假针灸",
      "premises": ["随机对照试验设计严谨", "样本量充足"],
      "evidence": ["Vickers et al. 2018, n=20,827", "WHO 认可针灸用于疼痛"],
      "credibility": 0.85
    }
  ],
  "con_arguments": [
    {
      "claim": "假针灸效应显著，提示安慰剂效应",
      "premises": ["假针灸（非穴位）同样有效", "机制缺乏生理学解释"],
      "evidence": ["Madsen et al. 2009 荟萃分析"],
      "credibility": 0.75
    }
  ],
  "synthesis": "证据支持针灸对慢性腰痛有临床效果，但安慰剂效应占比不明，机制待研究",
  "confidence": 0.65,
  "recommendation": "存疑",
  "is_experiential_domain": true,
  "known_limitations": ["机制不明", "个体差异大", "标准化困难"]
}
```

### 11.4 领域感知验证策略切换

系统根据内容领域自动选择验证策略：

```python
class VerificationStrategy(Enum):
    FORMAL = "formal"           # 形式化验证（物理/数学/工程）
    EMPIRICAL = "empirical"     # 经验验证（医学/心理学/社科）
    DIALECTIC = "dialectic"     # 辩证验证（哲学/人文/中医）
    HYBRID = "hybrid"           # 混合验证（跨学科）
```

| 领域 | 策略 | 原因 |
|------|------|------|
| 物理/数学/工程 | FORMAL | 可形式化，可精确验证 |
| 医学/生物 | EMPIRICAL | 依赖实验证据，但部分可量化 |
| 中医/心理学/人文 | DIALECTIC | 经验性/关联性导向，需辩证思维 |
| 跨学科 | HYBRID | 不同子问题用不同策略 |

```python
def select_strategy(domain: str, content_type: ContentType) -> VerificationStrategy:
    if domain in ("physics", "mathematics", "engineering"):
        return VerificationStrategy.FORMAL
    elif domain in ("medicine", "biology"):
        return VerificationStrategy.EMPIRICAL
    elif domain in ("traditional_chinese_medicine", "psychology", "humanities"):
        return VerificationStrategy.DIALECTIC
    else:
        return VerificationStrategy.HYBRID
```

### 11.5 模糊评分系统（Fuzzy Scoring）

**定位：** 当形式化校验失败但证据链充分时，不直接否定，而是给出模糊评分。

```python
class FuzzyScorer:
    """模糊评分器 — 处理形式化不可验证但证据充分的命题。"""
    
    def score(self, proposition: str, evidence: List[Document]) -> FuzzyScore:
        """
        输出模糊评分（不是 true/false，而是多维度评分）。
        """
```

#### 11.5.1 评分维度

| 维度 | 含义 | 范围 |
|------|------|------|
| **证据强度** | 支持证据的数量和质量 | 0-1 |
| **机制清晰度** | 是否有可解释的因果机制 | 0-1 |
| **可重复性** | 结果是否可被独立重复 | 0-1 |
| **共识度** | 专家社区的共识程度 | 0-1 |
| **异常容忍** | 对反例的容忍度（经验领域通常更高） | 0-1 |

#### 11.5.2 模糊评分输出

```python
@dataclass
class FuzzyScore:
    proposition: str
    
    # 五维度评分
    evidence_strength: float
    mechanism_clarity: float
    reproducibility: float
    consensus: float
    anomaly_tolerance: float
    
    # 综合模糊度（越高越不确定）
    fuzziness: float              # 0 = 清晰可判定，1 = 高度模糊
    
    # 判定
    verdict: str                  # "SUPPORTED" / "CONTESTED" / "UNCERTAIN" / "INSUFFICIENT_EVIDENCE"
    
    # 人类可读解释
    explanation: str
    
    # 建议
    recommendation: str           # "可谨慎接受" / "需更多研究" / "建议怀疑" / "无法判定"
```

**示例：**

命题："中医认为肝主疏泄，情志不畅可致肝气郁结"

```json
{
  "evidence_strength": 0.70,
  "mechanism_clarity": 0.20,
  "reproducibility": 0.40,
  "consensus": 0.80,
  "anomaly_tolerance": 0.90,
  "fuzziness": 0.75,
  "verdict": "CONTESTED",
  "explanation": "在中医内部共识度高（0.80），但缺乏现代生理学机制解释（0.20），可重复性低（0.40）。这是一个高度依赖经验和临床传统的命题。",
  "recommendation": "在中医框架内可谨慎接受，但不应视为已验证的科学事实"
}
```

### 11.6 快速预筛机制

**定位：** 避免对所有内容都跑完整验证，先快速预筛。

```python
class QuickPrescreener:
    """快速预筛器 — 低成本初步判断。"""
    
    def prescreen(self, raw: RawContent) -> PrescreenResult:
        """
        输入：原始内容
        输出：预筛结果（fast / slow / skip）
        """
```

| 预筛结果 | 含义 | 后续动作 |
|---------|------|---------|
| **FAST** | 来源可信 + 内容简单 + 无争议 | 浅层验证后直接通过 |
| **SLOW** | 来源可疑 或 内容复杂 或 有争议 | 进入完整多重校验 |
| **SKIP** | 已知垃圾/广告/低质内容 | 直接拒绝 |

预筛标准：
- 来源可信度 >= TRUSTED → 可能 FAST
- 内容长度 < 100 字 且 无引用 → 可能 FAST
- 来源可信度 <= SUSPICIOUS → 必须 SLOW
- 包含争议性声明 → 必须 SLOW

### 11.7 与 DialogMesh 的协同（扩展）

在辩证模式下，DialogMesh 可以：

```
用户："我听说针灸能治腰痛，是真的吗？"
  ↓
DialogMesh 识别：这是事实查询，需验证
  ↓
Cortex 进入辩证模式：
  - 检索相关文献（支持/反对）
  - 提取正反论证
  - 运行模糊评分
  ↓
返回 DialogMesh：
  {
    "answer": "证据显示针灸对慢性腰痛可能有帮助，但效果部分来自安慰剂。",
    "confidence": 0.65,
    "dialectic": {
      "pro": "多项RCT支持，WHO认可",
      "con": "假针灸效应显著，机制不明",
    },
    "recommendation": "可尝试，但不应替代常规治疗",
  }
  ↓
DialogMesh 根据用户画像调整表述：
  - 科学导向用户：强调证据质量和机制空白
  - 传统医学接受者：强调临床经验和历史传承
  - 保守用户：强调"建议咨询医生"
```

### 11.8 实施路线（扩展）

| Phase | 新增任务 | 工作量 |
|-------|---------|--------|
| Phase 1 | 快速预筛机制 | 2-3 天 |
| Phase 2 | 多重校验工作流（检索+聚合） | 1 周 |
| Phase 3 | 辩证引擎（正反论证提取） | 1-2 周 |
| Phase 4 | 模糊评分系统 | 3-5 天 |
| Phase 5 | 领域感知策略切换 | 2-3 天 |

---

## 12. 实施路线（总纲）

### 12.1 时间线

```
Phase 1: 统一入口 + 快速预筛（2 周）
Phase 2: 来源验证 + 多重检索（3 周）
Phase 3: 通用解析 + 辩证引擎（3 周）
Phase 4: 接入层 + 模糊评分（2 周）
Phase 5: 监控 + DialogMesh 协同（2 周）
─────────────────────────────────────
总计: 12 周（全职）/ 20 周（兼职）
```

### 12.2 关键里程碑

| 里程碑 | 验收标准 |
|--------|---------|
| M1（2周） | `lcortex verify <url>` 可用，输出 VerificationReport |
| M2（5周） | 能验证新闻来源，追溯引用链，检测过时信息 |
| M3（8周） | 能提取声明和数据，正反论证提取，辩证报告输出 |
| M4（10周） | RSS/网页/社交媒体接入，模糊评分可用 |
| M5（12周） | DialogMesh 双向接口，监控告警完整，端到端 benchmark |

---

*设计文档 v7.0-EXTERNAL-rev2 完成。包含多重校验、辩证引擎、模糊评分、领域感知策略切换。*

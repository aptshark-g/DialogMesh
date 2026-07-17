# 链路质量评估报告

## 当前状态

| 链路 | 之前 | 现在 | 评分 | 核心机制 |
|------|------|------|------|---------|
| L1 池→图 | stats>0 (2/10) | CamelCase比例 + 路径覆盖检查 | **5/10** | 真实管道但不是质量验证 |
| L2 渲染→上下文 | design>50 字 (2/10) | 架构文本非空 + 跨策略差异 | **4/10** | 同一对象不同策略渲染 |
| L5 提取→RS | 手工构造 (1/10) | 真实 jieba 提取 + RS 回写 | **6/10** | 真实提取管线 |
| L6 关键词→视角 | 纯字符串 (3/10) | PCR 意图识别为主 | **6/10** | **不是纯关键词** |

## L6 详细分析

### 不是"纯字符串匹配"

PerspectivePlanner 实际有两层：

```
Layer 1: PCR 意图识别 (TOOL/ADVISOR/COMPANION/UNKNOWN)
  ↓
  TOOL     → architecture  (工具使用)
  ADVISOR  → architecture  (咨询建议)
  COMPANION → evolution    (伴侣对话)
  UNKNOWN   → 关键词匹配 (fallback)
  
Layer 2: 关键词 fallback (_STRATEGY_MAP)
  "架构/设计/结构" → architecture
  "为什么/原因/演变" → evolution
  "代码/函数/实现" → engineering
  "流程/运行/调度" → execution
```

### 工业水平评估

| 维度 | 水平 | 说明 |
|------|------|------|
| **分层设计** | ✅ 工业 | PCR 意图→策略 + 关键词 fallback 是正确架构 |
| **PCR 质量** | ⚠️ 依赖外部 | PCR 本身是 IntentParser 的一部分，准确性未知 |
| **关键词 fallback** | ❌ 未达工业 | 15 个关键词覆盖不了用户所有表达方式 |
| **领域分配** | ✅ 工业 | K/C/P/E/B 五个域权重按期望类型分配 |
| **深度自适应** | ✅ 工业 | 按 token budget 动态调整渲染深度 |
| **视角切换** | ❌ 缺失 | 无 MetaCognition 参与——纯规则决策 |
| **泛化能力** | ❌ 低 | 新词=new miss, 无语义理解 |

### 四链路总评

| 链路 | 机制 | 工业级 | 泛化 | 瓶颈 |
|------|------|--------|------|------|
| L1 | ObservationPool→ConceptGraph | ⚠️ | ✅ 基于文档解析 | Graph 内存限制 |
| L2 | ObjectRuntime.render() | ⚠️ | ❌ | Projection resolver 全是 stub |
| L5 | jieba/Stanza/LMStudio/DeepSeek | ✅ | ✅ | LMStudio/DeepSeek 依赖外部服务 |
| L6 | PCR + 关键词 | ⚠️ | ❌ | 关键词表太小; MetaCognition 未接入 |

## 对比真工业系统 (LangChain/LlamaIndex)

| 组件 | 我们 | 工业标准 |
|------|------|---------|
| 文档解析 | ✅ Jieba分段+TieredParser | ✅ LangChain DocumentLoader |
| 图构建 | ✅ ConceptGraph (7K节点) | ✅ Neo4j/NetworkX |
| 渲染 | ⚠️ ObjectRuntime (stub resolver) | ✅ 多模态 + 代码+知识查询 |
| 提取 | ✅ 4层降级 | ✅ LlamaIndex ExtractionPipeline |
| 视角 | ⚠️ PCR+关键词 | ✅ LLM Agent 决策 |
| 检索 | ⚠️ BGE+Jieba hybrid | ✅ Hybrid + ReRank + LLM review |

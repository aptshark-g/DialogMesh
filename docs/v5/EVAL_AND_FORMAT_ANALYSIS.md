# 评估框架选型 + XML格式适配度分析

> 2026-07-24 · 开源复用 vs 自建 · XML 分布式部署考量

---

## 一、可复用的开源评估框架

### 1.1 直接可用

| 项目 | Stars | 核心能力 | 复刻难度 |
|------|-------|----------|----------|
| **GateMem** | ⭐194 | 多主体共享记忆治理评估, Python | 🟢 直接 fork |
| **goodai-ltm-benchmark** | ⭐88 | LTM 持续学习评估, task-based | 🟢 直接 fork |
| **ProsusAI/MemEval** | ⭐28 | Agent 记忆评估套件 | 🟢 直接 fork |
| **LoCoMo** | 论文 | 300轮×35会话, 3类任务 | 🟡 需适配对话格式 |

### 1.2 建议策略

```
Phase 1 (今天): fork GateMem + goodai-ltm-benchmark
  → 替换记忆后端为我们的 XML Cards
  → 运行现有测试集 → 得到 baseline 分数

Phase 2 (本周): 按 DialogMesh 场景扩展
  → 加多链场景 (行为链/关联链/工程链)
  → 加元认知验证场景 (规则逆推)

Phase 3: 贡献回开源
  → 我们的 XML格式 + 联邦索引 → PR 回上游
```

## 二、XML 格式适配度与分布式考量

### 2.1 XML vs JSON — 实际代价

```
Token 成本 (GPT-4o tokenizer):
  
  XML:  <person name=  "张 医生  " role=  "牙科  " />  
        5   4    1     1   2    1   4    1   2    1   2 = 24 tokens
  
  JSON: {  "name  ":"  张 医生  ","  role  ":"  牙科  "  }
        1   2    1  1    1   2    1  1   2   1  1   2   1  2 = 21 tokens

  差异: XML ≈ 14% more tokens — 但 LLM 理解精度高12% (XML-CLIP, 2023)
  结论: 性价比中性 — 用 token 换精度

LLM 生成可靠性:
  JSON: } 丢失 → 整个对象解析失败
  XML:  </person> 丢失 → 只影响当前标签，其他标签仍可解析
  结论: XML 容错性更好 — 部分失效 > 全部失效
```

### 2.2 分布式持久化场景

```
场景: 联邦式多 Agent 部署, 记忆跨节点共享

XML 问题:
  ✗ 序列化体积大 (25-30% > JSON)
  ✗ 解析成本高 (XML parser > JSON parser)
  ✗ 部分更新困难 (需要 XPath/XQuery)

混合方案 (推荐):
  存储层: JSON/Binary (SQLite/Redis)  ← 紧凑, 高效
  传输层: JSON/Protobuf               ← 网络开销小
  上下文层: XML                        ← LLM 理解, 只在注入 prompt 时生成
  
  流程: 存储(JSON) → 检索 → 转换(XML) → LLM → 解析(XML→JSON) → 存储
```

### 2.3 为什么不做纯 Executable 记忆 (User as Code)

```
User as Code 理念: 用户模型 = Python 对象 + 类型约束 + 方法

优势:
  ✅ 计算天然 (sum, filter, aggregate 无需LLM)
  ✅ 类型安全 (pydantic validation)
  ✅ 版本可追踪 (git diff)

不适合我们的原因:
  ❌ LLM 生成代码不可靠 (幻觉产生 buggy Python)
  ❌ 多 Agent 共享时安全风险 (exec() 沙箱逃逸)
  ❌ 序列化反序列化需 pickle (安全风险)
  
折中: XML + pydantic validation
  1. LLM 生成 XML (容错: 部分失效 > 全部失效)
  2. pydantic 解析 + 类型验证 (类型安全)
  3. JSON 存储 (紧凑, 高效)
  4. XML 注入 prompt (LLM 理解)
```

## 三、最终建议

```
记忆存储格式:
  热路径 (inject to LLM): XML Cards — 6类型, 层次清晰
  冷存储 (persist): JSON — 紧凑, CRUD高效
  索引 (search): 向量 768d — HNSW, 内容无关

评估框架:
  复刻 GateMem + goodai-ltm-benchmark
  自建: 多链场景扩展 + 元认知验证

格式拓展性:
  → 加新卡类型: 在 XML Schema 里加 — 向后兼容
  → 分布式: JSON 传输 → XML 注入 prompt
  → 多 Agent: 每个 Agent 独立索引, 联邦查询
```

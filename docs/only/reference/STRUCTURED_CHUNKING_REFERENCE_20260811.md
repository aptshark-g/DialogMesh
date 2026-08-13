# 结构化切分参考 — Unstructured 模式 + 我们的适配方案（2026-08-11）

> 触发: goldset 块以 "---。### 💭" 开头（markdown 分隔线/标题被 EDU 吞入）
> 用户判断: "硬切太乱来: 1上下文不闭环 2内容残缺且噪音"
> 用户方向: 结构化切分（识别噪音/结构）+ 参考语义切分方案

---

## 一、问题根因（已确认）

- SYNTACTIC_DECOMPOSER 是**纯标点切分**（BOUNDARY_MARKS: 。！？；，）
  + 代词注入; 无任何 markdown/代码/列表结构识别
- `---`（分隔线）、`###`（标题）、```代码块、JSON、列表 → 全被吞进 EDU
- goldset 生成器虽走 EDU 闭环切块, 但 EDU 本身把结构吞了 → 块以
  `---。` 开头, 语义残缺
- ChunkStore 的 SemanticSplitter 有 NON_CHUNKABLE_PATTERNS（code/json/
  quote）但不被 goldset/EDU 路径使用

## 二、Unstructured 模式（行业标准）

### 核心: partition → elements → chunk_by_title
```
文档 → partition() → [Element...]（Title/Table/CodeBlock/ListItem/
  NarrativeText/PageBreak, 各带 metadata: page/section/heading）
→ chunk_by_title(elements): 遇 Title 开新块, 超长再切, 小块合并
```

### 关键设计要素
1. **结构化元素类型**: Title/Table/CodeBlock/ListItem/NarrativeText —
   切分边界由元素类型决定（Title 是天然锚点）
2. **边界判定 is_title**: 正则识别标题（长度/格式/层级）
3. **metadata 保留**: 块继承 page/section/heading → 溯源
4. **块策略**: 按标题聚合 + 超长硬切 + 短块合并（combine_under_n）
5. **overlap**: 仅超长块切分时尾部重叠（保上下文, 不污染语义边界）

### 参考实现
- chunking/title.py: chunk_by_title（聚合/切分/合并）
- documents/elements.py: Element 类型体系

## 三、语义切分补充（jparkerweb/semantic-chunking）

- 基于 embedding 相似度: 相邻句相似度骤降 → 语义边界
- 适合: 无结构标记的散文（聊天记录/叙述）
- 不适合: 有明确结构（markdown/代码）——结构优先, 语义兜底

## 四、我们的适配方案（结构预分割层）

### 设计: 在 EDU 分解前加 StructurePreSplitter
```
原始文本
  → StructurePreSplitter（新增）
    ① markdown 结构边界: 标题(###)/分隔线(---)/列表/引用/代码块/JSON
       → 各自成独立结构单元（不吞并, 不打散）
    ② 代码块/JSON/表格 → 标记 non-chunkable（保持完整, 不切）
    ③ 噪音过滤: 纯分隔线/装饰性符号/空壳标题 → 丢弃
    ④ 结构单元内 → 交给 EDU 闭环切分（语法补全 + 闭环）
  → 语义块（结构完整 + 闭环 + 无噪音）
```

### 边界优先级（递归）
1. 代码块 ``` / JSON 大括号 → 整体保留（non-chunkable）
2. markdown 标题（##/###）→ 新块锚点
3. 分隔线 --- / 列表 / 引用 → 结构边界
4. 段落空行 → 软边界
5. 标点（现有 EDU）→ 块内闭环切分

### 落点
- core/agent/discourse_block_tree/structure_pre_splitter.py（新增）
- goldset 生成器 _build_goldset.py 改用: StructurePreSplitter → EDU
- SemanticSplitter 的 NON_CHUNKABLE 规则并入（代码/JSON/quote）
- ChunkStore 写即索引路径同步受益

## 五、验收

- goldset 重建: 无块以 ---/### 开头, 无拦腰截断的 JSON/代码
- 召回评测重跑: top1 应提升（噪音块减少 → 匹配更准）
- 保持: EDU 闭环（代词补全）不丢

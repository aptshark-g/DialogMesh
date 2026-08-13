# StructurePreSplitter 设计 — 结构化预分割层（2026-08-11）

> 触发: goldset 块以 "---.### 💭" 开头（markdown 分隔线/标题被 EDU 吞入）
> 用户: "硬切太乱来: 1上下文不闭环 2内容残缺且噪音"
> 参考: Unstructured（partition→elements→chunk_by_title）+
>       jparkerweb/semantic-chunking（语义边界兜底）
> 关联: RECALL_EVAL_STANDARDS / RECALL_RUST_DESIGN / goldset 重建

---

## 一、目标

在现有 EDU 闭环切分**之前**加一层结构预分割, 让:
1. markdown 结构（标题/分隔线/列表/引用）成为天然边界, 不被吞并
2. 代码块/JSON/表格保持完整（non-chunkable, 不打散）
3. 噪音（纯装饰分隔线/空壳标题）被过滤
4. 结构单元内部再走 EDU 闭环（代词补全 + 语法闭环不丢）

## 二、流水线（新增层的位置）

```
原始文本
  ↓ [新增] StructurePreSplitter
  → 结构单元列表: [{text, kind, non_chunkable, heading}]
       kind: title | code | json | list | quote | paragraph | noise
  ↓ 单元内（non_chunkable 除外）
  → SYNTACTIC_DECOMPOSER.decompose（EDU 闭环, 现有）
  → 块组装（现有 chunk_text 逻辑）
```

## 三、StructurePreSplitter 规则（递归优先级）

| 优先级 | 模式 | 处理 |
|---|---|---|
| 1 | ```代码块 (```...```) | 整体保留, non_chunkable=True |
| 2 | JSON/数组 (顶层 {...}/[...]) | 整体保留, non_chunkable=True |
| 3 | markdown 标题 (^#{1,6} ) | 新块锚点, heading=标题文本 |
| 4 | 分隔线 (^---+ / ^\*\*\*+) | 结构边界; 纯装饰→noise 丢弃 |
| 5 | 列表 (- / * / 1.) | 列表项成组（连续列表并入一块）|
| 6 | 引用 (> ) | 引用块成组 |
| 7 | 段落 (空行分隔) | 软边界, 相邻段按 maxlen 合并 |
| 8 | 标点 (现有 BOUNDARY) | 块内 EDU 闭环切分（不变）|

## 四、边界与合并策略

- **结构单元长度**: 单元内按 maxlen(280) 硬上限; 超长:
  - non_chunkable → 保留完整（语义压缩后续接入, 不机械截断）
  - 标题+正文段 → 标题段 + 正文段分别成块
- **相邻段落合并**: 相邻 paragraph 合并到 maxlen（保上下文连贯）
- **标题归属**: 标题与其后第一段同块（锚点语义）; 若该段超长, 标题独立成块
- **噪音判定**: 纯符号行（---、***、仅标点）、空壳标题（无后继内容）→ noise

## 五、数据结构

```python
@dataclass
class StructureUnit:
    kind: str          # title | code | json | list | quote | paragraph | noise
    text: str
    non_chunkable: bool = False
    heading: str = ""  # title 单元的标题文本（元数据, 供溯源）
```

## 六、接入点

1. `core/agent/discourse_block_tree/structure_pre_splitter.py`（新增）
   - `split(text) -> List[StructureUnit]`
   - `split_edus(text) -> List[EDU]`（结构预分割 → 单元内 EDU 合并）
2. goldset 生成器 `scripts/_build_goldset.py`:
   - `chunk_text` 改用 `split_edus`（结构单元内闭环, 不吞结构）
3. `SemanticSplitter.NON_CHUNKABLE_PATTERNS` 规则并入（代码/JSON/quote 一致）
4. 写即索引 / ChunkStore 路径同步受益（同一分解器）

## 七、验收门槛

1. goldset 重建后: 无块以 `---` / `###` 开头; 无拦腰截断的 JSON/代码
2. 召回评测重跑: top1 不低于现状（期望提升, 噪音块减少）
3. EDU 闭环不丢: 代词补全仍有（SPO 提炼测试保持绿）
4. 结构单元测试: title/code/json/list/quote/noise 各类型边界正确

## 八、不做（边界纪律）

- 不引入新依赖（Unstructured 太重; 自写轻量规则足够 markdown）
- 不做语义 embedding 切分（markdown 有结构, 结构优先; 语义切分是
  无结构散文的后续候选——goldset 是对话+markdown 混合, 结构够用）
- 不改 EDU 分解器内部（它做标点闭环没问题; 结构问题在它之前）

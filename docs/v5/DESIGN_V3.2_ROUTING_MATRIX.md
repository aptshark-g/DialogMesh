# Intent Routing — 二维复杂度路由矩阵 (V3.2)

> 2026-07-22 · 吸收 STC 提案，补全画像动态偏置
>
> 核心: 语义距离 (X) × 句法复杂度 (Y) × 用户状态偏置 (Z)
>       不是 5 路独立信号 → 是一个 3 维路由空间

---

## 一、问题回顾

```
旧设计 (V3.1): 5 路独立信号 → 贝叶斯乘积
  问题: 每路信号独立建模, 缺少交叉维度交互
        SVO距离远≠COMPANION (用户可能是跨域专家深度推理)
        SVO距离近≠TOOL (用户可能在闲聊技术名词)

新设计 (V3.2): 2D 语义-复杂度矩阵 + 1D 用户状态偏置层
  语义距离: 去哪找答案
  句法复杂度: 找答案需要多少步推理
  用户偏置: 矩阵阈值随用户状态动态浮动
```

---

## 二、句法地形复杂度 (Syntactic Terrain Complexity, STC)

```python
@dataclass
class SyntacticTerrain:
    """From stanza dependency parse only — zero LLM, ~5ms."""
    
    nesting_depth: int = 0       # 依存树最长路径 (Root → Leaf)
    information_density: float = 0.0  # 实词/总词 + 并列词数
    clause_count: int = 0        # 从句数量 (advcl/acl/ccomp)
    coordination_count: int = 0  # 并列结构数 (conj/cc)
    
    def tci(self) -> float:
        """Task Complexity Index: 0 (flat) → 2+ (mountain)."""
        nd_factor = min(self.nesting_depth / 5, 1.5) * 0.6
        id_factor = min(self.information_density * 2, 1.5) * 0.25
        clause_factor = min(self.clause_count * 0.15, 0.3)
        coord_factor = min(self.coordination_count * 0.15, 0.3)
        return nd_factor + id_factor + clause_factor + coord_factor
    
    @classmethod
    def from_stanza(cls, doc) -> "SyntacticTerrain":
        max_depth = 0; real_words = 0; total_words = 0
        clauses = 0; coordinations = 0
        
        for sent in doc.sentences:
            # Nesting depth per sentence
            depths = {}
            for w in sent.words:
                depth = 1
                cur = w
                while cur.head > 0:
                    depth += 1
                    cur = sent.words[cur.head - 1]
                depths[w.id] = depth
                max_depth = max(max_depth, depth)
                
                # Real words: noun/verb/adj/adv
                if w.upos in ('NOUN','VERB','ADJ','ADV','PROPN'):
                    real_words += 1
                total_words += 1
                
                # Clause detection
                if w.deprel in ('advcl','acl','acl:relcl','ccomp','xcomp'):
                    clauses += 1
                
                # Coordination
                if w.deprel in ('conj','cc','parataxis'):
                    coordinations += 1
        
        idensity = real_words / max(total_words, 1)
        return cls(
            nesting_depth=max_depth,
            information_density=idensity,
            clause_count=clauses,
            coordination_count=coordinations,
        )
```

---

## 三、六象限路由矩阵

```
                语义距离 (X) →
                近 ──────────── 远
     ┌─────────┬──────────────┬──────────────┐
  浅 │ 象限 I  │  原子操作     │  轻量检索     │
     │         │  cache/rule  │  retrieval    │
  STC│         │  不调 LLM    │  temp=0.1     │
  (Y) ├─────────┼──────────────┼──────────────┤
  ↓  │ 象限 II │  专家规划     │  混合推理     │
     │         │  planner     │  react-lite   │
  深 │         │  JSON plan   │  max_depth=2  │
     │         ├──────────────┼──────────────┤
     │ 象限 III│  重度工程     │  全量递归     │
     │         │  engineer    │  react-full   │
     │         │  tool chain  │  max_depth=5  │
     └─────────┴──────────────┴──────────────┘
```

路由映射：

| 象限 | X (距离) | Y (TCI) | 路由 | LLM策略 | 典型场景 |
|:---:|:---:|:---:|------|------|------|
| I | <0.3 | <0.5 | `FAST_EXECUTE` | 不调LLM | "scan 0x401000" |
| II | <0.3 | 0.5~1.0 | `PLANNER` | JSON结构化 | "重构这段代码" |
| III | <0.3 | >1.0 | `TOOL_CHAIN` | 工具链编排 | "反汇编→hook→比���→patch" |
| IV | >0.3 | <0.5 | `RETRIEVAL` | temp=0.1, 事实锚定 | "张三李四关系" |
| V | >0.3 | 0.5~1.0 | `REACT_LITE` | react, max_depth=2 | "跨域技术对比" |
| VI | >0.3 | >1.0 | `REACT_FULL` | react+CoT, depth=5 | "量子退火论证" |

---

## 四、动态偏置层 (Matrix Float)

**矩阵不是死的——用户状态让阈值浮动**：

```python
def apply_user_bias(matrix_position, user_state, profile, time_slot):
    """
    X_bias = f(attention_anchor, expertise)
    Y_bias = f(cog_resource, fatigue, time_of_day)
    
    效果: 下午2点专家用户在逆向工程域 → X阈值左移 → 更多"近"路由
          凌晨3点疲劳用户 → Y阈值下移 → 更多"浅"路由
    """
    # X偏置: 注意力锚点匹配→语义距离缩小
    if user_state.attention_anchor and anchor_in_text(text):
        matrix_position.x *= 0.6  # 感知距离缩小
    
    # X偏置: 领域专长→跨域容忍度提升  
    if profile.domain_expertise > 0.7:
        matrix_position.x *= 0.8  # 专家能handle更远的迁移
    
    # Y偏置: 认知疲劳→降低复杂度阈值
    cog_decay = 1.0 - user_state.cog_resource * 0.4  # fatigue factor
    matrix_position.y *= max(0.6, cog_decay)
    
    # Y偏置: 时间节律
    if time_slot == "deep_work" and profile.peak_hours_match(time_slot):
        matrix_position.y *= 1.2  # 黄金时段→接受更高复杂度
    
    return matrix_position
```

---

## 五、与已有系统的集成

```
输入 → stanza依存解析 (5ms)
       ├→ STC (嵌套深度+信息密度)
       └→ SVO提取 (主语+宾语)
            └→ BGE cosine (语义距离)

(STC, 距离) → 矩阵定位
               └→ 用户偏置浮动
                   └→ 路由决策
```

**Profile 需要新增的字段**：
- `domain_expertise_map`: {领域: 熟练度} — 影响 X 偏置
- `peak_hours`: [9,10,14,15,16] — 影响 Y 偏置
- `cog_decay_rate`: 连续工作衰减率 — 影响 Y 偏置

---

## 六、实施优先级

| 优先级 | 内容 | 状态 |
|:---:|------|:---:|
| P0 | stanza STC 提取 (嵌套深度+密度) | stanza已装, 需写提取器 |
| P0 | 六象限路由矩阵 | 设计完成 |
| P1 | BGE cosine 语义距离 | 需下 bge-small 模型 |
| P1 | 用户偏置浮动层 | Profile 扩展后 |
| P2 | 路由→LLM策略映射 | Planning 链集成 |

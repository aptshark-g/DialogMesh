# Topic Tree 实现——待讨论的模糊点

> 2026-07-22

---

## 可直接实现（无歧义）

| 项 | 内容 | 依赖 |
|----|------|------|
| L1 摘要 | 块内容 → LLM 压缩 (已有 summary_engine) | ✅ |
| L-root | 全局关键词提取 | ✅ |
| 图遍历距离 | BFS 从活跃节点 → GraphStore | ✅ |
| 分支管理 CRUD | fork/merge/switch 数据模型 | ✅ |

---

## 需要讨论（5 个模糊点）

### 1. 温度策略 vs 距离衰减——两套粒度体系怎么统一？

**问题**: 设计里存在两套控制摘要粒度的概念：

```
距离衰减:  近→细(L1), 中→中(L2), 远→粗(L3)
温度策略:  Hot(不压缩), Warm(规则压缩), Cold(LLM压缩), Frozen(只留索引)
```

它们的**轴不同**：
- 距离 = 空间维度 (离消费点多远)  
- 温度 = 时间+重要性维度 (多久没访问, 多不重要)

**核心矛盾**: 一个"距离近但温度冷"的节点应该用 L1(细) 还是 Cold(LLM压缩)？

**需要决策**: 
- A) 距离主导温度 (距离近就必须细, 温度只在同距离内区分)  
- B) 温度主导距离 (温度冷就压缩, 距离只影响注入优先级)  
- C) 乘法融合 (effective_granularity = distance × temperature)

---

### 1 结论：双视角并行，非融合

**本质**: 温度 ≠ 距离的另一种表达。它们是两个正交维度，不应"统一"。

```
距离 = 树拓扑推导链 (空间)
  → 同级发散: a,b,c 并列关系
  → 深度收束: a→b→c 因果推导
  → 回溯纠错: 发现推导链问题,回到a之前重新构建
  → 这是树结构的天然优势

温度 = 行为时序注意力 (时间)
  → 用户频繁访问a → a热
  → 用户三小时未碰b → b冷
  → 反映"用户此刻关心什么"
```

**核心洞察**: 系统不应只是用户影子——需要独立视角。

```
用户视角 (温度驱动):  a热 → 保证a的推导链完整不丢失
系统视角 (距离驱动):  b处于关键拓扑位置 → 即使b冷也独立推荐

典型场景:
  用户在调试内存扫描 → a(scan)高温 → 树推导a无误
  系统发现 b(packer_detection) 在拓扑上与a存在约束链 → b冷但推荐
  用户可能完全没注意到b, 但b是系统视角下的关键路径
```

**设计方案——双通道上下文**:

```python
class DualPerspectiveContext:
    """两个并行的上下文通道, 不是竞争Token, 是互补注入"""
    
    user_channel: List[Summary]   # 温度驱动: 保证用户关心的不丢失
    system_channel: List[Summary] # 距离驱动: 系统独立发现的关键路径
    
    def assemble(self, active_node: str, token_budget: int):
        # 用户通道 (50% budget): 温度排序, 取top-k热节点
        user_ctx = self._hot_path(active_node, budget=int(token_budget * 0.5))
        
        # 系统通道 (50% budget): 拓扑关键节点, 无论冷热
        sys_ctx = self._topology_critical(active_node, budget=int(token_budget * 0.5))
        
        return user_ctx + sys_ctx
```

**温度在树推导中的角色**: 自适应调节。用户注意力无限时 → 自然沿推导链层层收束。但现实中注意力有限且可能是网状思考（开放命题常见）→ 需要 LLM 协同判断何时"跳出当前推导链去看系统推荐"。这是后续优化方向，不是当前阻塞。

**决策**: 温度与距离**独立存在**, 不融合。各自驱动一个上下文通道。温度不截断距离, 距离不覆盖温度。

### 2. 摘要缓存失效——级联更新怎么控制？

**问题**: 一个叶子节点内容变了，需要重算哪些？

```
Block B3 修改
  → 重算 B3 的 L1 (直接包含)
  → 重算其分支的 L2 (间接影响)?
  → 重算所有祖先的 L3?
  → 甚至重算 root?
```

**关键**: 如果每次都全链路重算，LLM 成本爆炸。如果只算直接受影响层，摘要会越来越"陈旧"。

**需要决策**: 
- A) 仅重算直接包含层 (L1), 上层等 TTL 过期自然刷新
- B) 标记脏 (dirty flag), 下次访问时懒重算
- C) 异步队列, 低成本 LLM 逐层重算

---

### 2 结论：内容不变，关系变。关系块元信息 + 懒加载

**前提**: 对话是事实，事实不可变。变的是事实之间的**关系**，不是事实本身。

```
事实层 (不可变):
  Block A = "用户在调试内存扫描"
  Block B = "用户询问packer检测"
  Block C = "用户修改了hook逻辑"
  → 这些内容永远不变

关系层 (可变):
  旧: A → B → C (时序链)
  新: B → C → A (用户回溯, 关系重组)
  → A/B/C 内容没变, 变的只是它们的顺序和关联

摘要 = 对不变事实的多信息压缩
  → 事实不变 → 摘要内容不需要重算
  → 关系变了 → 只需要调整元信息
```

**核心抽象——关系块 (Relation Block)**:

```
关系块 = {事实引用, 关系元数据}
  
元数据内容:
  - 拓扑位置: 在推导链中的深度/同级位置
  - 关联类型: 因果/时序/并列/矛盾
  - 权重变化: 从主路径变成分支 / 从分支变为主路径
  - 版本标记: git-like diff, 可回滚
```

**工作流程——懒加载, LLM 按需重组**:

```python
class RelationMetadataManager:
    """管理关系块元信息, 不重算摘要内容"""
    
    def on_relation_change(self, block_a: str, block_b: str, new_relation: str):
        """关系变化时: 只更新元信息, 不触发摘要重算"""
        self.metadata_store.update(block_a, block_b, {
            "relation": new_relation,       # 新关系类型
            "version": self.version + 1,     # git-like 版本
            "changed_at": now(),
        })
        # ❌ 不调用 LLM 重算摘要
        # ✅ 只写元信息

    def prepare_for_llm(self, subgraph: Subgraph, blocks: List[str]):
        """子图来取时: 带上内容+元信息, 交给 LLM"""
        context = []
        for block_id in blocks:
            content = self.fact_store.get(block_id)     # 不可变事实
            metadata = self.metadata_store.get(block_id) # 当前关系元信息
            context.append({
                "content": content,
                "relation": metadata.relation,           # "这个block现在处于什么位置"
                "changed_from": metadata.previous_relation, # "之前是什么关系"
            })
        return context
        # LLM 自带内容+元信息 → 自行理解新关系拓扑 → 产出调整后的回应
```

**三级响应机制**:

```
第一级 (始终在线): 调整元信息
  → 记录关系变化, 标记版本, 不调 LLM

第二级 (小模型可用时): 小模型协作调整关系块
  → 本地 nemotron 处理简单关系重组
  → 降低远程 LLM 负担

第三级 (LLM 资源充足时): 元认知自动调整
  → Meta subscriber 发现关系变化累积
  → 触发 LLM 做深度关系重组
  → git-like 版本控制保证可回滚
```

**为什么不需要"重算摘要"**: 摘要内容来自事实 + 元信息的**投影**。事实不变 → 投影源不变。关系变化 → 只需改变"如何排列这些投影"。LLM 看到 {内容 + "这个block现在是A的前置而非B的后置"} → 自然理解新关系。子图负责排布顺序, LLM 负责识别关系。

**Git 底气的来源**:
```
metadata_store = {
    "block_a_to_b": [
        {"version": 1, "relation": "A_after_B", "timestamp": t1},
        {"version": 2, "relation": "A_before_B", "timestamp": t2},  # 关系变了
    ]
}
→ 任何时刻可回滚到 version 1
→ 关系变化是可追溯、可逆转的
```

**决策**: 
- 摘要不因关系变化而重算
- 只更新关系块元信息
- 子图取时带元信息给 LLM
- LLM 自行理解重组后的关系拓扑
- Git 版本控制保证安全

---

### 3. 分支定义——DiscourseBlockTree 边界 vs 图社区检测，谁说了算？

**问题**: 分支有两个可能的定义来源：

```
来源A: DiscourseBlockTree 的 segment 边界 (词汇链/主题切换)
  精确, 但只在对话树域内有效

来源B: GraphRAG 社区检测 (Leiden/Louvain)  
  跨域 (行为/关联/工程节点也可参与), 但计算昂贵
```

两者可能**不一致**——DiscourseBlockTree 说这属于分支A, 社区检测说属于分支B。

**需要决策**:
- A) DiscourseBlockTree 为主, 社区检测做验证/修正
- B) 社区检测为主, DiscourseBlockTree 做初始种子
- C) 两者并立, Topic Tree 维护自己的分支映射

---

### 4. 摘要刷新触发时机——每轮？懒加载？事件驱动？

**问题**: 什么时候触发摘要生成？

```
选项A: 每轮对话都刷新 — 最准确, LLM 成本高
选项B: 懒加载 (访问时生成) — 零浪费, 首次访问延迟高
选项C: 分支切换时触发 — 折中, 但"热"分支需要频繁刷新
选项D: 内容变化 + TTL 混合 — 灵活, 但实现复杂
```

**需要决策**: 对于 L1/L2/L3/L-root 各自应该用什么策略？可能不同层需要不同策略。

---

### 5. 跨分支上下文组装——Token 预算分配算法

**问题**: 消费一个节点时, 需要注入多少上下文？距离衰减公式给了粒度, 但 Token 预算是有限的。

```
场景: 用户问微观问题 (当前节点在叶子)
  需要: 大量 L1 (同分支细节) + 少量 L2 (兄弟分支) + 极少量 L3 (全局)

场景: 用户问宏观问题 (跨越多个分支)
  需要: 少量 L1 + 大量 L2/L3 + root
```

**需要决策**: Token 预算在各层之间如何动态分配？有没有优先级队列算法？

---

## 建议讨论顺序

1. 先定 **分支定义** (问题3) —— 这是基础, 影响所有上层
2. 再定 **温度vs距离** (问题1) —— 影响摘要生成策略
3. 然后定 **刷新时机** (问题4) + **缓存失效** (问题2) —— 一起决定
4. 最后定 **Token分配** (问题5) —— 这是调优, 可以后做

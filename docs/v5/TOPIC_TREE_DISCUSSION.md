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

### 3 结论：不求一致，求糅合。子图的多视角融合交给 LLM

**前提**: 对话是事实，不存在争议。存疑的是内在联系——不同模块对同一事实有不同的解读。这不是 bug，这是 feature。

```
用户: "实现功能A"

工程链视角:  A应该在现有模块B基础上扩展
  → 分支定义: A 属于 B 的子节点
  → 理由: 最小改动, 约束继承

关联链视角:  A应该重构到独立模块C
  → 分支定义: A 是独立分支, 与 B 同级
  → 理由: 语义本体类型不兼容, 长期维护成本

元认知:  两者都没有错, 取决于当前优先级
  → 工期紧迫 → 工程链视角权重↑
  → 质量优先 → 关联链视角权重↑
```

**核心**: 完全一致不仅不可能，也不需要。不一致本身就是 LLM 做权衡决策的关键输入。

**子图的真正角色——多视角糅合**:

```
子图 ≠ 选出"正确"的分支定义
子图 = 把多视角的分支定义都呈现出来

DiscourseBlockTree:  "从词汇链看, 这属于分支A"
社区检测:            "从跨域图结构看, 这属于分支B"
关联链:              "从语义本体看, A和B存在 type conflict"
工程链:              "从约束看, A在B的约束域内"

→ 子图打包这 4 个视角 → 交给 LLM
→ LLM 看到: "4个模块有3个认为该放A，关联链认为放B比较特殊"
→ LLM 自行权衡 (工期/质量/约束/语义)
```

**对应博客的三方案**:

```
方案一: 单关卡求解 → 适合确定性问题 (如分类)
方案二: 多层后验逐步收敛 → 适合可迭代验证的问题
方案三: 拉长 (extend) → 适合多视角不可调和的问题

分支定义 → 属于方案三。
  对话是事实 → 不需要妥协
  内在联系存疑 → 多个模块各自解读
  LLM 看到全貌 → 自行权衡
```

**实现**:

```python
class MultiPerspectiveBranchView:
    """不选边, 呈现多视角"""
    
    def get_branch_context(self, block_id: str) -> dict:
        perspectives = {}
        
        # 视角1: 对话树的词汇链
        dt_view = self.discourse_tree.get_segment(block_id)
        perspectives["discourse_tree"] = {
            "branch": dt_view.branch_id,
            "reason": f"词汇链相似度 {dt_view.cohesion:.2f}"
        }
        
        # 视角2: 图社区检测
        gc_view = self.graph_community.get_community(block_id)
        perspectives["graph_community"] = {
            "branch": gc_view.community_id,
            "reason": f"跨域图结构, 模块度 {gc_view.modularity:.2f}"
        }
        
        # 视角3: 关联链语义
        ac_view = self.association.get_type_compatibility(block_id)
        if ac_view.conflict:
            perspectives["association"] = {
                "conflict": ac_view.conflict_type,
                "reason": f"语义类型冲突: {ac_view.type_a} vs {ac_view.type_b}"
            }
        
        # 视角4: 工程链约束
        ec_view = self.engineering.get_constraint_domain(block_id)
        perspectives["engineering"] = {
            "domain": ec_view.domain,
            "reason": f"约束域: {ec_view.invariant}"
        }
        
        # 打包给 LLM — 不选边
        return {
            "block_content": self.fact_store.get(block_id),
            "perspectives": perspectives,
            "consensus": self._check_consensus(perspectives),  # True/False
        }
```

**共识状态的处理**:

```
有共识: perspectives 一致 → LLM 可以直接采纳
无共识: perspectives 分歧 → LLM 看到分歧原因, 自行权衡
  
无共识不是阻塞 — 是更好的上下文。
"3个模块说放A, 1个模块说放B因为类型冲突" 
→ LLM 获得的信息比"一致同意放A"更丰富
```

**决策**: 不选边。子图收集多视角分支定义 + 分歧原因。有共识自动采纳, 无共识交给 LLM 权衡。这恰好是元认知存在的意义——当需要最终基调时, Meta 根据全局状态做出统一决策。

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

### 4 结论：行为驱动 + 分层策略。纠错 = 最强信号

**核心纠正**: 摘要刷新的触发源不是时间, 不是内容变化——是**行为**。

```
对话 = 行为的一种形式
纠错 = 行为
情绪 = 行为
沉默 = 行为
一切用户动作 = 行为

这就是为什么我们需要 PCR/Association/Behavior/Profile/Meta 这么多模块——
不是只为了"记住对话", 而是捕捉行为的全维度。
```

**纠错作为最高优先级信号**:

```
用户纠正 → 意味着摘要已经出错了
  → 这不是 TTL 过期
  → 不是内容自然变化
  → 是系统理解错误 — 必须立即修复

关系块在单轮内也需关注:
  用户: "明天 14:00 会议室 B, 密码 8842"
  → 如果 L1 摘要写成 "用户安排了会议"
  → 漏掉了时间/地点/密码 — 这是关键实体丢失
  → 用户后续纠正 → 触发摘要修复 + 提取质量审查
```

**分层策略——行为触发 + 本地模型降本**:

```python
class BehaviorDrivenRefresh:
    """
    L1 (细粒度): 本地模型可每轮都跑 (Hermes 设计参考)
    L2 (中粒度): 纠错触发 OR 行为突变 OR TTL>10轮
    L3 (粗粒度): 分支切换 OR Meta 审查 OR TTL>30轮
    L-root:     新分支创建 OR 全局行为漂移
    """
    
    def on_user_correction(self, block_id: str, correction: str):
        """纠错 = 最强刷新信号 — 级联标记"""
        # L1: 立即用本地小模型重新摘要
        self.regenerate_l1(block_id, model="local")
        
        # 标记相关 L2/L3 为 dirty — 不立即重算
        affected = self.tree.ancestors(block_id, levels=2)
        for node in affected:
            self.mark_dirty(node, reason=f"correction_at_{block_id}")
        
        # 触发 Meta 审查
        self.event_bus.publish("summary_corrected", {
            "block": block_id,
            "correction": correction,
            "extraction_quality": "downgraded"  # 可能漏了关键实体
        })
    
    def on_behavior_surge(self, behavior_type: str):
        """行为突变 → 相关分支摘要可能过时"""
        if behavior_type in ("topic_switch", "emotion_spike", "tool_change"):
            active_branch = self.tree.current_branch
            self.mark_dirty_all(active_branch, reason=f"behavior_{behavior_type}")
    
    def should_refresh(self, layer: str, node: str) -> bool:
        rules = {
            "L1": lambda: (
                self.is_dirty(node) or
                self.local_model_available()  # 本地模型在 → 每轮跑
            ),
            "L2": lambda: (
                self.is_dirty(node) or
                self.since_last_refresh(node) > 10  # TTL 兜底
            ),
            "L3": lambda: (
                self.is_dirty(node) or
                self.branch_switched() or
                self.since_last_refresh(node) > 30
            ),
        }
        return rules.get(layer, lambda: False)()
```

**Hermes 设计参考**: Hermes Agent 的本地模型持续跑轻量任务, 远程模型处理重任务。我们的 L1 摘要同理——本地 nemotron 可以每轮都跑, L2/L3 等行为信号触发。

**行为信号的优先级排序**:

```
P0 (立即触发): 用户纠正 → 级联 dirty L1/L2/L3
P1 (本轮触发): 话题切换, 情绪突变, 工具更换
P2 (TTL 兜底): 距离上次刷新 > 阈值
P3 (资源空闲): Meta 审查 → 批量重组关系块
```

**决策**: 
- L1: 本地模型每轮可跑, 纠错立即可触
- L2/L3: 行为事件驱动 (纠错/切换/突变) + TTL 兜底
- L-root: 新分支或全局漂移
- 一切以用户纠正为最高优先级 — 这是摘要质量的真实反馈信号

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

### 5 结论：Token 预算是学习结果，不是固定算法。三维协同决定。

**核心纠正**: Token 预算不是工程师定义的一个公式——是**用户自己决定的**, 系统通过学习来适配。

```
质量优先型用户 (如你):
  → Token 预算高, 不怕消耗, 要最完整的上下文
  → "宁可多给, 不可遗漏"

性价比优先型用户:
  → Token 预算低, 要精炼的核心信息
  → "够用就好, 别浪费"

这不是一个"正确值" — 是用户画像的一维。
```

**三维协同模型**:

```
                    ┌─────────────┐
                    │  用户画像    │ ← "这个人偏好什么？"
                    │  (Profile)   │    OCEAN/质量倾向/耐心度
                    └──────┬──────┘
                           │ quality_preference
                           ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  行为链      │    │   Token     │    │  元认知      │
│ (Behavior)   │───→│   预算      │←───│  (Meta)     │
│              │    │  分配器     │    │             │
│ 用户在做什么？│    │             │    │ 现在该给多少？│
└─────────────┘    └─────────────┘    └─────────────┘
                           │
                           ▼
              其他模块也提供信号:
                Intent: query_complexity → 复杂问题多给
                PCR: expectation → TOOL 多给 (需要精确), MIRROR 少给 (要倾听)
                TopicTree: branch_depth → 深度推导需要更多上下文
```

**学习过程——不是预设，是观察**:

```python
class LearnedTokenBudget:
    """Token 预算从用户行为中学习, 不是硬编码"""
    
    def __init__(self):
        self.user_quality_bias = 0.5  # 初始中性
        self.observation_window = []
    
    def observe(self, interaction: dict):
        """观察用户行为, 调整质量偏好"""
        signals = {
            "reads_full_response": interaction.get("scroll_depth", 0) > 0.8,
            "asks_followup": interaction.get("followup_count", 0) > 0,
            "corrects_detail": interaction.get("corrections", 0) > 0,
            "accepts_quickly": interaction.get("response_time", 999) < 2,
            "ignores_long": interaction.get("skip_rate", 0) > 0.3,
        }
        
        # 质量追求者: 读完全文 + 追问 + 纠正细节
        if signals["reads_full_response"] and signals["asks_followup"]:
            self.user_quality_bias += 0.05  # 更喜欢完整信息
        
        # 效率追求者: 快速接受 + 跳过长文
        if signals["accepts_quickly"] and signals["ignores_long"]:
            self.user_quality_bias -= 0.05  # 更喜欢精炼
        
        self.user_quality_bias = max(0.1, min(1.0, self.user_quality_bias))
    
    def allocate(self, base_budget: int, context: dict) -> dict:
        """根据学习到的偏好分配 Token"""
        
        # 用户基础偏好
        quality_factor = self.user_quality_bias  # 0.1~1.0
        
        # 元认知调整: 当前状态
        if context.get("user_frustrated"):
            quality_factor *= 0.6  # 用户烦躁 → 精简
        if context.get("deep_exploration"):
            quality_factor *= 1.3  # 深度探索 → 扩展
        
        # 意图调整: 任务类型
        if context.get("expectation") == "TOOL":
            quality_factor *= 1.2  # 工具操作 → 需要精确上下文
        
        adjusted_budget = int(base_budget * quality_factor)
        
        # 在各层之间分配 (距离衰减权重不变, 总量可变)
        return self._distribute(adjusted_budget, context["active_node"])
```

**核心**: Token 预算不是一个静态的 `allocate(2000, active_node)`。它随用户变化——系统观察用户行为，学习这个用户是"质量型"还是"效率型"，然后动态调整。Profile 记录这个偏好，Behavior 提供实时信号，Meta 做最终协调。

**决策**: 
- Token 预算是学习结果, 不是预设算法
- Profile 记录用户质量偏好
- Behavior 提供实时行为信号
- Meta 根据当前状态 (疲劳/探索/纠正) 动态调整
- 距离衰减权重不变, Token 总量可变

---

## 讨论完成 ✅

全部 5 个模糊点已决议：
1. 温度vs距离 → 双视角并行, 不融合
2. 缓存失效 → 关系块元信息 + 懒加载
3. 分支定义 → 多视角糅合, LLM权衡
4. 刷新时机 → 行为驱动, 纠错=P0
5. Token预算 → 学习结果, 三维协同

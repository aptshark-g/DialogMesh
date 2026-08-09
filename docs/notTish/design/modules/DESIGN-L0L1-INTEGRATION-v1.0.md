# L0-L4 → Layer 1 反向索引集成设计方案

> **文档编号:** LC-DESIGN-L0L1-INTEGRATION-v1.0
> **版本:** v1.0
> **状态:** 📋 DRAFT
> **日期:** 2026-06-19
> **依赖:** v5.2d (Universal Coarse Matcher), L0-L4 Seed Library

---

## 1. 问题陈述

当前 Layer 1 领域分类器仅覆盖 6 个理工领域，而 L0-L4 种子库包含 49 个抽象节点（元理论、公理、数学、方法、物理）。两层之间无数据通路，导致：

1. **文本命中 L0-L4 但无法路由到 Layer 1 领域**
   - 例：文本含 "Bellman equation" → 命中 L3 "Dynamic Programming" → 但无法关联到 control_system / economics / biology
   
2. **新领域扩展依赖人工编码**
   - 每新增一个领域需手写关键词规则
   - 无法自动从 L0-L4 的丰富语义推导领域归属

3. **跨域同构判定缺少入口**
   - L0-L4 是跨域结构匹配的核心锚点
   - 但文本进入系统的第一层（领域分类）就断了

---

## 2. 核心设计：反向索引 (Reverse Index)

### 2.1 概念

```
L0-L4 抽象节点
    │
    │  反向索引: 每个抽象节点 → 候选应用领域列表
    │  (基于节点的 description/aliases/keywords 中提到的应用域)
    │
    ▼
候选领域列表（带关联强度）
    │
    │  与 Layer 1 精确匹配融合
    │
    ▼
最终领域分类
```

### 2.2 索引结构

```json
{
  "method-3": {
    "node_id": "method-3",
    "node_name": "Dynamic Programming & Optimal Substructure",
    "candidate_domains": [
      {"domain": "control_system", "strength": 0.9, "evidence": ["MPC", "reinforcement learning"]},
      {"domain": "economics", "strength": 0.7, "evidence": ["resource allocation", "Bellman"]},
      {"domain": "biology", "strength": 0.5, "evidence": ["sequence alignment"]}
    ]
  }
}
```

### 2.3 关联强度计算

从 L0-L4 节点的 `description` 中自动提取领域关联：

```python
def extract_domain_mentions(description: str) -> Dict[str, float]:
    """
    扫描 description 中的领域提及。
    格式："In [domain]: ..." 或 "In [field], ..."
    """
    domain_indicators = {
        "control": "control_system",
        "control system": "control_system",
        "machine learning": "machine_learning",
        "biology": "biology",
        "economics": "economics",
        "physics": "physics",
        "chemistry": "chemistry",
        "materials": "materials_science",
        "mechanical": "mechanical_system",
        "thermal": "thermal_system",
        "electrical": "electrical_system",
        "image processing": "image_processing",
        "signal processing": "signal_processing",
        "optimization": "optimization",
        "finance": "finance",
        "ecology": "ecology",
        "epidemiology": "epidemiology",
        "climate": "climate_science",
        "quantum": "quantum_physics",
    }
    
    # 统计每个领域指示词在 description 中的出现次数
    # 返回归一化的关联强度
```

---

## 3. 融合分类策略

### 3.1 三层信号融合（扩展版）

```
文本输入
    │
    ├──→ Layer 1 精确匹配（关键词） → score_exact
    │
    ├──→ L0-L4 抽象概念匹配 → 命中节点 → 反向索引 → score_abstract
    │
    └──→ 通用元框架（DEVS/范畴论） → score_meta
         (v5.2d Phase 3 实现)

最终分数 = w1 * score_exact + w2 * score_abstract + w3 * score_meta
```

### 3.2 权重配置

| 信号源 | 权重 | 说明 |
|--------|------|------|
| Layer 1 精确匹配 | 0.5 | 最高置信度，领域特异关键词 |
| L0-L4 反向索引 | 0.3 | 中等置信度，抽象到应用的推导 |
| 通用元框架 | 0.2 | 兜底，结构级归约 |

---

## 4. 自动扩展机制

### 4.1 从 L0-L4 推导候选领域

当文本命中 L0-L4 节点但 Layer 1 无精确匹配时，不直接降级到 LLM，而是：

```python
def classify_with_l0l4_bridge(text: str) -> DomainClassification:
    # 1. 先尝试 Layer 1 精确匹配
    exact = classify_exact(text)
    if exact.confidence >= 0.8:
        return exact
    
    # 2. 匹配 L0-L4 抽象节点
    matched_nodes = match_l0l4_nodes(text)
    if matched_nodes:
        # 3. 反向索引获取候选领域
        candidates = reverse_index_lookup(matched_nodes)
        
        # 4. 如果有候选领域，返回最高置信度
        if candidates:
            best = max(candidates, key=lambda x: x.strength)
            return DomainClassification(
                layer=1.5,  # 新层级：抽象推导
                domain_id=best.domain,
                confidence=best.strength * 0.8,  # 打折扣
                source="l0l4_bridge"
            )
    
    # 5. 降级到通用元框架 / LLM
    return classify_meta(text)
```

### 4.2 动态规则生成

当 L0-L4 反向索引产生一个新的 `domain_id`（不在当前 Layer 1 模板中）：

```python
# 自动生成最小领域规则
def generate_domain_rule_from_l0l4(domain_id: str, nodes: List[Node]) -> DomainRule:
    """
    从关联的 L0-L4 节点中提取关键词，生成领域规则。
    """
    all_keywords = set()
    for node in nodes:
        all_keywords.update(node.keywords)
        all_keywords.update(node.aliases)
    
    return DomainRule(
        domain_id=domain_id,
        keywords=all_keywords,
        formal_language=infer_formal_language(domain_id),  # 推断形式化语言
        template_path=f"templates/{domain_id}.json",  # 占位
        source="auto_generated_from_l0l4"
    )
```

---

## 5. 实施计划

### Phase 1：反向索引构建（1天）

| 任务 | 文件 | 说明 |
|------|------|------|
| 解析 L0-L4 JSON | `scripts/build_l0l4_index.py` | 从种子文件提取节点和描述 |
| 领域提及提取 | `layer1/l0l4_reverse_index.py` | 从 description 提取 "In X:" 模式 |
| 索引持久化 | `data/l0l4_reverse_index.json` | 预计算索引，运行时加载 |
| 集成到分类器 | `layer1/domain_classifier.py` | 添加 L0-L4 匹配分支 |

### Phase 2：动态扩展（0.5天）

| 任务 | 文件 | 说明 |
|------|------|------|
| 候选领域生成 | `layer1/domain_classifier.py` | 未命中时尝试 L0-L4 桥接 |
| 自动规则生成 | `layer1/auto_domain_generator.py` | 从节点推导最小规则 |
| 置信度校准 | `layer1/scoring.py` | 抽象推导的置信度折扣 |

### Phase 3：验证（0.5天）

| 测试 | 输入 | 期望 |
|------|------|------|
| Bellman 论文 | "Bellman equation in MPC" | control_system (via method-3) |
| 生物序列比对 | "Needleman-Wunsch alignment" | biology (via method-3) |
| 材料合金搜索 | "combinatorial search for alloys" | materials_science (via method-1) |

---

## 6. 预期效果

| 指标 | 当前 | 集成后 |
|------|------|--------|
| Layer 1 领域数 | 6 | 6 + 动态扩展 |
| 可推断领域数 | 0 | 20+ (从 L0-L4 推导) |
| 非物理覆盖 | 0% | ~40% (经 L0-L4 桥接) |
| LLM 降级率 | ~50% | ~20% |

---

## 7. 一句话总结

**L0-L4 不是与 Layer 1 割裂的抽象层，而是 Layer 1 的「语义放大器」。通过反向索引，49 个抽象节点成为 20+ 应用领域的推导入口，让文本在未命中精确关键词时，仍能经由「抽象概念 → 候选领域」的桥梁完成分类。**

---

*文档版本: v1.0*
*日期: 2026-06-19*
*维护者: 合作 (OpenClaw)*

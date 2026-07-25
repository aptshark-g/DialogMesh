# DialogMesh v6 — 核心设计哲学 × 实现状态

> 2026-07-24 · 重写: 纠正"LLM-first vs 规则优先"的伪二分

---

## 一、真正内核：一切皆为行为

```
每个操作 = 一次行为(Behavior)

LLM → call(规则)    = 行为
规则 → trigger(LLM)   = 行为
LLM → call(LLM)     = 行为 (子任务委派)
用户 → edit(节点)     = 行为
用户 → review(规则)   = 行为
算法 → notify(LLM)    = 行为
```

没有"LLM-first"也没有"规则优先"。**编排系统是唯一的调度者**——它从蓝图中选择执行模式。

## 二、四层调用权限模型

```
┌──────────────────────────────────────────────┐
│  编排系统 (AgentNativeOrchestrator)           │
│  选择蓝图 → 调度行为 → 记录结果               │
├──────────────────────────────────────────────┤
│                                              │
│  蓝图1: 规则直连 (0ms LLM)                   │
│    用户输入 → regex分类器 → 确定性回答        │
│    适用: 会员号查询、简单事实、高频模式        │
│                                              │
│  蓝图2: LLM+规则协同 (1次LLM)                 │
│    LLM分析 → 选择规则 → 规则执行 → LLM审查    │
│    适用: 意图分类、实体消歧、路由决策          │
│                                              │
│  蓝图3: LLM多步推理 (2-5次LLM)                │
│    LLM→工具→观察→LLM→决策→执行               │
│    适用: 复杂任务分解、多意图、开放域           │
│                                              │
│  蓝图4: 联邦并行 (多次LLM+规则并行)            │
│    6源并行搜索 → 结果合并 → LLM仲裁           │
│    适用: 跨域检索、长记忆、多视角决策          │
│                                              │
│  蓝图5: 用户交互 (LLM暂停, 等用户)             │
│    LLM提出候选 → 用户选择/编辑 → LLM继续       │
│    适用: 歧义消解、关键决策、关系标注          │
│                                              │
└──────────────────────────────────────────────┘
```

## 三、蓝图的本质：约束模式

```
蓝图不是"固定流程" — 是"约束模板"

Blueprint {
  "max_llm_calls": 3,         // 不希望无限循环
  "min_confidence": 0.7,       // 低置信不走规则
  "allowed_callers": ["LLM","user"],  // 权限控制
  "hot_path_first": true,      // 先试热路径
  "fallback": "blueprint_3",   // 失败→升级蓝图
}
```

编排器根据当前状态(用户画像/信念/上下文)选择蓝图，LLM在蓝图约束内自由操作。

## 四、当前实现对照

### ✅ 已完成

| 行为类型 | 实现 | 状态 |
|----------|------|------|
| LLM→call(LLM) | V4 MetaCognition submit→review→decision | ✅ 桥接接通 |
| LLM→call(算法) | PCR调用jieba+BM25+向量搜索 | ✅ |
| 算法→notify(LLM) | L4 drift检测→LLM verify_transition | ✅ |
| 用户→edit(节点) | correction_journal.record() | ✅ |
| LLM→多源并行 | federated_index 6源搜索 | ✅ |
| LLM→存储 | persistence broker 10链 | ✅ |

### 📋 未实现

| 行为类型 | 缺口 |
|----------|------|
| 规则→trigger(LLM) | regex分类器已移除, 需重建为可调用工具 |
| 蓝图选择引擎 | design存在, 代码为零 — 编排器直接硬编码了蓝图1 |
| 权限控制 | 无调用者身份验证 |
| 蓝图DSL | 蓝图定义格式存在于设计, 未序列化实现 |
| 用户→review(关系) | RelationSubstrate改完, 但无用户界面 |
| 规则→notify(规则) | 链式规则触发未实现 |

### 🔑 漏掉的根源：蓝图编排系统

```
当前 agent_native.py:
  process() { PCR → Intent → L4 → Behavior → Engineering → LLM }
  ↑ 硬编码了蓝图1的线性流程

设计意图:
  process() { 读蓝图 → 调度行为 → 监控 → 动态切换蓝图 }
  ↑ 编排器不预设流程
```

## 五、需要补的核心缺口（按优先级）

```
P0 — 蓝图选择引擎
  当前: agent_native 硬编码流程
  目标: AgentNativeOrchestrator 从 blueprint_registry 选择蓝图

P0 — 规则工具注册
  当前: regex分类器已移除
  目标: IntentClassifier 注册为可调用工具, LLM可选调

P1 — 权限 + 调用者追踪
  当前: 无
  目标: 每个行为记录 source(LLM/rule/user), blueprint_version

P1 — 蓝图热切换
  当前: 无
  目标: 低置信→自动升级蓝图 (blueprint_1→blueprint_3)
```

---

## 六、修正后的全模块对照

```
文档版本: v2 — 修正后
上一版(DESIGN_IMPLEMENTATION_DEEP_COMPARISON.md)的"LLM-first vs 规则优先"错误
→ 正确: 编排系统统一调度, LLM/规则/用户/算法是平等的行为主体
```

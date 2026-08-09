# B5-3 子图编辑 = 用户控制权 — 设计定案（2026-08-04）

> 定位: 真决策 B5-3（用户上下文控制权归属）正式定案 + 独立设计文档。
> 核心: 用户构想"决策白盒化 + 用户修正回流"完整闭环 → 三层分离设计。
> 关联: A19 白盒旗舰落地 + B2-3 多 agent 协作的用户侧版本 + A6/P6 用户纠正权重最高。
> 状态: ✅ 已拍板（2026-08-04）

---

## 一、核心洞察（三层分离，不是"子图编辑"）

```
层1 图结构 (用户可编辑)     ← 子图/关系图 (白盒)
层2 线性化编译 (给 LLM)     ← assemble_prompt / to_ir (现状: 纯文本 + IR 雏形)
层3 原始数据 (可恢复)       ← 持久化原文 (A17 记录永不可删)

关键: 用户编辑的是层1, LLM 消费的是层2, 层3 永远保留
→ 精确对应 PARADIGM:
  A19 白盒 (层1 可操作) + A2 颗粒度 (层2 是层1 的缩放投影) + A17 记录 (层3 不可删)
```

---

## 二、代码现状（支撑构想的证据，全部实测）

### 层1 — 图编辑层（✅ 已有，缺挂载）
```
api_viz_edit.py (/v6/edit/*, 9.8KB) 5 端点:
  PUT /v6/edit/graph          — 图编辑 (GraphEditRequest)
  PUT /v6/edit/discourse-tree — 对话树编辑
  PUT /v6/edit/objects        — 对象编辑
  PUT /v6/edit/relations      — 关系编辑
  PUT /v6/edit/ir             — IR 编辑 (IREditRequest)
前端 ReactFlow 组件齐备:
  GraphEditPanel.tsx (9.7KB) / GraphToolbar.tsx (10.2KB) /
  ConversationGraph.tsx (15.2KB) / DiscourseTreeView.tsx (10.4KB)
缺: v6_app 挂载 (FE-1 P0 — api_viz_edit 未注册, 前端 404)
```

### 层2 — 编译层（✅ 已有雏形，缺 serializer 家族）
```
assemble_prompt:
  context/assembler.py:215 assemble → CrossDomainContext
  context/assembler.py:245 assemble_ir → IR
  v4/cognitive/subgraph_compiler.py:304 assemble_prompt (文本线性化)
  v4/cognitive/subgraph_compiler.py:313 to_ir (Context IR v2 结构化 JSON)
  cross_domain_ir.py: IREntry / CrossDomainContextIR
缺: XML / 自然语言 serializer（用户要求"最终可做结构化: XML/JSON/自然语言"）
```

### 层3 — 数据层（✅ 已有，缺恢复端点）
```
correction_journal.py (6KB):
  CorrectionJournal.record(dimension, before, after, reason) — 每次用户修正记录
  before/after/timestamp 全保留
  → 行为回流通道已存在（journal → 行为链/画像）
缺: "恢复"端点 (revert to original — 从 journal/持久化读回 before)
```

---

## 三、设计（用户构想正式化）

### 3.1 三层职责
```
层1 图编辑层 (A19):
  编辑对象: 子图节点 / 边 / 域权重 / 触发条件 (调节/删除/修改)
  → 用户控制"系统给 LLM 什么"
  补: 恢复端点 (revert) — 从 journal/持久化读回

层2 编译层 (A2):
  to_ir (已有) → 补 serializer 家族:
    JSON       (已有, 结构化精确)
    XML        (A8 精确语义, 树形结构自然映射)
    自然语言   (模糊, 通用模型友好)
  用户可选"最终给 LLM 的形态"

层3 数据层 (A17):
  持久化原文 + journal (已有) — 永不删, 可恢复
  用户可随时恢复最原始扁平化上下文
```

### 3.2 行为回流（A6 — 用户纠正权重最高）
```
用户编辑 = 行为事件:
  api_viz_edit → _journal.record → correction_journal
  → 行为链学习 (用户习惯) → 画像 (偏好) → 下次默认子图调整
  → 一次纠正影响层级 (A6/P6: 用户纠正 > 系统自纠)

通道已有 (journal → 行为链/画像), 补显式化:
  编辑行为作为一等行为事件进入行为链 (B2-3 持久化能力底座消费)
```

### 3.3 三档模式（默认智能 + 白盒可改 + 全白可选）
```
档1 默认智能: 系统默认给出编译好的子图 (系统决策呈现, A16 快)
档2 白盒可改: 用户在图编辑层调整 (A19 落地)
档3 全白 (Comfy 式): 用户关掉默认编译, 自己搓上下文
  → 三档并存, 用户可切换

与 ComfyUI 的差异 = 价值:
  ComfyUI: 从零搓图, 系统不提供默认
  我们:    默认给系统编译 → 用户修改 → 学习用户习惯
  → "默认智能 + 白盒可改 + 学习修正" 三合一
```

---

## 四、施工前置

```
B5-3-P1  FE-1 P0: api_viz_edit 挂 v6_app + init(engine) 注入
B5-3-P2  恢复端点: /v6/edit/revert (读 journal before → 应用回滚)
B5-3-P3  serializer 家族: XML / 自然语言 (JSON 已有)
B5-3-P4  编辑行为显式进行为链 (journal → 行为链学习闭环)
B5-3-P5  三档模式开关 (默认智能 / 白盒 / 全白)
B5-3-P6  前端 GraphEditPanel 接通 (层1 → 层2 预览 → 层3 恢复)
```

---

## 五、验收标准

```
① 前端图编辑可改节点/边/权重/触发条件 (无 404)
② 用户编辑后 LLM 消费的是编辑后的线性化/结构化内容
③ 原始数据保留, revert 可恢复最原始扁平化
④ 编辑行为被行为链/画像学习 (用户习惯回流)
⑤ 三档模式可切换 (默认/白盒/全白)
⑥ 四种给 LLM 的形态可选 (文本/JSON/XML/自然语言)
```

---

> 关联: G4/FE-1 (挂载 P0) + B2-3 (能力底座) + LLM-1 (认知层) + A19/A2/A17/A6

# M9 子图编辑层2/3（B5-3）— 施工进度 2026-08-04

> 状态: ✅ 完成（P3 serializer 家族 + P4 编辑行为回流）
> 定案依据: `docs/only/B53_SUBGRAPH_USER_EDIT_DESIGN_20260804.md`
> 前置: M2（层1 图编辑 + revert + 三档模式）+ M8（命令内核模式）
> 完成 M9 = **M1-M9 模块化施工清单全部完成（阶段 A 核心 9 模块）**

---

## 一、B5-3-P3 serializer 家族（✅ 完成）

### 1.1 新增 `core/agent/v4/cognitive/serializers.py`（~180 行）

```text
单一入口: serialize(ir, fmt) → {format, text, tokens}
四形态:
  json      — Context IR v2 直出（结构化精确, 默认）
  xml       — A8 精确语义, 树形结构自然映射 + XML 转义
  markdown  — 文本线性化（原 assemble_prompt 形态）
  natural   — 自然语言（通用模型友好, 模糊）
别名归一: text→markdown, nl→natural, prompt→markdown, structured→json
非法回退: json
```

### 1.2 SubgraphCompiler 接线（`subgraph_compiler.py`）

```text
set_format(fmt)   — 选择层2 默认形态（持久化到编译器实例）
get_format()      — 当前形态 + 可选列表
serialize(ctx|ir) — 统一渲染（接受 SubgraphContext 或 IR dict）
```

### 1.3 REST 端点（`api_viz_edit.py`）

```text
POST /v6/edit/serialize  — 渲染 _last_context IR 为指定形态（用户可编辑层2）
GET  /v6/edit/format     — 当前形态 + 可选列表
PUT  /v6/edit/format     — 切换默认形态（journaled + 同步 subgraph compiler）
```

---

## 二、B5-3-P4 编辑行为回流（✅ 完成）

### 2.1 `api_viz_edit.py` 新增 `_emit_behavior_edit`

```text
用户编辑 = 一等行为事件（A6: 用户纠正权重最高）:
  _journal() → journal.record (A17 修正记录, 已有)
             → _emit_behavior_edit → BehaviorGraphAdapter.record_step(
                 action_type="user_edit", correction=True)

→ 行为链学习用户习惯 → 画像偏好 → 下次默认子图调整
（B2-3 持久化能力底座消费, 一次纠正影响层级）
```

### 2.2 实测

```text
编辑前: behavior_graph stats node_count=0 session_steps=0
触发 user_edit 后: node_count=1 session_steps=1 ✅
```

---

## 三、测试（✅ 全绿）

```text
新增: core/agent/api/tests/test_m9_serializer_flow.py  11/11
  - serializer 四形态渲染（json/xml/markdown/natural + XML 转义 + 别名）
  - SubgraphCompiler set_format/serialize 接线（_subgraph 实例）
  - REST /v6/edit/serialize + /v6/edit/format
  - 编辑行为 → 行为链回流
回归: M9 11 + M2 viz_edit 29 + M8 kernel 49 = 89/89
```

### 环境注意

```text
- engine 的 subgraph 编译器属性名是 `_subgraph`（非 _subgraph_compiler）
- api_viz_edit 的 engine 注入靠 v6_app startup 事件 → 测试需 `with TestClient`
```

---

## 四、B5-3 验收对照

| 验收项 | 状态 |
|---|---|
| ① 前端图编辑可改节点/边/权重/触发条件（无 404） | ✅ M2（api_viz_edit 挂载） |
| ② 用户编辑后 LLM 消费编辑后形态 | ✅ P3 serialize（层2 = 层1 投影） |
| ③ 原始数据保留, revert 可恢复 | ✅ M2（/v6/edit/revert） |
| ④ 编辑行为被行为链/画像学习 | ✅ P4 _emit_behavior_edit |
| ⑤ 三档模式可切换 | ✅ M2（/v6/edit/mode） |
| ⑥ 四种给 LLM 的形态可选 | ✅ P3（json/xml/markdown/natural） |

---

## 五、遗留（归后续）

```text
- B5-3-P6 前端 GraphEditPanel 接通（阶段 B 一次性绑前端时做）
- 编辑行为 → 画像偏好 feed（当前到行为链, 画像侧归画像模块 P 系列）
```

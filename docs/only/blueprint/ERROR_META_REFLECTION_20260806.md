# 错误模式 → 元认知反思 — 基础设施 + 自改进闭环（2026-08-06）

> 触发讨论：类型/编码/匹配类错误反复出现（PowerShell 转码 / 中英文匹配 /
> 序列化防御 / conftest 崩溃），每次 patch 治标不治本。
> 结论：① 建 text_utils 基础设施（治标工具层）② 错误重复 = 元认知模式
> 信号（治本机制）——同类错误超阈值 → 反思裁决 → 改进，或用户明示触发。
> 状态：设计定案，待施工。前置：META_ARBITER P0（decision_bus 已可承载）。

---

## 一、问题分类（反复出现的 3 类）

| 类 | 实例 | 根因 | 解法 |
|---|------|------|------|
| 跨 shell 编码 | heredoc 中文变 `????` / 文件写入乱码 / 终端乱码 | PowerShell 管道编码 ≠ UTF-8 | **操作约定**（heredoc 走文件/apply_patch）+ normalize_text |
| 中英文语义匹配 | `discover("查论文")` 匹配不到英文工具描述 | 子串匹配算法 | **zh_keyword_match**（ToolAdapter.keywords_zh 已加） |
| 序列化/类型防御 | PathState 重复定义 / `str.value` / `Dict` 未 import / `float("high")` / conftest list-in 崩溃 | 缺统一类型安全层 | **safe_str / to_json_safe / assertrepr 防御** |

---

## 二、基础设施：`core/agent/common/text_utils.py`

```
safe_str(x, limit=500)      — 任意对象 → str（防 None/Dict 未定义/对象 repr 崩溃）
to_json_safe(x)             — 任意对象 → JSON 可序列化（before/after/工具结果）
zh_keyword_match(query, zh, en_text) — 双语言匹配（中文字典优先, 英文子串兜底）
normalize_text(s)           — UTF-8 归一化（去 BOM/混入编码/控制字符）
```

消费方（收拢散落 patch）:
- `discover()` → zh_keyword_match
- `DecisionEvent.to_dict()` → to_json_safe
- `executor._summarize_tool_result()` → safe_str
- `conftest.assertrepr_compare()` → 防御 list-in
- 工具结果/元认知 payload → to_json_safe

---

## 三、元认知反思闭环（治本机制）

### 3.1 错误模式事件（复用 decision_bus）

```
错误发生 → 写决策事件 kind=meta_advice, dimension="error_pattern.<type>"
  error_type: type_mismatch | encoding | zh_match | serialization | ...
  payload: {occurrence: N, window: 滑动窗口, examples: [...]}
```

### 3.2 触发源（双通道）

```
① 规则触发: 同 error_type 滑动窗口计数 ≥ 阈值（默认 3）
   → 自动进入反思队列（LLM 自触发, 不阻塞）
② 用户明示: 用户说"这个反复出现" → 最高优先级反思（A6 用户纠正权重最高）
```

### 3.3 反思裁决 → 改进

```
反思裁决（meta_advice 事件）:
  低风险（日志防御/参数默认）→ 自动应用（A18 参数自适应）
  中风险（匹配算法/序列化层）→ 建议 + 用户 approve（PR review 语义）
  高风险（架构改动）→ 进审核队列（PlanGate）

裁决输出 → decision_bus strategy_switch/meta_advice → 前端可回看
```

### 3.4 与 META_ARBITER 的关系

```
META_ARBITER: 执行偏差（超时/质量）→ 元认知裁决 → 策略切换
本设计:      错误模式（类型/编码/匹配）→ 元认知反思 → 基础设施改进
两者同构: 都是"信号 → 裁决 → 动作 → 事件 → 用户可介入"
只是信号源不同（执行偏差 vs 错误模式）
```

---

## 四、施工顺序

| # | 任务 | 内容 | 验收 |
|---|------|------|------|
| E1 | text_utils 模块 | safe_str / to_json_safe / zh_keyword_match / normalize_text | 单元测试 |
| E2 | discover 接 zh_keyword_match | "查论文" → arxiv_search | 中文 discover 测试 |
| E3 | 决策事件接 to_json_safe | before/after/工具结果可序列化 | 已有测试补强 |
| E4 | conftest assertrepr 防御 | list-in 崩溃修复 | 全量收集 0 错 |
| E5 | 错误模式计数 → meta_advice | 滑动窗口 + 阈值 + 反思事件 | 测试 |
| E6 | 用户明示触发 | 显式输入 "反复出现" → 反思 | 测试 |

---

## 五、验收门槛

1. 中文意图 discover 到英文工具（"查论文" → arxiv_search）
2. 任意对象进决策事件不崩（含 dataclass/None/自定义类）
3. conftest 不因 list-in 断言崩溃
4. 同类错误 3 次 → 自动 meta_advice 事件（可回看）
5. 用户明示 → 最高优先级反思事件
6. 基础设施消费方统一走 text_utils（无散落 str() 直接调用）

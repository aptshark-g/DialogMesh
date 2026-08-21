# B-3 固化前缀契约（编译器侧, 2026-08-22）

> 对齐网关 switch/prefix（B-1 指纹 / B-2 亲和 / B-4 预热）。
> 分工: **编译器拥有前缀, 网关拥有局部性**（基线原则 1）——固化在 DialogMesh,
> 网关只做指纹/亲和/预热/检测, 禁止静默改写字节。

## 一、分层映射

| 层 | 内容 | 网关段 |
|----|------|--------|
| P0 | 系统提示 + 平台工具定义 | Seg0（system + tools） |
| P1 | 租户块（人格/合规/租户知识） | Seg1（历史） |
| P2 | 项目块（项目语料/约束） | Seg1 |
| P3 | 会话块（折叠历史） | Seg1 |
| P4 | 本轮输入（时间戳/uuid/trace 等易变） | Seg2 |

## 二、铁律

1. P0..P3 **只追加、不插入、不重排**; 新知识用稳定 id 排序追加。
2. 时间戳/uuid/trace_id/request_id/session_id **只进 P4 或 header**——
   进前缀 = 每次命中失效。
3. 工具定义按 name 排序（编译器 + 网关 prefix 包双侧一致）。
4. 会话块折叠: 超过阈值用稳定模板摘要, 摘要字段固定, 每 K 轮一次。
5. 网关禁止改字节; 检测到漂移打 `prefix_drift_detected_total`, 不"修复"。

## 三、实现

- `core/agent/compiler/prefix_layout.py`:
  - `strip_volatile`（时间戳/uuid/req/trace/session 归一化占位）
  - `normalize_stable_prefix`（system 置前 + 历史去噪 + P4 保留原文）
  - `stable_fingerprint`（golden 0 漂移断言）
  - `tool_defs_sorted`
- 接线: `v3_session_api.py` llm_reply 路径, `DM_PREFIX_STABILIZE=1` 启用
  （默认关, 验证后开）。
- golden 测试: `core/agent/compiler/tests/test_prefix_layout.py`（5 例,
  同逻辑上下文不同时间戳/request_id → 0 漂移）。

## 四、验收

- golden 测试 0 漂移; 网关 `prefix_drift_detected_total` 只来自违规调用方。
- 启用后, 相同逻辑上下文的 `X-Context-Hash` 稳定 → L0 命中提升;
  上游前缀命中块变长（Profiler `hit_tokens_by_layer` 观察）。

## 五、待办

- 历史折叠实现（当前 P3 原文透传, 折叠器未做）。
- 工具定义真正进入前缀（当前工具在请求体, 网关 Seg0 已含; DialogMesh
  侧工具列表排序已在 helper, 生产接线待做）。
- P1/P2 分层（租户/项目块）随项目页语料体系落地。

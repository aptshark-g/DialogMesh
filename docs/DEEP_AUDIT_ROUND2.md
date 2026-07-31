# DialogMesh 深度核查 — 第二轮

> 2026-08-01 · 方法: 逐批次追踪真实行为, 非数端点
> 状态: 🔍 进行中

## 核查方法

```
每批核查 = 真实调用 + 检查返回数据 + 判断是否简化/存根
  1. 调用 CLI 命令 / API 端点
  2. 检查返回的是真实数据还是空壳
  3. 标记: ✅ 真实行为 / ⚠️ 部分简化 / ❌ 存根或失败
  4. 记录证据 (命令 + 输出摘要)
```

## 核查批次清单

| 批次 | 范围 | 状态 |
|------|------|:---:|
| Batch 1 | 引擎启动 + 管线 + 持久化 | ✅ 19/19 (verify_round1.py) |
| Batch 2 | v6 API 18 端点 | 🔍 |
| Batch 3 | CLI 核心命令 (engine/session/discourse) | ⏳ |
| Batch 4 | CLI 命令 (pcr/intent/behavior/meta) | ⏳ |
| Batch 5 | CLI 命令 (assoc/profile/concepts/mind) | ⏳ |
| Batch 6 | CLI 命令 (rules/engineering/annotations/knowledge) | ⏳ |
| Batch 7 | CLI 命令 (task/learning/data/registry) | ⏳ |
| Batch 8 | 存储层深度 (ChunkStore/RelationGraph/BlockMeta) | ⏳ |
| Batch 9 | 关联链深度 (L1/L2/L3/coref) | ⏳ |
| Batch 10 | 模型层 (stanza/st) | ⏳ |

## 核查结果汇总

| 批次 | ✅ | ⚠️ | ❌ | 备注 |
|------|:--:|:--:|:--:|------|
| Batch 1 | 19 | 0 | 0 | 引擎+管线+落盘全通 |
| Batch 2 | | | | |
| ... | | | | |

---

## Batch 2 — v6 API 深度核查

### 方法

启动后端 (scripts/start_server.py) → 逐端点 curl → 检查返回真实数据

### 结果

```
总端点: 89 (v6_app 挂载 5 个 router + legacy v3/v4)
✅ 200+真实数据: 66 (74%)
⚠️ 200+空数据:   7
❌ 错误:         16 (其中 14 个是 422 = 测试脚本没带 body, 非端点问题)
```

### 真实数据端点 (示例)

| 端点 | 返回 | 判断 |
|------|------|:---:|
| /v6/profile | OCEAN 8 维度真实值 | ✅ |
| /v6/abc | 6 条 neuro_symbolic 规则 (修复后) | ✅ |
| /v6/graph | 真实 graph nodes | ✅ |
| /v6/discourse-tree | 真实 block (session b84e1b45) | ✅ |
| /v6/objects | 真实 concept objects | ✅ |
| /v6/parameters | 真实参数配置 | ✅ |
| /v6/sessions | 真实 session 文件列表 | ✅ |
| /v6/context | assembler/budget/pruner | ✅ |

### 发现的问题

1. **/v6/abc 字段名 bug (已修复)** — 代码取 `antecedent`, 数据是 `premise`
   → 返回 5 个空串。修复: `_rule_summary` 用 name/premise。
   → 教训: "有查询逻辑" ≠ "字段对得上", 必须验真实输出。

2. **7 个空数据端点 (待深查)**:
   - /v6/pipeline → {}
   - /v6/extraction → {}
   - /v6/perspectives → {}
   - /v6/subgraph → {}
   - /v6/versions → {}
   - /v6/persistence/graphs → []
   - /v6/session/{filename} → empty (路径参数未替换)

3. **/v6/providers active 全空** — `{"name":"","display_name":"",...}` 
   → gateway 未配置 active provider (真实空, 非简化)

4. **/v6/chat + /v6/checkpoint/respond 慢** — 需 ~14s (加载 embedding 模型)
   → 首次加载开销, 非 bug

### 简化检测

- [x] /v6/abc: 曾有字段错位 (修复)
- [ ] /v6/pipeline, /v6/extraction, /v6/perspectives, /v6/subgraph: 返回 {} — 待查是否纯存根
- [ ] /v6/providers: active 全空 — 待查 gateway 初始化
- [ ] 14 个 POST 422 — 测试方法问题, 非端点问题 (已确认 schema)

---

## 简化/存根检测清单

遇到以下模式必须记录:

- [ ] 返回空列表/dict 但应有数据
- [ ] `except: pass` 吞错
- [ ] 硬编码值而非真实计算
- [ ] 未实现的函数体 (pass/NotImplementedError)
- [ ] 假数据 (mock 返回但没标注)
- [ ] 重复实现 (两处代码做同一件事)

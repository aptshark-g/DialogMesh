# 召回计算核心 Rust 重构设计（2026-08-10）

> 依据: LANG_STRATEGY_20260804（三明治结构: Python 认知 + Go 网关 + Rust 数据层）
> 先例: persistence_rs（Python persistence 的 Rust 直译, pyo3 嵌入）
> 痛点: 全库扫描单 query 215s（10969 块 Python 循环余弦）; 粗筛后 1.1s
> 用户拍板: 精细化评测完成后, Rust 重构提速度

---

## 一、persistence_rs 经验复盘（重构必读）

### 教训 1: FFI 边界按"批量操作"设计（最大坑）
- commit 6c2addc: put_turns_batch 单事务 1 次 FFI 调用
  → 4.2ms → 1.1ms（**4x 提速**）
- 逐条跨 FFI 边界是灾难: 每次调用有 Python↔Rust 转换开销
- 设计原则: **能一次传 Vec 就不要循环调**

### 教训 2: 无状态纯函数优先
- lsm_store/unified 用 Mutex<Connection> 持有状态 → 锁竞争
- 召回计算核心（余弦/BM25/粗筛）是无状态的 → 直接纯函数,
  天然可并行（rayon）, 无锁

### 教训 3: 接口不变, 实现替换（rust_bridge 模式）
- core/agent/persistence/rust_bridge.py: _check_rust() → Rust 优先 + Python 回退
- 召回同构: recall_rust_bridge 检测 .pyd, 有则 Rust 计算, 无则 Python

### 教训 4: 行为等价验收
- 同一测试集跑 py/rs 双实现, 结果一致 + 性能收益实测（不空谈）

---

## 二、重构范围（只迁计算核心, 不迁业务）

```
Rust 计算核心（新）                      Python 保留（不迁）
─────────────────────────              ─────────────────────────
✓ 余弦相似度矩阵（10969 块点积）          ✗ 融合权重/时序/溯源置信度
✓ BM25 打分（jieba 词项 → 稀疏向量）      ✗ SPO 提炼（规则, 低频）
✓ 粗筛候选集（词法交集 + 向量 top-C）     ✗ 扩散（图遍历, 图在 Python）
✓ 排序/截断                              ✗ RecallService 接口/调度
                                       ✗ HyDE/LLM 选择（云端）
```

理由: 计算核心稳定（数学不变）, 业务逻辑在演进（融合权重/温度/置信度
可学习）——迁业务会锁死迭代。LANG_STRATEGY 层3 明确: 性能热点 pyo3
渐进替换。

---

## 三、接口设计（pyo3）

```python
# recall_rust_bridge.py（Python 侧）
from dialogmesh_recall import (
    cosine_topk,        # (vecs: list[list[f64]], query: Vec<f64>, k) -> Vec<(idx, score)>
    bm25_score_matrix,  # (queries_terms, docs_terms, k1, b) -> Vec<Vec<f64>>
    coarse_candidates,  # (query_terms, doc_terms) -> Vec<usize>
)

def get_recall_kernel() -> Optional[Any]:
    """Rust 优先, 未编译回退 Python（rust_bridge 同款）。"""
```

### 关键设计: 批量边界
- cosine_topk: 一次传全部块向量（内存中已是 numpy 数组 → 零拷贝 via
  numpy→Rust 指针, 或 pyo3 的 vec 转换）
- bm25_score_matrix: query 词项 × 全部文档词项, 一次算完
- 粗筛: 词项交集一次算

### 向量来源
- 块向量已在内存（prepare_vectors 缓存 + recall_service._embeddings）
- 方案: numpy 2D array → pyo3 读取（numpy 的 .data 指针, 零拷贝）
  需要 numpy crate 或手动 PyArray 转换（先 vec 转换, 后优化零拷贝）

---

## 四、性能目标（验收门槛）

| 操作 | 现状（Python） | 目标（Rust） |
|---|---|---|
| 全库余弦 10969 块 | 215s/query | < 500ms（rayon 并行 + SIMD）|
| BM25 全库打分 | ~4s/query | < 100ms |
| 粗筛候选 200 | ~0.5s/query | < 50ms |
| 融合排序 | Python 保留 | 不变 |

- 用 SIMD（f32x8 点积）+ rayon 并行分块
- 验收: doc_recall_bench 同配置, py vs rs 数字一致 + 时间对比

---

## 五、施工步骤

1. **精细化评测**（前置, 量化 LLM 选择增益）— 进行中
2. 新建 persistence_rs 同构 crate: `recall_rs/`
   - Cargo.toml: pyo3 + rayon + numpy(可选)
   - src/cosine.rs（SIMD 点积 + 并行）
   - src/bm25.rs（稀疏词项打分）
   - src/coarse.rs（词项交集粗筛）
   - src/lib.rs（pyo3 导出）
3. Python 侧 recall_rust_bridge.py（Rust 优先 + 回退）
4. RecallService 接入: _vector_anchors/_bm25_anchors/粗筛 → Rust 内核
5. 行为等价测试（py/rs 双跑）+ 性能对比
6. 若收益达标, 再考虑: 扩散/SPO 提炼逐步迁

---

## 六、风险与边界

- 中文分词: BM25 词项依赖 jieba（Python）→ 词项在 Python 侧预计算,
  Rust 只做稀疏打分（词项 → id 映射传入）
- 向量内存: 10969 × 1024 × 8B ≈ 90MB → 单次拷贝可接受
- numpy 零拷贝依赖 numpy crate 版本兼容; 先用 Vec 转换保行为等价,
  再优化零拷贝
- 不迁: SPO 提炼（规则, 低频, 业务耦合）、扩散（图遍历）、
  融合权重（可学习, 在 Python 演进）

---

## 七、关联

- LANG_STRATEGY_20260804（三明治结构 + persistence_rs 模式）
- persistence_rs/（先例: FFI 批量边界教训）
- RECALL_EVAL_STANDARDS_20260810（评测口径）
- AGENT_EVAL_SUMMARY_20260810（量化基线）

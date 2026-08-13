# recall_rs Rust 内核优化经验记录（2026-08-11）

> 目的: 记录已实测的优化方向与数据, 避免下次重复摸索。
> 关联: RECALL_RUST_DESIGN（原始设计）/ persistence_rs（先例, 未真正导入成功）

---

## 一、已实测数据（2026-08-11, RTX3080 机器, .venv Python 3.13）

### 378 块 × 1024 维（goldset 小池）
| 路径 | 耗时 | 说明 |
|---|---|---|
| numpy 矩阵乘（BLAS） | **1.9 ms** | Python 生产最优路径 |
| Python 逐块循环 | 1.9 ms | 与矩阵乘相当（块少） |
| ~~Rust 全流程（pyo3+rayon）~~ | 10.3 ms | 初版: 转换+并行开销主导（已优化） |
| **Rust PyBuffer 零拷贝** | **2.03 ms** | ✅ 优化后: 与 numpy 持平（5 倍提升） |
| numpy→list 转换（纯转换） | 13.6 ms | **最大浪费点** |

### 10969 块 × 1024 维（全库扫描）
| 路径 | 耗时 | 说明 |
|---|---|---|
| numpy 矩阵乘 | 438 ms | BLAS 线程化 |
| Rust（f64 标量+rayon） | 262 ms | **1.7x 提速** |

### f64 vs f32（numpy 内测）
- f32 点积比 f64 快 **47%**（带宽减半）

---

## 二、结论（规模感知路由）

```
块数 < 2000  → numpy 矩阵乘（1.9ms, 零转换, Python 原生最快）
块数 ≥ 2000 → Rust（262ms vs 438ms, 1.7x）
```

- **小池用 Rust 是负优化**（rayon 并行调度 + pyo3 转换 > 计算本身）
- Rust 收益只在**万级全库扫描**显现
- 生产冷路径若接入文档语料（数千块）→ Rust 才有意义

---

## 三、待优化方向（未做, 按收益排序）

### 1. numpy 零拷贝（最大收益: 省 13.6ms/378 块 转换）
```rust
// pyo3 用 Buffer 直接读 numpy 指针, 不经过 tolist()
// 需要: numpy crate 或手动 PyBuffer / memoryview
#[pyfunction]
fn cosine_topk_buffer<'py>(py: Python<'py>, vecs: Bound<'py, PyAny>, ...) {
    let buf = vecs.extract::<PyBuffer<f64>>()?;  // 零拷贝
    // 直接 buf.as_slice() 计算
}
```

### 2. 规模感知并行（次大收益）
```rust
fn cosine_topk(vecs, dim, query, k, n_blocks) {
    if n_blocks < 2000 {
        sequential_dot(vecs, dim, query)  // 顺序, 省 rayon 调度
    } else {
        rayon_parallel_dot(vecs, dim, query)
    }
}
```

### 3. f32 计算（带宽减半, 47%）
```rust
// Python 侧传 float32（编码层已可产出 f32）; Rust 侧 f32 点积 + SIMD
```

### 4. SIMD 显式点积（在 f32 基础上再压）
```rust
// AVX2 f32x8: 一次 8 维; 或依赖 auto-vectorization + #[target_feature]
```

### ✅ 已做（2026-08-11 追加）

1. **PyBuffer 零拷贝**（`cosine_topk_buffer`）: numpy 数组直接提取,
   一次 memcpy; 378 块 10.3ms → **2.03ms**（与 numpy 持平）
2. **规模感知并行**: `n < 2000` 顺序执行（省 rayon 调度）, 否则 rayon
3. **生产接入**: recall_service `_vector_anchors` 优先走 buffer 版,
   自动回退 bytes/list/Python（四级回退链）

### 实测结论（生产路径）
- `_vector_anchors` 生产: Rust 24.4ms vs Python 17.5ms —— **Rust 只优化了
  计算核心, Python 侧 batch 构造/embed 检查循环仍是外围开销**
  （378 块场景 Python 原生就快; Rust 价值在万级块）
- 纯 cosine 计算已持平（2ms 级）; 生产外围优化是独立工作

---

## 四、环境坑（本机实测）

1. **pyo3 0.21 不支持 Python 3.13** — 编译的 .pyd 导入失败
   （anaconda 3.9 也失败 → 0.21 与本地 Python 兼容问题）
   **解法: pyo3 0.22 + abi3-py39 feature**（跨 3.9~3.13 同一 .pyd）
2. **persistence_rs 的 .pyd 从未成功导入** — LANG_STRATEGY 只写"已编译",
   无"导入成功/性能实测"记录 → rust_bridge 一直回退 Python
3. **cargo 联网下载依赖** — 沙箱内 crates.io 被挡; 需提权 cargo fetch
   （或走 python urllib 手动下 .crate 进缓存）
4. **cdylib → .pyd** — cargo build 产出 .dll, 需复制/重命名 .pyd 才能导入
5. **abi3 模式** — `crate-type = ["cdylib"]` + `abi3-py39` 跨版本,
   persistence_rs 用 pyo3 0.21 无 abi3 → 绑定单一版本
6. **abi3-py39 + PyBuffer 冲突** — pyo3 buffer 模块在
   `abi3 + Python<3.11` 被 `#![cfg(any(not(Py_LIMITED_API), Py_3_11))]`
   禁用 → 用 buffer 必须 `abi3-py311`（覆盖 3.11-3.13, 放弃 3.9）
7. **PYO3_PYTHON 必须显式指向目标解释器** — 否则 cargo 用 PATH 里的
   anaconda 3.9 编译, abi3-py311 报 "interpreter version 3.9 < 3.11"

---

## 五、验收门槛（RECALL_RUST_DESIGN §四, 复述）

- 行为等价: 同测试集 py/rs 双实现 top-k 一致（✅ 已验证 10969 块一致）
- 性能收益实测: 大池 1.7x ✅ / 小池负优化（需规模路由后重测）
- 不空谈: 每次优化后跑 recall_prod_bench 对比

> 下一步: ① 零拷贝 ② 规模路由 ③ f32 — 做完后 recall_prod_bench 应
> 小池 ~2ms / 大池 <150ms（当前 262ms 的 f32 版）

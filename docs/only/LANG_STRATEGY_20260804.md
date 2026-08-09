# 语言战略 — Python 原型 → Rust 重写（参考实现）（2026-08-04）

> 定位: 架构级拍板（用户 2026-08-04）。回答"网关 Go 化 / Rust 重构 / k8s"三问。
> 结论先行: **三明治结构（Python 认知 + Go 网关 + Rust 数据层）+ 
> Python 先写 → 验证 → Rust 重写（参考 Python 实现）**。
> 先例: persistence_rs 就是 Python persistence 的 Rust 重写（6 文件已编译）。

---

## 一、三明治结构（语言按层选型，不是一刀切）

```
层1 基础设施/IO 密集（Go + Rust）:
  switch 网关（Go）— ✅ 已成立（并发/网络/流式强项）
  persistence_rs（Rust）— 持久化/向量/索引（event_log/lsm/unified）
  → Go 管"面向连接"（网关代理），Rust 管"面向数据"（存储内核）

层2 认知/编排（Python）:
  DialogMesh 主体 — 认知链/意图/画像/子图/蓝图
  → 业务逻辑密度高 + LLM 生态在 Python → 迭代快

层3 性能热点（Rust 嵌入式 pyo3，渐进替换）:
  候选: 向量编码（BGE）、jieba 分词、图遍历（子图扩散）、
        A24 可逆推校验、事件流压缩（G2 冷摘要）
  → Python 保持接口，Rust 换实现（先 py 后 rs）
```

---

## 二、工作流：Python 原型 → 验证 → Rust 重写

```
① Python 先写（快 + 内含 Python 生态优化）:
   - 业务语义验证（正确性、边界、接口设计）
   - 与认知层直接集成（同进程，无 FFI 摩擦）
   - 压测暴露性能热点（哪里真的慢）

② 验证通过 → 标记"可 Rust 化"（performance_critical: true）

③ Rust 重写（参考 Python 实现）:
   - persistence_rs 模式: 照着 Python 版写 Rust 版
     （sqlite_store.rs / lsm_store.rs / event_log.rs / federated_index.rs
       = Python sqlite_store / lsm_store / api_event_log / 对应物的直译）
   - pyo3 嵌入，Python 接口不变，实现替换
   - 验收: 行为等价（同一测试集跑 py/rs 双实现）+ 性能收益实测

统一性来源 = 接口层（LLMProvider / OpenAI 协议 / 存储接口），不是语言
```

---

## 三、k8s（现在不看，G5 触发）

```
switch 已有完整 k8s 部署（deploy/k8s/deployment.yaml）:
  Secret 管理 key（DEEPSEEK_API_KEY 从 secretKeyRef 注入）
  ConfigMap 管 provider.yaml + 2 副本 RollingUpdate + 探针
→ 部署形态已就绪，单用户单进程不需要 → G5 分布式触发时启用
```

---

## 四、与既有拍板的关系

```
G10 存储分层:
  阶段1（现在）: Python 实现（UnifiedStore/TieredStorage 接线）— 先 py
  阶段2（规模）: Rust 重写（persistence_rs 演进，参考 Python 实现）
  → Kuzu 降级为备选（若 Rust 自写成本过高则用现成嵌入式向量图库）
B4-5 内核唯一: 传输层（CLI/REST/MCP）+ 语言层（py/go/rs）同构 —
  接口统一，实现可换
G5 分布式: k8s + 多副本 + 多租户 = 触发条件（非现在）
```

---

## 五、验收标准（语言战略落地）

```
① 新性能热点默认先写 Python（标注 performance_critical），不直接 Rust
② Rust 重写必须有对应 Python 参考实现（persistence_rs 模式）
③ 重写后行为等价（同一测试集）+ 性能收益实测（不空谈）
④ 接口层（Provider/存储/协议）语言无关，可替换
⑤ k8s 部署不提前启用（G5 触发），但 switch deployment.yaml 保持可用
```

---

> 关联: G10（存储分层）/ B4-5（内核唯一）/ G5（分布式触发）/ persistence_rs（先例）

# chromadb 环境修复 + 向量后端离线化 — 施工记录（2026-08-10）

> 依据: G10 存储选型（chromadb = 可选后端, UnifiedStore = 阶段 1 首选）
> 待办来源: STATE_HANDOFF_20260809 §七「chromadb 环境修复（独立完备性任务）」

---

## 一、环境修复

### 1. chromadb 1.5.9 装入 .venv
```
.venv\Scripts\python.exe -m pip install chromadb -i https://pypi.tuna.tsinghua.edu.cn/simple
成功安装: chromadb-1.5.9（含 grpcio/kubernetes/opentelemetry 等依赖）
```
- 用清华镜像（clash 当时未开, 镜像足够）
- 验证: PersistentClient 建库/显式 embeddings 检索/重启后 count 恢复 OK

### 2. .venv 补 pytest 9.1.1
- .venv 是 chromadb 唯一可用环境（anaconda numpy 坏 → chromadb import 失败）
- 装 pytest 后用 .venv 跑 chromadb 相关测试

---

## 二、代码修复（离线化 + 持久化 + 锁释放）

### 1. ChunkStore chromadb 后端（core/agent/storage/chunk_store.py）
- 根因: 原 _init_chromadb 用 chromadb.Client()（临时内存）+ 不传 embeddings
  → chromadb 默认 embedding function（ONNX MiniLM）会在首次 add 时联网下载模型
  （正是 G10 说"轻量替代 chromadb 79MB 模型"要避免的）
- 修复:
  - 改用 chromadb.PersistentClient(path=data/chroma_discourse)（持久化）
  - _embed(): 有 BGE 用 BGE；无 BGE 用本地 char-hash 64d（零下载兜底）
  - add/query 显式传 embeddings/query_embeddings → 永不触发默认模型下载
  - 冷重开修复: search 时若内存 atoms 为空（重启后），从 chromadb
    documents/metadatas 重建 Atom（此前直接返回空）
  - 新增 close() 释放 sqlite 文件锁（Windows）

### 2. ChromaBridge（core/agent/event/pluggable.py）
- 同样问题: add/search 用 documents/query_texts → 触发默认模型下载
- 修复: 本地 char-hash embedder 显式传 embeddings/query_embeddings
- close() 修正: 原 reset() 会清空整个库（危险）→ 改官方 client.close()
  （引用计数 + 条件停止系统, 释放 Windows 文件锁）
- 修 metadata 空 dict 报错（chromadb 1.5.x 要求非空 dict）→ {"added": True} 兜底

### 3. ChromaStore（core/agent/learning/chroma_store.py）
- 预存在 bug: available 属性不触发 _init → 装了 chromadb 也永远不可用
  （lazy init 从不执行）。修复: available 检查前先 _init()
- query 无 embedding 时用本地 768d embedder（与 ingestion 768d 对齐）
- 新增 close() 释放文件锁

### 4. UnifiedStore 持久化接线（G10-P1 补全）
- ChunkStore unified 后端: 新增 unified_persist=True 参数
  - init 时 load("data/recall_index/unified_text_index.npz")（跨重启恢复）
  - add 后节流落盘（每 25 条, _unified_save_every 可调）; close() flush 残留
- 引擎接线: registry.py + subsystem_registrations.py 的 chunk_store 工厂
  → DM_CHUNK_BACKEND=unified 时自动 unified_persist=True

---

## 三、测试

### 新增 test_chunk_store_chromadb.py（6 项, .venv 跑）
- chromadb 后端无 BGE 本地 embedding 离线可用
- metadata 往返
- PersistentClient 冷重开重建 Atom（跨重启召回）
- Atom 显式 embedding 路径
- ChromaBridge 离线 add/search
- ChromaStore lazy-init available 修复 + 重开持久化

### 新增 test_chunk_store_unified.py::test_unified_backend_persist_restore
- unified_persist=True: 落盘 → 冷重开 → search_texts 恢复

### 回归
- .venv: storage+event+learning+recall+tools = 119 passed / 3 failed
  （3 failed 是 test_recall_service 环境差异: .venv 有 BGE/torch → 召回更宽,
  预存在, 与本批改动无关——recall 文件未被触碰）
- anaconda（生产测试环境）: 同范围 = 116 passed / 1 skipped
  （1 skipped = chromadb 不可用环境, 新测试文件 importorskip 保护）
- chromadb 单测 10/10 + pluggable 4/4 + unified 5/5 全绿

---

## 四、遗留/边界
- data/chroma 与 data/chroma_learning 为 7/27、7/29 历史残留, 非本批创建, 未动
- anaconda numpy 坏（预存在, 独立环境问题）→ chromadb 测试只能在 .venv 跑
- recall_service 3 个测试在 .venv 下因 BGE 可用而行为不同（预存在, 已记录）

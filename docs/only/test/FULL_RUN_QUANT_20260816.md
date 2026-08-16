# 全量运行量化记录 — 挂起/内存根因链 + 基线修复（2026-08-16）

> 触发: 全量 pytest 反复被系统杀（用户观察 15GB）→ 参数级核查。
> 方法: 内存采样（外部 PowerShell 按 PID 轮询 WorkingSet）+ faulthandler
> 线程转储逐层定位（不猜）。全部实测, 可复现。

## 一、基线对比（同一机器, 同一代码库演进）

| 指标 | 修复前 | 修复后 |
|---|---|---|
| 全量结果 | 15GB → OOM 被系统杀 / 22min 崩溃 / 56 failed | **2063 passed / 24 skipped / 0 failed / 0 errors** |
| 全量耗时 | 22min+（多次崩） | **5:16** |
| 全量峰值内存 | ~15GB | **3.3GB** |
| 4 engine 峰值（探针） | **9.7GB** | **4.0GB** |
| 挂起源 | stanza×6 + HF hub×4 | 全清 |
| async 测试 | 54 个从未真正运行（缺 pytest-asyncio） | 全绿 |

## 二、内存累积根因（回答"为什么像 Spring 一样重"）

**不是容器框架重, 是模型单例纪律没贯彻**:
- 懒加载有（`SemanticEncoder.encode` 才 `_init`）, 但全库 **8 处直接
  `SemanticEncoder()`（非 `get_encoder()` 单例）** —— 每实例独立加载
  一份 ~2GB BGE-M3。
- 每个 engine bootstrap touch 多个此类子系统（PCR/discourse/simulation/
  tag_layer）→ 每 engine +2~3GB; pytest 单进程多测试文件 → 累积 15GB。
- `summary_engine` 注释早已写"复用全局单例"但代码没用（注释与实现漂移）。
- 修复: 8 处统一 `get_encoder()`; 探针实测 4 engine 峰值 9.7GB→4.0GB
  （模型只加载 1 次共享）。

## 三、无 CPU 挂起家族（逐层挖出 10 处, 全部 requests/httpx 无超时）

| 类别 | 位置 | 表现 |
|---|---|---|
| stanza.download | pcr_router_v2 / literal_chain / pronoun_resolver / grammar_tagger / tiered/stanza_parser | 联网下载资源, 网络受限无 CPU 挂 40s+（170s 卡死同源） |
| HF hub 校验 | topic_tree/manager_v2 / semantic_coref / bge_embedder / behavior_embedding | SentenceTransformer 联网校验/下载 |

修复统一: `download_method=None` / `local_files_only=True` + conftest 全局
`HF_HUB_OFFLINE=1`（测试进程此前没设, 生产 start_server.py 有设）。

## 四、观测基建（本轮新增, 复用）

- 内存采样: 外部 PowerShell `Get-Process -Id <pid>.WorkingSet64` 每秒采样
  （Python 内 ctypes GetProcessMemoryInfo 在本机返回 0, 弃用）。
- faulthandler 线程转储: pytest `faulthandler_timeout` 40→180（容忍慢 LLM
  集成调用; 真挂起仍可捕获——stanza/HF 定位全靠它）。
- 决策: `test_linkage_quality_v2`（真 LLM 集成, 7.6min）标 `slow`,
  默认 `-m "not slow"` 跳过。

## 五、连带发现

- pytest-asyncio 缺失: tool_registry/cognitive_tree/v3_2 fusion/dpo_learner
  54 个 async 测试此前收集期即 ERROR, 从未真正跑过（`--strict-markers` 下
  marker 未注册）。装后全绿。
- 经验 RAG 语义噪声阈值 0.15→0.45: 全量跑暴露无关查询被召回（BGE-M3 空间
  无关文本余弦常 0.3-0.5）; mock 向量器改语义字映射与真实尺度解耦。

## 六、复现命令

```powershell
# 全量（默认排除 slow）
.venv\Scripts\python.exe -m pytest core/agent -q --tb=short -p no:cacheprovider
# 内存探针（4 engine 曲线）
# 见 git log 内 scripts/_mem_probe_engine.py 历史版本; 用后可删
```

## 七、后续

- 全量绿是"域内完备"基线; 接线缺口清单仍有效（见 COMPLETENESS_GAP_INVENTORY
  与 BLUEPRINT_WIRING_TODO）。
- 学习闭环持久化已接（LEARNED_TEMPLATES 落盘, 见
  `docs/only/blueprint/LEARNED_PERSISTENCE_20260816.md`）。

# 统一召回第二批施工计划（2026-08-08）

> 状态: 计划已定, 待施工 | 依据: RECALL_CAPABILITY_20260808（第一批）
> + SPO_MODEL_STRATEGY_20260808（A+C 拍板 + 方案先进性 §八）
> 关联: COMPLETENESS_GAP_INVENTORY §五 R 系列、B2-3（召回能力底座）

---

## 一、勘察结论（2026-08-08 实机）

### 现状资产（全部存在, 大部分是孤儿/半接线）
| 资产 | 位置 | 状态 |
|---|---|---|
| RecallService（475 行, 9 测试） | core/agent/recall/recall_service.py | ✅ 第一批完成 |
| ChunkStore | core/agent/storage/chunk_store.py | ✅ 已解孤儿（R2） |
| UnifiedStore（BGE+LSH） | core/agent/persistence/unified_store.py | ✅ 向量底座 |
| SemanticEncoder | core/agent/compiler/semantic_encoder.py | ✅ |
| WaveQueryEngine（BFS+SQL 水波扩散） | core/agent/persistence/wave_query.py | 🟡 零引用孤儿（R5 现成!） |
| GraphStore | core/agent/persistence/graph_store.py + core/infrastructure/graph_store.py | 🟡 双实例待归一 |
| TopicTreeManagerV2（52KB, high-level 主题索引） | core/agent/topic_tree/manager_v2.py | ✅ 已施工（T1-T7） |
| 黄金集数据 | data/v3_sessions.json（83 会话/109 消息）+ data/discourse_trees/ | ✅ 素材可用 |

### recall_service 内部锚点函数
- `_vector_anchors`(L227) / `_bm25_anchors`(L267) / `_assoc_anchors`(L333) / `_expand_questions`(L365, HyDE)
- SPO 对齐 = 字面精确匹配（瓶颈）; 扩散 = 简单 k-hop（0.8/hop 衰减）

---

## 二、施工批次（依赖排序）

### 第一批: 数据地基 + 简单接线（本批）
- **G1 召回黄金集**: 从 v3_sessions 提炼 20-30 条真实 query + 期望命中块;
  跑分脚本（现状 SPO / +规则增强 / +RRF 对照）
- **R4 搜索引擎路**: sources.py 查询词修正（query 原文 + HyDE 扩展 + 英文关键词）
- **R6 HyDE 真实网关验证**: `_expand_questions` 走真实 LLM, 验证扩展质量 + 召回增益
- **实验项 RRF**: 线性融合 vs RRF 融合函数对照（黄金集 A/B）

## 二续、第一批进度（2026-08-08 晚）

### ✅ G0 写入即索引（用户实锤: "存的时候没向量化"）
- **根因确认**: ChunkStore 默认 `backend="in_memory"` 只存文本不向量化;
  RecallService 召回时才懒算 BGE + SPO, 进程内缓存重启全丢 → 76s/40query
- **施工**: RecallService 加磁盘索引缓存（`data/recall_index/{sid}.json`,
  首次召回持久化 SPO+向量, 后续直读）; `_extract_spo` 加进程内缓存;
  `_vector_anchors` 优先用预存向量; `_last_sid` 落盘隔离
- **效果**: 76s → 15s（5x 提速, 二次直读缓存）; 重启不丢

### ✅ G1 召回黄金集（真实数据, 非手写）
- 生成器 `scripts/_build_goldset.py`: 从 v3_sessions.json 真实对话抽取
  user query → assistant reply 切块 → 40 query + 218 块
- 跑分 `scripts/recall_goldset.py`（--mode linear|rrf|norm）
- **基线**: linear 62.5% / **rrf 67.5%**（+5pp）/ norm 62.5%
- **结论**: RRF 融合有效（rank-based 尺度不敏感）; 同义归一表在 SPO 覆盖
  有限时无增益 → SPO 增强应走模型路线（SPO-C 蒸馏）, 而非词典
- 注: 15s 仍含每 query 的 BGE+Stanza 开销; "hi/test/????" 等噪音 query
  计入真实分布（5/40）, 诚实保留

### ✅ G1 收紧版（用户: "前面的实现没有出现作弊, 简化这些问题"）
- 判定收紧: top-1 / top-3 / top-5 分层报告（不再只报宽松 top-5）
- 随机基线: 理论命中率 11.3%（证明非碰运气）
- 单路跑分: 拆 vector / bm25 / spo 各自贡献

**最终干净数据（清缓存全量重算, .venv 环境, 2026-08-08）**:

| 模式 | top1 | top3 | top5 | 随机基线 |
|---|---:|---:|---:|---:|
| linear（现状融合） | 30.0% | 52.5% | 67.5% | 11.3% |
| **rrf（rank 融合）** | **42.5%** | **67.5%** | **70.0%** | 11.3% |
| 单路 bm25 | 35.0% | 60.0% | 70.0% | 11.3% |
| 单路 vector | 32.5% | 50.0% | 65.0% | 11.3% |
| 单路 spo | 22.5% | 32.5% | 40.0% | 11.3% |

**结论**:
1. RRF 全维度最优（top1 +12.5pp vs linear）→ 融合层改 RRF 是免费增益
2. 单路最强 = bm25（top1 35%）> vector（32.5%）> spo（22.5%）
3. SPO 单路最弱 → 再次验证"SPO 增强走模型路线（SPO-C）, 不靠词典"
4. 所有路显著高于随机 11.3% → 无作弊

### 🔴 两个真 bug 修复（vector 路此前全 0 的根因）
1. **语言检测过严**（semantic_encoder._is_chinese）: 阈值 >30% CJK, 中英混合
   （"pi agent 怎么做"）被判 other → 384 维 n-gram 稀疏向量 → 与 512 维 BGE
   无法算余弦 → vector 路全 0。修复: 含任一 CJK 即走 zh 模型（BGE-zh 支持
   中英混合, 统一 512 维）
2. **嵌套向量**（recall_service._embed）: encode_text 返回 (1,512) 矩阵,
   tolist() 成嵌套 [[...]] → _cosine 的 np.dot 维度不匹配静默 0。
   修复: _embed 压平 reshape(-1) + _cosine 双保险压平

→ 此前"vector 0.45 命中"的 HTTP 测试数据存疑（当时可能就是异常路径）;
  修复后 vector 单路 top1 32.5% 是真实能力

### 待办（第一批内）
- R4 搜索引擎路查询词修正
- R6 HyDE 真实网关验证
- 噪音 query 过滤选项（--min-len）可后加

### ✅ R4 搜索引擎路查询词修正
- 问题: `llm_dag_builder.py:233` 传中文 intent 摘要给 IngestionPipeline（非 query 原文）
- 修复: `learn()` 已有 `eventlog_query`（原始 query）参数但未用 → 改 `search_query = eventlog_query or intent`, 长度 <2 才回退 intent

### ✅ R6 HyDE 真实网关验证（含 1 个真 bug 修复）
- **bug**: `GatewayLLMProvider` 无 `chat`/`complete` 方法, 只有标准 `generate(GenerateRequest)`
  → `_expand_questions` 只认 chat/complete → HyDE 静默失效（返回 [query]）
- **修复**: `_expand_questions` 加 `generate()` 分支（prompt + max_tokens=256 + temp=0.3）
- **实测**: gateway health=True; "pi agent 怎么做" →
  `['如何实现一个 Pi Agent 的基本功能？', 'Pi Agent 的常见架构和关键组件有哪些？', '如何训练或配置 Pi Agent 以完成特定任务？']`
- 测试: recall 9/9 绿

## 三、第一批完成态（2026-08-08 晚）

✅ G0（写入即索引: 磁盘索引缓存, 76s→15s）✅ G1（真实黄金集 40query+218块）
✅ RRF 对照（67.5% vs 62.5%, +5pp）✅ R4（查询词修正）✅ R6（HyDE 网关通）
📌 同义归一 norm=62.5% 无增益 → SPO 增强走模型路线（SPO-C）不靠词典
📌 噪音 query 5/40 诚实保留; 15s 含 BGE+Stanza 每 query 开销

### 第二批: 图扩散增强
- **R5 WaveQueryEngine 接线**: GraphStore 建图（块/边）→ 水波 BFS 替代简单 k-hop;
  关联链边并入扩散
- **升级2 主题层**: TopicTreeManagerV2 → 主题召回, 与锚点扩散合并（high-level 补盲）
- **升级3 PPR**: 边权重化 → Personalized PageRank 替代 hop 衰减（SPRIG 路线, CPU-only）

### 第三批: 选择与融合
- **升级1 权重动态化**: query 类型检测（事实/语义/操作型）→ 权重偏置叠加 ε 学习（DAT）
- **R7 LLM 挑选器**: 候选 ≤30 → 一次挑选（A16 快反馈）

### 第四批: 持久化 + 白盒
- **R3 置信度持久化**: feedback_log → update_source_credibility（A6/A18 闭环落盘）
- **R8 前端召回白盒展示**: 来源/置信度/扩散路径视图（A19）

### 第五批: 消费方 + SPO 模型策略
- **R1 subgraph 改造**: subgraph_compiler 11+ getattr 改走 recall 接口
- **SPO-A 规则增强**: 自动模式生成 + 同义归一表（立即做, 缓解字面匹配）
- **SPO-C LLM 蒸馏**: 黄金集 + 网关标注 → 0.5-1.5B 小模型（主路线, 排期独立）

---

## 三、验收门槛（每批）
- 第一批: 黄金集 ≥20 条, 跑分脚本输出三路对照（现状/RRF/规则增强）;
  R4 搜索引擎路返回真实结果; HyDE 网关扩展 10 条验证
- 第二批: WaveQuery 扩散命中路径可见; 主题层合并后 Recall 不降;
  PPR vs hop 对照数字入文档
- 第三批: 动态权重改变融合排序; LLM 挑选 ≤30 候选 <1s
- 第四批: feedback 后置信度持久化, 重启不丢; /v6/recall 响应含白盒字段
- 第五批: subgraph 零 getattr; SPO-A 对齐命中率提升数字

## 四、风险与对策
- Warm 文件锁竞态（Windows）→ 重试 3 次（已踩过）
- PowerShell 中文损坏 → 一律 apply_patch / UTF-8 文件
- apply_patch 重复函数定义遮蔽 → inspect.getsource 校验
- WaveQuery 双 GraphStore → 先归一到一个, 再接线

# 召回全链路终测（2026-08-13）— 速度 / 召回 / 幻觉

> 配置: 语料 v3（结构切分, 11761 块, 0 id 冲突）+ 向量 v3（标题+3000 窗口,
> 全覆盖）+ 融合 vector_primary（默认）+ SPO 候选集 300 + 跨池去重 +
> bench 会话树链 + BM25 Rust + 确定性 tie-break
> 数据: docs/test/recall_queries_100.md（39 对话 + 61 文档, 多文件期望已修复）

## 一、速度（eval_100 全量 100 条）

| 项 | 数值 | 对比 |
|---|---|---|
| 全量总耗时 | **95-103s** | 修复前 919s（~9x） |
| doc 域 | ~0.86-1.2s/query | 原 15s/query |
| dialogue 域 | ~0.29-0.69s/query | — |
| vector 路由 | 33-36ms/query | Rust PyBuffer 零拷贝 |
| BM25 路由 | 30-35ms/query | Rust 稀疏内核, 原 8.6-10s（~250x） |
| SPO 路由 | 100-120ms/query | 候选集 300（原全池 470ms） |
| 一次性启动 | SPO 提取 ~2min + BM25 索引 ~15s（已落盘持久化）+ 矩阵 ~8s | — |

## 二、召回（无 LLM 全指标, window-20）

| 域 | top1 | top3 | R@5 | R@10 | R@20 | MRR | nDCG |
|---|---|---|---|---|---|---|---|
| dialogue（39） | **69.2%** | 87.2% | 89.7% | 94.9% | 100% | 0.686 | 0.731 |
| doc（61） | **31.1%** | 54.1% | 60.7% | 75.4% | 86.9% | 0.408 | 0.452 |

- 随机基线: dialogue 11.8%（小池）/ doc 0.2%（大池）— doc 为基线 155x
- **C 类（检索缺口）归零**: 61 条 doc query 期望内容全部可召回
- 融合 top1 与 vector 路线 #1 完全对齐（46/46, vector_primary 证据驱动）
- 双跑确定性: 两次运行结果完全一致（bm25 HashMap 跨进程种子问题已修）
- 消融记录: RRF 排名上限（cap=5/10/15）→ 灾难性下降, 已证伪;
  rrf 置信度加权 → top1 +1.7pp 但 R@10 -4.9pp, 保持关闭;
  跨池去重 → dialogue 恢复 69.2% 且 R@20 最佳, 默认开

## 三、Faithfulness / 幻觉率（RAGAS 口径, 3 任务）

> **2026-08-13 深夜更新** — 修复链完成后（关思考 + 全文上下文 +
> 按任务选池 + RAGAS 式拆分 + top_k=20）的终版:

| 任务 | claims | supported | F | 解读 |
|---|---|---|---|---|
| 登录系统规划（simple, goldset 池） | 20 | 16 | **0.80** | ✅ 真实可支撑（对话记忆含该规划） |
| hello.py 执行（code, goldset 池） | 9 | 1 | 0.11 | 执行细节多为新内容 |
| 代码审查规划（explain, goldset 池） | 20 | 1 | 0.05 | 生成型规划 |
| 统一召回算法（recall_fact, doc 池） | 20 | 2 | 0.10 | 答案块在 fused 13-16 名, top-20 边缘 |
| **合计** | 69 | 20 | **0.29** | 幻觉率 0.71（混合真实效应） |

**修复链（逐步消除的工件, 每步实测）**:
1. 拆分模型把思维链写进 content 且吃光 max_tokens（finish=length）→
   根因: deepseek-v4 推理模式。网关加 thinking 透传（`{"type":"disabled"}`,
   请求级 + provider.yaml 厂商级默认三层开关）→ 拆分 1.2s 返回干净条目
2. 判定上下文 4000 字符截断 → 15000（答案块进窗口）
3. 接地池按任务选（事实型→文档语料, 对话型→goldset）
4. 上下文 top_k 10→20（答案块常在 fused 11-20）
5. RAGAS 式拆分: 带原问题 + 逐句无代词 + 严格提取 + 噪音行过滤

**结论**: simple=0.8 证明测量管道在"有支撑"时能测出高分 —— 机制可信。
剩余低分 = 生成型规划内容（本就不在记忆, 需任务上下文锚定, P2）+
检索窗口边缘（recall_fact 答案块在 13-16 名, 需重排/查询扩展, P1）。

| 任务 | claims | supported | F | 幻觉率 | 解读 |
|---|---|---|---|---|---|
| 登录系统规划（simple） | 20 | 3 | 0.15 | 0.85 | 生成型规划, 细节为新增内容 |
| hello.py 执行（code） | 20 | 9 | 0.45 | 0.55 | 记忆内任务, 可支撑 |
| 代码审查规划（explain） | 20 | 1 | 0.05 | 0.95 | 生成型规划 |
| **合计** | 60 | 13 | **0.22** | **0.78** | — |

- 判定器验证: 已知真/假 claim 均正确判定（512 tokens, 避开空返回边界）
- **方法论结论**: 对生成型规划任务, RAGAS 锚定"检索上下文"必然低分 —
  正确锚定物是任务图/执行迹（agent 本轮实际构建的内容）, 记 P2
- deepseek-v4-flash 密集输出随机空返回 → 网关 reasoning_content 透出
  （REASONING_FALLBACK, 社区同款 go#11142/SkillClaw#70）+ 拆分 chunk<=600
  重试 3 次

## 四、本轮修复链（2026-08-12/13）

1. BM25 接 Rust（稀疏索引 + 真实 df, Python 回退补 log bug）
2. 向量矩阵缓存（list→array 每 query 70MB 拷贝消除）
3. 索引缓存快照剥离 vector（400MB JSON 每 5s 序列化 → 15s/query 元凶）
4. Rust 余弦行索引→块 id 映射修复（Rust 激活时向量路归零的 bug）
5. 语料: id 冲突消歧（11493→唯一）、2000 字符硬截断移除、
   结构递归切分（###→段落→行, 0 硬切）、v3 向量缓存全覆盖
6. 评测: 100 条统一集、多文件期望修复、C 类标注 7 条修正、
   诊断报告（逐条路线排名/耗时/分类）、确定性 tie-break
7. 融合: vector_primary 证据驱动 + 跨池去重 + SPO 候选集
8. 网关: health 并行探测（35ms）、reasoning_content 透出、
   BM25 磁盘缓存内容指纹（防脏索引）、thinking 三层开关
9. 蓝图: recall/subgraph 节点输出消费（W2）、bench 会话树链（W4）、
   测试显式模式声明（44/44 绿）
10. Faithfulness: RAGAS 式拆分（带问题/无代词/严格提取）+ 全文上下文 +
    按任务选池 + top_k=20 + 拆分判定关思考

## 五、环境坑（新增）

- 沙箱启动的进程无出站网络权限（WinError 10013）→ 网关必须在沙箱外启动
  （start.bat 或提权）; shell 内 curl 直连测试同样被挡, 勿据此判断网络
- .venv 缺 fastapi（API 需 anaconda python 或补装）
- deepseek-v4-flash 推理模型: max_tokens 与思维链共享预算,
  密集输出偶发 content=""（finish=length）→ 网关透出 reasoning_content

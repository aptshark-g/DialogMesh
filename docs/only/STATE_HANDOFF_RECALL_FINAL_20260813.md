# 压缩交接 — 召回终测 + Faithfulness 机制修复（2026-08-13）

> 状态: 压缩恢复唯一入口（本轮）
> 前置: STATE_HANDOFF_RECALL_COMPLETE_20260812.md
> 恢复三步: 读本文档 → 读 RECOVERY_PLAN → 按待办优先级开工

## 一、终测结果（全量 100 条, 详见 docs/test/RECALL_EVAL_FINAL_20260813.md）

- 速度: 全量 95-103s（原 919s）; doc ~1s/query; BM25 Rust 250x;
  vector 33ms; SPO 候选集 100ms; 首启 SPO 提取 ~2min + BM25 索引
  （已落盘持久化）~15s
- 召回: dialogue top1 69.2% / R@10 94.9%; doc top1 31.1% / R@10 75.4% /
  R@20 86.9%; **C 类归零**; 双跑确定性
- 幻觉（RAGAS, 4 任务）: 总 F=0.29; simple（登录规划, goldset 池）
  **0.80** ✅ 机制验证; explain/code（生成型规划）低 = 新内容无记忆支撑
  （口径正确）; recall_fact 0.10 = 答案块在 fused 13-16 名（检索窗口,
  P1 重排的活）

## 二、本轮修复链（12 项, 全部实测）

1. BM25 Rust 接线 + Python 回退 log bug
2. 向量矩阵缓存 + Rust 余弦索引→id 映射修复（向量路归零 bug）
3. 索引缓存快照剥离 vector（15s/query → 1s/query 元凶）
4. 语料: id 冲突消歧 + 硬截断移除 + 结构递归切分 + v3 向量全覆盖
5. 评测: 多文件期望修复 + C 类标注 7 条 + 诊断报告 + 确定性 tie-break
6. 融合 vector_primary（top1 21.3%→31.1%）+ 跨池去重 + SPO 候选集
7. 网关: health 并行（35ms）+ reasoning_content 透出 + BM25 磁盘缓存
   内容指纹 + **thinking 三层开关**（请求级 > provider.yaml 厂商默认 >
   默认思考开; deepseek-v4 用 {"type":"disabled"} 关思考）
8. 蓝图: recall/subgraph 节点输出消费（W2 模板驱动）+ bench 会话树链
   （W4）+ 测试显式模式（44/44 绿）
9. Faithfulness: RAGAS 式拆分（带原问题/逐句无代词/严格提取/噪音过滤）+
   全文上下文 + 按任务选池 + top_k=20 + 拆分判定关思考

## 三、待办（优先级）

- **P0**: 无（eval_100 全量 / Faithfulness / BM25 Rust / batch_vecs 全清）
- **P1**: 意图感知自适应融合（W1: per-intent profile + A18 按意图学习,
  评测按意图分组）; 重排层（doc top1 31%→40%+ 正路, 也解锁 recall_fact
  的 F）; HyDE 真实现（查询措辞脆弱性已实锤: 同一事实两种措辞
  rank 5 vs 10000）; task 类 query 走执行层轨（W5）; recall 本体图扩展（W3）
- **P2**: Faithfulness 生成型任务改锚定任务图/执行迹; 行为链深度偏好学习
  （W7）; 蓝图模板覆盖补全（W6）; 五维评测（相关性/流畅/连贯, LLM-judge
  rubric）; .venv 补 fastapi; LLM 章节摘要 / C-MTEB / BEIR / Rust f32+SIMD /
  博客 chapter4 / 前端 B

## 四、环境坑（必读）

1. **沙箱启动的进程无出站网络权限（10013）** — 网关必须在沙箱外启动
   （start.bat / 提权）; shell 内 curl 直连测试被挡, 勿据此判断网络
2. **deepseek-v4 推理模型**: 思维链写进 content 且与正文共享 max_tokens
   （finish=length 空返回）→ 提取/判定类调用必须带
   `thinking: {"type":"disabled"}`（网关已支持, 前端后续可选）
3. .venv 缺 fastapi（API 用 anaconda python）; anaconda numpy 坏
   （向量/评测用 .venv）
4. BM25 磁盘缓存带内容指纹（同 id 不同内容不再脏命中）
5. PowerShell 管道传中文必变 ? — 中文脚本写文件执行
6. gateway.exe 源码在 C:\Users\APTShark\PycharmProjects\switch;
   编译需提权 + 本地 GOCACHE + GOPROXY=off

## 五、git 状态

- 改动未提交（按惯例）; DialogMesh 侧: recall_service / recall_rust_bridge /
  doc_recall_bench / recall_goldset / eval_100 / claim_eval / v3_session_api /
  测试若干 / 评测文档; switch 侧（另一仓库）: interface.go / openai.go /
  models.go / api.go（health 并行 + reasoning 透出 + thinking 开关）

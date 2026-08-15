# 压缩交接 — 召回加固 + 空回复根治 + 设计过程基建（2026-08-15）

> 状态: 压缩恢复唯一入口（本轮）
> 前置: docs/only/STATE_HANDOFF_GATEWAY_FRONTEND_20260813.md
> 恢复三步: 读本文档 → 读 RECOVERY_PLAN → 读 AGENTS.md + 追踪矩阵
> 环境: 8000(.venv API) + 8080(网关, 修复版) 在跑; LM Studio 1234;
> llama.cpp b10428 在 tools/llama.cpp（--reasoning on --reasoning-budget）;
> clash 7877

## 一、召回体系终态（2026-08-14~15, 全部实测）

- **语料卫生修复（P0）**: 12056→8138 块（docs/only 双份装载 + docs/test
  832 处 query 原文自污染 + notTish 别家文档）→ doc top1 37.7%→**50.8%**
- **四个精排试点全输 fused**: LLM 单选 41% / CE(bge-reranker-v2-m3) 44.3% /
  推理 LLM 44.3% / RRF(fused+CE) 45.9% vs fused 50.8%; 唯一正收益 =
  **cap=4 受限覆盖模拟 55.7%**（LLM 只在融合排名 2-4 内覆盖）。结论:
  单信号精排赢不了融合基线, 精排价值在"受限修正"或"答案侧"
- **B 尾巴消融**: 文件层信号进重排权重（DM_FILE_RERANK）49.2% 净损,
  默认关; small 摘要消融排除质量假说 → **机制=颗粒度错配**
  （文件主题命中 ≠ 块级相关）
- **C 最小版**: pool_extras 候选池扩展 0/12 救回 — 文件摘要索引在难点
  查询召回侧也无力; C 社区层需换索引材料（实体/关系/高质量聚类）
- **加固（P9/A7 细节保留落地）**: RecallHit.full_text 全文回填 + llm_reply
  细节节点 top-3 全文注入（DM_CTX_DETAIL_TOP/CHARS 变体）+ grounding
  约束 + 工具结果 300→2000 → **claim 三分真幻觉率 0.175→0.000/0.045**,
  F 0.254→0.568; 五维忠实 4.25(↑0.5)
- **claim_eval 三分口径**: 支持/矛盾(真幻觉)/池外扩展分离 — 老口径
  0.56 幻觉率里 57% 是池外扩展（规划结构, 非幻觉）
- **质量筛选试点**: 推理 LLM 可答性判断（能/不能）判断对时很准
  （83%/95%）但 52% 解析失败, 需结构化输出+重试; 只适合低置信闸门

## 二、空回复根治（执行层, 三层修复链）

- **真因**: ①tool_loop.py NameError（args 未定义, 08-14 引入）;
  ②switch 流式 tool_call 聚合 bug（append 不合并 index → 24 碎片,
  arguments 空）; ③deepseek-v4-flash 密集输出随机空返回;
  ④**规划任务 dir_list 探索死循环**（23 次调用烧完轮数无回答）
- **修复**: ①NameError 修正; ②网关 mergeToolCalls 按 index 合并 +
  3 用例一致性测试（switch 117aceb）; ③三调用点空返回重试;
  ④**tool_loop doom-loop 止损**（连续同工具≥3 → 强制直接回答）+
  **A2 project_map 粗结构注入**（治本: 模型先看全景, 规划任务
  9.4s 直接回答零工具调用）
- **验证**: explain 5/5 成功（14-20s, 2-3KB）; agent_bench 6/6 100%
  （延迟 33.4s, ~8430 token/任务, 0.016 元/任务）; 69/69 测试绿

## 三、设计/过程基建（用户深度讨论产出）

- **AGENTS.md**: 施工约束层 — 按任务类型激活公理子集（4-5 条内 LLM
  可靠, 25 条全量必漂移）+ 铁律 5 条（P9 原文存在性/记录/安全/真实验证/
  双向等价）
- **PARADIGM_TRACEABILITY.md**: 承诺级双向追踪矩阵（25 公理 →
  落点/状态/验收样例）; **双向等价判据 = A24 可逆推性**
  （设计↔实现 coverage 60-80%; 100%=过拟合/契约化, 0%=空转/漂移）
- **CONTEXT_GRANULARITY_CONTRACT.md**: 颗粒度**变体注册表**（非硬约束）
  — 每个注入点档位 + 选择机制（消融→意图级默认→用户白盒）;
  唯一不可协商: 原文存在性
- **核心结论**: 设计自洽 ≠ 设计可执行; 缺的是翻译层（承诺级追踪）+
  参照物（参考实现标注）+ 验收物（承诺级一致性测试）; 开发流程本身
  需要 dogfood 自己的"蓝图+执行层+元认知"
- **网关问题剖析**: 调用侧打补丁 ≠ 网关侧机制; 缺 ①thinking 默认绑定
  模型能力 ②承诺级一致性测试（已补聚合测试）③模型行为变更感知

## 四、提交状态（均本地, 未推 GitHub）

- DialogMesh: `39fd491 → 5af2b86 → cc6504f → 6960ac0 → ae2bcce`
- switch: `57eff25 → e8d9532 → 117aceb`
- 数据/缓存: models/(bge-reranker 2.2GB), tools/llama.cpp, 向量缓存
  已 gitignore; gateway.exe 已取消跟踪

## 五、环境坑（新增, 必读）

1. **API 必须 .venv 起**（anaconda torch 首次加载 BGE 死锁, 卡 200s+）—
   start.bat 已改 .venv python
2. **网关必须提权/start.bat 起**（沙箱进程无出网 10013 → 503）
3. **HF 联网 HEAD 10013 噪音**（~6s/请求）→ start_server 已设
   HF_HUB_OFFLINE=1（模型已缓存）
4. **PowerShell `\t` 不是转义** → Go/Python 补丁必须用 Python 写
5. **switch 根目录 nul 保留名文件** → `cmd /c ren \\?\...\nul _x` + del
6. **沙箱 git 报 dubious ownership**（CodexSandboxOffline 用户）→ 提权操作
7. **沙箱审批对长命令断流** → 下载类让用户跑, 施工拆小步
8. **llama.cpp**: LM Studio 后端是引擎包装版不能独立用; 官方 b10428
   CUDA 版在 tools/llama.cpp; `--reasoning on` 必须显式否则预算不生效
9. **deepseek-v4-flash 随机空返回** → 调用点重试（已补）

## 六、待办（优先级）

- **P1**: ①claim_eval 完整复跑确认整体数字（explain 修复后）;
  ②蓝图节点约束映射（任务形态声明: 规划→只读/空工具, A12 落地剩余）;
  ③多次采样校准评测（P2 老账, 单次噪声已证实）
- **P2**: 网关 thinking 默认绑定模型能力; 模型变更感知; docs/only/
  frontend/ 未跟踪文件核查; eval 产物提交策略; recall_fact 细节利用率
  （DM_CTX_DETAIL_TOP=8 未验证）; 执行层量化报告落盘; 博客 chapter4

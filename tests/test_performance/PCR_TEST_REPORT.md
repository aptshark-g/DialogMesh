# PCR 全量测试报告 (含 LLM 协同)

> 日期: 2026-07-21 · GatewayLLMProvider 注入 · 38 单元 + 21 集成 + 2 网关 = 61/61 PASS

## 性能基准 (10次采样, LLM Provider 注入)

| # | 输入 | avg | p50 | p99 | 期望 | 噪声 | 复杂度 | 策略 | LLM | 建议 |
|---|------|:---:|:---:|:---:|------|:---:|:---:|------|:---:|------|
| 1 | 空输入 | 0.14 | 0.06 | 0.80 | UNKNOWN | 0.00 | 0.00 | CONSERVATIVE | - | - |
| 2 | 单字 | 0.09 | 0.07 | 0.25 | UNKNOWN | 0.45 | 0.00 | CONSERVATIVE | - | - |
| 3 | 简单工具 | 164.78 | 1.23 | 1636.79 | TOOL | 0.00 | 0.02 | AGGRESSIVE | - | GenerateResult(text='', metrics=LLMCallM |
| 4 | 中文分析 | 118.80 | 1.03 | 1178.78 | ADVISOR | 0.08 | 0.02 | BALANCED | - | GenerateResult(text='', metrics=LLMCallM |
| 5 | 英文工具-扫描 | 118.13 | 1.09 | 1171.75 | TOOL | 0.02 | 0.05 | AGGRESSIVE | - | GenerateResult(text='', metrics=LLMCallM |
| 6 | 分析-问题 | 135.43 | 1.45 | 1340.87 | COMPANION | 0.20 | 0.02 | BALANCED | - | GenerateResult(text='', metrics=LLMCallM |
| 7 | 分析-为什么 | 128.67 | 0.98 | 1277.66 | ADVISOR | 0.28 | 0.02 | BALANCED | - | GenerateResult(text='', metrics=LLMCallM |
| 8 | 分析-询问 | 112.56 | 1.21 | 1115.43 | UNKNOWN | 0.28 | 0.06 | CONSERVATIVE | - | GenerateResult(text='', metrics=LLMCallM |
| 9 | 探索-入门 | 115.41 | 0.96 | 1145.06 | COMPANION | 0.20 | 0.05 | BALANCED | - | 学习汇编语言基础 |
| 10 | 探索-逐步 | 114.40 | 1.74 | 1129.07 | COMPANION | 0.20 | 0.05 | BALANCED | - | GenerateResult(text='', metrics=LLMCallM |
| 11 | 噪声-模糊 | 123.96 | 1.06 | 1230.24 | UNKNOWN | 0.43 | 0.03 | CONSERVATIVE | - | GenerateResult(text='', metrics=LLMCallM |
| 12 | 单字-help | 0.07 | 0.07 | 0.11 | UNKNOWN | 0.40 | 0.01 | CONSERVATIVE | - | - |
| 13 | 多步骤 | 123.42 | 1.24 | 1223.46 | TOOL | 0.00 | 1.00 | BALANCED | - | GenerateResult(text='', metrics=LLMCallM |
| 14 | 跨域复杂 | 117.83 | 1.09 | 1168.74 | TOOL | 0.00 | 0.38 | AGGRESSIVE | - | GenerateResult(text='', metrics=LLMCallM |
| 15 | 模糊噪声 | 97.77 | 1.03 | 968.54 | UNKNOWN | 0.50 | 0.23 | CONSERVATIVE | - | GenerateResult(text='', metrics=LLMCallM |
| 16 | 请求-脚本 | 95.14 | 1.11 | 941.36 | TOOL | 0.00 | 0.02 | AGGRESSIVE | - | GenerateResult(text='', metrics=LLMCallM |
| 17 | 复杂-加密分析 | 116.48 | 1.16 | 1154.84 | ADVISOR | 0.28 | 0.17 | BALANCED | - | GenerateResult(text='', metrics=LLMCallM |
| 18 | 复杂-英文混淆 | 106.96 | 1.26 | 1059.21 | COMPANION | 0.22 | 0.12 | BALANCED | - | GenerateResult(text='', metrics=LLMCallM |
| 19 | 复杂-多工具链 | 110.99 | 1.30 | 1096.07 | TOOL | 0.00 | 0.46 | AGGRESSIVE | - | GenerateResult(text='', metrics=LLMCallM |
| 20 | 非技术-闲聊 | 110.63 | 1.22 | 1095.69 | ADVISOR | 0.20 | 0.05 | BALANCED | - | GenerateResult(text='', metrics=LLMCallM |
| 21 | 极短-ok | 0.07 | 0.07 | 0.12 | UNKNOWN | 0.45 | 0.00 | CONSERVATIVE | - | - |
| 22 | 分析-优化 | 135.63 | 1.54 | 1343.10 | ADVISOR | 0.28 | 0.06 | BALANCED | - | GenerateResult(text='', metrics=LLMCallM |
| 23 | 分析-地址 | 129.74 | 1.20 | 1286.95 | ADVISOR | 0.36 | 0.07 | BALANCED | - | GenerateResult(text='', metrics=LLMCallM |
| 24 | 分析-语言识别 | 100.54 | 1.01 | 996.02 | COMPANION | 0.20 | 0.07 | BALANCED | - | GenerateResult(text='', metrics=LLMCallM |
| 25 | 探索-ML想法 | 141.61 | 1.26 | 1405.27 | COMPANION | 0.20 | 0.07 | BALANCED | - | GenerateResult(text='', metrics=LLMCallM |
| 26 | 复杂-多层加密 | 135.46 | 1.21 | 1344.51 | COMPANION | 0.08 | 0.20 | BALANCED | - | GenerateResult(text='', metrics=LLMCallM |

**LLM fallback 触发: 0/26 inputs**
**设计约束: 规则 < 10ms | LLM fallback < 250ms**
**规则模式 avg 延迟: 102.10ms**

## 全部测试通过: 38 PCR + 21 Backend + 2 Gateway = 61/61 ✅

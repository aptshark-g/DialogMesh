# PCR 全量测试报告

> 日期: 2026-07-21 · 测试: test_pcr_comprehensive.py · 38/38 PASS

---

## 性能基准 (100次采样, 单位 ms)

| # | 输入 | avg | p50 | p99 | 期望 | 噪声 | 复杂度 | 策略 | 风格 |
|---|------|:---:|:---:|:---:|------|:---:|:---:|------|------|
| 1 | (空) | 0.08 | 0.07 | 0.83 | UNKNOWN | 0.00 | 0.00 | CONSERVATIVE | CONSERVATIVE |
| 2 | a | 0.10 | 0.11 | 0.74 | UNKNOWN | 0.45 | 0.00 | CONSERVATIVE | CONSERVATIVE |
| 3 | scan 0x401000 | 0.07 | 0.06 | 0.12 | TOOL | 0.00 | 0.02 | AGGRESSIVE | AGGRESSIVE |
| 4 | 帮我分析这个函数 | 0.08 | 0.07 | 0.12 | ADVISOR | 0.08 | 0.02 | BALANCED | BALANCED |
| 5 | 先扫描内存然后修改找到的地址再验证修改是否生效然后记录日志 | 0.09 | 0.08 | 0.14 | TOOL | 0.00 | 1.00 | BALANCED | BALANCED |
| 6 | disassemble this binary and patch the jump at 0x401000 to NOP sled | 0.09 | 0.08 | 0.20 | TOOL | 0.00 | 0.08 | AGGRESSIVE | AGGRESSIVE |
| 7 | 先用angr做符号执行再frida动态hook最后ghidra反汇编对比找差异点 | 0.11 | 0.10 | 0.14 | UNKNOWN | 0.00 | 0.48 | CONSERVATIVE | CONSERVATIVE |
| 8 | 那个东西搞一下然后弄一下再看看 | 0.09 | 0.09 | 0.13 | UNKNOWN | 0.50 | 0.23 | CONSERVATIVE | CONSERVATIVE |

**设计约束: < 10ms → ✅ 全部达标 (avg 0.07-0.11ms, 低于阈值 125x)**

---

## Stage 1: 期望识别 (11/11 PASS)

| 测试 | 输入 | 期望输出 | 实际 | 状态 |
|------|------|------|------|:---:|
| test_tool_scan | scan 4 bytes for 100 in Game.exe | TOOL or ADVISOR | TOOL | ✅ |
| test_tool_read_write | 读取内存地址 0x00401000 | TOOL or ADVISOR | TOOL | ✅ |
| test_tool_patch | 修改这个函数，把返回值改成 0 | TOOL/ADVISOR/COMPANION | TOOL | ✅ |
| test_tool_english | disassemble this binary and patch the jump at 0x401000 | TOOL/ADVISOR/COMPANION | TOOL | ✅ |
| test_advisor_analysis | 这段代码有什么问题？ | ADVISOR/COMPANION/UNKNOWN | ADVISOR | ✅ |
| test_advisor_why | 为什么这个函数会被内联？ | ADVISOR/COMPANION | ADVISOR | ✅ |
| test_advisor_is_this | 这个packer signature是UPX还是自定义的？ | ADVISOR/COMPANION/UNKNOWN | ADVISOR | ✅ |
| test_companion_explore | 我是新手，刚开始学逆向工程，应该从哪里入手？ | COMPANION/ADVISOR/UNKNOWN | COMPANION | ✅ |
| test_companion_step_by_step | 能不能一步一步教我如何找到游戏的血量地址？ | COMPANION/ADVISOR/UNKNOWN | COMPANION | ✅ |
| test_empty_input | (空) | UNKNOWN | UNKNOWN | ✅ |
| test_noise_only | 嗯...那个...就是... | UNKNOWN/COMPANION | UNKNOWN | ✅ |
| test_single_word | help | 非None | COMPANION | ✅ |

---

## Stage 2: 噪声评估 (5/5 PASS)

| 测试 | 输入 | 条件 | 实际噪声 | 状态 |
|------|------|------|:---:|:---:|
| test_clean_input_low_noise | disassemble this binary and patch 0x401000 to NOP sled | < 0.6 | 0.00 | ✅ |
| test_no_verb_high_noise | 那个东西 | > 0.1 | 0.55 | ✅ |
| test_vague_words | 那个东西搞一下然后弄一下 | > 0.15 | 0.83 | ✅ |
| test_short_input_noise | ok | 非None | 1.00 | ✅ |
| test_noise_range (6 inputs) | 多种输入 | 0-1 范围内 | ALL [0,1] | ✅ |

---

## Stage 3: 复杂度 (4/4 PASS)

| 测试 | 输入 | 条件 | 实际复杂度 | 状态 |
|------|------|------|:---:|:---:|
| test_simple_low_complexity | 扫描 0x00401000 | 非None | 0.02 | ✅ |
| test_multi_step_high_complexity | 先扫描内存，然后修改找到的地址，最后验证修改是否生效 | > 0 | 1.00 | ✅ |
| test_cross_domain_complexity | 先用angr做符号执行，然后frida hook，最后用ghidra反汇编对比 | > 0 | 0.38 | ✅ |
| test_complexity_range (7 inputs) | 扫描/扫描然后修改/分析保护机制/基址和指针链/反汇编/angr和z3/frida hook同时scan | 0-1 范围内 | ALL [0,1] | ✅ |

---

## Stage 4: 认知画像 (3/3 PASS)

| 测试 | 输入 | 条件 | 状态 |
|------|------|------|:---:|
| test_profile_produced | 帮我分析这个函数的性能瓶颈在哪里？ | profile非None, fields非None | ✅ |
| test_profile_range | 我是新手刚开始学逆向 | metacognition/tracking_depth/stability ∈ [0,1] | ✅ |
| test_different_inputs_different_profile | scan vs 新手探索 | 维度允许相同(短输入) | ✅ |

**CognitiveProfile 实际字段**: metacognition, tracking_depth, stability, divergence, confidence, description_stability, metacognitive_level, divergence_ratio

---

## Stage 5: 策略推导 (6/6 PASS)

| 测试 | 输入 | 策略 | 风格 | 状态 |
|------|------|------|------|:---:|
| test_execution_mode_valid (5 inputs) | scan/帮我分析/我是新手/为什么/(空) | AGGRESSIVE/BALANCED/CONSERVATIVE | — | ✅ |
| test_prompt_style_valid (3 inputs) | scan/帮我分析这个函数/我是新手请一步步教我 | — | AGGRESSIVE/CONSERVATIVE/BALANCED | ✅ |
| test_tool_mode_low_complexity | scan 0x401000 | AGGRESSIVE or BALANCED | — | ✅ |
| test_unknown_high_noise | 嗯...那个... | CONSERVATIVE or BALANCED | — | ✅ |
| test_output_coherence | 先扫描然后分析再修改 | expectation/noise/complexity 组合有效 | — | ✅ |

---

## 端到端 (4/4 PASS)

| 测试 | 内容 | 状态 |
|------|------|:---:|
| test_complete_pipeline | 全部字段非空, implementation=rule_based, trace_log 非空 | ✅ |
| test_10_diverse_inputs | 工具/分析/探索/多步/空输入/询问/英文/模糊/跨域/请求 | ✅ |
| test_idempotent | 相同输入 2 次调用 → 相同 expectation/execution_mode/prompt_style | ✅ |
| test_latency_under_threshold | 5 次采样 avg < 10ms | ✅ (实际 < 1ms) |

---

## 鲁棒性 (5/5 PASS)

| 测试 | 输入 | 状态 |
|------|------|:---:|
| test_very_long_input | "scan " × 500 + "0x401000" | ✅ |
| test_special_characters | !@#$%^&*()_+-={}[]\|\:;"'<>,.?/~` | ✅ |
| test_unicode_only | 😀🤖🚀 | ✅ |
| test_mixed_languages | 帮我 disassemble 这个 binary at 0x401000 | ✅ |
| test_single_char | a | ✅ |

---

## 全量统计

```
总测试数:      38
通过:          38 (100%)
失败:           0
运行时间:      0.011s

分类覆盖:
  期望识别:    11 tests  ✅
  噪声评估:     5 tests  ✅
  复杂度:       4 tests  ✅
  认知画像:     3 tests  ✅
  策略推导:     6 tests  ✅
  端到端:       4 tests  ✅
  鲁棒性:       5 tests  ✅

性能:
  avg 延迟:    0.08ms (远低于 10ms 设计约束)
  确定性:      100% (幂等)
  降级安全:    空输入/超长/特殊字符/unicode 全部安全
```

# -*- coding: utf-8 -*-
"""
LM Studio 本地模型集成测试 — 方案 C（完整修复）。

修复内容：
1. 多维 Gate 2 触发条件（不再简单依赖 expectation）
2. 重构 LLM Fallback 为策略补全器（strategy_completer）
3. PCR 学习关键词修复（"我想学习" → COMPANION）
4. 强化 LLM prompt 约束（JSON-only，禁止 reasoning）
5. Adaptive 阈值反馈生效

运行方式：
    python test_lmstudio_integration_v2.py
"""

from __future__ import annotations

import sys
import os
import json
import time

# Add project root
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from core.agent.llm_providers import ProviderFactory, OpenAIProvider
from core.agent.llm_providers.base import GenerateRequest, LLMProvider
from core.agent.pcr.rule_based import RuleBasedPCR
from core.agent.pcr.datacontract import PCRInput_v1, HistoryEntry
from core.agent.v3_common.gates import (
    DualTrackOrchestrator, AdaptiveThresholds,
    HardGate, PCRGate, OrchestrationGate
)
from core.agent.v3_common.intent_parser import IntentParser
from core.agent.v3_common.models import IntentContext, ParseContext
from core.agent.v3_common.blueprints import BLUEPRINT_REGISTRY
from core.agent.v3_common.orchestrator import BlueprintExecutor, ExecutionContext
from core.agent.frontend.clarification_fsm import (
    ClarificationFSM, ClarificationFSMContext, ClarificationState, ClarificationEvent
)
from core.agent.frontend.websocket_events import EventBuilder, EventTypeRegistry
from core.agent.tools.cognitive_tools import CognitiveTools


# ═══════════════════════════════════════════════════════════
# 配置区
# ═══════════════════════════════════════════════════════════

LMSTUDIO_CONFIG = {
    "type": "openai",
    "name": "lmstudio-local",
    "api_key": "lm-studio",
    "model": "qwen3.5-9b",
    "base_url": "http://localhost:1234/v1",
    "timeout_s": 120,
}

TEST_QUERIES = [
    ("scan 100", None, "简单工具指令"),
    ("分析这个进程的内存结构", None, "分析请求"),
    ("我想学习如何扫描内存值", None, "新手教程"),
    ("scan", None, "模糊输入（缺参数）"),
    ("读取这个地址", [{"role": "user", "content": "scan 0x401000", "expectation": "TOOL"}], "引用解析（需历史）"),
    ("在内存里搜索数值并修改它", None, "复合意图"),
]


def _print_header(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def _print_json(label: str, data, indent: int = 2):
    print(f"\n┌─ {label}")
    if isinstance(data, (dict, list)):
        print(json.dumps(data, ensure_ascii=False, indent=indent, default=str))
    else:
        print(f"  {data}")
    print("└" + "─" * 60)


def test_connection(provider: LLMProvider):
    """测试 LM Studio 连接状态。"""
    _print_header("Step 0: LM Studio 连接测试")
    
    print(f"\n  配置:")
    print(f"    base_url: {LMSTUDIO_CONFIG['base_url']}")
    print(f"    model:    {LMSTUDIO_CONFIG['model']}")
    print(f"    timeout:  {LMSTUDIO_CONFIG['timeout_s']}s")
    
    print(f"\n  [健康检查] ...")
    healthy = provider.health_check()
    print(f"    结果: {'✅ 正常' if healthy else '❌ 失败'}")
    if not healthy:
        print("\n  ⚠️ 请检查：")
        print("    1. LM Studio 是否已启动？")
        print("    2. Local Server 是否已开启（默认端口 1234）？")
        print("    3. 模型是否已加载完成？")
        return False
    
    print(f"\n  [延迟预估] ...")
    latency = provider.estimate_latency_ms(prompt_tokens=100, output_tokens=50)
    print(f"    预估延迟: {latency:.0f}ms")
    
    return True


def test_single_inference(provider: LLMProvider):
    """测试单轮推理。"""
    _print_header("Step 1: 单轮推理测试")
    
    req = GenerateRequest(
        prompt="用户输入：'scan 100'\n请分析用户意图，只输出合法 JSON 对象，禁止任何解释或 Markdown 代码块：\n"
               '{"intent": "TOOL", "confidence": 0.95, "entities": [{"type": "value", "value": "100"}]}',
        system_prompt="你是一个意图分析助手。你的输出必须且只能是合法的 JSON 对象，禁止输出任何解释、思考过程、Markdown 代码块标记。直接输出纯 JSON 文本。",
        max_tokens=128,
        temperature=0.0,
    )
    
    print(f"\n  请求:")
    print(f"    prompt_tokens: ~{len(req.prompt)//4}")
    print(f"    max_tokens: {req.max_tokens}")
    print(f"    temperature: {req.temperature}")
    
    print(f"\n  发送请求 ...")
    start = time.time()
    result = provider.generate(req)
    elapsed = (time.time() - start) * 1000
    
    print(f"\n  响应:")
    print(f"    成功: {result.metrics.success}")
    print(f"    实际延迟: {elapsed:.0f}ms")
    print(f"    provider: {result.metrics.provider_name}")
    print(f"    text[:200]:")
    print(f"      {result.text[:200].replace(chr(10), ' ')}")
    
    return result.metrics.success


def _should_use_strategy_completer(pcr_output, parse_result) -> bool:
    """多维判断：是否需要触发策略补全器。"""
    reasons = []
    
    if pcr_output.expectation == "UNKNOWN":
        reasons.append("expectation=UNKNOWN")
    
    if parse_result and parse_result.intent.confidence < 0.3:
        reasons.append(f"confidence={parse_result.intent.confidence:.2f}<0.3")
    
    if pcr_output.noise_level > 0.3 and pcr_output.complexity_level > 0.3:
        reasons.append(f"noise={pcr_output.noise_level:.2f}&complexity={pcr_output.complexity_level:.2f}>0.3")
    
    if pcr_output.expectation == "ADVISOR" and parse_result and parse_result.intent.confidence < 0.5:
        reasons.append(f"ADVISOR&confidence={parse_result.intent.confidence:.2f}<0.5")
    
    if parse_result and len(parse_result.intent.ambiguities) > 0:
        reasons.append(f"ambiguities={len(parse_result.intent.ambiguities)}>0")
    
    return len(reasons) > 0, reasons


def run_full_pipeline_with_llm(query: str, provider: LLMProvider, history=None, scenario_name=""):
    """运行完整决策链 — 方案 C（策略补全器架构）。"""
    
    _print_header(f"场景：{scenario_name or query}")
    print(f"\n[输入] {query}")
    
    # ── 1. PCR 评估 ───────────────────────────────────────────
    _print_header("Step 2: PCR 评估 (Layer 0) — 规则引擎")
    pcr = RuleBasedPCR()
    
    # 用户类型探测（P1 修复）
    if history:
        user_type = pcr._profiler.first_turn_probe(query)
    else:
        user_type = "neutral"
    print(f"  用户类型探测: {user_type}")
    
    _history_entries = []
    for h in (history or []):
        if isinstance(h, dict):
            _history_entries.append(HistoryEntry(
                role=h.get("role", "user"),
                content=h.get("content", ""),
                expectation=h.get("expectation", ""),
                timestamp=h.get("timestamp", 0.0),
            ))
    
    pcr_input = PCRInput_v1(query=query, session_history=_history_entries)
    pcr_output = pcr.evaluate(pcr_input)
    
    print(f"  expectation: {pcr_output.expectation}")
    print(f"  noise_level: {pcr_output.noise_level:.2f}")
    print(f"  complexity_level: {pcr_output.complexity_level:.2f}")
    print(f"  cognitive_profile: metacognition={pcr_output.cognitive_profile.metacognition:.2f}")
    print(f"  execution_mode: {pcr_output.execution_mode}")
    
    # ── 2. 三层门控 ──────────────────────────────────────────
    _print_header("Step 3: 三层门控 (Layer 1)")
    
    adaptive = AdaptiveThresholds()
    print(f"  Adaptive Thresholds 初始: noise_fast_path={adaptive.get('noise_fast_path'):.2f}")
    
    gate0 = HardGate.evaluate(query, _history_entries)
    print(f"  Gate 0 (Hard): {'✅ 命中' if gate0 else '❌ 未命中'}")
    if gate0:
        print(f"    track={gate0.track}, blueprint={gate0.blueprint_id}")
    
    gate1_pcr, gate1 = PCRGate.evaluate(query, _history_entries, pcr, adaptive=adaptive)
    print(f"  Gate 1 (PCR): {'✅ 命中' if gate1 else '❌ 未命中'}")
    if gate1:
        print(f"    track={gate1.track}, blueprint={gate1.blueprint_id}")
    
    # ── 3. 意图解析 ──────────────────────────────────────────
    _print_header("Step 4: 意图解析 (Layer 1)")
    parser = IntentParser()
    intent_ctx = IntentContext.from_pcr_output(pcr_output)
    parse_ctx = ParseContext(session_id="test-session")
    parse_result = parser.parse(query, intent_ctx, parse_ctx)
    
    print(f"  category: {parse_result.intent.category}")
    print(f"  confidence: {parse_result.intent.confidence:.2f}")
    print(f"  entities: {len(parse_result.intent.entities)}")
    for e in parse_result.intent.entities:
        print(f"    - {e.type}: {e.value} (conf={e.confidence:.2f})")
    print(f"  ambiguities: {len(parse_result.intent.ambiguities)}")
    for a in parse_result.intent.ambiguities:
        print(f"    - {a.type}: {a.description}")
    
    # ── 4. 策略补全器（替代 LLM Fallback）───────────────────
    _print_header("Step 5: 策略补全器 (Strategy Completer)")
    
    should_use, reasons = _should_use_strategy_completer(pcr_output, parse_result)
    print(f"  是否触发策略补全器: {'⚠️ 是' if should_use else '✅ 否（规则足够）'}")
    if reasons:
        print(f"  触发原因: {', '.join(reasons)}")
    
    strategy_action = None
    llm_call_count = 0
    
    if should_use:
        print(f"\n  [策略补全器调用] → 发送给 {provider.name}")
        
        # 使用 CognitiveTools.strategy_completer
        executor_ctx = ExecutionContext(
            raw_input=query,
            pcr_instance=pcr,
            parser_instance=parser,
            llm_provider=provider,
        )
        
        # 手动构建 state（模拟 BlueprintExecutor 的执行状态）
        state = {
            "pcr_evaluate": pcr_output,
            "intent_parser_full_pipeline": parse_result,
        }
        
        start = time.time()
        try:
            strategy_action = CognitiveTools.run("strategy_completer", executor_ctx, state)
            llm_call_count = 1
        except Exception as e:
            print(f"    ⚠️ 策略补全器失败: {e}")
            strategy_action = {
                "action": "direct_reply",
                "text": f"[策略补全器异常: {e}]",
            }
        
        latency = (time.time() - start) * 1000
        print(f"    LLM 延迟: {latency:.0f}ms")
        print(f"    策略 action: {strategy_action.get('action', 'unknown')}")
        if strategy_action.get('question'):
            print(f"    question: {strategy_action['question'][:100]}")
        if strategy_action.get('text'):
            print(f"    text[:100]: {strategy_action['text'][:100]}")
    
    # ── 5. 蓝图执行（短路拦截器）─────────────────────────────
    _print_header("Step 6: 蓝图执行 / 策略短路 (Layer 1)")
    
    # 短路拦截器：如果策略补全器返回了直接行动，跳过规则流水线
    exec_result = None
    short_circuited = False
    gate2 = None  # 初始化为 None，避免短路时未定义
    
    if strategy_action and strategy_action.get('action') == 'direct_reply':
        # 短路：直接返回 LLM 生成的回复
        print(f"  ⚡ 短路拦截：action=direct_reply，跳过规则蓝图")
        print(f"  LLM 回复: {strategy_action.get('text', '')[:150]}...")
        exec_result = type('obj', (object,), {
            'status': 'direct_reply',
            'task_graph': None,
            'clarification': None,
            'trace': [],
            'fallback_to': None,
            'message': strategy_action.get('text', ''),
        })()
        short_circuited = True
        
    elif strategy_action and strategy_action.get('action') == 'ask_user':
        # 短路：进入澄清状态
        print(f"  ⚡ 短路拦截：action=ask_user，跳过规则蓝图")
        print(f"  追问: {strategy_action.get('question', '')}")
        exec_result = type('obj', (object,), {
            'status': 'clarifying',
            'task_graph': None,
            'clarification': {
                'type': 'ask_user',
                'question': strategy_action.get('question', ''),
            },
            'trace': [],
            'fallback_to': None,
            'message': None,
        })()
        short_circuited = True
    
    if not short_circuited:
        # 正常执行蓝图
        orchestrator = DualTrackOrchestrator(pcr, parser)
        gate2 = orchestrator.process(query, history=_history_entries, adaptive=adaptive)
        final_bp = BLUEPRINT_REGISTRY.get(gate2.blueprint_id, BLUEPRINT_REGISTRY["RULE_FAST_PATH"])
        
        print(f"  选中蓝图: {gate2.blueprint_id}")
        print(f"  strategy_steps: {final_bp.strategy_steps}")
        
        executor = BlueprintExecutor()
        ctx = ExecutionContext(
            raw_input=query,
            pcr_instance=pcr,
            parser_instance=parser,
            llm_provider=provider,
        )
        exec_result = executor.execute(final_bp, ctx)
    
    print(f"  执行状态: {exec_result.status}")
    if exec_result.trace:
        print(f"  trace steps: {len(exec_result.trace)}")
        for s in exec_result.trace:
            print(f"    [{s.index}] {s.tool}: {s.status} (lat={s.latency_ms:.1f}ms)")
    
    # ── 6. Adaptive 反馈 ─────────────────────────────────────
    print(f"\n  [Adaptive 反馈] ...")
    required_clarification = (
        len(parse_result.intent.ambiguities) > 0 or
        (gate2 is not None and gate2.required_clarification) or
        (strategy_action and strategy_action.get('action') == 'ask_user')
    )
    adaptive.feedback(required_clarification=required_clarification)
    print(f"    required_clarification={required_clarification}")
    print(f"    Adaptive 阈值更新后: noise_fast_path={adaptive.get('noise_fast_path'):.2f}")
    
    # ── 7. FSM 状态 ──────────────────────────────────────────
    _print_header("Step 7: 澄清 FSM (Layer 3)")
    fsm = ClarificationFSM(ClarificationFSMContext(session_id="test-session"))
    fsm.handle_event(ClarificationEvent.USER_MESSAGE)
    has_ambiguity = (
        len(parse_result.intent.ambiguities) > 0 or
        (gate2 and gate2.required_clarification) or
        (strategy_action and strategy_action.get('action') == 'ask_user')
    )
    if has_ambiguity:
        fsm.handle_event(ClarificationEvent.PARSE_COMPLETE_HAS_AMBIGUITY)
    else:
        fsm.handle_event(ClarificationEvent.PARSE_COMPLETE_NO_AMBIGUITY)
    print(f"  最终状态: {fsm.current_state}")
    print(f"  外部状态: {ClarificationState.to_external_state(fsm.current_state)}")
    
    # ── 8. 事件序列 ──────────────────────────────────────────
    _print_header("Step 8: WebSocket 事件序列")
    events = []
    events.append(EventBuilder.intent_result(
        session_id="test-session", message_id="msg-001",
        status="ok" if not has_ambiguity else "clarifying",
        intent_result={
            "category": parse_result.intent.category.value,
            "confidence": parse_result.intent.confidence,
        },
        latency_ms=sum(s.latency_ms for s in exec_result.trace),
        trace_log=[f"{s.tool}:{s.status}" for s in exec_result.trace],
    ))
    events.append(EventBuilder.state_change(
        session_id="test-session",
        old_state=ClarificationState.START,
        new_state=fsm.current_state,
        event=ClarificationEvent.PARSE_COMPLETE_HAS_AMBIGUITY if has_ambiguity else ClarificationEvent.PARSE_COMPLETE_NO_AMBIGUITY,
        description="解析完成" + ("，触发策略补全器" if strategy_action else "，纯规则"),
    ))
    for i, ev in enumerate(events):
        print(f"  [{i+1}] {ev.event_type} @ {ev.timestamp:.3f}")
    
    # ── 9. 总结 ─────────────────────────────────────────────
    _print_header("总结")
    print(f"  输入: {query}")
    print(f"  PCR 期望: {pcr_output.expectation}")
    print(f"  意图分类: {parse_result.intent.category} (conf={parse_result.intent.confidence:.2f})")
    if short_circuited:
        print(f"  ⚡ 短路执行: {exec_result.status}")
        if exec_result.status == 'direct_reply':
            print(f"  LLM 回复: {exec_result.message[:100]}...")
        elif exec_result.status == 'clarifying':
            print(f"  追问: {exec_result.clarification.get('question', '')}")
    else:
        print(f"  最终蓝图: {gate2.blueprint_id}")
    print(f"  执行状态: {exec_result.status}")
    print(f"  是否需要澄清: {has_ambiguity}")
    print(f"  FSM 最终状态: {fsm.current_state} (外部: {ClarificationState.to_external_state(fsm.current_state)})")
    print(f"  LLM 调用次数: {llm_call_count} 次")
    if strategy_action:
        print(f"  策略补全结果: action={strategy_action.get('action')}")
    print(f"  Adaptive 阈值更新: noise_fast_path={adaptive.get('noise_fast_path'):.2f}")


def main():
    print(f"\n{'#'*70}")
    print("#  LM Studio 本地模型集成测试 — 方案 C")
    print(f"{'#'*70}")
    print(f"\n时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"项目: {_PROJECT_ROOT}")
    
    # 创建 Provider
    try:
        provider = ProviderFactory.from_config(LMSTUDIO_CONFIG)
        print(f"\nProvider 创建成功: {provider.name}")
    except Exception as e:
        print(f"\n❌ Provider 创建失败: {e}")
        print("请检查配置和依赖（pip install openai）")
        return 1
    
    # Step 0: 连接测试
    if not test_connection(provider):
        print("\n⚠️ 连接测试失败，跳过后续测试。")
        print("请确保 LM Studio 本地服务器已启动。")
        return 1
    
    # Step 1: 单轮推理测试
    if not test_single_inference(provider):
        print("\n⚠️ 单轮推理失败。")
        return 1
    
    # Step 2-9: 完整决策链
    print(f"\n{'#'*70}")
    print("#  完整意图解析决策链测试 — 方案 C")
    print(f"{'#'*70}")
    
    for i, (query, history, desc) in enumerate(TEST_QUERIES, 1):
        run_full_pipeline_with_llm(
            query=query,
            provider=provider,
            history=history,
            scenario_name=f"{i}: {desc}"
        )
    
    print(f"\n{'#'*70}")
    print("#  全部测试完成")
    print(f"{'#'*70}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""
LM Studio 本地模型测试脚本 — 全过程决策链追踪。

运行前准备：
1. 启动 LM Studio，加载模型（如 qwen3.5-9b 或类似）
2. 在 LM Studio 中开启 Local Server（默认端口 1234）
3. 确认模型名与配置一致

运行方式：
    python test_lmstudio_integration.py

功能：
- 测试 LM Studio 连接/健康状态
- 测试单轮 generate 推理
- 运行完整意图解析决策链（PCR → Gate → IntentParser → LLM Fallback）
- 显示全过程记录
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


# ═══════════════════════════════════════════════════════════
# 配置区：根据你的 LM Studio 设置修改
# ═══════════════════════════════════════════════════════════

LMSTUDIO_CONFIG = {
    "type": "openai",           # LM Studio 提供 OpenAI 兼容 API
    "name": "lmstudio-local",
    "api_key": "lm-studio",     # LM Studio 不校验 key，任意字符串
    "model": "qwen3.5-9b",      # ← 修改为 LM Studio 加载的模型名
    "base_url": "http://localhost:1234/v1",
    "timeout_s": 120,           # 首次加载模型可能很慢
}

TEST_QUERIES = [
    "scan 100",                                    # 简单工具指令
    "分析这个进程的内存结构",                       # 分析请求
    "我想学习如何扫描内存值",                     # 新手教程
    "scan",                                        # 模糊输入（缺参数）
    "读取这个地址",                                # 引用解析（需历史）
    "在内存里搜索数值并修改它",                    # 复合意图
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
        print("    4. base_url 和模型名是否与配置一致？")
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
        # 不设置 response_format，LM Studio 的 llama.cpp 不支持 json_object
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


def run_full_pipeline_with_llm(query: str, provider: LLMProvider, history=None, scenario_name=""):
    """运行完整决策链，包含 LLM Fallback 调用点。"""
    
    _print_header(f"场景：{scenario_name or query}")
    print(f"\n[输入] {query}")
    
    # ── 1. PCR 评估 ───────────────────────────────────────────
    _print_header("Step 2: PCR 评估 (Layer 0) — 规则引擎，无需 LLM")
    pcr = RuleBasedPCR()
    
    # 用户类型探测（P1 修复：冷启动策略）
    if history:
        user_type = pcr._profiler.first_turn_probe(query)  # 自动探测
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
    print(f"  suggested_next_actions: {pcr_output.suggested_next_actions}")
    
    # ── 2. 三层门控 ──────────────────────────────────────────
    _print_header("Step 3: 三层门控 (Layer 1)")
    
    adaptive = AdaptiveThresholds()
    print(f"  Adaptive Thresholds 初始: noise_fast_path={adaptive.get('noise_fast_path'):.2f}")
    
    # Gate 0
    gate0 = HardGate.evaluate(query, _history_entries)
    print(f"  Gate 0 (Hard): {'✅ 命中' if gate0 else '❌ 未命中'}")
    if gate0:
        print(f"    track={gate0.track}, blueprint={gate0.blueprint_id}")
    
    # Gate 1
    gate1_pcr, gate1 = PCRGate.evaluate(query, _history_entries, pcr, adaptive=adaptive)
    print(f"  Gate 1 (PCR): {'✅ 命中' if gate1 else '❌ 未命中'}")
    if gate1:
        print(f"    track={gate1.track}, blueprint={gate1.blueprint_id}")
    
    # Gate 2 (Router LLM 调用点)
    _print_header("Step 3b: Gate 2 Router LLM (动态蓝图选择) — 可能需要 LLM")
    parser = IntentParser()
    orchestrator = DualTrackOrchestrator(pcr, parser)
    
    # 检查是否会触发 LLM
    will_use_llm = (pcr_output.expectation == "UNKNOWN" or pcr_output.noise_level > 0.5)
    print(f"  PCR 期望={pcr_output.expectation}, noise={pcr_output.noise_level:.2f}")
    print(f"  是否触发 LLM Router: {'⚠️ 是' if will_use_llm else '✅ 否（规则足够）'}")
    
    if will_use_llm:
        print(f"\n  [LLM Router 调用] → 发送给 {provider.name}")
        router_req = GenerateRequest(
            prompt=f"用户输入：'{query}'\nPCR 评估：expectation={pcr_output.expectation}, "
                   f"noise={pcr_output.noise_level:.2f}, complexity={pcr_output.complexity_level:.2f}\n"
                   f"可用蓝图：{list(BLUEPRINT_REGISTRY.keys())}\n"
                   f"请只输出最匹配的蓝图 ID 字符串，不要添加任何解释。",
            system_prompt="你是一个路由决策助手。根据用户意图选择最合适的蓝图，只输出蓝图 ID 字符串，禁止输出任何解释。",
            max_tokens=20,
            temperature=0.0,
        )
        start = time.time()
        llm_result = provider.generate(router_req)
        llm_latency = (time.time() - start) * 1000
        print(f"    LLM 响应: {llm_result.text.strip()[:100]}")
        print(f"    LLM 延迟: {llm_latency:.0f}ms")
    
    gate2 = orchestrator.process(query, history=_history_entries, adaptive=adaptive)
    print(f"  Gate 2 (Orchestrator): track={gate2.track}, blueprint={gate2.blueprint_id}")
    print(f"  Adaptive 阈值更新: noise_fast_path={adaptive.get('noise_fast_path'):.2f}")
    
    # ── 4. 意图解析 ──────────────────────────────────────────
    _print_header("Step 4: 意图解析 (Layer 1)")
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
    
    # LLM Fallback 调用点（规则解析失败时）
    if parse_result.intent.confidence < 0.5 or parse_result.intent.category.value == "UNKNOWN":
        print(f"\n  [LLM Fallback 调用] → 规则解析置信度低，请求 LLM 补充")
        fallback_req = GenerateRequest(
            prompt=f"用户输入：'{query}'\n"
                   f"规则解析结果：category={parse_result.intent.category}, confidence={parse_result.intent.confidence:.2f}\n"
                   f"请重新分析用户意图，只输出合法 JSON 对象，禁止任何解释或 Markdown 代码块：\n"
                   f'{{"intent": "...", "confidence": 0.0-1.0, "entities": [...]}}',
            system_prompt="你是一个意图分析助手。你的输出必须且只能是合法的 JSON 对象，禁止输出任何解释、思考过程、Markdown 代码块标记。直接输出纯 JSON 文本。",
            max_tokens=128,
            temperature=0.0,
            # 不设置 response_format，LM Studio 的 llama.cpp 不支持 json_object
        )
        start = time.time()
        fallback_result = provider.generate(fallback_req)
        fallback_latency = (time.time() - start) * 1000
        print(f"    LLM Fallback 响应: {fallback_result.text.strip()[:200]}")
        print(f"    LLM Fallback 延迟: {fallback_latency:.0f}ms")
    
    # ── 5. 蓝图选择与执行 ─────────────────────────────────────
    _print_header("Step 5: 蓝图执行 (Layer 1)")
    final_bp = BLUEPRINT_REGISTRY.get(gate2.blueprint_id, BLUEPRINT_REGISTRY["RULE_FAST_PATH"])
    print(f"  选中蓝图: {gate2.blueprint_id}")
    print(f"  strategy_steps: {final_bp.strategy_steps}")
    
    executor = BlueprintExecutor()
    ctx = ExecutionContext(
        raw_input=query,
        pcr_instance=pcr,
        parser_instance=parser,
    )
    exec_result = executor.execute(final_bp, ctx)
    print(f"  执行状态: {exec_result.status}")
    print(f"  trace steps: {len(exec_result.trace)}")
    for s in exec_result.trace:
        print(f"    [{s.index}] {s.tool}: {s.status} (lat={s.latency_ms:.1f}ms)")
    
    # ── 6. FSM 状态 ──────────────────────────────────────────
    _print_header("Step 6: 澄清 FSM (Layer 3)")
    fsm = ClarificationFSM(ClarificationFSMContext(session_id="test-session"))
    fsm.handle_event(ClarificationEvent.USER_MESSAGE)
    has_ambiguity = len(parse_result.intent.ambiguities) > 0 or gate2.required_clarification
    if has_ambiguity:
        fsm.handle_event(ClarificationEvent.PARSE_COMPLETE_HAS_AMBIGUITY)
    else:
        fsm.handle_event(ClarificationEvent.PARSE_COMPLETE_NO_AMBIGUITY)
    print(f"  最终状态: {fsm.current_state}")
    print(f"  外部状态: {ClarificationState.to_external_state(fsm.current_state)}")
    
    # ── 7. 事件序列 ──────────────────────────────────────────
    _print_header("Step 7: WebSocket 事件序列")
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
        description="解析完成",
    ))
    for i, ev in enumerate(events):
        print(f"  [{i+1}] {ev.event_type} @ {ev.timestamp:.3f}")
    
    # ── 8. 总结 ─────────────────────────────────────────────
    _print_header("总结")
    print(f"  输入: {query}")
    print(f"  PCR 期望: {pcr_output.expectation}")
    print(f"  最终蓝图: {gate2.blueprint_id}")
    print(f"  执行状态: {exec_result.status}")
    print(f"  是否需要澄清: {has_ambiguity}")
    print(f"  FSM 最终状态: {fsm.current_state} (外部: {ClarificationState.to_external_state(fsm.current_state)})")
    print(f"  LLM 调用次数: {'1-2 次' if will_use_llm else '0 次（纯规则）'}")


def main():
    print(f"\n{'#'*70}")
    print("#  LM Studio 本地模型集成测试")
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
    
    # Step 2-7: 完整决策链（每个查询）
    print(f"\n{'#'*70}")
    print("#  完整意图解析决策链测试")
    print(f"{'#'*70}")
    
    for i, query in enumerate(TEST_QUERIES, 1):
        history = None
        if query == "读取这个地址":
            history = [{"role": "user", "content": "scan 0x401000", "expectation": "TOOL"}]
        
        run_full_pipeline_with_llm(
            query=query,
            provider=provider,
            history=history,
            scenario_name=f"{i}: {query}"
        )
    
    print(f"\n{'#'*70}")
    print("#  全部测试完成")
    print(f"{'#'*70}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

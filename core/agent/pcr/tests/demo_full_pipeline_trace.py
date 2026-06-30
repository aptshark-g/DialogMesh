# -*- coding: utf-8 -*-
"""
全过程决策追踪演示（非 GUI，纯控制台输出）。

运行方式：
    python core/agent/pcr/tests/demo_full_pipeline_trace.py

功能：输入一句话 → 打印 PCR → Gate → 蓝图 → 执行 → 结果/澄清 的完整决策链。
"""

from __future__ import annotations

import sys
import os
import json
import time
from typing import Any, Dict, List, Optional

# Add project root (3 levels up from this file)
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from core.agent.pcr.rule_based import RuleBasedPCR
from core.agent.pcr.datacontract import PCRInput_v1
from core.agent.intent_parser import IntentParser, IntentCategory
from core.agent.gates import (
    DualTrackOrchestrator, GateResult, AdaptiveThresholds,
    HardGate, PCRGate, OrchestrationGate
)
from core.agent.blueprints import BLUEPRINT_REGISTRY, Blueprint
from core.agent.orchestrator import BlueprintExecutor, ExecutionContext
from core.agent.frontend.clarification_fsm import (
    ClarificationFSM, ClarificationFSMContext, ClarificationState, ClarificationEvent
)
from core.agent.frontend.websocket_events import EventBuilder, EventTypeRegistry
from core.agent.frontend.clarification_ui import ClarificationUIFactory
from core.agent.tools.cognitive_tools import CognitiveTools


def _print_header(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def _print_json(label: str, data: Any, indent: int = 2):
    print(f"\n┌─ {label}")
    if isinstance(data, (dict, list)):
        print(json.dumps(data, ensure_ascii=False, indent=indent, default=str))
    else:
        print(f"  {data}")
    print("└" + "─" * 50)


def _print_gate_result(label: str, result: Optional[GateResult]):
    if result is None:
        print(f"  {label}: None (未命中)")
        return
    print(f"  {label}:")
    print(f"    track: {result.track}")
    print(f"    blueprint_id: {result.blueprint_id}")
    print(f"    latency_ms: {result.latency_ms:.2f}")
    print(f"    trace: {result.trace}")
    if result.execution_result:
        print(f"    execution_result: {result.execution_result}")
    print(f"    required_clarification: {result.required_clarification}")


def run_trace(
    query: str,
    history: Optional[List[Dict[str, Any]]] = None,
    user_type_hint: Optional[str] = None,
    scenario_name: str = ""
):
    """运行一条查询的完整决策链并打印全过程。"""
    
    _print_header(f"场景：{scenario_name or query}")
    print(f"\n[输入] {query}")
    print(f"[历史] {history or []}")
    print(f"[用户类型] {user_type_hint or 'auto-detect'}")
    
    # ── 1. PCR 评估 ───────────────────────────────────────────
    _print_header("Step 1: PCR 评估 (Layer 0)")
    # 转换 history dict 为 HistoryEntry
    from core.agent.pcr.datacontract import HistoryEntry
    _history_entries = []
    for h in (history or []):
        if isinstance(h, dict):
            _history_entries.append(HistoryEntry(
                role=h.get("role", "user"),
                content=h.get("content", ""),
                expectation=h.get("expectation", ""),
                timestamp=h.get("timestamp", 0.0),
            ))
        else:
            _history_entries.append(h)

    pcr = RuleBasedPCR()
    pcr_input = PCRInput_v1(
        query=query,
        session_history=_history_entries,
    )
    pcr_output = pcr.evaluate(pcr_input)
    
    print(f"  expectation: {pcr_output.expectation}")
    print(f"  noise: {pcr_output.noise_level:.2f}")
    print(f"  complexity: {pcr_output.complexity_level:.2f}")
    print(f"  cognitive_profile:")
    cp = pcr_output.cognitive_profile
    print(f"    metacognition={cp.metacognition:.2f}, divergence={cp.divergence:.2f}, "
          f"tracking_depth={cp.tracking_depth:.2f}, stability={cp.stability:.2f}")
    print(f"  execution_mode: {pcr_output.execution_mode}")
    print(f"  prompt_style: {pcr_output.prompt_style}")
    print(f"  ambiguities: {len(pcr_output.suggested_next_actions)} 个建议")
    for a in pcr_output.suggested_next_actions:
        print(f"    - {a}")
    
    # ── 2. 三层门控逐层检查 ──────────────────────────────────
    _print_header("Step 2: 三层门控 (Layer 1)")
    
    # Gate 0: Hard Gate
    print("\n  [Gate 0: Hard Gate] — 极速规则匹配")
    gate0_result = HardGate.evaluate(query, _history_entries)
    _print_gate_result("Gate 0 result", gate0_result)
    
    # 自适应阈值（P0 修复）
    adaptive = AdaptiveThresholds()
    print(f"\n  [Adaptive Thresholds] 初始:")
    print(f"    noise_fast_path={adaptive.get('noise_fast_path'):.2f}")
    print(f"    confidence_min={adaptive.get('confidence_min'):.2f}")
    
    # Gate 1: PCR Gate
    print("\n  [Gate 1: PCR Gate] — 策略评估")
    gate1_pcr_out, gate1_result = PCRGate.evaluate(query, _history_entries, pcr, adaptive=adaptive)
    _print_gate_result("Gate 1 result", gate1_result)
    
    # Gate 2: Orchestration Gate（如果 Gate 0/1 未命中）
    print("\n  [Gate 2: Orchestration Gate] — 动态蓝图选择")
    parser = IntentParser()
    orchestrator = DualTrackOrchestrator(pcr, parser)
    gate2_result = orchestrator.process(query, history=_history_entries, adaptive=adaptive)
    _print_gate_result("Gate 2 / Orchestrator result", gate2_result)
    
    print(f"\n  [Adaptive Thresholds] 执行后:")
    print(f"    noise_fast_path={adaptive.get('noise_fast_path'):.2f}")
    print(f"    confidence_min={adaptive.get('confidence_min'):.2f}")
    
    # ── 3. 意图解析详情 ──────────────────────────────────────
    _print_header("Step 3: 意图解析详情 (Layer 1)")
    from core.agent.models import IntentContext, ParseContext
    intent_ctx = IntentContext.from_pcr_output(pcr_output)
    parse_ctx = ParseContext(session_id="demo-session-001")
    parse_result = parser.parse(query, intent_ctx, parse_ctx)
    
    print(f"  category: {parse_result.intent.category}")
    print(f"  confidence: {parse_result.intent.confidence:.2f}")
    print(f"  entities: {len(parse_result.intent.entities)}")
    for e in parse_result.intent.entities:
        print(f"    - {e.type}: {e.value} (conf={e.confidence:.2f})")
    print(f"  ambiguities: {len(parse_result.intent.ambiguities)}")
    for a in parse_result.intent.ambiguities:
        print(f"    - type={a.type}, desc={a.description}")
    print(f"  task_graph: {parse_result.task_graph is not None}")
    if parse_result.task_graph:
        print(f"    nodes: {len(parse_result.task_graph.nodes)}")
        print(f"    edges: {len(parse_result.task_graph.edges)}")
    
    # ── 4. 蓝图选择 ──────────────────────────────────────────
    _print_header("Step 4: 蓝图选择 (Layer 1)")
    
    # 确定最终使用的蓝图
    final_bp_id = gate2_result.blueprint_id if gate2_result else "RULE_FAST_PATH"
    final_bp = BLUEPRINT_REGISTRY.get(final_bp_id, BLUEPRINT_REGISTRY["RULE_FAST_PATH"])
    
    print(f"  selected blueprint: {final_bp_id}")
    print(f"  description: {final_bp.description}")
    print(f"  strategy_steps: {final_bp.strategy_steps}")
    print(f"  gate: {final_bp.gate}")
    print(f"  latency_budget_ms: {final_bp.latency_budget_ms}")
    print(f"  requires_llm: {final_bp.requires_llm}")
    print(f"  fallback_id: {final_bp.fallback_id}")
    
    # ── 5. 蓝图执行 ──────────────────────────────────────────
    _print_header("Step 5: 蓝图执行 (Layer 1)")
    
    executor = BlueprintExecutor()
    ctx = ExecutionContext(raw_input=query)
    exec_result = executor.execute(final_bp, ctx)
    
    print(f"  status: {exec_result.status}")
    print(f"  trace steps: {len(exec_result.trace)}")
    for step in exec_result.trace:
        print(f"    [{step.index}] {step.tool}: {step.status} "
              f"(lat={step.latency_ms:.1f}ms)")
    if exec_result.fallback_to:
        print(f"  fallback_to: {exec_result.fallback_to}")
    
    # ── 6. 澄清 FSM 状态机 ───────────────────────────────────
    _print_header("Step 6: 澄清 FSM (Layer 3)")
    
    fsm = ClarificationFSM(ClarificationFSMContext(session_id="demo-session-001"))
    print(f"  initial state: {fsm.current_state}")
    print(f"  external state: {ClarificationState.to_external_state(fsm.current_state)}")
    
    # 模拟用户消息触发
    fsm.handle_event(ClarificationEvent.USER_MESSAGE)
    print(f"  after USER_MESSAGE: {fsm.current_state} "
          f"(external: {ClarificationState.to_external_state(fsm.current_state)})")
    
    # 如果有歧义，进入 CLARIFYING
    if parse_result.intent.ambiguities or (gate2_result and gate2_result.required_clarification):
        fsm.handle_event(ClarificationEvent.PARSE_COMPLETE_HAS_AMBIGUITY)
        print(f"  after PARSE_COMPLETE_HAS_AMBIGUITY: {fsm.current_state} "
              f"(external: {ClarificationState.to_external_state(fsm.current_state)})")
        
        # 生成 UI Schema
        _print_header("Step 7: 澄清 UI Schema (Layer 3)")
        if parse_result.intent.ambiguities:
            amb = parse_result.intent.ambiguities[0]
            if amb.type == "ambiguous_address":
                schema = ClarificationUIFactory.create_address_selector(
                    addresses=amb.suggestions or ["0x1000", "0x2000"],
                    recommended_idx=0
                )
            elif amb.type == "ambiguous_process":
                schema = ClarificationUIFactory.create_process_selector(
                    candidates=amb.suggestions or ["notepad.exe", "chrome.exe"],
                    recommended_idx=0
                )
            elif amb.type == "missing_value":
                schema = ClarificationUIFactory.create_value_input(
                    field_name=amb.description or "value",
                    expected_type="number",
                    default=None
                )
            else:
                schema = ClarificationUIFactory.create_tutorial_hint(
                    title="需要澄清",
                    bullets=[amb.description or "请提供更多信息"]
                )
            print(f"  UI Schema type: {schema.schema_type}")
            print(f"  components: {len(schema.components)}")
            for c in schema.components:
                print(f"    - {c.type}: {c.label}")
    else:
        fsm.handle_event(ClarificationEvent.PARSE_COMPLETE_NO_AMBIGUITY)
        print(f"  after PARSE_COMPLETE_NO_AMBIGUITY: {fsm.current_state} "
              f"(external: {ClarificationState.to_external_state(fsm.current_state)})")
    
    # ── 8. WebSocket 事件序列 ─────────────────────────────────
    _print_header("Step 8: WebSocket 事件序列 (Layer 3)")
    
    events = []
    events.append(EventBuilder.intent_result(
        session_id="demo-session-001",
        message_id="msg-001",
        status="ok" if not parse_result.intent.ambiguities else "clarifying",
        intent_result={
            "category": parse_result.intent.category.value,
            "confidence": parse_result.intent.confidence,
            "entities": [{"type": e.type.value, "value": e.value} for e in parse_result.intent.entities]
        },
        latency_ms=sum(s.latency_ms for s in exec_result.trace) if exec_result.trace else 0.0,
        trace_log=[f"{s.tool}:{s.status}" for s in exec_result.trace]
    ))
    
    if parse_result.intent.ambiguities:
        events.append(EventBuilder.clarification(
            session_id="demo-session-001",
            clarification_id="clarify-001",
            message=parse_result.intent.ambiguities[0].description or "需要澄清",
            ui_schema=schema.to_dict() if 'schema' in dir() else {},
            timeout_seconds=60,
        ))
    
    events.append(EventBuilder.state_change(
        session_id="demo-session-001",
        old_state=ClarificationState.START,
        new_state=fsm.current_state,
        event=ClarificationEvent.PARSE_COMPLETE_HAS_AMBIGUITY if parse_result.intent.ambiguities else ClarificationEvent.PARSE_COMPLETE_NO_AMBIGUITY,
        description="解析完成" + ("，需要澄清" if parse_result.intent.ambiguities else "，无歧义")
    ))
    
    for i, ev in enumerate(events):
        print(f"  [{i+1}] {ev.event_type} @ {ev.timestamp:.3f}")
        print(f"       payload keys: {list(ev.payload.keys())}")
    
    # ── 9. 事件类型校验 ──────────────────────────────────────
    _print_header("Step 9: 事件类型校验 (P2 修复)")
    print(f"  EventTypeRegistry.is_valid('intent_result'): {EventTypeRegistry.is_valid('intent_result')}")
    print(f"  EventTypeRegistry.is_valid('clarification'): {EventTypeRegistry.is_valid('clarification')}")
    print(f"  EventTypeRegistry.is_valid('custom_event'): {EventTypeRegistry.is_valid('custom_event')}")
    EventTypeRegistry.register("custom_event")
    print(f"  after register: EventTypeRegistry.is_valid('custom_event'): {EventTypeRegistry.is_valid('custom_event')}")
    print(f"  all types: {EventTypeRegistry.list_all()}")
    
    # ── 10. 总结 ─────────────────────────────────────────────
    _print_header("总结")
    print(f"  输入: {query}")
    print(f"  PCR 期望: {pcr_output.expectation}")
    print(f"  最终蓝图: {final_bp_id}")
    print(f"  执行状态: {exec_result.status}")
    print(f"  总延迟: {sum(s.latency_ms for s in exec_result.trace):.1f}ms")
    print(f"  是否需要澄清: {bool(parse_result.intent.ambiguities)}")
    print(f"  FSM 最终状态: {fsm.current_state} (外部: {ClarificationState.to_external_state(fsm.current_state)})")
    print(f"  Adaptive 阈值更新: noise_fast_path={adaptive.get('noise_fast_path'):.2f}")


# ── 测试场景 ─────────────────────────────────────────────────

if __name__ == "__main__":
    
    # 场景 A: 简单扫描请求 — 快速路径
    run_trace(
        query="scan 100",
        scenario_name="A: 简单扫描（快速路径）"
    )
    
    # 场景 B: 分析请求 — 分析型
    run_trace(
        query="分析这个进程的内存结构",
        scenario_name="B: 分析请求（ADVISOR）"
    )
    
    # 场景 C: 新手教程 — 低元认知
    run_trace(
        query="我想学习如何扫描内存值",
        scenario_name="C: 新手教程（低元认知）",
        user_type_hint="novice"
    )
    
    # 场景 D: 有歧义 — 缺少参数
    run_trace(
        query="scan",  # 缺少数值，会有歧义
        scenario_name="D: 模糊输入（歧义/澄清）"
    )
    
    # 场景 E: 引用解析 — 有历史上下文
    run_trace(
        query="读取这个地址",
        history=[{"role": "user", "content": "scan 0x401000", "expectation": "TOOL"}],
        scenario_name="E: 引用解析（历史上下文）"
    )
    
    # 场景 F: 规则冲突 — 同域多规则
    run_trace(
        query="在内存里搜索数值并修改它",
        scenario_name="F: 复合意图（多意图/高复杂度）"
    )
    
    print(f"\n{'='*60}")
    print("  全部场景运行完毕")
    print(f"{'='*60}")

# -*- coding: utf-8 -*-
"""
core/agent/pcr/tests/intent_trace_cli.py — 交互式意图解析全过程追踪 CLI。

用法：
    python intent_trace_cli.py --query "scan 100"
    python intent_trace_cli.py --interactive
    python intent_trace_cli.py --lmstudio-url http://localhost:1234/v1 --model qwen3.5-9b
    python intent_trace_cli.py --interactive --persist --window-compress --observe
    python intent_trace_cli.py --list-sessions

功能：
- 输入用户查询 → 打印完整决策链（PCR → Gate → Intent → Strategy Completer → 执行/短路 → FSM → 总结）
- 支持多轮对话（历史上下文自动继承，可选持久化到 SQLite）
- 支持 LM Studio 本地模型（可选）
- 支持上下文窗口压缩（Hot/Warm/Cold 三层）
- 支持观测系统（日志/指标/告警/链路追踪）
- 支持会话管理（list / load / delete）

依赖：项目根目录需在 PYTHONPATH 中。
"""

from __future__ import annotations

import sys
import os
import json
import time
import argparse
from typing import List, Dict, Any, Optional

# 确保项目根目录在路径中
_SCRIPT_DIR = os.path.dirname(__file__)
_PROJECT_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", "..", "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from core.agent.llm_providers import ProviderFactory
from core.agent.llm_providers.base import GenerateRequest, LLMProvider
from core.agent.pcr.rule_based import RuleBasedPCR
from core.agent.pcr.datacontract import PCRInput_v1, HistoryEntry
from core.agent.gates import (
    DualTrackOrchestrator, AdaptiveThresholds,
    HardGate, PCRGate,
)
from core.agent.intent_parser import IntentParser
from core.agent.models import IntentContext, ParseContext
from core.agent.blueprints import BLUEPRINT_REGISTRY
from core.agent.orchestrator import BlueprintExecutor, ExecutionContext
from core.agent.frontend.clarification_fsm import (
    ClarificationFSM, ClarificationFSMContext, ClarificationState, ClarificationEvent
)
from core.agent.frontend.websocket_events import EventBuilder, EventTypeRegistry
from core.agent.tools.cognitive_tools import CognitiveTools

# 新增模块（可选导入，向后兼容）
try:
    from core.agent.persistence import CLISessionPersistence, TurnRecord
    from core.agent.window import ContextWindowManager, WindowBudget
    from core.agent.observability import Telemetry
    _PERSISTENCE_AVAILABLE = True
except ImportError:
    _PERSISTENCE_AVAILABLE = False


# ───────────────────────────────────────────
# 格式化输出工具
# ───────────────────────────────────────────

def _print_header(title: str, width: int = 70):
    print(f"\n{'='*width}")
    print(f"  {title}")
    print(f"{'='*width}")


def _print_section(title: str, indent: int = 2):
    print(f"\n{' '*indent}[>] {title}")


def _print_kv(key: str, value: Any, indent: int = 4):
    if isinstance(value, float):
        print(f"{' '*indent}{key}: {value:.2f}")
    else:
        print(f"{' '*indent}{key}: {value}")


def _print_json(label: str, data: Any, indent: int = 2):
    print(f"\n{' '*indent}[{label}]")
    if isinstance(data, (dict, list)):
        for line in json.dumps(data, ensure_ascii=False, indent=2, default=str).splitlines():
            print(f"{' '*indent}  {line}")
    else:
        print(f"{' '*indent}  {data}")


def _print_badge(label: str, status: str):
    """打印状态徽章。"""
    badges = {
        "ok": "[OK]",
        "error": "[ERR]",
        "warning": "[WARN]",
        "info": "[INFO]",
        "skip": "[SKIP]",
        "hit": "[HIT]",
        "miss": "[MISS]",
        "bolt": "[BOLT]",
    }
    badge = badges.get(status, "[*]")
    print(f"    {badge} {label}")


# ───────────────────────────────────────────
# 核心决策链执行
# ───────────────────────────────────────────

def _should_use_strategy_completer(pcr_output, parse_result) -> tuple[bool, List[str]]:
    """多维判断：是否需要触发策略补全器（阈值从配置读取）。"""
    from core.agent.config import get_config
    cfg = get_config()
    th = cfg.thresholds.strategy_completer
    
    reasons = []
    if pcr_output.expectation == "UNKNOWN":
        reasons.append("expectation=UNKNOWN")
    
    confidence_low = th.get("confidence_low", 0.3)
    if parse_result and parse_result.intent.confidence < confidence_low:
        reasons.append(f"confidence={parse_result.intent.confidence:.2f}<{confidence_low}")
    
    combo = th.get("noise_complexity_combo", 0.3)
    if pcr_output.noise_level > combo and pcr_output.complexity_level > combo:
        reasons.append(f"noise={pcr_output.noise_level:.2f}&complexity={pcr_output.complexity_level:.2f}>{combo}")
    
    advisor_low = th.get("advisor_confidence_low", 0.5)
    if pcr_output.expectation == "ADVISOR" and parse_result and parse_result.intent.confidence < advisor_low:
        reasons.append(f"ADVISOR&confidence={parse_result.intent.confidence:.2f}<{advisor_low}")
    
    if parse_result and len(parse_result.intent.ambiguities) > 0:
        reasons.append(f"ambiguities={len(parse_result.intent.ambiguities)}>0")
    return len(reasons) > 0, reasons


def run_intent_trace(
    query: str,
    provider: Optional[LLMProvider],
    history: List[Dict[str, Any]] = None,
    session_id: str = "cli-session",
    verbose: bool = True,
    conversation_mode: bool = False,
    persistence: Optional[Any] = None,
    telemetry: Optional[Any] = None,
    window_manager: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    执行完整意图解析决策链，返回结构化结果。
    
    Args:
        query: 用户输入
        provider: LLM Provider（可选，None 则纯规则）
        history: 历史对话记录（内存中的，会被持久化历史合并）
        session_id: 会话 ID
        verbose: 是否打印详细过程
        conversation_mode: 对话模式 — 当意图为 UNKNOWN 时强制调用 LLM 生成自然语言回复
        persistence: CLISessionPersistence 实例（可选）
        telemetry: Telemetry 实例（可选）
        window_manager: ContextWindowManager 实例（可选）
    
    Returns:
        包含全过程结果的字典
    """
    
    start_time = time.time()
    
    # ── Telemetry Trace 启动 ──
    if telemetry:
        telemetry.start_trace(session_id, 0, query)  # turn_index 由 caller 维护
        telemetry.start_span("COMPILE", input_summary=query[:50])
    
    result = {
        "query": query,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "session_id": session_id,
        "has_llm": provider is not None,
        "steps": [],
    }
    
    if verbose:
        _print_header(f"查询: {query}")
    
    # ── 从持久化加载历史 ──
    _history_entries = []
    loaded_from_persistence = False
    if persistence:
        session = persistence.get_or_load(session_id)
        if session and session.history:
            loaded_from_persistence = True
            for turn in session.history:
                _history_entries.append(HistoryEntry(
                    role=turn.role,
                    content=turn.content,
                    expectation=turn.intent_result.get("expectation", "") if turn.intent_result else "",
                    timestamp=turn.timestamp,
                ))
    
    # 合并 caller 提供的 history（覆盖/追加）
    for h in (history or []):
        if isinstance(h, dict):
            _history_entries.append(HistoryEntry(
                role=h.get("role", "user"),
                content=h.get("content", ""),
                expectation=h.get("expectation", ""),
                timestamp=h.get("timestamp", 0.0),
            ))
    
    # ── 窗口压缩 ──
    compression_meta = None
    if window_manager and _history_entries:
        compressed, compression_meta = window_manager.compress(_history_entries)
        _history_entries = compressed
        if verbose and compression_meta and compression_meta.get("status") != "pass_through":
            _print_section("窗口压缩")
            _print_kv("status", compression_meta.get("status"))
            _print_kv("tokens_before", compression_meta.get("tokens_before"))
            _print_kv("tokens_after", compression_meta.get("tokens_after"))
            _print_kv("compression_ratio", compression_meta.get("compression_ratio"))
    
    if telemetry:
        telemetry.end_span("ok", output_summary=f"history={len(_history_entries)}")
        telemetry.start_span("PCR", input_summary="rule_based_pcr")
    
    # ── Step 1: PCR 评估 ───────────────────────────────
    if verbose:
        _print_section("Step 1: PCR 评估 (Layer 0) — 规则引擎")
    
    pcr = RuleBasedPCR()
    
    # 用户类型探测
    user_type = pcr._profiler.first_turn_probe(query) if not _history_entries else "neutral"
    if verbose:
        _print_kv("用户类型探测", user_type)
    
    pcr_input = PCRInput_v1(query=query, session_history=_history_entries)
    pcr_output = pcr.evaluate(pcr_input)
    
    if verbose:
        _print_kv("expectation", pcr_output.expectation)
        _print_kv("noise_level", pcr_output.noise_level)
        _print_kv("complexity_level", pcr_output.complexity_level)
        _print_kv("cognitive_profile.metacognition", pcr_output.cognitive_profile.metacognition)
        _print_kv("execution_mode", pcr_output.execution_mode)
    
    result["steps"].append({
        "step": "PCR",
        "expectation": pcr_output.expectation,
        "noise": pcr_output.noise_level,
        "complexity": pcr_output.complexity_level,
        "metacognition": pcr_output.cognitive_profile.metacognition,
    })
    
    if telemetry:
        telemetry.end_span("ok", output_summary=f"expectation={pcr_output.expectation}")
        telemetry.start_span("GATES", input_summary="hard+pcr")
    
    # ── Step 2: 三层门控 ───────────────────────────────
    if verbose:
        _print_section("Step 2: 三层门控 (Layer 1)")
    
    adaptive = AdaptiveThresholds()
    if verbose:
        _print_kv("Adaptive.noise_fast_path (初始)", adaptive.get("noise_fast_path"))
    
    gate0 = HardGate.evaluate(query, _history_entries)
    if verbose:
        _print_badge(f"Gate 0 (Hard): {'命中' if gate0 else '未命中'} — {gate0.blueprint_id if gate0 else 'N/A'}",
                     "hit" if gate0 else "miss")
    
    gate1_pcr, gate1 = PCRGate.evaluate(query, _history_entries, pcr, adaptive=adaptive)
    if verbose:
        _print_badge(f"Gate 1 (PCR): {'命中' if gate1 else '未命中'} — {gate1.blueprint_id if gate1 else 'N/A'}",
                     "hit" if gate1 else "miss")
    
    if telemetry:
        telemetry.end_span("ok", output_summary=f"gate0={gate0 is not None}, gate1={gate1 is not None}")
        telemetry.start_span("INTENT", input_summary="intent_parser")
    
    # ── Step 3: 意图解析 ───────────────────────────────
    if verbose:
        _print_section("Step 3: 意图解析 (Layer 1)")
    
    parser = IntentParser()
    intent_ctx = IntentContext.from_pcr_output(pcr_output)
    parse_ctx = ParseContext(session_id=session_id)
    parse_result = parser.parse(query, intent_ctx, parse_ctx)
    
    if verbose:
        _print_kv("category", parse_result.intent.category)
        _print_kv("confidence", parse_result.intent.confidence)
        _print_kv("entities", len(parse_result.intent.entities))
        for e in parse_result.intent.entities:
            print(f"      • {e.type}: {e.value} (conf={e.confidence:.2f})")
        _print_kv("ambiguities", len(parse_result.intent.ambiguities))
        for a in parse_result.intent.ambiguities:
            print(f"      • {a.type}: {a.description}")
    
    result["steps"].append({
        "step": "IntentParser",
        "category": str(parse_result.intent.category),
        "confidence": parse_result.intent.confidence,
        "entities": [{"type": str(e.type), "value": e.value, "confidence": e.confidence} for e in parse_result.intent.entities],
        "ambiguities": [{"type": a.type, "description": a.description} for a in parse_result.intent.ambiguities],
    })
    
    if telemetry:
        telemetry.end_span("ok", output_summary=f"category={parse_result.intent.category}")
        telemetry.start_span("STRATEGY", input_summary="strategy_completer")
    
    # ── Step 4: 策略补全器 ─────────────────────────────
    if verbose:
        _print_section("Step 4: 策略补全器 (Strategy Completer)")
    
    should_use, reasons = _should_use_strategy_completer(pcr_output, parse_result)
    if verbose:
        _print_badge(f"是否触发: {'是' if should_use else '否'}", "warning" if should_use else "ok")
        if reasons:
            print(f"      原因: {', '.join(reasons)}")
    
    strategy_action = None
    llm_latency_ms = 0
    
    if should_use and provider:
        if verbose:
            _print_section(f"  [LLM 调用] -> {provider.name}")
        
        executor_ctx = ExecutionContext(
            raw_input=query,
            pcr_instance=pcr,
            parser_instance=parser,
            llm_provider=provider,
        )
        state = {
            "pcr_evaluate": pcr_output,
            "intent_parser_full_pipeline": parse_result,
        }
        
        start_llm = time.time()
        try:
            if conversation_mode:
                strategy_action = CognitiveTools.run("conversation_handler", executor_ctx, state)
            else:
                strategy_action = CognitiveTools.run("strategy_completer", executor_ctx, state)
        except Exception as e:
            if verbose:
                _print_badge(f"策略补全器异常: {e}", "error")
            strategy_action = {
                "action": "direct_reply",
                "text": f"[策略补全器异常: {e}]",
            }
        llm_latency_ms = (time.time() - start_llm) * 1000
        
        if verbose:
            _print_kv("LLM 延迟", f"{llm_latency_ms:.0f}ms")
            tool_name = "conversation_handler" if conversation_mode else "strategy_completer"
            _print_kv("工具", tool_name)
            _print_kv("action", strategy_action.get("action", "unknown"))
            if strategy_action.get("question"):
                _print_kv("question", strategy_action["question"][:100])
            if strategy_action.get("text"):
                _print_kv("text", strategy_action["text"][:100])
    
    result["steps"].append({
        "step": "StrategyCompleter",
        "triggered": should_use,
        "reasons": reasons,
        "llm_latency_ms": llm_latency_ms,
        "action": strategy_action.get("action") if strategy_action else None,
    })
    
    if telemetry:
        telemetry.end_span("ok", output_summary=f"triggered={should_use}, action={strategy_action.get('action') if strategy_action else None}")
        telemetry.start_span("EXECUTE", input_summary="blueprint_executor")
    
    # ── Step 5: 蓝图执行 / 短路 ──────────────────────────
    if verbose:
        _print_section("Step 5: 蓝图执行 / 策略短路 (Layer 1)")
    
    exec_result = None
    short_circuited = False
    gate2 = None
    
    if strategy_action and strategy_action.get("action") == "direct_reply":
        # 短路：直接返回 LLM 生成的回复
        if verbose:
            _print_badge("[BOLT] 短路拦截: direct_reply，跳过规则蓝图", "bolt")
            _print_kv("LLM 回复", strategy_action.get("text", "")[:150] + "...")
        
        exec_result = type('obj', (object,), {
            'status': 'direct_reply',
            'task_graph': None,
            'clarification': None,
            'trace': [],
            'fallback_to': None,
            'message': strategy_action.get("text", ""),
        })()
        short_circuited = True
        
    elif strategy_action and strategy_action.get("action") == "ask_user":
        # 短路：进入澄清状态
        if verbose:
            _print_badge("[BOLT] 短路拦截: ask_user，跳过规则蓝图", "bolt")
            _print_kv("追问", strategy_action.get("question", ""))
        
        exec_result = type('obj', (object,), {
            'status': 'clarifying',
            'task_graph': None,
            'clarification': {
                'type': 'ask_user',
                'question': strategy_action.get("question", ""),
            },
            'trace': [],
            'fallback_to': None,
            'message': None,
        })()
        short_circuited = True
    
    else:
        # 正常执行蓝图
        orchestrator = DualTrackOrchestrator(pcr, parser)
        gate2 = orchestrator.process(query, history=_history_entries, adaptive=adaptive)
        final_bp = BLUEPRINT_REGISTRY.get(gate2.blueprint_id, BLUEPRINT_REGISTRY["RULE_FAST_PATH"])
        
        if verbose:
            _print_kv("选中蓝图", gate2.blueprint_id)
            _print_kv("strategy_steps", final_bp.strategy_steps)
        
        executor = BlueprintExecutor()
        ctx = ExecutionContext(
            raw_input=query,
            pcr_instance=pcr,
            parser_instance=parser,
            llm_provider=provider,
        )
        exec_result = executor.execute(final_bp, ctx)
        
        if verbose:
            _print_kv("执行状态", exec_result.status)
            if exec_result.trace:
                for s in exec_result.trace:
                    print(f"      [{s.index}] {s.tool}: {s.status} (lat={s.latency_ms:.1f}ms)")
    
    result["steps"].append({
        "step": "Execution",
        "status": exec_result.status,
        "short_circuited": short_circuited,
        "blueprint": gate2.blueprint_id if gate2 else None,
        "trace": [{"tool": s.tool, "status": s.status, "latency_ms": s.latency_ms} for s in exec_result.trace] if exec_result.trace else [],
    })
    
    if telemetry:
        telemetry.end_span("ok", output_summary=f"status={exec_result.status}")
    
    # ── Step 5b: 对话回退 (Conversation Fallback) ────────
    if conversation_mode and provider and exec_result.status not in ("direct_reply", "clarifying"):
        category_str = str(parse_result.intent.category)
        if category_str in ("IntentCategory.UNKNOWN", "IntentCategory.CHITCHAT") or pcr_output.expectation in ("UNKNOWN", "COMPANION"):
            if verbose:
                _print_section("Step 5b: 对话回退 (Conversation Fallback)")
                _print_badge("意图未识别 -> 强制 LLM 对话回复", "info")
            try:
                from core.agent.llm_providers.base import GenerateRequest
                from core.agent.config import config as cfg_mgr
                sp_cfg = cfg_mgr.get_system_prompt("conversation_handler")
                profile_cfg = cfg_mgr.get_llm_profile("local_thinking" if (provider and getattr(provider, "name", "").lower() in ("lmstudio", "local")) else "default")
                
                req = GenerateRequest(
                    system_prompt=sp_cfg.index_card,
                    prompt=f"""用户输入："{query}"

参数速查：
{chr(10).join(f"- {k}: {v}" for k, v in (sp_cfg.parameter_glossary or {}).items())}

当前状态：expectation=UNKNOWN, confidence=0.0

请分析并给出 Final Output。""",
                    temperature=profile_cfg.temperature,
                    max_tokens=profile_cfg.max_tokens,
                    timeout_ms=profile_cfg.timeout_ms,
                )
                reply = provider.generate(req)
                exec_result = type('obj', (object,), {
                    'status': 'direct_reply',
                    'task_graph': None,
                    'clarification': None,
                    'trace': [],
                    'fallback_to': 'conversation_fallback',
                    'message': reply.text or "[LLM 未返回内容]",
                })()
                short_circuited = True
                if verbose:
                    _print_kv("LLM 回复", exec_result.message[:150] + "...")
            except Exception as e:
                if verbose:
                    _print_badge(f"对话回退失败: {e}", "error")
    
    # ── Step 6: Adaptive 反馈 ────────────────────────────
    if verbose:
        _print_section("Step 6: Adaptive 反馈")
    
    required_clarification = (
        len(parse_result.intent.ambiguities) > 0 or
        (gate2 is not None and gate2.required_clarification) or
        (strategy_action and strategy_action.get("action") == "ask_user")
    )
    adaptive.feedback(required_clarification=required_clarification)
    
    if verbose:
        _print_kv("required_clarification", required_clarification)
        _print_kv("noise_fast_path (更新后)", adaptive.get("noise_fast_path"))
    
    # ── Step 7: FSM 状态 ────────────────────────────────
    if verbose:
        _print_section("Step 7: 澄清 FSM (Layer 3)")
    
    fsm = ClarificationFSM(ClarificationFSMContext(session_id=session_id))
    fsm.handle_event(ClarificationEvent.USER_MESSAGE)
    has_ambiguity = (
        len(parse_result.intent.ambiguities) > 0 or
        (gate2 is not None and gate2.required_clarification) or
        (strategy_action and strategy_action.get("action") == "ask_user")
    )
    if has_ambiguity:
        fsm.handle_event(ClarificationEvent.PARSE_COMPLETE_HAS_AMBIGUITY)
    else:
        fsm.handle_event(ClarificationEvent.PARSE_COMPLETE_NO_AMBIGUITY)
    
    if verbose:
        _print_kv("内部状态", fsm.current_state)
        _print_kv("外部状态", ClarificationState.to_external_state(fsm.current_state))
    
    result["steps"].append({
        "step": "FSM",
        "internal_state": fsm.current_state,
        "external_state": ClarificationState.to_external_state(fsm.current_state),
        "has_ambiguity": has_ambiguity,
    })
    
    # ── Step 8: 总结 ────────────────────────────────
    if verbose:
        _print_header("总结", width=60)
        _print_kv("输入", query)
        _print_kv("PCR 期望", pcr_output.expectation)
        _print_kv("意图分类", f"{parse_result.intent.category} (conf={parse_result.intent.confidence:.2f})")
        if short_circuited:
            _print_kv("[BOLT] 执行方式", f"短路: {exec_result.status}")
            if exec_result.status == "direct_reply":
                _print_kv("LLM 回复", exec_result.message[:100] + "...")
            elif exec_result.status == "clarifying":
                _print_kv("追问", exec_result.clarification.get("question", ""))
        else:
            _print_kv("蓝图", gate2.blueprint_id if gate2 else "N/A")
        _print_kv("是否需要澄清", has_ambiguity)
        _print_kv("FSM 状态", f"{fsm.current_state} (外部: {ClarificationState.to_external_state(fsm.current_state)})")
        _print_kv("LLM 调用", f"{'1 次' if (should_use and provider) else '0 次'}")
        _print_kv("Adaptive 阈值", adaptive.get("noise_fast_path"))
    
    total_latency = (time.time() - start_time) * 1000
    
    result["summary"] = {
        "query": query,
        "expectation": pcr_output.expectation,
        "category": str(parse_result.intent.category),
        "confidence": parse_result.intent.confidence,
        "execution_status": exec_result.status,
        "short_circuited": short_circuited,
        "has_ambiguity": has_ambiguity,
        "fsm_state": fsm.current_state,
        "llm_used": should_use and provider is not None,
    }
    if exec_result.message:
        result["summary"]["message"] = exec_result.message
    
    # ── 持久化 ──
    if persistence:
        intent_summary = result["summary"]
        persistence.add_turn(
            session_id=session_id,
            role="user",
            content=query,
            intent_result=intent_summary,
            execution_status=intent_summary.get("execution_status"),
            latency_ms=total_latency,
        )
        if exec_result.status == "direct_reply" and exec_result.message:
            persistence.add_turn(
                session_id=session_id,
                role="assistant",
                content=exec_result.message,
                intent_result={"expectation": "DIRECT_REPLY"},
                execution_status="direct_reply",
                latency_ms=0,
            )
    
    # ── 观测记录 ──
    if telemetry:
        trace, alerts = telemetry.end_trace(
            intent=str(parse_result.intent.category),
            confidence=parse_result.intent.confidence,
            execution_status=exec_result.status,
            required_clarification=has_ambiguity,
            used_llm_fallback=should_use and provider is not None,
            metadata={
                "cohesion": 0.0,
                "compression": compression_meta,
                "persistence_loaded": loaded_from_persistence,
            },
        )
        if alerts and verbose:
            for alert in alerts:
                _print_badge(f"ALERT: {alert.message}", alert.severity.value)
    
    return result


# ───────────────────────────────────────────
# CLI 入口
# ───────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="意图解析全过程追踪 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python intent_trace_cli.py --query "scan 100"
  python intent_trace_cli.py --query "分析内存结构" --lmstudio
  python intent_trace_cli.py --interactive
  python intent_trace_cli.py --query "scan" --output result.json
  python intent_trace_cli.py --interactive --persist --window-compress --observe
  python intent_trace_cli.py --list-sessions
  python intent_trace_cli.py --load-session cli-123456 --interactive
        """
    )
    parser.add_argument("--query", "-q", type=str, help="用户查询（单轮模式）")
    parser.add_argument("--interactive", "-i", action="store_true", help="交互模式（多轮对话）")
    parser.add_argument("--lmstudio", action="store_true", help="使用 LM Studio 本地模型")
    parser.add_argument("--lmstudio-url", type=str, default="http://localhost:1234/v1", help="LM Studio 地址")
    parser.add_argument("--model", type=str, default="qwen3.5-9b", help="模型名称")
    parser.add_argument("--output", "-o", type=str, help="输出结果到 JSON 文件")
    parser.add_argument("--quiet", action="store_true", help="静默模式（只输出结果）")
    parser.add_argument("--pipeline", type=str, choices=["v1", "v2"], default="v1",
                        help="Pipeline 版本: v1=纯内存, v2=AgentPipeline(持久化/编译器/话题树/窗口/观测)")
    parser.add_argument("--conversation-mode", "-c", action="store_true",
                        help="对话模式 — 当意图无法识别时，强制调用 LLM 生成自然语言回复")
    
    # 新增：持久化/窗口/观测开关
    parser.add_argument("--persist", "-p", action="store_true", help="启用 SQLite 持久化（会话历史保存到本地）")
    parser.add_argument("--window-compress", "-w", action="store_true", help="启用上下文窗口压缩（Hot/Warm/Cold）")
    parser.add_argument("--observe", "-obs", action="store_true", help="启用观测系统（日志/指标/告警/链路追踪）")
    parser.add_argument("--db-path", type=str, default="~/.memorygraph/sessions.db", help="持久化数据库路径")
    
    # 新增：会话管理
    parser.add_argument("--list-sessions", "-ls", action="store_true", help="列出所有会话")
    parser.add_argument("--load-session", "-sid", type=str, help="加载指定会话 ID 继续对话")
    parser.add_argument("--delete-session", "-ds", type=str, help="删除指定会话")
    
    args = parser.parse_args()
    
    # 检查新模块可用性
    if (args.persist or args.window_compress or args.observe or args.list_sessions or args.load_session or args.delete_session) and not _PERSISTENCE_AVAILABLE:
        print("[ERROR] 持久化/窗口/观测模块未安装或导入失败。请确认项目结构正确。")
        return 1
    
    # 初始化可选模块
    persistence = None
    window_manager = None
    telemetry = None
    
    if args.persist or args.observe or args.window_compress or args.list_sessions or args.load_session or args.delete_session:
        if _PERSISTENCE_AVAILABLE:
            if args.persist or args.load_session or args.delete_session or args.list_sessions:
                persistence = CLISessionPersistence(db_path=args.db_path)
            if args.window_compress:
                window_manager = ContextWindowManager()
            if args.observe:
                telemetry = Telemetry.from_config(store_db_path=args.db_path.replace("sessions.db", "observability.db"))
    
    # ── 会话管理命令 ──
    if args.list_sessions:
        if not persistence:
            print("[ERROR] 持久化未启用，无法列出会话")
            return 1
        sessions = persistence.list_sessions(limit=20)
        print(f"\n{'='*60}")
        print(f"  会话列表 ({len(sessions)} 个)")
        print(f"{'='*60}")
        for s in sessions:
            print(f"  {s.session_id[:20]}... | turns={s.turn_count} | state={s.state} | health={s.health_score:.1f}")
        print(f"{'='*60}")
        return 0
    
    if args.delete_session:
        if not persistence:
            print("[ERROR] 持久化未启用，无法删除会话")
            return 1
        # 先关闭会话（触发保存），然后删除底层记录
        persistence.close_session(args.delete_session)
        # 底层删除通过 store 的 delete_session
        deleted = persistence._manager._store.delete_session(args.delete_session)
        print(f"[INFO] 会话 {args.delete_session} {'已删除' if deleted else '删除失败'}")
        persistence.shutdown()
        return 0
    
    # 初始化 LLM Provider
    provider = None
    if args.lmstudio:
        config = {
            "type": "openai",
            "name": "lmstudio-cli",
            "api_key": "lm-studio",
            "model": args.model,
            "base_url": args.lmstudio_url,
            "timeout_s": 120,
        }
        try:
            provider = ProviderFactory.from_config(config)
            if not args.quiet:
                print(f"[INFO] LLM Provider 已连接: {provider.name} @ {args.lmstudio_url}")
                print(f"[INFO] 健康检查: {'通过' if provider.health_check() else '失败'}")
        except Exception as e:
            print(f"[WARN] LLM Provider 连接失败: {e}")
            print("[WARN] 将使用纯规则模式（无 LLM 策略补全）")
            provider = None
    
    # 确定会话 ID
    session_id = args.load_session or f"cli-{int(time.time())}"
    
    # 单轮模式
    if args.query:
        if args.pipeline == "v2":
            from core.agent.integration_bridge import AgentPipeline
            pipeline = AgentPipeline(
                session_id=session_id,
                db_path=args.db_path,
                use_persistence=args.persist,
                use_compiler=True,
                use_topic_tree=True,
                use_window=args.window_compress,
                use_observability=args.observe,
                verbose_bridge=not args.quiet,
                conversation_mode=args.conversation_mode,
            )
            result = pipeline.process(args.query, provider=provider, verbose=not args.quiet, conversation_mode=args.conversation_mode)
            pipeline.shutdown()
        else:
            result = run_intent_trace(
                query=args.query,
                provider=provider,
                session_id=session_id,
                verbose=not args.quiet,
                conversation_mode=args.conversation_mode,
                persistence=persistence,
                telemetry=telemetry,
                window_manager=window_manager,
            )
        
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2, default=str)
            if not args.quiet:
                print(f"\n[INFO] 结果已保存到: {args.output}")
        
        # 单轮后清理
        if persistence:
            persistence.close_session(session_id)
            persistence.shutdown()
        if telemetry:
            telemetry.shutdown()
        
        return 0
    
    # 交互模式
    if args.interactive or args.load_session:
        if args.pipeline == "v2":
            # v2: AgentPipeline 模式
            from core.agent.integration_bridge import AgentPipeline
            pipeline = AgentPipeline(
                session_id=session_id,
                db_path=args.db_path,
                use_persistence=args.persist,
                use_compiler=True,
                use_topic_tree=True,
                use_window=args.window_compress,
                use_observability=args.observe,
                verbose_bridge=not args.quiet,
                conversation_mode=args.conversation_mode,
            )
            print("\n" + "="*60)
            print("  意图解析全过程追踪 — 交互模式 (v2 Pipeline)")
            print("  输入 'quit' 或 'exit' 退出")
            print("  输入 'history' 查看历史")
            print("  输入 'save <file>' 保存结果")
            print("  输入 'summary' 查看会话摘要")
            print("  输入 'stats' 查看观测指标")
            print("  输入 'compress' 手动压缩窗口")
            print("="*60 + "\n")
            
            last_results = []
            
            while True:
                try:
                    query = input("\n[USER] > ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\n再见！")
                    break
                
                if not query:
                    continue
                
                if query.lower() in ("quit", "exit", "q"):
                    print("再见！")
                    break
                
                if query.lower() == "history":
                    summary = pipeline.get_session_summary()
                    print(f"\n历史记录 ({summary['turn_index']} 轮):")
                    for i, h in enumerate(pipeline._session_history, 1):
                        print(f"  [{i}] {h['role']}: {h['content'][:50]}...")
                    continue
                
                if query.lower().startswith("save "):
                    filename = query[5:].strip()
                    if last_results:
                        with open(filename, "w", encoding="utf-8") as f:
                            json.dump(last_results[-1], f, ensure_ascii=False, indent=2, default=str)
                        print(f"[INFO] 结果已保存到: {filename}")
                    else:
                        print("[WARN] 没有可保存的结果")
                    continue
                
                if query.lower() == "summary":
                    summary = pipeline.get_session_summary()
                    print(f"\n{'-'*50}")
                    print(f"  会话摘要 (Session ID: {summary['session_id']})")
                    print(f"{'-'*50}")
                    print(f"  轮次: {summary['turn_index']}")
                    print(f"  模块: {summary['modules']}")
                    if 'topic_tree' in summary:
                        print(f"  话题树: {summary['topic_tree']}")
                    if 'window' in summary:
                        print(f"  窗口: {summary['window']}")
                    if 'metrics' in summary:
                        print(f"  指标: {summary['metrics']}")
                    print(f"{'-'*50}")
                    continue
                
                if query.lower() == "stats":
                    if hasattr(pipeline, '_metrics') and pipeline._metrics:
                        m = pipeline._metrics.get_summary()
                        print(f"\n{'-'*50}")
                        print(f"  观测指标")
                        print(f"{'-'*50}")
                        print(f"  总轮次: {m['total_turns']}")
                        print(f"  健康度: {m['health_score']}")
                        print(f"  澄清率: {m['clarification_rate']:.1%}")
                        print(f"  LLM回退率: {m['llm_fallback_rate']:.1%}")
                        print(f"  平均置信度: {m['avg_confidence']:.3f}")
                        print(f"  平均延迟: {m['avg_latency_ms']:.1f}ms")
                        print(f"{'-'*50}")
                    else:
                        print("[WARN] 观测系统未启用")
                    continue
                
                if query.lower() == "compress":
                    if hasattr(pipeline, '_window') and pipeline._window:
                        entries = pipeline._window.build_pcr_input()
                        print(f"[INFO] 当前窗口: {len(entries)} entries")
                        print("[INFO] v2 Pipeline 的窗口压缩由系统自动管理")
                    else:
                        print("[WARN] 窗口系统未启用")
                    continue
                
                # 执行 v2 Pipeline
                result = pipeline.process(query, provider=provider, verbose=not args.quiet, conversation_mode=args.conversation_mode)
                last_results.append(result)
            
            pipeline.shutdown()
            return 0
        
        # v1: 升级后的模式（支持持久化/窗口/观测）
        print("\n" + "="*60)
        print("  意图解析全过程追踪 — 交互模式 (v1)")
        if args.persist:
            print(f"  持久化: {args.db_path}")
        if args.window_compress:
            print("  窗口压缩: 已启用")
        if args.observe:
            print("  观测系统: 已启用")
        print("  输入 'quit' 或 'exit' 退出")
        print("  输入 'history' 查看历史")
        print("  输入 'save <file>' 保存结果")
        print("  输入 'stats' 查看观测指标")
        print("  输入 'compress' 手动压缩窗口")
        print("  输入 'list-sessions' 查看所有会话")
        print("="*60 + "\n")
        
        history = []
        last_results = []
        turn_index = 0
        
        # 如果加载已有会话，从持久化恢复历史到内存
        if args.load_session and persistence:
            session = persistence.get_or_load(args.load_session)
            if session and session.history:
                for turn in session.history:
                    history.append({
                        "role": turn.role,
                        "content": turn.content,
                        "expectation": turn.intent_result.get("expectation", "") if turn.intent_result else "",
                        "timestamp": turn.timestamp,
                    })
                turn_index = session.turn_count
                print(f"[INFO] 已加载会话 {args.load_session}，{turn_index} 轮历史")
        
        while True:
            try:
                query = input("\n[USER] > ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n再见！")
                break
            
            if not query:
                continue
            
            if query.lower() in ("quit", "exit", "q"):
                print("再见！")
                break
            
            if query.lower() == "history":
                print(f"\n历史记录 ({len(history)} 轮):")
                for i, h in enumerate(history, 1):
                    print(f"  [{i}] {h['role']}: {h['content'][:50]}...")
                continue
            
            if query.lower().startswith("save "):
                filename = query[5:].strip()
                if last_results:
                    with open(filename, "w", encoding="utf-8") as f:
                        json.dump(last_results[-1], f, ensure_ascii=False, indent=2, default=str)
                    print(f"[INFO] 结果已保存到: {filename}")
                else:
                    print("[WARN] 没有可保存的结果")
                continue
            
            if query.lower() == "stats":
                if telemetry:
                    health = telemetry.get_global_health()
                    print(f"\n{'-'*50}")
                    print(f"  观测指标")
                    print(f"{'-'*50}")
                    print(f"  会话数: {health.get('sessions', 0)}")
                    print(f"  总轮次: {health.get('total_turns', 0)}")
                    print(f"  平均置信度: {health.get('avg_confidence', 0.0):.3f}")
                    print(f"  平均延迟: {health.get('avg_latency_ms', 0.0):.1f}ms")
                    print(f"{'-'*50}")
                else:
                    print("[WARN] 观测系统未启用（使用 --observe 开启）")
                continue
            
            if query.lower() == "compress":
                if window_manager and history:
                    entries = [HistoryEntry(
                        role=h["role"],
                        content=h["content"],
                        expectation=h.get("expectation", ""),
                        timestamp=h.get("timestamp", 0.0),
                    ) for h in history]
                    compressed, meta = window_manager.compress(entries)
                    print(f"[INFO] 压缩前: {meta.get('tokens_before', 0)} tokens, {len(entries)} entries")
                    print(f"[INFO] 压缩后: {meta.get('tokens_after', 0)} tokens, {len(compressed)} entries")
                    print(f"[INFO] 压缩率: {meta.get('compression_ratio', 1.0):.2%}")
                else:
                    print("[WARN] 窗口压缩未启用（使用 --window-compress 开启）")
                continue
            
            if query.lower() == "list-sessions":
                if persistence:
                    sessions = persistence.list_sessions(limit=20)
                    print(f"\n{'-'*50}")
                    print(f"  会话列表 ({len(sessions)} 个)")
                    print(f"{'-'*50}")
                    for s in sessions:
                        print(f"  {s.session_id[:20]}... | turns={s.turn_count} | state={s.state} | health={s.health_score:.1f}")
                    print(f"{'-'*50}")
                else:
                    print("[WARN] 持久化未启用（使用 --persist 开启）")
                continue
            
            # 执行追踪
            turn_index += 1
            result = run_intent_trace(
                query=query,
                provider=provider,
                history=history,
                session_id=session_id,
                verbose=True,
                conversation_mode=args.conversation_mode,
                persistence=persistence,
                telemetry=telemetry,
                window_manager=window_manager,
            )
            last_results.append(result)
            
            # 更新内存历史（供下一轮使用）
            history.append({
                "role": "user",
                "content": query,
                "expectation": result["summary"]["expectation"],
                "timestamp": time.time(),
            })
            
            # 如果 LLM 返回了 direct_reply，加入历史作为 assistant
            if result["summary"]["execution_status"] == "direct_reply":
                history.append({
                    "role": "assistant",
                    "content": result["summary"].get("message", ""),
                    "expectation": "DIRECT_REPLY",
                    "timestamp": time.time(),
                })
        
        # 优雅关闭
        if persistence:
            persistence.close_session(session_id)
            persistence.shutdown()
        if telemetry:
            telemetry.shutdown()
        
        return 0
    
    # 没有参数，显示帮助
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())

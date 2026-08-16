# -*- coding: utf-8 -*-
"""LLM 自主工具调用循环（function calling, OpenClaw agentLoop 对标）。

2026-08-09: v3 主路径此前是纯文本 chat（LLM 不能返回 tool_use）→
代码执行靠"检测代码块后处理"（权宜之计）。本模块让 LLM 真正成为
决策者: 注入工具 schema → LLM 返回 tool_calls → 权限门执行 →
结果回灌 → 循环直到 LLM 给出最终回复。
"""
from __future__ import annotations

import json
import logging
import time
import urllib.request
from typing import Dict, List, Optional

logger = logging.getLogger("dm.tool_loop")

GATEWAY_URL = "http://127.0.0.1:8080/v1/chat/completions"
DEFAULT_MODEL = "deepseek-v4-flash"
MAX_ROUNDS = 6


def build_tools_schema(allowed_tools: Optional[List[str]] = None) -> List[Dict]:
    """从 ToolRegistry 生成 OpenAI function schema（注入 LLM）。

    allowed_tools: 只注入指定工具名（蓝图节点约束, 2026-08-09 v2 执行层）。
    None = 全部可用工具。
    """
    from core.agent.tools.registry import ToolRegistry
    tools = []
    for t in ToolRegistry.list_all():
        if allowed_tools and t["name"] not in allowed_tools:
            continue
        schema = t.get("schema") or {}
        if isinstance(schema, dict) and "properties" in schema:
            params = schema
        else:
            # 简单 dict 格式 {"param": "desc"} → 转 JSON Schema
            props = {}
            for k, desc in (schema.items() if isinstance(schema, dict) else []):
                props[k] = {"type": "string", "description": str(desc)}
            params = {"type": "object", "properties": props}
        tools.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", "")[:500],
                "parameters": params,
            },
        })
    return tools


def _call_gateway(messages: List[Dict], tools: List[Dict],
                  model: str = DEFAULT_MODEL,
                  timeout_s: float = 90.0) -> Dict:
    body = {
        "model": model,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        # 2026-08-14 修复: deepseek-v4 推理模式吃光预算 → content 空
        # （openai.go 三层开关: 请求级 > 厂商级 > 默认开）。工具调用
        # prompt 复杂必触发推理 → 显式关思考（可靠优先, 需思考再开）。
        "thinking": {"type": "disabled"},
    }
    req = urllib.request.Request(
        GATEWAY_URL, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer dm-client"})
    # 2026-08-15 修复: deepseek-v4-flash 对密集输出任务随机空返回
    # （content="" 且无 tool_calls, claim_eval 08-13 实测）→ 空响应
    # 重试 2 次（与 claim_eval 同模式）。此前生产调用点无重试,
    # 规划类任务（密集输出）偶发空回复根因。
    import time as _time
    last = None
    for _attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                data = json.loads(resp.read())
            choice = (data.get("choices") or [{}])[0]
            msg = choice.get("message", {})
            if (msg.get("content") or "") or (msg.get("tool_calls") or []):
                return data
            last = data
            # 2026-08-16: 预算感知 — 剩余预算少时不再磨蹭重试
            if timeout_s < 30.0:
                return last
            _time.sleep(0.4 * (_attempt + 1))
        except Exception as e:
            last = {"error": str(e)[:200]}
            if timeout_s < 30.0:
                return last
            _time.sleep(0.4 * (_attempt + 1))
    return last or {}


def _execute_tool_call(tc: Dict) -> Dict:
    """执行单个 tool_call（权限门 + ToolRegistry）。"""
    fn = tc.get("function", {})
    name = fn.get("name", "")
    try:
        args = json.loads(fn.get("arguments") or "{}")
    except Exception:
        args = {}
    # 权限门（与 statemachine tool 分支同语义）
    try:
        from core.agent.blueprint.permission_engine import (
            PermissionEngine, has_shell_operators)
        decision = PermissionEngine().evaluate(name, args)
        if not decision.allowed:
            if ("writable root" in decision.reason
                    or "read-only" in decision.reason):
                return {"error": decision.reason}
            if name == "run_shell" or name.startswith("shell:"):
                cmd = str(args.get("command", ""))
                if has_shell_operators(cmd):
                    return {"error": "shell chaining blocked"}
    except Exception:
        pass
    try:
        from core.agent.tools.registry import ToolRegistry
        result = ToolRegistry.execute(name, **args)
        data = result.data if hasattr(result, "data") else result
        return {"ok": True, "tool": name, "result": data}
    except Exception as e:
        return {"ok": False, "tool": name, "error": str(e)[:300]}


def tool_loop(messages: List[Dict], model: str = DEFAULT_MODEL,
              max_rounds: int = MAX_ROUNDS,
              allowed_tools: Optional[List[str]] = None,
              system_inject: Optional[str] = None,
              on_step=None, timeout_s: float = 0.0,
              symbol_interval: int = 0,
              symbol_keep_last: int = 2) -> Dict:
    """function calling 循环。返回 {content, tool_calls, rounds, trace}。

    流程: 注入 tools → LLM → 有 tool_calls → 执行 → 回灌 → 再调
          → 无 tool_calls → 返回最终 content。

    v2 执行层参数（2026-08-09, EXECUTION_LAYER_ARCHITECTURE）:
      allowed_tools — 蓝图节点约束: 只允许该节点范围内的工具
      system_inject — 节点目标/约束注入（合并进首条 system 消息）
      on_step       — Hot 监视钩子: 每步执行后回调 {round, tool, ok, latency_ms}
      timeout_s     — 总执行截止时间（0 = 不限）; 超时提前终止返回 error=timeout
      symbol_interval — 符号注入: 每 N 轮把早期 tool 原文压缩为 Mermaid 状态图
                    （0 = 关闭, 默认; >0 = 开启, 上下文只留符号摘要+最近轮原文）
      symbol_keep_last — 保留最近几轮 tool 原文（LLM 近期细节需要）
    """
    tools = build_tools_schema(allowed_tools)
    msgs = [dict(m) for m in messages]
    if system_inject:
        if msgs and msgs[0].get("role") == "system":
            msgs[0] = dict(msgs[0])
            msgs[0]["content"] = (msgs[0].get("content", "")
                                  + "\n\n" + system_inject)
        else:
            msgs.insert(0, {"role": "system", "content": system_inject})
    deadline = (time.time() + timeout_s) if timeout_s and timeout_s > 0 else 0.0
    executed = []
    trace = []
    for _round in range(max_rounds):
        if deadline and time.time() > deadline:
            return {"content": "", "error": "timeout",
                    "rounds": _round + 1, "tool_calls": executed,
                    "trace": trace}
        try:
            # 2026-08-16 修复: 单次 LLM 调用按剩余预算截断（此前固定
            # 90s × 重试 3 次 → 单轮最长 270s, 与 deadline 检查只在轮间
            # 组合 → 实测 180s+ 卡死）。每轮最多用剩余预算, 总时长受
            # timeout_s 硬约束。
            _remaining = (deadline - time.time()) if deadline else 0.0
            if deadline and _remaining <= 0:
                return {"content": "", "error": "timeout",
                        "rounds": _round + 1, "tool_calls": executed,
                        "trace": trace}
            resp = _call_gateway(
                msgs, tools, model,
                timeout_s=min(90.0, _remaining) if deadline else 90.0)
        except Exception as e:
            return {"content": "", "error": f"gateway: {str(e)[:200]}",
                    "rounds": _round + 1, "tool_calls": executed,
                    "trace": trace}
        choice = (resp.get("choices") or [{}])[0]
        msg = choice.get("message", {})
        finish = choice.get("finish_reason", "")
        if finish == "tool_calls" and msg.get("tool_calls"):
            msgs.append({"role": "assistant",
                         "content": msg.get("content") or "",
                         "tool_calls": msg["tool_calls"]})
            for tc in msg["tool_calls"]:
                _t0 = time.time()
                result = _execute_tool_call(tc)
                step = {
                    "round": _round + 1,
                    "tool": (tc.get("function", {}).get("name", "")),
                    "ok": result.get("ok", False),
                    "latency_ms": round((time.time() - _t0) * 1000, 1),
                    "error": str(result.get("error", ""))[:200],
                    # 2026-08-14（阶段 0, 吸收 O3）: 输入摘要进 step —
                    # doom loop 判定需要"同工具+同输入"（不是失败次数）;
                    # 执行树消费端据此检测死循环。
                    "input": json.dumps(
                        tc.get("function", {}).get("arguments")
                        or "{}", ensure_ascii=False)[:200],
                }
                trace.append(step)
                executed.append({
                    "name": (tc.get("function", {}).get("name", "")),
                    "ok": result.get("ok", False),
                    "summary": str(result.get("result") or
                                   result.get("error", ""))[:120],
                })
                if on_step is not None:
                    try:
                        on_step(dict(step))
                    except Exception:
                        pass
                msgs.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": json.dumps(result, ensure_ascii=False)[:4000],
                })
            # doom loop 止损（2026-08-15, 空回复真因）: 同一工具连续
            # 重复 >=3 次（不限输入 — 实测 dir_list 探索循环输入各异）
            # → 停止工具调用, 追加"直接回答"轮。规划类任务模型陷入
            # dir_list 探索循环（23 次调用）烧完轮数无回答 → 空回复。
            recent_tools = [s.get("tool", "") for s in trace[-3:]]
            if (len(recent_tools) >= 3
                    and len({t for t in recent_tools}) == 1):
                msgs.append({
                    "role": "user",
                    "content": "你已经连续多次执行同一操作但没有进展。"
                               "请停止调用工具，直接基于当前信息回答用户问题。",
                })
                resp = _call_gateway(msgs, [], model)
                msg = (resp.get("choices") or [{}])[0].get("message", {})
                return {
                    "content": msg.get("content", ""),
                    "tool_calls": executed,
                    "rounds": _round + 1,
                    "trace": trace,
                    "doom_loop_stop": True,
                }
            # 符号注入（2026-08-10）: 每 N 轮压缩早期轮次为状态图
            if symbol_interval > 0 and (_round + 1) % symbol_interval == 0:
                try:
                    from core.agent.llm.symbol_injector import (
                        compress_old_tool_rounds)
                    msgs = compress_old_tool_rounds(
                        msgs, trace, keep_last=symbol_keep_last)
                except Exception:
                    pass
            continue
        return {"content": msg.get("content", "") or "",
                "tool_calls": executed, "rounds": _round + 1,
                "trace": trace}
    return {"content": "", "error": f"max rounds ({max_rounds}) exceeded",
            "rounds": max_rounds, "tool_calls": executed, "trace": trace}

# -*- coding: utf-8 -*-
"""AsyncDiagnoser — 元认知异步诊断（A10 大环兑现, 第二大脑）。

设计: ASYNC_DIAGNOSIS_DESIGN_20260816.md
  Governor（小环）管"怎么活下去"（熔断/降级/重试, 秒级算法）;
  AsyncDiagnoser（大环）管"为什么会这样, 怎么不再犯"（分钟级 LLM
  根因分析 + 自调节）。失败信号 → 门槛判定 → 证据收集 → LLM 分析 →
  落决策事件 → 低风险建议自动应用。

触发门槛: breaker OPEN / 预算耗尽重复 / 空返回重复 / 新错误类型。
频率门控: 每 scope 5 分钟（诊断是慢思考, 不每失败都跑）。
"""
from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


GATEWAY_URL = "http://127.0.0.1:8080/v1/chat/completions"
DIAG_PROMPT_TEMPLATE = (
    "你是 DialogMesh 元认知诊断器。基于以下执行链路故障证据, 诊断根因, "
    "输出 JSON（不要其他文字）:\n"
    "{{\"root_cause\": \"根因(中文, ≤80字)\", \"confidence\": 0.0-1.0, "
    "\"evidence_summary\": \"关键证据(≤200字)\", "
    "\"suggestions\": [{{\"action_type\": \"adjust_breaker|adjust_retry|"
    "adjust_budget|note\", \"scope\": \"...\", \"params\": {{}}, "
    "\"reason\": \"...\"}}]}}\n\n"
    "证据: {evidence}"
)


class DiagnosisTask:
    def __init__(self, scope: str, reason: str,
                 evidence: Optional[Dict] = None):
        self.scope = scope
        self.reason = reason
        self.evidence = dict(evidence or {})
        self.ts = time.time()


class AsyncDiagnoser:
    """异步诊断器（队列 + 后台线程; 线程安全）。"""

    def __init__(self, bus: Any = None, min_interval: float = 300.0,
                 llm_enabled: bool = True,
                 gateway_url: str = GATEWAY_URL,
                 auto_attach: bool = True):
        self._bus = bus
        self._gateway_url = gateway_url
        self._min_interval = min_interval
        self._llm_enabled = llm_enabled
        self._auto_attach = auto_attach
        self._engine: Any = None
        self._lock = threading.Lock()
        self._queue: deque = deque()
        self._thread: Optional[threading.Thread] = None
        self._last_trigger: Dict[str, float] = {}
        self._reports: List[Dict[str, Any]] = []
        self._running = True

    def attach_engine(self, engine: Any) -> None:
        """注入 engine 引用（证据收集用执行树/七树）。"""
        self._engine = engine

    # ── 触发（门槛 + 入队）────────────────────────────────────

    def trigger(self, scope: str, reason: str,
                evidence: Optional[Dict] = None) -> bool:
        """门槛判定: 频率门控（每 scope min_interval）; 过则入队。"""
        if self._engine is None and self._auto_attach:
            try:
                # 只 attach"已存在"的 engine —— 不触发 get_engine() 的
                # 惰性初始化（测试环境会因此启动真实 engine 单例, 污染
                # 后续 start_engine; 2026-08-16 实测定位）。
                import core.agent.cli.engine as _ce
                if getattr(_ce, "_engine", None) is not None:
                    self._engine = _ce._engine
            except Exception:
                pass
        now = time.time()
        with self._lock:
            last = self._last_trigger.get(scope, 0.0)
            if now - last < self._min_interval:
                return False
            self._last_trigger[scope] = now
            self._queue.append(DiagnosisTask(scope, reason, evidence))
            self._ensure_thread_locked()
        return True

    def _ensure_thread_locked(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(
                target=self._worker, daemon=True)
            self._thread.start()

    def _worker(self) -> None:
        while self._running:
            try:
                task = self._queue.popleft()
            except IndexError:
                return
            try:
                self._diagnose(task)
            except Exception as e:
                logger.debug("diagnosis failed: %s", e)

    # ── 诊断流程 ─────────────────────────────────────────────

    def _diagnose(self, task: DiagnosisTask) -> None:
        evidence = self._collect(task)
        report = self._analyze(task, evidence)
        self._finalize(task, report)

    def _collect(self, task: DiagnosisTask) -> Dict[str, Any]:
        """证据包: 触发上下文 + governor 熔断 + llm-calls + 执行树。"""
        out: Dict[str, Any] = dict(task.evidence)
        try:
            from core.agent.meta.governor import get_governor
            for b in get_governor().stats().get("breakers", []):
                if b.get("scope") == task.scope:
                    out["breaker"] = b
        except Exception:
            pass
        try:
            from core.agent.llm.call_recorder import llm_call_stats
            out["llm_stats"] = llm_call_stats()
        except Exception:
            pass
        eng = self._engine
        sid = (task.evidence or {}).get("session_id", "")
        if eng is not None and sid and hasattr(eng, "get_agent_tree"):
            try:
                tree = eng.get_agent_tree(sid).execution
                out["exec_tasks"] = [{
                    "node_id": t.node_id,
                    "status": t.status.value,
                    "steps": t.content.get("steps", [])[:8],
                    "result": (t.content.get("result") or {}).get(
                        "status", ""),
                } for t in tree.get_tasks()[-3:]]
            except Exception:
                pass
        return out

    def _analyze(self, task: DiagnosisTask,
                 evidence: Dict[str, Any]) -> Dict[str, Any]:
        """LLM 根因分析; LLM 不可用/解析失败 → 算法降级（统计摘要）。"""
        base = {
            "scope": task.scope, "trigger": task.reason,
            "ts": time.time(), "source": "stats_only",
            "root_cause": "", "confidence": 0.0,
            "evidence_summary": json.dumps(
                evidence, ensure_ascii=False)[:400],
            "suggestions": [],
        }
        if not self._llm_enabled:
            return base
        try:
            prompt = DIAG_PROMPT_TEMPLATE.format(
                evidence=json.dumps(evidence, ensure_ascii=False)[:1500])
            text = self._call_llm(prompt)
            if not text:
                return base
            data = self._parse_llm_json(text)
            if data is None:
                return base
            return {
                "scope": task.scope, "trigger": task.reason,
                "ts": time.time(), "source": "llm",
                "root_cause": str(data.get("root_cause", ""))[:200],
                "confidence": float(data.get("confidence", 0.0)),
                "evidence_summary": str(
                    data.get("evidence_summary", ""))[:300],
                "suggestions": [
                    s for s in (data.get("suggestions") or [])[:5]
                    if isinstance(s, dict)],
            }
        except Exception as e:
            logger.debug("diagnosis llm failed: %s", e)
            return base

    def _call_llm(self, prompt: str) -> str:
        import urllib.request
        body = json.dumps({
            "provider": "deepseek", "model": "deepseek-v4-flash",
            "messages": [{"role": "user", "content": prompt}],
            "thinking": {"type": "disabled"},
            "max_tokens": 600, "temperature": 0.1,
        }).encode("utf-8")
        req = urllib.request.Request(
            self._gateway_url, data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer dm-client"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            d = json.loads(resp.read())
        return d["choices"][0]["message"].get("content") or ""

    @staticmethod
    def _parse_llm_json(text: str) -> Optional[Dict]:
        t = text.strip()
        if t.startswith("```"):
            t = t.strip("`")
            if t.startswith("json"):
                t = t[4:]
            t = t.strip()
        try:
            start = t.find("{")
            end = t.rfind("}")
            if start >= 0 and end > start:
                return json.loads(t[start:end + 1])
        except Exception:
            pass
        return None

    def _finalize(self, task: DiagnosisTask,
                  report: Dict[str, Any]) -> None:
        """落决策事件 + MetaTree + 自调节 apply。"""
        bus = self._bus
        if bus is not None and hasattr(bus, "log"):
            try:
                bus.log(
                    kind="diagnosis_report",
                    dimension=f"governor.{task.scope}",
                    before=None,
                    after={"scope": task.scope,
                           "root_cause": report.get("root_cause", ""),
                           "suggestions": len(report.get("suggestions", []))},
                    reason=report.get("root_cause", "") or task.reason,
                    actor="meta", attribution="diagnosis")
            except Exception as e:
                logger.debug("diagnosis bus log failed: %s", e)
        # MetaTree.record_decision（元认知裁决落树）
        eng = self._engine
        sid = (task.evidence or {}).get("session_id", "")
        if eng is not None and sid and hasattr(eng, "get_agent_tree"):
            try:
                eng.get_agent_tree(sid).meta.record_decision(
                    decision_type=f"diagnosis.{task.scope}",
                    inputs={"trigger": task.reason,
                            "report": report},
                    verdict="diagnosed",
                    reasoning=report.get("root_cause", ""))
            except Exception:
                pass
        # 自调节: 低风险建议自动应用（A16 快反馈后修正）
        applied = []
        for s in report.get("suggestions", []):
            res = self._apply_suggestion(s)
            if res:
                applied.append(res)
        with self._lock:
            self._reports.append(dict(report))
            if len(self._reports) > 100:
                self._reports = self._reports[-100:]

    def _apply_suggestion(self, s: Dict[str, Any]) -> Optional[Dict]:
        action_type = str(s.get("action_type", "note"))
        scope = str(s.get("scope", ""))
        try:
            from core.agent.meta.governor import get_governor
            gov = get_governor()
            if action_type == "adjust_breaker":
                applied = gov.adjust(scope, **(s.get("params") or {}))
                return {"action": "adjust_breaker", "applied": applied}
            if action_type == "adjust_retry":
                kind = str(s.get("scope", ""))
                params = s.get("params") or {}
                applied = gov.adjust_retry(
                    kind or "unknown", int(params.get("max_retries", 1)))
                return {"action": "adjust_retry", "applied": applied}
            if action_type == "adjust_budget":
                # 预算分配由请求级 deadline 控制（固定 150s 总预算）;
                # 当前记录为 note, 供后续按 scope 分预算时消费。
                return {"action": "adjust_budget",
                        "note": "budget adjust recorded, per-scope split P2"}
            return None  # note 类: 仅记录在报告里
        except Exception as e:
            logger.debug("diagnosis apply failed: %s", e)
            return {"action": action_type, "error": str(e)[:100]}

    # ── 白盒 ────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "pending": len(self._queue),
                "last_trigger": {
                    k: round(v, 1) for k, v in self._last_trigger.items()},
                "reports": list(self._reports[-20:]),
            }


_diagnoser: Optional[AsyncDiagnoser] = None


def get_diagnoser(bus: Any = None) -> AsyncDiagnoser:
    global _diagnoser
    if _diagnoser is None:
        _diagnoser = AsyncDiagnoser(bus=bus)
    if bus is not None and _diagnoser._bus is None:
        _diagnoser._bus = bus
    return _diagnoser

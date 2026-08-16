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
import os
import threading
import time
from collections import deque
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
GATEWAY_URL = "http://127.0.0.1:8080/v1/chat/completions"
DIAG_PROMPT_TEMPLATE = (
    "你是 DialogMesh 元认知诊断器。基于以下执行链路故障证据, 诊断根因, "
    "输出 JSON（不要其他文字）:\n"
    "{{\"root_cause\": \"根因(中文, ≤80字)\", \"confidence\": 0.0-1.0, "
    "\"evidence_summary\": \"关键证据(≤200字)\", "
    "\"suggestions\": [{{\"action_type\": \"adjust_breaker|adjust_retry|"
    "adjust_budget|code_fix|note\", \"scope\": \"...\", \"params\": {{}}, "
    "\"reason\": \"...\"}}]}}\n"
    "code_fix 使用规则: 仅当根因是明确代码缺陷; params 必须含 "
    "patch（unified diff, 可被 git apply --check 接受）与 verify_plan"
    "（验证命令列表, 如 [\"pytest core/agent/meta -q\"]）; "
    "不确定时用 note, 不要编造 patch。\n\n"
    "设计约束（被修系统 a 的视角, 诊断先验, 修复须符合设计意图）:\n"
    "{design}\n\n"
    "既往自愈经验（贝叶斯 prior, 相似根因参考）:\n{experience}\n\n"
    "证据: {evidence}"
)


# 验证命令白名单（A21: 自修复验证只允许确定性检查, 防任意命令执行）
ALLOWED_VERIFY_PREFIXES = (
    "pytest", "python -m pytest", "python -m compileall",
    "python -c", "python3 -m pytest",
)


class DiagnosisTask:
    def __init__(self, scope: str, reason: str,
                 evidence: Optional[Dict] = None):
        self.scope = scope
        self.reason = reason
        self.evidence = dict(evidence or {})
        self.ts = time.time()


def _design_constraints() -> str:
    """a 的设计约束摘要（prior）: AGENTS.md 铁律 + 追踪矩阵关键行。

    外部修复（bc）缺的就是这个 —— 元认知持有 a 的设计意图, 诊断/修复
    才有逆推验证的锚点（伪二阶抽象）。
    """
    parts = []
    try:
        agents_md = os.path.join(PROJECT_ROOT, "AGENTS.md")
        if os.path.exists(agents_md):
            with open(agents_md, "r", encoding="utf-8",
                      errors="ignore") as f:
                lines = f.readlines()[:80]
            for line in lines:
                s = line.strip()
                if s.startswith(("1.", "2.", "3.", "4.", "5.")) or "铁律" in s:
                    parts.append(s[:150])
    except Exception:
        pass
    try:
        tb = os.path.join(PROJECT_ROOT,
                          "docs/only/wise/PARADIGM_TRACEABILITY.md")
        if os.path.exists(tb):
            with open(tb, "r", encoding="utf-8", errors="ignore") as f:
                for line in f.readlines():
                    if "| A" in line and "|" in line:
                        parts.append(line.strip()[:160])
    except Exception:
        pass
    return "\n".join(parts[:25]) or "（设计约束不可用）"


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
        self._repairs: List[Dict[str, Any]] = []
        self._repo_root: str = PROJECT_ROOT
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
            # 贝叶斯 prior: 设计约束（a 的视角）+ 既往自愈经验
            design = _design_constraints()
            try:
                from core.agent.meta.experience import search_experience
                past = search_experience(
                    f"{task.scope} {task.reason}", limit=5)
            except Exception:
                past = []
            experience_txt = "\n".join(
                f"- [{e.get('scope')}] {e.get('root_cause', '')} "
                f"→ {e.get('fix_summary', '')} (教训: "
                f"{e.get('design_lesson', '')[:80]})"
                for e in past) or "（无既往经验）"
            prompt = DIAG_PROMPT_TEMPLATE.format(
                design=design[:1500],
                experience=experience_txt[:1200],
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
        self._log_action(
            "diagnosis_report", task.scope, {
                "scope": task.scope,
                "root_cause": report.get("root_cause", ""),
                "suggestions": len(report.get("suggestions", []))},
            reason=report.get("root_cause", "") or task.reason)
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
            if action_type == "code_fix":
                return self._queue_repair(scope, s)
            return None  # note 类: 仅记录在报告里
        except Exception as e:
            logger.debug("diagnosis apply failed: %s", e)
            return {"action": action_type, "error": str(e)[:100]}

    # ── SelfRepair（受控自修复, A21: 默认不自动应用）───────────

    def _log_action(self, kind: str, scope: str,
                    detail: Dict[str, Any], reason: str = "") -> None:
        bus = self._bus
        if bus is not None and hasattr(bus, "log"):
            try:
                bus.log(
                    kind=kind, dimension=f"governor.{scope}",
                    before=None, after=detail, reason=reason,
                    actor="meta", attribution="diagnosis")
            except Exception as e:
                logger.debug("diagnosis bus log failed: %s", e)

    def _queue_repair(self, scope: str,
                      suggestion: Dict[str, Any]) -> Dict[str, Any]:
        """code_fix 建议 → 修复包入待审队列（高风险, 需 gate）。"""
        import uuid as _uuid
        repair = {
            "id": f"fix_{_uuid.uuid4().hex[:8]}",
            "ts": time.time(),
            "source": f"diagnosis.{scope}",
            "files": (suggestion.get("params") or {}).get(
                "files", []),
            "summary": str(suggestion.get("reason", ""))[:300],
            "suggestion": str(
                (suggestion.get("params") or {}).get(
                    "suggestion", ""))[:500],
            "verify_plan": (suggestion.get("params") or {}).get(
                "verify_plan", ["pytest -q --tb=short"]),
            "patch": str((suggestion.get("params") or {}).get(
                "patch", "")),
            "risk": "high",
            "status": "pending",
            "apply_result": None,
        }
        # 验证命令白名单校验（A21）: 不合规直接拒收
        for cmd in repair["verify_plan"]:
            cmd_s = str(cmd).strip()
            if not any(cmd_s.startswith(p) for p in ALLOWED_VERIFY_PREFIXES):
                return {"action": "code_fix", "error": (
                    f"verify_plan command not allowed: {cmd_s[:80]}")}
        if not repair["patch"]:
            return {"action": "code_fix",
                    "error": "patch required for code_fix"}
        with self._lock:
            self._repairs.append(repair)
            if len(self._repairs) > 100:
                self._repairs = self._repairs[-100:]
        logger.info("diagnosis: repair queued %s (source=%s)",
                    repair["id"], repair["source"])
        return {"action": "code_fix", "repair_id": repair["id"],
                "status": "pending"}

    def repairs(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._repairs)

    def apply_repair(self, repair_id: str) -> Dict[str, Any]:
        """审批 gate → 真实应用（git apply + 验证 + 失败自动回滚）。

        A21 安全（2026-08-16 P1）:
          1. patch 必须存在且可被 `git apply --check` 接受
          2. 验证命令受 ALLOWED_VERIFY_PREFIXES 白名单约束
          3. 应用后跑验证计划; 失败 → `git apply -R` 自动回滚
          4. 全部动作记录（bus + apply_result）
        """
        with self._lock:
            for r in self._repairs:
                if r["id"] == repair_id:
                    target = r
                    break
            else:
                return {"error": "repair not found"}
            if target["status"] != "pending":
                return {"error": f"repair already {target['status']}"}
            target["status"] = "verifying"
            patch = target.get("patch", "")
        if not patch:
            with self._lock:
                target["status"] = "pending"
            return {"error": "patch required (code_fix must include diff)"}
        import subprocess
        root = self._repo_root
        # 1. 预检（不落盘）
        chk = subprocess.run(
            ["git", "apply", "--check"], input=patch.encode("utf-8"),
            cwd=root, capture_output=True, timeout=30)
        if chk.returncode != 0:
            with self._lock:
                target["status"] = "pending"
            return {"error": "patch check failed",
                    "detail": chk.stderr.decode("utf-8", "ignore")[:300]}
        # 2. 应用
        ap = subprocess.run(
            ["git", "apply"], input=patch.encode("utf-8"),
            cwd=root, capture_output=True, timeout=30)
        if ap.returncode != 0:
            with self._lock:
                target["status"] = "pending"
            return {"error": "patch apply failed",
                    "detail": ap.stderr.decode("utf-8", "ignore")[:300]}
        target["apply_result"] = {"applied_at": time.time()}
        # 3. 验证（白名单命令）
        verify_out = ""
        passed = True
        for cmd in target.get("verify_plan", []):
            cmd_s = str(cmd).strip()
            if not any(cmd_s.startswith(p)
                       for p in ALLOWED_VERIFY_PREFIXES):
                passed = False
                verify_out += f"$ {cmd_s}\nBLOCKED (not in allowlist)\n"
                break
            try:
                v = subprocess.run(
                    cmd_s, shell=True, cwd=root,
                    capture_output=True, text=True, timeout=300)
                verify_out += f"$ {cmd_s}\n{v.stdout[-400:]}{v.stderr[-200:]}\n"
                if v.returncode != 0:
                    passed = False
                    break
            except Exception as e:
                passed = False
                verify_out += f"$ {cmd_s}\nERROR {e}\n"
                break
        if passed:
            with self._lock:
                target["status"] = "applied"
                target["apply_result"].update(
                    {"passed": True,
                     "verify_output": verify_out[-800:]})
            self._log_action(
                "repair_applied", target["source"], {
                    "repair_id": repair_id,
                    "reason": target["summary"][:120]})
            # 凝练回写经验库（伪二阶抽象: 存"可逆推的教训"而非补丁）:
            # 后验 → 先验, 下次诊断可检索（贝叶斯累积）。
            try:
                from core.agent.meta.experience import record_experience
                record_experience({
                    "scope": target["source"],
                    "root_cause": target["summary"][:200],
                    "fix_summary": target.get("suggestion", "")[:200],
                    "design_lesson": (
                        "scope %s 曾失败并修复: %s — 复用时先核对该 scope "
                        "的设计约束与测试, 修复须可逆推回设计意图。"
                        % (target["source"], target["summary"][:120])),
                    "axioms": ["A11", "A21"],
                    "verify_passed": True,
                    "source": "self_repair",
                })
            except Exception as e:
                logger.debug("experience record failed: %s", e)
            return {"repair_id": repair_id, "status": "applied"}
        # 4. 失败 → 自动回滚
        rollback_ok = False
        try:
            rb = subprocess.run(
                ["git", "apply", "-R"], input=patch.encode("utf-8"),
                cwd=root, capture_output=True, timeout=30)
            rollback_ok = rb.returncode == 0
        except Exception:
            rollback_ok = False
        with self._lock:
            target["status"] = "failed"
            target["apply_result"].update({
                "passed": False, "rollback": rollback_ok,
                "verify_output": verify_out[-800:]})
        self._log_action(
            "repair_failed_rolled_back", target["source"], {
                "repair_id": repair_id, "rollback": rollback_ok,
                "reason": target["summary"][:120]})
        return {"repair_id": repair_id, "status": "failed",
                "rollback": rollback_ok}

    def confirm_repair(self, repair_id: str,
                       passed: bool = True) -> Dict[str, Any]:
        """验证结果回写（passed → applied; failed → 建议回滚）。"""
        with self._lock:
            for r in self._repairs:
                if r["id"] == repair_id:
                    target = r
                    break
            else:
                return {"error": "repair not found"}
            if passed:
                target["status"] = "applied"
                target["apply_result"] = {
                    "ts": time.time(), "passed": True,
                    "note": "verify passed (patch apply is P1)"}
                self._log_action("repair_applied", target["source"], {
                    "repair_id": repair_id,
                    "reason": target["summary"][:120]})
            else:
                target["status"] = "failed"
                target["apply_result"] = {
                    "ts": time.time(), "passed": False,
                    "note": "verify failed — rollback suggested"}
            return {"repair_id": repair_id,
                    "status": target["status"]}

    # ── 白盒 ────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "pending": len(self._queue),
                "repairs": list(self._repairs[-20:]),
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

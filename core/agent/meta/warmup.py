# -*- coding: utf-8 -*-
"""WarmupManager — 启动期有界预热（2026-08-16 P1-②, 根治冷启动卡死）。

背景（实测, PROACTIVE_PROBE 同轮）: API 重启后首个 message 请求要付
冷启动税 —— run_dag 内懒路径首调:
  - DualTrack intent process(): ~13.5s（首调 LLM 分类 + 5 链验证）
  - discourse feed / topic route: ~14.2s（EmbeddingEngine.encode 首调）
  - planner 懒初始化: LLMPlanner 构造
实测衰减: 首请求 43.9s → 第二条 14.6s → 第三条 3.8s（稳态）。

本模块: 启动后**后台线程**按预算把懒路径预热一遍, 副作用收敛到
`__warmup__` 会话; 预算耗尽/步骤超时/失败 → 记录 partial/degraded,
不阻塞启动（A16 快反馈后修正）。预热历史 JSONL 落盘（A17 记录）。
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _default_path() -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))))),
        "data", "warmup_history.jsonl")


class WarmupManager:
    """启动期预热（后台线程; 线程安全; 单例使用）。"""

    def __init__(self, engine: Any = None, budget_s: float = 75.0,
                 path: str = "", prewarmer: Any = None):
        self._engine = engine
        self._budget = max(0.5, float(budget_s))
        self._path = path or _default_path()
        self._prewarmer = prewarmer
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._last: Optional[Dict[str, Any]] = None
        self._history: List[Dict[str, Any]] = []
        self._load_history()

    # ── 生命周期 ─────────────────────────────────────────

    def start(self, engine: Any = None) -> None:
        if engine is not None:
            self._engine = engine
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._running = True
            self._thread = threading.Thread(
                target=self._run_async, daemon=True)
            self._thread.start()

    def _run_async(self) -> None:
        try:
            self.run()
        except Exception as e:
            logger.warning("warmup failed: %s", e)
        finally:
            with self._lock:
                self._running = False

    # ── 预热主流程 ────────────────────────────────────────

    def run(self) -> Dict[str, Any]:
        """按预算跑一遍懒路径（同步, 供测试/手动 /v6/warmup/run 用）。"""
        engine = self._engine
        if engine is None:
            return self._record({"steps": [], "status": "skipped",
                                 "reason": "no engine"})
        deadline = time.time() + self._budget
        # 步内自带硬超时（LLM 调用 provider 60s/10s; embedding 有限 CPU）,
        # 同步执行 —— 不用子线程超时（超时线程残留会占锁, 实测级联卡死）。
        # 首步 = 共享 BGE 预热（幂等, 内部有锁/状态机; 与引擎 bootstrap 的
        # prewarm_models(blocking=False) 串行化, 不再各自加载竞争）。
        steps = [
            ("prewarm", lambda: self._warm_models(engine)),
            ("pcr", lambda: self._warm_pcr(engine)),
            ("intent", lambda: self._warm_intent(engine)),
            ("discourse", lambda: self._warm_discourse(engine)),
            ("topic", lambda: self._warm_topic(engine)),
            ("planner", lambda: self._warm_planner(engine)),
        ]
        results: List[Dict[str, Any]] = []
        for name, fn in steps:
            if time.time() > deadline:
                results.append({"step": name, "status": "skipped",
                                "reason": "budget_exhausted"})
                break
            t0 = time.time()
            err = ""
            try:
                fn()
                st = "ok"
            except Exception as e:  # noqa: BLE001 — 预热步骤失败不致命
                st = "error"
                err = str(e)[:200]
            rec = {"step": name, "status": st,
                   "ms": round((time.time() - t0) * 1000, 1)}
            if st == "error":
                rec["error"] = err
            results.append(rec)
        has_error = any(r["status"] == "error" for r in results)
        has_partial = any(r["status"] == "skipped" for r in results)
        status = "ok"
        if has_error:
            status = "degraded"
        elif has_partial:
            status = "partial"
        rec = {"ts": time.time(), "budget_s": self._budget,
               "status": status, "steps": results}
        return self._record(rec)

    # ── 各懒路径 ─────────────────────────────────────────

    def _warm_models(self, engine: Any) -> None:
        """共享 BGE / ModelService / PCR mood vectors 就绪（阻塞到 warm）。"""
        if self._prewarmer is not None:
            self._prewarmer()
            return
        from core.infrastructure.model_service import prewarm_models
        prewarm_models(blocking=True)

    @staticmethod
    def _warm_pcr(engine: Any) -> None:
        """Phase 1 认知分析的 pcr.route 首调（embedding/结构特征/模型探测）。

        与 v3_session_api Phase 1 同路径; 首调实测 14.7s（向量轴冷加载）。
        """
        pcr = getattr(engine, "_pcr_router", None)
        if pcr is None or not hasattr(pcr, "route"):
            return
        r = pcr.route("预热")
        engine._last_pcr = r

    @staticmethod
    def _warm_intent(engine: Any) -> None:
        parser = getattr(engine, "_intent_parser", None)
        if parser is not None and hasattr(parser, "process"):
            # 与 run_dag INTENT handler 同路径; 首调 LLM 分类 + 5 链验证。
            # 副作用: 更新 engine._last_*（无害）; 不写持久会话。
            parser.process("预热")

    @staticmethod
    def _warm_discourse(engine: Any) -> None:
        dt = getattr(engine, "_discourse_tree", None)
        if dt is not None and hasattr(dt, "feed"):
            # 与 DISCOURSE handler 同路径; EmbeddingEngine.encode 首调
            # 是主要冷启动税。副作用收敛到 __warmup__ 会话。
            try:
                dt.feed("预热", "__warmup__")
            except TypeError:
                dt.feed("预热", "__warmup__", history=None)

    @staticmethod
    def _warm_topic(engine: Any) -> None:
        tt = getattr(engine, "_topic_tree", None)
        if tt is not None and hasattr(tt, "route"):
            tt.route(query="预热", turn_index=0,
                     extracted_entities=[], query_intent="general")

    @staticmethod
    def _warm_planner(engine: Any) -> None:
        if getattr(engine, "_planner", None) is not None:
            return
        try:
            from core.agent.planner.llm_planner import LLMPlanner
            engine._planner = LLMPlanner(
                llm=getattr(engine, "_llm_provider", None))
        except Exception as e:
            logger.debug("planner warmup failed: %s", e)

    # ── 记录（A17: 预热历史不删, JSONL 落盘）────────────────

    def _record(self, rec: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            self._history.append(rec)
            if len(self._history) > 200:
                self._history = self._history[-200:]
            self._last = rec
            try:
                os.makedirs(os.path.dirname(self._path), exist_ok=True)
                with open(self._path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            except Exception as e:
                logger.debug("warmup history persist failed: %s", e)
        return rec

    def _load_history(self) -> None:
        try:
            if not os.path.exists(self._path):
                return
            with open(self._path, "r", encoding="utf-8") as f:
                for line in f.readlines()[-200:]:
                    line = line.strip()
                    if line:
                        try:
                            self._history.append(json.loads(line))
                        except Exception:
                            pass
            if self._history:
                self._last = self._history[-1]
        except Exception as e:
            logger.debug("warmup history load failed: %s", e)

    # ── 白盒 ─────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "running": bool(self._thread and self._thread.is_alive()),
                "budget_s": self._budget,
                "last": self._last,
                "runs": len(self._history),
                "history": list(self._history[-10:]),
            }


_warmup: Optional[WarmupManager] = None


def get_warmup(engine: Any = None) -> WarmupManager:
    global _warmup
    if _warmup is None:
        budget = float(os.environ.get("DM_WARMUP_BUDGET", "75"))
        _warmup = WarmupManager(engine=engine, budget_s=budget)
    elif engine is not None and _warmup._engine is None:
        _warmup._engine = engine
    return _warmup

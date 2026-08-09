# -*- coding: utf-8 -*-
"""AssociationService — 关联链独立服务（蓝图 §7.3 / DESIGN_HYBRID §四/§六）。

形态（防广播风暴）:
  - M→1 定向通道: 生产者调用 ``enqueue()`` 定向投递，服务持有专用有界队列，
    唯一消费者是后台消费线程 —— **不做全广播订阅**。
  - EventLog (SQLite append-only, 幂等): 每个事件先写 EventLog（一次，不广播），
    服务按 last_seq 增量拉取（replay_unconsumed），崩溃从 last_seq 重放。
  - 一致性: 写入单线程强一致 / 读取单调不重不丢 / 崩溃重放 / 反压丢最旧+计数
    （EventLog 完整 → 重放可恢复）。
  - 同步拉取: ``pull()`` 直接调用漏斗（C/S 直连，热路径用）；异步通知走队列。

触发: topic 切换 >= 2 或 behavior 计数 >= 10 → 漏斗 run → association_discovered。
产出: ASSOCIATION_DISCOVERED（含 l1/l3/l4/l5 摘要）→ 定向输出（回调 + EventLog），
     不向全局广播。
"""
from __future__ import annotations

import logging
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# 关联链关心的 6 链主题（PCR/Router/Intent/Discourse/Topic/Behavior）+ 回执
INTERESTED_KINDS = frozenset({
    "pcr_computed", "route_generated", "intent_parsed", "reply_generated",
    "discourse_updated", "topic_switched", "behavior_recorded",
    "message_received", "association_discovered",
})

# 队列唤醒信号（DESIGN_HYBRID §四：EventBus 通知有新事件 → 增量追赶 from last_seq）。
# 队列只承载"有新事件"的唤醒，不承载事件数据 —— EventLog 是唯一事实源，天然去重。
_WAKE = object()


@dataclass
class AssociationState:
    """本地投射（纯函数 evolve，可重放）。"""
    current_intent: str = "UNKNOWN"
    topic_shift_count: int = 0
    behavior_count: int = 0
    cohesion: float = 1.0
    last_discovery: Dict[str, Any] = field(default_factory=dict)
    discoveries: int = 0


class AssociationService:
    """关联链独立服务：M→1 定向通道 + EventLog Event Sourcing。

    生产者（engine `_publish` / blueprint executor）调用 :meth:`enqueue` 定向投递；
    服务在 :meth:`start` 后由后台线程消费，事件先落 EventLog（幂等）再 evolve 状态，
    触发阈值后跑漏斗并定向输出 ``association_discovered``。
    """

    DEFAULT_QUEUE_SIZE = 256
    DEFAULT_CATCHUP_INTERVAL = 2.0  # 秒：即使唤醒信号被丢弃，也周期性从 EventLog 追赶

    def __init__(
        self,
        event_log: Any = None,
        bus: Any = None,
        llm_provider: Any = None,
        db_path: str = "data/event_log.db",
        queue_size: int = DEFAULT_QUEUE_SIZE,
    ):
        self._log = event_log
        self._log_owned = event_log is None
        self._db_path = db_path or "data/event_log.db"
        self._bus = bus
        self._llm_provider = llm_provider
        self._queue: "queue.Queue" = queue.Queue(maxsize=queue_size)
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._last_seq = 0
        self._state = AssociationState()
        self._funnel = None  # 懒加载（消费线程首事件时创建，避免 import 环）
        self._discover_callbacks: List[Callable[[dict], None]] = []
        self._stats = {
            "enqueued": 0, "consumed": 0, "dropped": 0,
            "replayed": 0, "discoveries": 0, "errors": 0,
        }
        self._lock = threading.Lock()
        self._log_lock = threading.Lock()  # EventLog 写入单线程强一致（§六）

    # ────────────────────────────────────────────── #
    # 生命周期
    # ────────────────────────────────────────────── #

    def start(self) -> bool:
        """打开 EventLog + 崩溃重放 + 启动消费线程。"""
        with self._lock:
            if self._running:
                return True
            self._running = True
        try:
            self._ensure_log()
            self._replay_unconsumed()
        except Exception as e:
            logger.warning("AssociationService start (log/replay) failed: %s", e)
        self._thread = threading.Thread(
            target=self._consume_loop, name="assoc-service", daemon=True,
        )
        self._thread.start()
        logger.info("AssociationService started (queue=%d)", self._queue.maxsize)
        return True

    def stop(self) -> None:
        """停止消费线程并关闭自持 EventLog。"""
        with self._lock:
            self._running = False
        try:
            self._queue.put_nowait(_WAKE)  # 唤醒消费线程检查 _running 退出
        except queue.Full:
            pass
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None
        if self._log_owned and self._log is not None:
            try:
                self._log.close()
            except Exception as e:
                logger.debug("AssociationService close log: %s", e)
        logger.info("AssociationService stopped")

    @property
    def running(self) -> bool:
        return self._running

    # ────────────────────────────────────────────── #
    # 生产者 API — M→1 定向投递（不广播）
    # ────────────────────────────────────────────── #

    def enqueue(self, kind: str, payload: Optional[Dict[str, Any]] = None,
                trace_id: str = "") -> bool:
        """定向投递一个事件到关联链服务。

        只接受 :data:`INTERESTED_KINDS` 内的主题；事件先写 EventLog（幂等，
        崩溃可重放），再投唤醒信号。EventLog 是唯一事实源 —— 消费线程被唤醒
        后统一从 EventLog 增量拉取（last_seq 语义），单调不重不丢。
        唤醒信号队列满 → 丢弃 + 计数（周期追赶兜底，事件不丢）。
        """
        if kind not in INTERESTED_KINDS:
            logger.debug("AssociationService: ignore kind=%s (not interested)", kind)
            return False
        eid = self._persist(kind, dict(payload or {}), trace_id)
        if not eid:
            self._stats["errors"] += 1
            return False
        self._stats["enqueued"] += 1
        try:
            self._queue.put_nowait(_WAKE)
            return True
        except queue.Full:
            # 反压: 唤醒信号丢弃 + 计数（事件已在 EventLog，周期追赶兜底）
            self._stats["dropped"] += 1
            return True

    def pull(self, text: str = "", pcr_zone: str = "MIXED") -> Dict[str, Any]:
        """C/S 同步拉取: 直接跑漏斗（热路径直连，不进队列）。"""
        funnel = self._get_funnel()
        if funnel is None:
            return {"error": "association funnel unavailable"}
        return funnel.run_layers(text=text, pcr_zone=pcr_zone)

    def on_discover(self, callback: Callable[[dict], None]) -> None:
        """注册定向输出回调（不广播，只发给关心的消费者）。"""
        self._discover_callbacks.append(callback)

    # ────────────────────────────────────────────── #
    # 白盒
    # ────────────────────────────────────────────── #

    def stats(self) -> Dict[str, Any]:
        return {
            **dict(self._stats),
            "queue_depth": self._queue.qsize(),
            "queue_max": self._queue.maxsize,
            "last_seq": self._last_seq,
            "running": self._running,
            "state": {
                "current_intent": self._state.current_intent,
                "topic_shift_count": self._state.topic_shift_count,
                "behavior_count": self._state.behavior_count,
                "cohesion": self._state.cohesion,
                "discoveries": self._state.discoveries,
            },
        }

    def state_snapshot(self) -> AssociationState:
        return AssociationState(**self._state.__dict__)

    # ────────────────────────────────────────────── #
    # 内部: EventLog 持久化 + 重放
    # ────────────────────────────────────────────── #

    def _ensure_log(self) -> None:
        if self._log is None:
            from core.agent.api.api_event_log import EventLog
            self._log = EventLog(db_path=self._db_path)
            self._log_owned = True
        if getattr(self._log, "_conn", None) is None and hasattr(self._log, "open"):
            self._log.open()

    def _persist(self, kind: str, payload: dict, trace_id: str = "") -> str:
        """写 EventLog（幂等）。返回 event_id；失败返回 ''。"""
        eid = f"{kind}:{uuid.uuid4().hex[:12]}"
        with self._log_lock:
            try:
                self._ensure_log()
                if self._log is None:
                    return ""
                self._log.put_event(
                    event_id=eid, kind=kind,
                    payload=payload, trace_id=trace_id,
                )
                return eid
            except Exception as e:
                logger.debug("AssociationService persist failed: %s", e)
                return ""

    def _ack(self, event_id: str) -> None:
        with self._log_lock:
            try:
                if self._log is not None:
                    self._log.ack_event(event_id)
            except Exception as e:
                logger.debug("AssociationService ack failed: %s", e)

    def _replay_unconsumed(self) -> None:
        """从 EventLog 增量拉取未 ack 事件并处理（last_seq 语义，唯一消费路径）。

        处理成功立即 ack → 下轮不重；崩溃未 ack → 重启重放。
        失败事件不 ack → 下轮重试（不丢）。读取单调不重不丢（DESIGN_HYBRID §六）。
        """
        if self._log is None:
            return
        try:
            while True:
                events = self._log.replay_unconsumed(limit=500)
                if not events:
                    break
                progressed = False
                for evt in events:
                    kind = evt.get("kind", "")
                    if kind not in INTERESTED_KINDS:
                        continue
                    try:
                        self._process_event({
                            "kind": kind,
                            "payload": evt.get("payload", {}),
                            "trace_id": evt.get("trace_id", ""),
                        })
                        self._ack(evt.get("event_id", ""))
                        self._last_seq += 1
                        self._stats["replayed"] += 1
                        self._stats["consumed"] += 1
                        progressed = True
                    except Exception as e:
                        self._stats["errors"] += 1
                        logger.error("AssociationService replay error: %s", e)
                        # 不 ack → 下轮重试（不丢）
                if not progressed:
                    break
        except Exception as e:
            logger.debug("AssociationService replay failed: %s", e)

    # ────────────────────────────────────────────── #
    # 内部: 消费循环（唯一消费者）
    # ────────────────────────────────────────────── #

    def _consume_loop(self) -> None:
        last_catchup = 0.0
        while self._running:
            try:
                item = self._queue.get(timeout=0.5)
            except queue.Empty:
                item = None
            now = time.time()
            # 唯一消费路径: 被唤醒或周期兜底 → 从 EventLog 增量追赶（无重复）。
            if item is not None or now - last_catchup >= self.DEFAULT_CATCHUP_INTERVAL:
                self._replay_unconsumed()
                last_catchup = now
        # 退出前最后追赶一次（排空）
        self._replay_unconsumed()

    def _get_funnel(self):
        if self._funnel is None:
            try:
                from core.agent.association.association_funnel import AssociationFunnel
                self._funnel = AssociationFunnel(llm_provider=self._llm_provider)
            except Exception as e:
                logger.debug("AssociationFunnel unavailable: %s", e)
        return self._funnel

    def _process_event(self, event: dict) -> None:
        """evolve 纯函数 + 喂漏斗 + 触发阈值。"""
        kind = event.get("kind", "")
        self._state = self._evolve(self._state, event)
        funnel = self._get_funnel()
        if funnel is not None:
            try:
                funnel.ingest_event(event)
            except Exception as e:
                logger.debug("AssociationService funnel ingest failed: %s", e)
        if self._should_discover():
            self._discover_and_publish(funnel)

    def _evolve(self, state: AssociationState, event: dict) -> AssociationState:
        """纯函数: 事件 → 新状态（可重放、可测试）。"""
        kind = event.get("kind", "")
        payload = event.get("payload", {})
        new_state = AssociationState(**state.__dict__)
        if kind == "intent_parsed":
            new_state.current_intent = payload.get("category", "UNKNOWN")
        elif kind == "topic_switched":
            new_state.topic_shift_count += 1
        elif kind == "discourse_updated":
            new_state.cohesion = payload.get("cohesion", 1.0)
        elif kind == "behavior_recorded":
            new_state.behavior_count += 1
        return new_state

    def _should_discover(self) -> bool:
        return (self._state.topic_shift_count >= 2
                or self._state.behavior_count >= 10)

    def _discover_and_publish(self, funnel) -> Dict[str, Any]:
        """跑漏斗并定向输出 association_discovered（回调 + EventLog，不广播）。"""
        result = {}
        if funnel is not None:
            try:
                result = funnel.run()
            except Exception as e:
                logger.debug("AssociationService funnel run failed: %s", e)
        payload = {
            "intent": self._state.current_intent,
            "behavior_count": self._state.behavior_count,
            "funnel": {
                "l1_relations": len(result.get("layer1_relations", [])),
                "l3_consensus": result.get("layer3_consensus", []),
                "l4_chains": result.get("layer4_chains", []),
                "l5_causal": result.get("layer5_causal", {}),
                "stats": result.get("stats", {}),
            },
            "ts": time.time(),
        }
        event = {"kind": "association_discovered", "payload": payload}
        # 定向输出: 只发给注册的消费者（不广播）
        for cb in list(self._discover_callbacks):
            try:
                cb(event)
            except Exception as e:
                logger.debug("AssociationService discover callback failed: %s", e)
        # 产出是输出快照（溯源用），不是输入事件 —— 写 EventLog 后立即 ack，
        # 避免回流消费循环被重复处理（监控曾暴露 consumed>enqueued）。
        out_eid = self._persist(event["kind"], event["payload"])
        if out_eid:
            self._ack(out_eid)
        self._state.last_discovery = payload
        self._state.discoveries += 1
        self._stats["discoveries"] += 1
        # 重置触发计数（每轮发现后重新累积）
        self._state.topic_shift_count = 0
        self._state.behavior_count = 0
        logger.info("AssociationService discovered: intent=%s discoveries=%d",
                    self._state.current_intent, self._state.discoveries)
        return event

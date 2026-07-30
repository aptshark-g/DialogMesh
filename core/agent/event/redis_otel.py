"""Week 4: Redis + OTel integration (DESIGN_DISTRIBUTED §4).

RedisHotStore: shared cache for multi-worker (replaces per-engine HotStore)
RedisRateLimiter: global rate limiting (replaces per-engine TokenBucket)
OTelExporter: export traces to Jaeger/Prometheus

All optional — graceful fallback when Redis/OTel unavailable."""
import time, json, logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
#  Redis backends (optional — pip install redis)
# ═══════════════════════════════════════════════════════════

class RedisBridge:
    """Shared Redis connection pool for HotStore + RateLimiter."""

    def __init__(self, url: str = "redis://localhost:6379/0"):
        self._url = url
        self._client = None
        self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def connect(self, timeout: float = 2.0) -> bool:
        try:
            import redis
            self._client = redis.from_url(self._url, socket_connect_timeout=timeout, decode_responses=True)
            self._client.ping()
            self._available = True
            logger.info("Redis connected: %s", self._url)
            return True
        except Exception as e:
            logger.debug("Redis unavailable (%s), using memory fallback", e)
            self._available = False
            return False

    def get(self, key: str) -> Optional[str]:
        if not self._available: return None
        try: return self._client.get(key)
        except: return None

    def set(self, key: str, value: str, ttl: int = 300) -> bool:
        if not self._available: return False
        try:
            self._client.setex(key, ttl, value)
            return True
        except: return False

    def incr(self, key: str, amount: int = 1) -> int:
        if not self._available: return 0
        try:
            val = self._client.incrby(key, amount)
            # Set TTL on first increment
            if val == amount:
                self._client.expire(key, 60)
            return val
        except: return 0

    def ttl(self, key: str) -> int:
        if not self._available: return -1
        try:
            return self._client.ttl(key)
        except: return -1

    def delete(self, key: str) -> None:
        if self._available:
            try: self._client.delete(key)
            except: pass

    def close(self):
        if self._client:
            try: self._client.close()
            except: pass
            self._available = False


class RedisHotStore:
    """Shared HotStore backed by Redis. Falls back to memory dict."""

    def __init__(self, redis_bridge: RedisBridge = None, prefix: str = "hot:"):
        self._redis = redis_bridge
        self._prefix = prefix
        self._memory: Dict[str, Any] = {}  # fallback

    def get(self, key: str, default: Any = None) -> Any:
        full_key = f"{self._prefix}{key}"
        if self._redis and self._redis.available:
            raw = self._redis.get(full_key)
            if raw:
                try: return json.loads(raw)
                except: return raw
        return self._memory.get(key, default)

    def set(self, key: str, value: Any, ttl: int = 300):
        full_key = f"{self._prefix}{key}"
        self._memory[key] = value  # always cache locally
        if self._redis and self._redis.available:
            try:
                self._redis.set(full_key, json.dumps(value, default=str), ttl)
            except: pass

    def delete(self, key: str):
        full_key = f"{self._prefix}{key}"
        self._memory.pop(key, None)
        if self._redis and self._redis.available:
            self._redis.delete(full_key)


class RedisRateLimiter:
    """Distributed rate limiter using Redis INCR + TTL."""

    def __init__(self, redis_bridge: RedisBridge = None, prefix: str = "rl:"):
        self._redis = redis_bridge
        self._prefix = prefix
        self._memory: Dict[str, dict] = {}  # fallback

    def check(self, stage: str, limit_per_minute: int = 60) -> bool:
        """Returns True if allowed, False if rate limited."""
        key = f"{self._prefix}{stage}"
        if self._redis and self._redis.available:
            count = self._redis.incr(key)
            return count <= limit_per_minute
        # Memory fallback: simple counter with TTL
        now = time.time()
        entry = self._memory.get(stage, {"count": 0, "reset_at": now + 60})
        if now > entry["reset_at"]:
            entry = {"count": 1, "reset_at": now + 60}
        else:
            entry["count"] += 1
        self._memory[stage] = entry
        return entry["count"] <= limit_per_minute

    def stats(self) -> dict:
        return {stage: e["count"] for stage, e in self._memory.items()}


# ═══════════════════════════════════════════════════════════
#  OpenTelemetry exporter (optional — pip install opentelemetry)
# ═══════════════════════════════════════════════════════════

class OTelExporterV2:
    """Export PipelineTracer spans to Jaeger/Prometheus via OTel SDK."""

    def __init__(self, service_name: str = "dialogmesh", endpoint: str = None):
        self._available = False
        self._tracer_provider = None
        try:
            from opentelemetry import trace
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            self._tracer_provider = TracerProvider()
            exporter = OTLPSpanExporter(endpoint=endpoint or "http://localhost:4317")
            self._tracer_provider.add_span_processor(BatchSpanProcessor(exporter))
            trace.set_tracer_provider(self._tracer_provider)
            self._tracer = trace.get_tracer(service_name)
            self._available = True
            logger.info("OTel exporter ready: %s", endpoint or "localhost:4317")
        except Exception as e:
            logger.debug("OTel unavailable (%s), using local tracer only", e)

    @property
    def available(self) -> bool:
        return self._available

    def export_trace(self, trace_id: str, subsystem: str, latency_ms: float, success: bool, metadata: dict = None):
        if not self._available: return
        try:
            from opentelemetry import trace as otel_trace
            with self._tracer.start_as_current_span(f"{subsystem}.process") as span:
                span.set_attribute("trace_id", trace_id)
                span.set_attribute("subsystem", subsystem)
                span.set_attribute("latency_ms", latency_ms)
                span.set_attribute("success", success)
                if metadata:
                    for k, v in metadata.items():
                        span.set_attribute(k, str(v)[:100])
        except Exception:
            pass


def wire_redis_otel(engine, redis_url: str = "redis://localhost:6379/0", otel_endpoint: str = None) -> dict:
    """Wire Redis + OTel into engine. Returns status dict."""
    status = {"redis": "unavailable", "otel": "unavailable"}

    # Redis
    try:
        redis_bridge = RedisBridge(redis_url)
        if redis_bridge.connect(timeout=1.0):
            engine._redis = redis_bridge
            engine._redis_hot = RedisHotStore(redis_bridge)
            engine._redis_rl = RedisRateLimiter(redis_bridge)
            status["redis"] = "active"
    except Exception as e:
        logger.debug("Redis wiring skipped: %s", e)

    # OTel
    try:
        otel = OTelExporterV2(endpoint=otel_endpoint)
        if otel.available:
            engine._otel = otel
            status["otel"] = "active"
    except Exception as e:
        logger.debug("OTel wiring skipped: %s", e)

    return status

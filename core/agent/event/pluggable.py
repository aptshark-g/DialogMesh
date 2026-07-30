"""Pluggable backends — NATS, ChromaDB, OpenTelemetry integration.

All optional: if dependencies aren't installed, gracefully fall back.
"""
import logging, json, os
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
#  NATS EventBus bridge (optional)
# ═══════════════════════════════════════════════════════════

class NATSBridge:
    """NATS pub/sub bridge. Requires `pip install nats-py`.

    Falls back to in-memory EventBus if NATS server is unavailable.
    """

    def __init__(self, server_url: str = "nats://localhost:4222"):
        self._nc = None
        self._js = None
        self._available = False
        self._server_url = server_url

        try:
            import nats
            from nats.aio.client import Client as NATS
            self._nats = NATS
            self._available = True
            logger.info("NATS library loaded, server=%s", server_url)
        except ImportError:
            logger.info("NATS not installed (pip install nats-py). Using in-memory EventBus.")

    @property
    def available(self) -> bool:
        return self._available

    async def connect(self) -> bool:
        if not self._available:
            return False
        try:
            self._nc = await self._nats().connect(self._server_url)
            logger.info("NATS connected: %s", self._server_url)
            return True
        except Exception as e:
            logger.debug("NATS connect failed: %s", e)
            self._available = False
            return False

    async def publish(self, subject: str, payload: dict) -> bool:
        if not self._nc:
            return False
        try:
            await self._nc.publish(subject, json.dumps(payload).encode())
            return True
        except Exception:
            return False

    async def subscribe(self, subject: str, callback) -> Optional[str]:
        if not self._nc:
            return None
        try:
            sub = await self._nc.subscribe(subject, cb=callback)
            return str(sub)
        except Exception:
            return None

    async def close(self):
        if self._nc:
            await self._nc.drain()


# ═══════════════════════════════════════════════════════════
#  ChromaDB vector store (optional)
# ═══════════════════════════════════════════════════════════

class ChromaBridge:
    """ChromaDB vector store. Requires `pip install chromadb`.

    Falls back to JSON file storage if unavailable.
    """

    def __init__(self, persist_dir: str = None):
        self._client = None
        self._collection = None
        self._available = False

        if persist_dir is None:
            from pathlib import Path
            persist_dir = str(Path(__file__).resolve().parent.parent.parent.parent / "data" / "chroma")

        try:
            import chromadb
            self._client = chromadb.PersistentClient(path=persist_dir)
            self._collection = self._client.get_or_create_collection("semantic_objects")
            self._available = True
            logger.info("ChromaDB connected: %s objects", self._collection.count())
        except ImportError:
            logger.info("ChromaDB not installed (pip install chromadb). Using JSON storage.")
        except Exception as e:
            logger.debug("ChromaDB init failed: %s", e)

    @property
    def available(self) -> bool:
        return self._available

    def add(self, obj_id: str, text: str, metadata: dict = None) -> bool:
        if not self._collection:
            return False
        try:
            self._collection.add(
                ids=[obj_id],
                documents=[text],
                metadatas=[metadata or {}],
            )
            return True
        except Exception:
            return False

    def search(self, query: str, limit: int = 5) -> list:
        if not self._collection:
            return []
        try:
            results = self._collection.query(query_texts=[query], n_results=limit)
            return results.get("documents", [[]])[0] if results else []
        except Exception:
            return []

    def count(self) -> int:
        return self._collection.count() if self._collection else 0

    def close(self):
        """Close ChromaDB client to release file locks."""
        if self._client:
            try:
                self._client.reset()
            except Exception:
                pass
            self._client = None
            self._collection = None


# ═══════════════════════════════════════════════════════════
#  OpenTelemetry bridge (optional)
# ═══════════════════════════════════════════════════════════

class OTelBridge:
    """OpenTelemetry tracer. Requires `pip install opentelemetry-api opentelemetry-sdk`.

    Bridges PipelineTracer records to OTel spans for standard observability tools.
    """

    def __init__(self, service_name: str = "dialogmesh"):
        self._tracer = None
        self._available = False

        try:
            from opentelemetry import trace
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter

            provider = TracerProvider()
            processor = SimpleSpanProcessor(ConsoleSpanExporter())
            provider.add_span_processor(processor)
            trace.set_tracer_provider(provider)

            self._tracer = trace.get_tracer(service_name)
            self._available = True
            logger.info("OpenTelemetry ready: %s", service_name)
        except ImportError:
            logger.info("OpenTelemetry not installed (pip install opentelemetry-api opentelemetry-sdk).")
        except Exception as e:
            logger.debug("OTel init failed: %s", e)

    @property
    def available(self) -> bool:
        return self._available

    def start_span(self, name: str, attributes: dict = None) -> Optional[Any]:
        if not self._tracer:
            return None
        try:
            span = self._tracer.start_span(name)
            if attributes:
                span.set_attributes(attributes)
            return span
        except Exception:
            return None

    def record_trace(self, name: str, latency_ms: float, success: bool, metadata: dict = None):
        if not self._tracer:
            return
        try:
            with self._tracer.start_as_current_span(name) as span:
                span.set_attribute("latency_ms", latency_ms)
                span.set_attribute("success", success)
                if metadata:
                    for k, v in metadata.items():
                        span.set_attribute(k, str(v)[:100])
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════
#  PostgreSQL bridge (optional — Week 3)
# ═══════════════════════════════════════════════════════════

class PgBridge:
    """PostgreSQL backend for WarmStore + ColdStore.
    Falls back gracefully if psycopg2 not installed or server unavailable."""

    def __init__(self, dsn: str = None):
        self._dsn = dsn or "postgresql://localhost:5432/dialogmesh"
        self._conn = None
        self._available = False
        self._init_tried = False

    @property
    def available(self) -> bool:
        if not self._init_tried:
            self._try_connect()
        return self._available

    def _try_connect(self):
        self._init_tried = True
        try:
            import psycopg2
            self._conn = psycopg2.connect(self._dsn, connect_timeout=3)
            self._conn.autocommit = True
            self._available = True
            self._ensure_tables()
        except Exception:
            self._available = False

    def _ensure_tables(self):
        if not self._conn: return
        cur = self._conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS warm_events (
                id SERIAL PRIMARY KEY,
                event_id TEXT UNIQUE, kind TEXT, payload JSONB,
                trace_id TEXT, created_at TIMESTAMPTZ DEFAULT NOW(),
                consumed BOOLEAN DEFAULT FALSE
            );
            CREATE TABLE IF NOT EXISTS cold_store (
                key TEXT PRIMARY KEY,
                data JSONB,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_warm_kind ON warm_events(kind);
            CREATE INDEX IF NOT EXISTS idx_warm_created ON warm_events(created_at);
        """)
        cur.close()

    def insert_event(self, event_id: str, kind: str, payload: dict, trace_id: str = "") -> bool:
        if not self._available: return False
        try:
            import json
            cur = self._conn.cursor()
            cur.execute(
                "INSERT INTO warm_events (event_id, kind, payload, trace_id) VALUES (%s,%s,%s,%s) ON CONFLICT (event_id) DO NOTHING",
                (event_id, kind, json.dumps(payload, default=str), trace_id)
            )
            cur.close()
            return True
        except Exception:
            return False

    def save_state(self, key: str, data: dict) -> bool:
        if not self._available: return False
        try:
            import json
            cur = self._conn.cursor()
            cur.execute(
                "INSERT INTO cold_store (key, data, updated_at) VALUES (%s,%s,NOW()) ON CONFLICT (key) DO UPDATE SET data=%s, updated_at=NOW()",
                (key, json.dumps(data, default=str), json.dumps(data, default=str))
            )
            cur.close()
            return True
        except Exception:
            return False

    def load_state(self, key: str) -> Optional[dict]:
        if not self._available: return None
        try:
            import json
            cur = self._conn.cursor()
            cur.execute("SELECT data FROM cold_store WHERE key=%s", (key,))
            row = cur.fetchone()
            cur.close()
            return json.loads(row[0]) if row else None
        except Exception:
            return None

    def query_events(self, kind: str = None, limit: int = 50) -> list:
        if not self._available: return []
        try:
            cur = self._conn.cursor()
            if kind:
                cur.execute("SELECT event_id, kind, payload, created_at FROM warm_events WHERE kind=%s ORDER BY created_at DESC LIMIT %s", (kind, limit))
            else:
                cur.execute("SELECT event_id, kind, payload, created_at FROM warm_events ORDER BY created_at DESC LIMIT %s", (limit,))
            rows = cur.fetchall()
            cur.close()
            return [{"event_id": r[0], "kind": r[1], "payload": r[2], "created_at": str(r[3])} for r in rows]
        except Exception:
            return []

    def close(self):
        if self._conn:
            try: self._conn.close()
            except: pass
            self._available = False


# ═══════════════════════════════════════════════════════════
#  ACID transactions (SQLite-based)
# ═══════════════════════════════════════════════════════════

def atomic_save(save_fn, *paths: str) -> bool:
    """Atomic file write — write to temp, then rename.

    Provides ACID-like atomicity for ColdStore JSON files
    without requiring a full database transaction layer.
    """
    for path in paths:
        tmp = path + ".tmp"
        try:
            save_fn(tmp)
            os.replace(tmp, path)  # atomic on POSIX/Windows
        except Exception:
            if os.path.exists(tmp):
                try: os.remove(tmp)
                except: pass
            return False
    return True

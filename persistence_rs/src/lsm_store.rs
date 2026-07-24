// LSM-tuned SQLite store with 5 column families + JVM-GC tiering.
// Matches Python LSMStore feature set.

use pyo3::prelude::*;
use pyo3::types::PyDict;
use rusqlite::Connection;
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};

const LSM_PRAGMAS: &str = "
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA mmap_size=268435456;
PRAGMA cache_size=-65536;
PRAGMA page_size=4096;
PRAGMA temp_store=MEMORY;
PRAGMA wal_autocheckpoint=1000;
PRAGMA foreign_keys=ON;
PRAGMA busy_timeout=5000;
";

#[pyclass]
pub struct PyLSMStore {
    conn: Mutex<Connection>,
}

#[pymethods]
impl PyLSMStore {
    #[new]
    pub fn new(db_path: String) -> PyResult<Self> {
        let path = std::path::Path::new(&db_path);
        if let Some(parent) = path.parent() {
            let _ = std::fs::create_dir_all(parent);
        }

        let conn = Connection::open(&db_path)
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;

        conn.execute_batch(LSM_PRAGMAS)
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;

        let store = PyLSMStore {
            conn: Mutex::new(conn),
        };
        store.create_tables()?;
        Ok(store)
    }

    // ── Column Families (5 CFs) ──

    fn create_tables(&self) -> PyResult<()> {
        let conn = self.conn.lock().unwrap();
        conn.execute_batch("
            -- CF_SESSIONS
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY, user_id TEXT DEFAULT '',
                version INTEGER DEFAULT 1, data TEXT, updated_at REAL,
                tier TEXT DEFAULT 'H'
            );
            -- CF_TURNS
            CREATE TABLE IF NOT EXISTS turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL, sequence INTEGER NOT NULL,
                role TEXT NOT NULL, content TEXT NOT NULL,
                data TEXT, timestamp REAL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
            );
            -- CF_GRAPH_NODES
            CREATE TABLE IF NOT EXISTS graph_nodes (
                node_id TEXT PRIMARY KEY, node_type TEXT DEFAULT 'entity',
                data TEXT, tier TEXT DEFAULT 'W',
                activation_count INTEGER DEFAULT 0, importance REAL DEFAULT 0.5,
                created_at REAL, updated_at REAL
            );
            -- CF_GRAPH_EDGES
            CREATE TABLE IF NOT EXISTS graph_edges (
                source TEXT NOT NULL, target TEXT NOT NULL,
                relation_kind TEXT DEFAULT 'structural',
                confidence REAL DEFAULT 0.5, data TEXT,
                PRIMARY KEY (source, target, relation_kind)
            );
            -- CF_SNAPSHOTS
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id TEXT UNIQUE, data TEXT, created_at REAL,
                node_count INTEGER DEFAULT 0, edge_count INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_tier ON sessions(tier, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id, sequence DESC);
            CREATE INDEX IF NOT EXISTS idx_graph_tier ON graph_nodes(tier, importance DESC);
            CREATE INDEX IF NOT EXISTS idx_graph_edges_source ON graph_edges(source);
            CREATE INDEX IF NOT EXISTS idx_snapshots_created ON snapshots(created_at DESC);
        ").map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
        Ok(())
    }

    // ── WriteBatch ──

    pub fn begin_batch(&self) -> PyResult<()> {
        let conn = self.conn.lock().unwrap();
        conn.execute("BEGIN IMMEDIATE", [])
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
        Ok(())
    }

    pub fn commit_batch(&self) -> PyResult<()> {
        let conn = self.conn.lock().unwrap();
        conn.execute("COMMIT", [])
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
        Ok(())
    }

    // ── Session CRUD ──

    pub fn put_session(&self, session_id: String, data: String, user_id: String) -> PyResult<()> {
        let conn = self.conn.lock().unwrap();
        let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs_f64();
        conn.execute(
            "INSERT OR REPLACE INTO sessions (session_id, user_id, data, updated_at) VALUES (?1, ?2, ?3, ?4)",
            rusqlite::params![session_id, user_id, data, now],
        ).map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
        Ok(())
    }

    pub fn get_session(&self, session_id: String) -> PyResult<Option<String>> {
        let conn = self.conn.lock().unwrap();
        let result = conn.query_row(
            "SELECT data FROM sessions WHERE session_id = ?1",
            rusqlite::params![session_id],
            |row| row.get::<_, String>(0),
        );
        match result {
            Ok(data) => Ok(Some(data)),
            Err(rusqlite::Error::QueryReturnedNoRows) => Ok(None),
            Err(e) => Err(pyo3::exceptions::PyRuntimeError::new_err(e.to_string())),
        }
    }

    pub fn list_sessions(&self, limit: i64) -> PyResult<Vec<String>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT session_id FROM sessions ORDER BY updated_at DESC LIMIT ?1"
        ).map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
        let ids: Vec<String> = stmt.query_map(
            rusqlite::params![limit],
            |row| row.get(0),
        ).map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?
         .filter_map(|r| r.ok()).collect();
        Ok(ids)
    }

    // ── Turn CRUD ──

    pub fn put_turn(&self, session_id: String, sequence: i64, role: String,
                    content: String, data: String) -> PyResult<()> {
        let conn = self.conn.lock().unwrap();
        let ts = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs_f64();
        conn.execute(
            "INSERT INTO turns (session_id, sequence, role, content, data, timestamp) VALUES (?1,?2,?3,?4,?5,?6)",
            rusqlite::params![session_id, sequence, role, content, data, ts],
        ).map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
        Ok(())
    }

    pub fn get_turns(&self, session_id: String, limit: i64) -> PyResult<Vec<String>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT data FROM turns WHERE session_id = ?1 ORDER BY sequence DESC LIMIT ?2"
        ).map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
        let turns: Vec<String> = stmt.query_map(
            rusqlite::params![session_id, limit],
            |row| row.get(0),
        ).map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?
         .filter_map(|r| r.ok()).collect();
        Ok(turns)
    }

    // ── Graph CRUD ──

    pub fn put_node(&self, node_id: String, node_type: String, data: String) -> PyResult<()> {
        let conn = self.conn.lock().unwrap();
        let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs_f64();
        conn.execute(
            "INSERT OR REPLACE INTO graph_nodes (node_id, node_type, data, tier, created_at, updated_at)
             VALUES (?1, ?2, ?3, 'W', COALESCE((SELECT created_at FROM graph_nodes WHERE node_id=?1), ?4), ?4)",
            rusqlite::params![node_id, node_type, data, now],
        ).map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
        Ok(())
    }

    pub fn touch_node(&self, node_id: String) -> PyResult<()> {
        let conn = self.conn.lock().unwrap();
        let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs_f64();
        conn.execute(
            "UPDATE graph_nodes SET activation_count = activation_count + 1, updated_at = ?1 WHERE node_id = ?2",
            rusqlite::params![now, node_id],
        ).map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
        Ok(())
    }

    pub fn put_edge(&self, source: String, target: String, relation_kind: String,
                    confidence: f64) -> PyResult<()> {
        let conn = self.conn.lock().unwrap();
        conn.execute(
            "INSERT OR REPLACE INTO graph_edges (source, target, relation_kind, confidence) VALUES (?1,?2,?3,?4)",
            rusqlite::params![source, target, relation_kind, confidence],
        ).map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
        Ok(())
    }

    // ── JVM-GC Tiering ──

    pub fn get_tier_counts(&self) -> PyResult<String> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT tier, COUNT(*) as cnt FROM graph_nodes GROUP BY tier"
        ).map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
        let rows: Vec<(String, i64)> = stmt.query_map([], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, i64>(1)?))
        }).map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?
         .filter_map(|r| r.ok()).collect();
        let result: std::collections::HashMap<String, i64> = rows.into_iter().collect();
        Ok(serde_json::to_string(&result).unwrap_or_default())
    }

    pub fn demote_stale(&self, from_tier: String, to_tier: String,
                        max_activation: i64, limit: i64) -> PyResult<()> {
        let conn = self.conn.lock().unwrap();
        conn.execute(
            "UPDATE graph_nodes SET tier = ?1 WHERE node_id IN (
                SELECT node_id FROM graph_nodes WHERE tier = ?2 AND activation_count < ?3
                ORDER BY updated_at ASC LIMIT ?4
            )",
            rusqlite::params![to_tier, from_tier, max_activation, limit],
        ).map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
        Ok(())
    }

    // ── Snapshot ──

    pub fn create_snapshot(&self, metadata: String) -> PyResult<String> {
        use std::time::{SystemTime, UNIX_EPOCH};
        let conn = self.conn.lock().unwrap();
        let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs_f64();
        let snap_id = format!("snap_{}", now as u64);
        let node_count: i64 = conn.query_row("SELECT COUNT(*) FROM graph_nodes", [], |r| r.get(0)).unwrap_or(0);
        let edge_count: i64 = conn.query_row("SELECT COUNT(*) FROM graph_edges", [], |r| r.get(0)).unwrap_or(0);
        conn.execute(
            "INSERT INTO snapshots (snapshot_id, data, created_at, node_count, edge_count) VALUES (?1,?2,?3,?4,?5)",
            rusqlite::params![snap_id, metadata, now, node_count, edge_count],
        ).map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
        Ok(snap_id)
    }

    // ── Maintenance ──

    pub fn compact(&self) -> PyResult<()> {
        let conn = self.conn.lock().unwrap();
        conn.execute_batch("PRAGMA incremental_vacuum(100); PRAGMA optimize;")
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
        Ok(())
    }

    pub fn cleanup(&self, ttl_seconds: f64) -> PyResult<i64> {
        let conn = self.conn.lock().unwrap();
        let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs_f64();
        let cutoff = now - ttl_seconds;
        let count = conn.execute(
            "DELETE FROM sessions WHERE updated_at < ?1",
            rusqlite::params![cutoff],
        ).map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
        Ok(count as i64)
    }

    pub fn close(&self) -> PyResult<()> {
        let conn = self.conn.lock().unwrap();
        conn.execute_batch("PRAGMA wal_checkpoint(TRUNCATE);")
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
        Ok(())
    }
}

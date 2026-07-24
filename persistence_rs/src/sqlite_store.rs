use pyo3::prelude::*;
use pyo3::types::PyDict;
use rusqlite::Connection;
use std::sync::Mutex;

/// Rust SQLite store with WAL mode
#[pyclass]
pub struct PySQLiteStore {
    conn: Mutex<Connection>,
}

#[pymethods]
impl PySQLiteStore {
    #[new]
    fn new(db_path: String) -> PyResult<Self> {
        let conn = Connection::open(&db_path)
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;

        // Enable WAL mode for concurrent reads
        conn.execute_batch(
            "PRAGMA journal_mode=WAL;
             PRAGMA synchronous=NORMAL;
             PRAGMA foreign_keys=ON;
             CREATE TABLE IF NOT EXISTS sessions (
                 session_id TEXT PRIMARY KEY,
                 user_id TEXT DEFAULT '',
                 version INTEGER DEFAULT 1,
                 data TEXT,
                 updated_at REAL
             );
             CREATE TABLE IF NOT EXISTS turns (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 session_id TEXT NOT NULL,
                 sequence INTEGER NOT NULL,
                 role TEXT NOT NULL,
                 content TEXT NOT NULL,
                 data TEXT,
                 timestamp REAL,
                 FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
             );
             CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id, sequence DESC);"
        ).map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;

        Ok(PySQLiteStore {
            conn: Mutex::new(conn),
        })
    }

    fn save_session(&self, session_id: String, user_id: String, data: String) -> PyResult<bool> {
        let conn = self.conn.lock().unwrap();
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs_f64();

        conn.execute(
            "INSERT INTO sessions (session_id, user_id, data, updated_at)
             VALUES (?1, ?2, ?3, ?4)
             ON CONFLICT(session_id) DO UPDATE SET
                 user_id = excluded.user_id,
                 data = excluded.data,
                 updated_at = excluded.updated_at",
            rusqlite::params![session_id, user_id, data, now],
        ).map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;

        Ok(true)
    }

    fn load_session(&self, session_id: String) -> PyResult<Option<String>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT data FROM sessions WHERE session_id = ?1"
        ).map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;

        let result = stmt.query_row(
            rusqlite::params![session_id],
            |row| row.get::<_, String>(0),
        );

        match result {
            Ok(data) => Ok(Some(data)),
            Err(rusqlite::Error::QueryReturnedNoRows) => Ok(None),
            Err(e) => Err(pyo3::exceptions::PyRuntimeError::new_err(e.to_string())),
        }
    }

    fn save_turn(&self, session_id: String, sequence: i64, role: String,
                 content: String, data: String) -> PyResult<bool> {
        let conn = self.conn.lock().unwrap();
        let ts = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs_f64();

        conn.execute(
            "INSERT INTO turns (session_id, sequence, role, content, data, timestamp)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
            rusqlite::params![session_id, sequence, role, content, data, ts],
        ).map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;

        Ok(true)
    }

    fn load_turns(&self, session_id: String, limit: i64) -> PyResult<Vec<String>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT data FROM turns WHERE session_id = ?1 ORDER BY sequence DESC LIMIT ?2"
        ).map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;

        let rows = stmt.query_map(
            rusqlite::params![session_id, limit],
            |row| row.get::<_, String>(0),
        ).map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;

        let mut turns = Vec::new();
        for row in rows {
            if let Ok(data) = row {
                turns.push(data);
            }
        }
        Ok(turns)
    }

    fn list_sessions(&self, limit: i64) -> PyResult<Vec<String>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT session_id FROM sessions ORDER BY updated_at DESC LIMIT ?1"
        ).map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;

        let rows = stmt.query_map(
            rusqlite::params![limit],
            |row| row.get::<_, String>(0),
        ).map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;

        let mut sessions = Vec::new();
        for row in rows {
            if let Ok(id) = row {
                sessions.push(id);
            }
        }
        Ok(sessions)
    }

    fn close(&self) -> PyResult<()> {
        // Connection closed on drop
        Ok(())
    }
}

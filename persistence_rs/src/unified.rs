use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use std::sync::Mutex;

use crate::event_log::PyChainedEventLog;
use crate::lsm_store::PyLSMStore;

/// Unified persistence broker — single entry point for all 10 chains
#[pyclass]
pub struct PyUnifiedBroker {
    event_log: Mutex<PyChainedEventLog>,
    sqlite: Mutex<PyLSMStore>,
    startup_events: Mutex<u64>,
}

#[pymethods]
impl PyUnifiedBroker {
    #[new]
    fn new(data_dir: String) -> PyResult<Self> {
        let events_path = format!("{}/events/unified_log.jsonl", data_dir);
        let db_path = format!("{}/sessions.db", data_dir);

        // Ensure directories exist
        let _ = std::fs::create_dir_all(format!("{}/events", data_dir));

        Ok(PyUnifiedBroker {
            event_log: Mutex::new(PyChainedEventLog::new(events_path)),
            sqlite: Mutex::new(PyLSMStore::new(db_path)?),
            startup_events: Mutex::new(0),
        })
    }

    /// Startup: verify chain + count events
    fn startup(&self) -> PyResult<String> {
        let log = self.event_log.lock().unwrap();
        let verify = log.verify().unwrap_or_default();
        let stats = log.stats().unwrap_or_default();

        *self.startup_events.lock().unwrap() = {
            let v: serde_json::Value = serde_json::from_str(&verify).unwrap_or_default();
            v["total"].as_u64().unwrap_or(0)
        };

        Ok(format!(
            r#"{{"verify": {}, "stats": {}, "events": {}}}"#,
            verify, stats,
            self.startup_events.lock().unwrap(),
        ))
    }

    /// Shutdown: final verify
    fn shutdown(&self) -> PyResult<String> {
        let log = self.event_log.lock().unwrap();
        log.verify()
    }

    // ── Chain 01: DiscourseTree ──

    fn persist_block(&self, py: Python, block_id: String, data: &PyDict) -> PyResult<String> {
        let log = self.event_log.lock().unwrap();
        log.append(py, "NodeEdited".to_string(), data)
    }

    // ── Chain 02: Context / Session ──

    fn persist_turn(&self, session_id: String, sequence: i64, role: String,
                    content: String) -> PyResult<bool> {
        let sqlite = self.sqlite.lock().unwrap();
        let data = format!(r#"{{"sequence":{},"role":"{}","content":"{}"}}"#, sequence, role, content);
        sqlite.put_turn(session_id, sequence, role, content, data)?;
        Ok(true)
    }

    fn persist_session(&self, session_id: String, user_id: String) -> PyResult<bool> {
        let sqlite = self.sqlite.lock().unwrap();
        sqlite.put_session(session_id, user_id, "{}".to_string())?;
        Ok(true)
    }

    // ── Chain 03-10: Generic event append ──

    fn persist_event(&self, py: Python, event_type: String, data: &PyDict) -> PyResult<String> {
        let log = self.event_log.lock().unwrap();
        log.append(py, event_type, data)
    }

    // ── Queries ──

    fn event_stats(&self) -> PyResult<String> {
        let log = self.event_log.lock().unwrap();
        log.stats()
    }

    fn verify_chain(&self) -> PyResult<String> {
        let log = self.event_log.lock().unwrap();
        log.verify()
    }
}

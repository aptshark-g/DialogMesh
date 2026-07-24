use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use std::sync::Mutex;
use std::collections::HashMap;

use crate::event_log::PyChainedEventLog;
use crate::lsm_store::PyLSMStore;

// 10-chain persistence + batch + GC + restore
#[pyclass]
pub struct PyUnifiedBroker {
    pub event_log: Mutex<PyChainedEventLog>,
    pub store: Mutex<PyLSMStore>,
    startup_events: Mutex<u64>,
}

#[pymethods]
impl PyUnifiedBroker {
    #[new]
    pub fn new(data_dir: String) -> PyResult<Self> {
        let events_path = format!("{}/events/unified_log.jsonl", data_dir);
        let db_path = format!("{}/lsm.db", data_dir);
        let _ = std::fs::create_dir_all(format!("{}/events", data_dir));

        Ok(PyUnifiedBroker {
            event_log: Mutex::new(PyChainedEventLog::new(events_path)),
            store: Mutex::new(PyLSMStore::new(db_path)?),
            startup_events: Mutex::new(0),
        })
    }

    // ── Lifecycle ──

    pub fn startup(&self) -> PyResult<String> {
        let log = self.event_log.lock().unwrap();
        let verify = log.verify().unwrap_or_default();
        let stats = log.stats().unwrap_or_default();
        let events = {
            let v: serde_json::Value = serde_json::from_str(&verify).unwrap_or_default();
            v["total"].as_u64().unwrap_or(0)
        };
        *self.startup_events.lock().unwrap() = events;
        
        let sessions = self.store.lock().unwrap().list_sessions(100).unwrap_or_default();
        Ok(serde_json::json!({
            "verify": serde_json::from_str::<serde_json::Value>(&verify).unwrap_or_default(),
            "stats": serde_json::from_str::<serde_json::Value>(&stats).unwrap_or_default(),
            "events": events,
            "sessions": sessions.len(),
        }).to_string())
    }

    pub fn shutdown(&self) -> PyResult<String> {
        let store = self.store.lock().unwrap();
        store.compact()?;
        self.event_log.lock().unwrap().verify()
    }

    // ── Chain 01: DiscourseBlock ──

    pub fn persist_block(&self, _py: Python, block_id: String, text: String) -> PyResult<String> {
        self.event_log.lock().unwrap().append_text("NodeEdited", &serde_json::json!({
            "block_id": block_id, "text": &text[..200.min(text.len())]
        }).to_string())
    }

    // ── Chain 02: Session ──

    pub fn persist_session(&self, session_id: String, user_id: String) -> PyResult<bool> {
        self.store.lock().unwrap().put_session(session_id, "{}".into(), user_id)?;
        Ok(true)
    }

    pub fn persist_turn(&self, session_id: String, sequence: i64, role: String,
                        content: String) -> PyResult<bool> {
        let data = serde_json::json!({"sequence": sequence, "role": &role, "content": &content}).to_string();
        self.store.lock().unwrap().put_turn(session_id, sequence, role, content, data)?;
        Ok(true)
    }

    pub fn persist_turns_batch(&self, session_id: String, 
                               turns: Vec<(i64, String, String)>) -> PyResult<bool> {
        let typed: Vec<(i64, String, String, String)> = turns.into_iter()
            .map(|(seq, role, content)| {
                let data = serde_json::json!({"role": &role, "content": &content}).to_string();
                (seq, role, content, data)
            }).collect();
        self.store.lock().unwrap().put_turns_batch(session_id, typed)?;
        Ok(true)
    }

    // ── Chain 03: MultiIntent ──

    pub fn persist_intent_lock(&self, _py: Python, session_id: String, intent: String, 
                               confidence: f64) -> PyResult<String> {
        self.event_log.lock().unwrap().append_text("MetaDecision", &serde_json::json!({
            "review_id": format!("intent_{}", session_id),
            "verdict": "locked",
            "reason": format!("intent={} conf={:.2}", intent, confidence)
        }).to_string())
    }

    // ── Chain 04: PCR ──

    pub fn persist_route(&self, _py: Python, session_id: String, zone: String,
                         x: f64, y: f64, z: f64) -> PyResult<String> {
        self.event_log.lock().unwrap().append_text("ParameterChanged", &serde_json::json!({
            "param": format!("pcr.{}", session_id),
            "old": "", "new": format!("zone={} x={:.2} y={:.2} z={:.2}", zone, x, y, z),
            "author": "pcr_v2"
        }).to_string())
    }

    // ── Chain 05: Behavior ──

    pub fn persist_behavior_pattern(&self, _py: Python, pattern_key: String,
                                     confidence: f64, support: i64) -> PyResult<String> {
        self.event_log.lock().unwrap().append_text("PatternDiscovered", &serde_json::json!({
            "pattern": pattern_key, "confidence": confidence, "support": support
        }).to_string())
    }

    // ── Chain 08: Profile ──

    pub fn persist_profile_correction(&self, _py: Python, dimension: String,
                                       old_val: f64, new_val: f64) -> PyResult<String> {
        self.event_log.lock().unwrap().append_text("ProfileEdited", &serde_json::json!({
            "dimension": dimension, "old": old_val, "new": new_val
        }).to_string())
    }

    // ── Chain 09: Metacognition ──

    pub fn persist_meta_decision(&self, _py: Python, review_id: String, 
                                  verdict: String) -> PyResult<String> {
        self.event_log.lock().unwrap().append_text("MetaDecision", &serde_json::json!({
            "review_id": review_id, "verdict": verdict
        }).to_string())
    }

    // ── Chain 07: Engineering ──

    pub fn persist_constraint(&self, _py: Python, module: String,
                               constraint: String) -> PyResult<String> {
        self.event_log.lock().unwrap().append_text("ConstraintAdded", &serde_json::json!({
            "module": module, "constraint": constraint
        }).to_string())
    }

    // ── Generic event ──

    pub fn persist_event(&self, _py: Python, event_type: String, 
                         data_json: String) -> PyResult<String> {
        self.event_log.lock().unwrap().append_text(&event_type, &data_json)
    }

    // ── Remaining chain methods ──

    pub fn persist_block_split(&self, original_id: String, new_ids: Vec<String>) -> PyResult<String> {
        self.event_log.lock().unwrap().append_text("NodeSplit", &serde_json::json!({
            "original_id": original_id, "new_ids": new_ids
        }).to_string())
    }

    pub fn persist_belief_update(&self, intent_key: String, belief_7d: String) -> PyResult<String> {
        self.event_log.lock().unwrap().append_text("ParameterChanged", &serde_json::json!({
            "param": format!("belief.{}", intent_key), "old": "", "new": belief_7d, "author": "l2_5"
        }).to_string())
    }

    pub fn persist_pattern_feedback(&self, pattern_key: String, accepted: bool) -> PyResult<String> {
        self.event_log.lock().unwrap().append_text("PatternFeedback", &serde_json::json!({
            "pattern": pattern_key, "accepted": accepted
        }).to_string())
    }

    pub fn persist_profile_drift(&self, dimension: String, drift: f64) -> PyResult<String> {
        self.event_log.lock().unwrap().append_text("ProfileDrifted", &serde_json::json!({
            "dimension": dimension, "drift": drift
        }).to_string())
    }

    pub fn verify_integrity(&self) -> PyResult<String> {
        let chain = self.event_log.lock().unwrap().verify().unwrap_or_default();
        let sessions = self.store.lock().unwrap().list_sessions(10).unwrap_or_default();
        Ok(serde_json::json!({
            "event_chain": serde_json::from_str::<serde_json::Value>(&chain).unwrap_or_default(),
            "sessions": sessions,
            "events_total": *self.startup_events.lock().unwrap(),
        }).to_string())
    }

    // ── Graph ──

    pub fn put_node(&self, node_id: String, node_type: String, data: String) -> PyResult<()> {
        self.store.lock().unwrap().put_node(node_id, node_type, data)
    }

    pub fn put_edge(&self, source: String, target: String, 
                    relation: String, confidence: f64) -> PyResult<()> {
        self.store.lock().unwrap().put_edge(source, target, relation, confidence)
    }

    pub fn get_tier_counts(&self) -> PyResult<String> {
        self.store.lock().unwrap().get_tier_counts()
    }

    pub fn create_snapshot(&self, metadata: String) -> PyResult<String> {
        self.store.lock().unwrap().create_snapshot(metadata)
    }

    // ── GC ──

    pub fn gc_tick(&self, ttl_seconds: f64) -> PyResult<i64> {
        let store = self.store.lock().unwrap();
        store.demote_stale("W".into(), "C".into(), 5, 100)?;
        store.cleanup(ttl_seconds)
    }

    // ── Restore ──

    pub fn restore_sessions(&self) -> PyResult<Vec<String>> {
        self.store.lock().unwrap().list_sessions(100)
    }

    pub fn restore_turns(&self, session_id: String, limit: i64) -> PyResult<Vec<String>> {
        self.store.lock().unwrap().get_turns(session_id, limit)
    }

    // ── Queries ──

    pub fn event_stats(&self) -> PyResult<String> {
        self.event_log.lock().unwrap().stats()
    }

    pub fn verify_chain(&self) -> PyResult<String> {
        self.event_log.lock().unwrap().verify()
    }
}

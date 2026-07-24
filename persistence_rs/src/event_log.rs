use pyo3::prelude::*;
use pyo3::types::PyDict;
use sha2::{Sha256, Digest};
use serde::{Serialize, Deserialize};
use std::fs::File;
use std::io::{BufRead, BufReader, Write};
use std::sync::Mutex;
use std::collections::HashMap;

/// SHA256-chained event
#[derive(Debug, Clone, Serialize, Deserialize)]
struct ChainedEvent {
    event_id: String,
    event_type: String,
    timestamp: f64,
    data: serde_json::Value,
    prev_hash: String,
    hash: String,
}

/// Python binding for ChainedEventLog
#[pyclass]
pub struct PyChainedEventLog {
    inner: Mutex<ChainedEventLog>,
}

#[pymethods]
impl PyChainedEventLog {
    #[new]
    pub fn new(path: String) -> Self {
        PyChainedEventLog {
            inner: Mutex::new(ChainedEventLog::new(&path)),
        }
    }

    pub fn append(&self, py: Python, event_type: String, data: &PyDict) -> PyResult<String> {
        let data_json: serde_json::Value = py_to_json(data);
        let mut log = self.inner.lock().unwrap();
        let event = log.append(&event_type, data_json);
        Ok(serde_json::to_string(&event).unwrap_or_default())
    }

    pub fn append_text(&self, event_type: &str, data_json_str: &str) -> PyResult<String> {
        let data_json: serde_json::Value = serde_json::from_str(data_json_str).unwrap_or_default();
        let mut log = self.inner.lock().unwrap();
        let event = log.append(event_type, data_json);
        Ok(serde_json::to_string(&event).unwrap_or_default())
    }

    pub fn verify(&self) -> PyResult<String> {
        let log = self.inner.lock().unwrap();
        let result = log.verify();
        Ok(serde_json::to_string(&result).unwrap_or_default())
    }

    pub fn replay(&self) -> PyResult<Vec<String>> {
        let log = self.inner.lock().unwrap();
        let events: Vec<String> = log.replay_all()
            .iter()
            .map(|e| serde_json::to_string(e).unwrap_or_default())
            .collect();
        Ok(events)
    }

    pub fn stats(&self) -> PyResult<String> {
        let log = self.inner.lock().unwrap();
        Ok(serde_json::to_string(&log.stats()).unwrap_or_default())
    }
}

fn py_to_json(data: &PyDict) -> serde_json::Value {
    let mut map = serde_json::Map::new();
    for (key, value) in data.iter() {
        if let (Ok(k), Ok(v)) = (key.extract::<String>(), value.extract::<String>()) {
            map.insert(k, serde_json::Value::String(v));
        } else if let (Ok(k), Ok(v)) = (key.extract::<String>(), value.extract::<f64>()) {
            map.insert(k, serde_json::json!(v));
        } else if let Ok(k) = key.extract::<String>() {
            // Fallback: try to stringify
            let s = format!("{:?}", value);
            map.insert(k, serde_json::Value::String(s));
        }
    }
    serde_json::Value::Object(map)
}

struct ChainedEventLog {
    path: String,
    events: Vec<ChainedEvent>,
    last_hash: String,
    counter: u64,
}

impl ChainedEventLog {
    fn new(path: &str) -> Self {
        let mut log = ChainedEventLog {
            path: path.to_string(),
            events: Vec::new(),
            last_hash: "genesis".to_string(),
            counter: 0,
        };
        log.load();
        log
    }

    fn append(&mut self, event_type: &str, data: serde_json::Value) -> &ChainedEvent {
        let ts = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs_f64();
        let event_id = format!("evt_{}_{}", self.counter, (ts * 1000.0) as u64);
        let payload = format!("{}|{}", self.last_hash, serde_json::to_string(&data).unwrap_or_default());
        let hash = format!("{:x}", Sha256::digest(payload.as_bytes()));

        let event = ChainedEvent {
            event_id,
            event_type: event_type.to_string(),
            timestamp: ts,
            data,
            prev_hash: self.last_hash.clone(),
            hash: hash.clone(),
        };

        // Persist to disk
        if let Some(parent) = std::path::Path::new(&self.path).parent() {
            let _ = std::fs::create_dir_all(parent);
        }
        if let Ok(mut f) = std::fs::OpenOptions::new()
            .create(true).append(true).open(&self.path)
        {
            let line = serde_json::json!({
                "id": &event.event_id,
                "type": &event.event_type,
                "ts": event.timestamp,
                "prev": &event.prev_hash,
                "hash": &event.hash,
                "data": &event.data,
            });
            let _ = writeln!(f, "{}", serde_json::to_string(&line).unwrap_or_default());
        }

        self.last_hash = hash;
        self.events.push(event);
        self.counter += 1;
        self.events.last().unwrap()
    }

    pub fn verify(&self) -> serde_json::Value {
        let mut prev = String::from("genesis");
        let mut broken = Vec::new();
        for e in &self.events {
            let payload = format!("{}|{}", prev, serde_json::to_string(&e.data).unwrap_or_default());
            let expected = format!("{:x}", Sha256::digest(payload.as_bytes()));
            if e.hash != expected {
                broken.push(e.event_id.clone());
            }
            prev = e.hash.clone();
        }
        serde_json::json!({
            "total": self.events.len(),
            "broken": broken.len(),
            "chain_intact": broken.is_empty(),
            "last_hash": &self.last_hash,
        })
    }

    fn replay_all(&self) -> &Vec<ChainedEvent> {
        &self.events
    }

    pub fn stats(&self) -> serde_json::Value {
        let mut by_type = HashMap::new();
        for e in &self.events {
            *by_type.entry(&e.event_type).or_insert(0u64) += 1;
        }
        serde_json::json!({
            "total_events": self.events.len(),
            "last_hash": &self.last_hash[..16.min(self.last_hash.len())],
            "by_type": by_type,
        })
    }

    fn load(&mut self) {
        let path = std::path::Path::new(&self.path);
        if !path.exists() { return; }
        if let Ok(f) = File::open(path) {
            for line in BufReader::new(f).lines().flatten() {
                if let Ok(val) = serde_json::from_str::<serde_json::Value>(&line) {
                    let event = ChainedEvent {
                        event_id: val["id"].as_str().unwrap_or("").to_string(),
                        event_type: val["type"].as_str().unwrap_or("").to_string(),
                        timestamp: val["ts"].as_f64().unwrap_or(0.0),
                        data: val["data"].clone(),
                        prev_hash: val["prev"].as_str().unwrap_or("genesis").to_string(),
                        hash: val["hash"].as_str().unwrap_or("").to_string(),
                    };
                    self.last_hash = event.hash.clone();
                    self.events.push(event);
                    self.counter += 1;
                }
            }
        }
    }
}

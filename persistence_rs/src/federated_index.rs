// Federated Anchor Index — merge + dedup + temperature scoring in Rust.
// Python calls individual sources, Rust merges results.

use pyo3::prelude::*;
use std::sync::Mutex;
use std::collections::{HashMap, HashSet};
use std::time::{SystemTime, UNIX_EPOCH};

#[pyclass]
pub struct PyFederatedIndex {
    access_counts: Mutex<HashMap<String, u64>>,
    last_access: Mutex<HashMap<String, f64>>,
    max_results: usize,
}

#[pymethods]
impl PyFederatedIndex {
    #[new]
    pub fn new(max_results: usize) -> Self {
        PyFederatedIndex {
            access_counts: Mutex::new(HashMap::new()),
            last_access: Mutex::new(HashMap::new()),
            max_results: max_results.max(1),
        }
    }

    /// Merge hits from multiple sources. Python passes lists of dicts.
    /// Each hit: {"anchor_id": str, "source": str, "score": float, "temperature": int}
    pub fn merge(&self, py: Python, all_hits: Vec<Vec<PyObject>>, min_temperature: i32) -> PyResult<Vec<PyObject>> {
        let mut merged: Vec<(f64, PyObject)> = Vec::new();
        let mut seen = HashSet::new();

        for source_hits in &all_hits {
            for hit_obj in source_hits {
                let dict = hit_obj.downcast::<pyo3::types::PyDict>(py)?;
                
                let anchor_id: String = dict.get_item("anchor_id")
                    .and_then(|v| v.map(|x| x.extract().ok()).flatten().ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("missing")))
                    .unwrap_or_default();
                if seen.contains(&anchor_id) { continue; }
                
                let score: f64 = dict.get_item("score")
                    .and_then(|v| v.map(|x| x.extract::<f64>().unwrap_or(0.5)).ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("missing")))
                    .unwrap_or(0.5);
                let temperature: i32 = dict.get_item("temperature")
                    .and_then(|v| v.map(|x| x.extract::<i32>().unwrap_or(1)).ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("missing")))
                    .unwrap_or(1);

                if temperature > min_temperature { continue; }

                // Temperature-weighted priority
                let temp_weight = match temperature { 0 => 1.0, 1 => 0.7, 2 => 0.4, _ => 0.1 };
                let priority = score * temp_weight;

                // Touch for LRU
                let mut counts = self.access_counts.lock().unwrap();
                let mut last = self.last_access.lock().unwrap();
                *counts.entry(anchor_id.clone()).or_default() += 1;
                let ts = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs_f64();
                last.insert(anchor_id.clone(), ts);
                drop(counts); drop(last);

                seen.insert(anchor_id);
                merged.push((priority, hit_obj.clone_ref(py)));
            }
        }

        // Sort by priority descending
        merged.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap_or(std::cmp::Ordering::Equal));

        // Take top max_results
        let result: Vec<PyObject> = merged.into_iter()
            .take(self.max_results)
            .map(|(_, obj)| obj)
            .collect();

        Ok(result)
    }

    pub fn get_temperature(&self, anchor_id: String) -> i32 {
        let counts = self.access_counts.lock().unwrap();
        let last = self.last_access.lock().unwrap();
        let count = counts.get(&anchor_id).copied().unwrap_or(0);
        let last_ts = last.get(&anchor_id).copied().unwrap_or(0.0);
        let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs_f64();
        let age = now - last_ts;

        if count > 10 && age < 60.0   { 0 }
        else if count > 3 && age < 3600.0  { 1 }
        else if age < 86400.0              { 2 }
        else { 3 }
    }

    pub fn status(&self) -> PyResult<String> {
        let counts = self.access_counts.lock().unwrap();
        let hot = counts.iter().filter(|(id, _)| self.get_temperature((*id).clone()) == 0).count();
        Ok(serde_json::json!({
            "total_anchors": counts.len(),
            "hot_anchors": hot,
        }).to_string())
    }
}

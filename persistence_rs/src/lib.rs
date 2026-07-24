use pyo3::prelude::*;
use pyo3::types::PyDict;

mod event_log;
mod sqlite_store;
mod unified;

#[pymodule]
fn dialogmesh_persistence(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<event_log::PyChainedEventLog>()?;
    m.add_class::<sqlite_store::PySQLiteStore>()?;
    m.add_class::<unified::PyUnifiedBroker>()?;
    Ok(())
}

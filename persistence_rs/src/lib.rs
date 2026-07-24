use pyo3::prelude::*;

mod event_log;
mod lsm_store;
mod unified;

#[pymodule]
fn dialogmesh_persistence(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<event_log::PyChainedEventLog>()?;
    m.add_class::<lsm_store::PyLSMStore>()?;
    m.add_class::<unified::PyUnifiedBroker>()?;
    Ok(())
}

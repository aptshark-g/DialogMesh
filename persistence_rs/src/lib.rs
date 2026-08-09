use pyo3::prelude::*;

mod event_log;
mod lsm_store;
mod unified;
mod federated_index;

#[pymodule]
fn dialogmesh_persistence(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<event_log::PyChainedEventLog>()?;
    m.add_class::<lsm_store::PyLSMStore>()?;
    m.add_class::<unified::PyUnifiedBroker>()?;
    m.add_class::<federated_index::PyFederatedIndex>()?;
    Ok(())
}

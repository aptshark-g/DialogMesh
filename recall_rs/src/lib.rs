use pyo3::prelude::*;
use pyo3::buffer::PyBuffer;

mod bm25;
mod coarse;
mod cosine;

/// 余弦 top-k: vecs 扁平 (n,dim), query 归一向量 → [(idx, score)]。
#[pyfunction]
fn cosine_topk(vecs: Vec<f64>, dim: usize, query: Vec<f64>, k: usize)
    -> Vec<(usize, f64)> {
    cosine::cosine_topk(&vecs, dim, &query, k)
}

/// 零拷贝版本: numpy bytes（f64 LE 扁平）→ 直读, 规模感知并行。
#[pyfunction]
fn cosine_topk_bytes(data: Vec<u8>, dim: usize, query_bytes: Vec<u8>, k: usize)
    -> Vec<(usize, f64)> {
    cosine::cosine_topk_bytes(&data, dim, &query_bytes, k)
}

/// PyBuffer 零拷贝: numpy 数组直接提取（一次 memcpy, 2026-08-11）。
#[pyfunction]
fn cosine_topk_buffer<'py>(
    py: Python<'py>,
    vecs: Bound<'py, PyAny>,
    dim: usize,
    query: Bound<'py, PyAny>,
    k: usize,
) -> PyResult<Vec<(usize, f64)>> {
    let buf = PyBuffer::<f64>::get_bound(&vecs)?;
    let qbuf = PyBuffer::<f64>::get_bound(&query)?;
    let n = buf.item_count() / dim;
    let mut data = vec![0.0f64; n * dim];
    let mut q = vec![0.0f64; dim];
    buf.copy_to_slice(py, &mut data)?;
    qbuf.copy_to_slice(py, &mut q)?;
    Ok(cosine::cosine_topk_bytes(
        unsafe {
            std::slice::from_raw_parts(
                data.as_ptr() as *const u8, data.len() * 8)
        },
        dim,
        unsafe {
            std::slice::from_raw_parts(
                q.as_ptr() as *const u8, q.len() * 8)
        },
        k))
}

/// BM25 打分: 稀疏词项 → [(doc, score)]。
#[pyfunction]
fn bm25_scores(
    docs: Vec<(usize, u32, u32)>,
    df: Vec<(u32, u32)>,
    n_docs: usize,
    query_terms: Vec<u32>,
    k1: f64,
    b: f64,
    doc_lens: Vec<f64>,
    avg_len: f64,
) -> Vec<(usize, f64)> {
    bm25::bm25_scores(&docs, &df, n_docs, &query_terms, k1, b, &doc_lens, avg_len)
}

/// 词项交集粗筛 → 候选文档索引。
#[pyfunction]
fn coarse_candidates(query_terms: Vec<u32>, docs: Vec<(usize, u32)>)
    -> Vec<usize> {
    coarse::coarse_candidates(&query_terms, &docs)
}

#[pymodule]
fn dialogmesh_recall(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(cosine_topk, m)?)?;
    m.add_function(wrap_pyfunction!(cosine_topk_bytes, m)?)?;
    m.add_function(wrap_pyfunction!(cosine_topk_buffer, m)?)?;
    m.add_function(wrap_pyfunction!(bm25_scores, m)?)?;
    m.add_function(wrap_pyfunction!(coarse_candidates, m)?)?;
    Ok(())
}

//! BM25 打分（RECALL_RUST_DESIGN §三）: 稀疏词项矩阵 × query, 并行。
use rayon::prelude::*;

/// BM25 词项打分: 每文档稀疏词项（term_id → 频次）对 query 词项打分。
///
/// docs: Vec<(doc_idx, term_id, tf)> 稀疏表示; df: term_id → 文档频率;
/// n_docs: 文档总数; k1/b: BM25 参数。
pub fn bm25_scores(
    docs: &[(usize, u32, u32)],   // (doc, term, tf)
    df: &[(u32, u32)],            // (term, doc_freq)
    n_docs: usize,
    query_terms: &[u32],
    k1: f64,
    b: f64,
    doc_lens: &[f64],             // 每文档长度（归一化用）
    avg_len: f64,
) -> Vec<(usize, f64)> {
    if docs.is_empty() || query_terms.is_empty() {
        return Vec::new();
    }
    // term → df 查找表
    let df_map: std::collections::HashMap<u32, u32> = df.iter().copied().collect();
    // 每文档聚合 query 词项 tf
    let mut doc_tf: std::collections::HashMap<usize, Vec<(u32, u32)>> =
        std::collections::HashMap::new();
    for &(doc, term, tf) in docs {
        if query_terms.contains(&term) {
            doc_tf.entry(doc).or_default().push((term, tf));
        }
    }
    let idf_denom = n_docs.max(1) as f64;
    let scores: Vec<(usize, f64)> = doc_tf.par_iter()
        .map(|(&doc, terms)| {
            let len = doc_lens.get(doc).copied().unwrap_or(avg_len);
            let norm = len / avg_len.max(1e-12);
            let mut s = 0.0;
            for &(term, tf) in terms {
                let df = df_map.get(&term).copied().unwrap_or(0) as f64;
                let idf = ((idf_denom - df + 0.5) / (df + 0.5) + 1.0).ln();
                let tf_ = tf as f64;
                s += idf * (tf_ * (k1 + 1.0)) / (tf_ + k1 * (1.0 - b + b * norm));
            }
            (doc, s)
        })
        .collect();
    scores
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn basic_bm25() {
        // 2 文档: d0 含 term1×2, d1 含 term1×1 + term2×1; query=[term1]
        let docs = vec![(0usize, 1u32, 2u32), (1, 1, 1), (1, 2, 1)];
        let df = vec![(1u32, 2u32), (2, 1)];
        let scores = bm25_scores(&docs, &df, 2, &[1], 1.2, 0.75,
                                 &[2.0, 2.0], 2.0);
        assert_eq!(scores.len(), 2);
        let s0 = scores.iter().find(|(d, _)| *d == 0).unwrap().1;
        assert!(s0 > 0.0);
    }
}

//! 词项交集粗筛（RECALL_RUST_DESIGN §三）: query 词项 ∩ 文档词项。
use rayon::prelude::*;

/// 粗筛候选: 返回与 query 有 ≥1 词项交集的文档索引。
/// docs: Vec<(doc_idx, term_id)>（每文档词项列表）。
pub fn coarse_candidates(
    query_terms: &[u32],
    docs: &[(usize, u32)],
) -> Vec<usize> {
    if query_terms.is_empty() {
        return Vec::new();
    }
    let qset: std::collections::HashSet<u32> = query_terms.iter().copied().collect();
    // 按文档聚合词项, 并行过滤
    let mut by_doc: std::collections::HashMap<usize, Vec<u32>> =
        std::collections::HashMap::new();
    for &(doc, term) in docs {
        by_doc.entry(doc).or_default().push(term);
    }
    let mut out: Vec<usize> = by_doc.par_iter()
        .filter(|(_, terms)| terms.iter().any(|t| qset.contains(t)))
        .map(|(&doc, _)| doc)
        .collect();
    out.sort_unstable();
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn finds_intersection() {
        let docs = vec![(0usize, 1u32), (0, 2), (1, 3), (2, 4)];
        let out = coarse_candidates(&[2, 9], &docs);
        assert_eq!(out, vec![0]);  // 只有 doc0 含 term2
    }

    #[test]
    fn empty_query_safe() {
        assert!(coarse_candidates(&[], &[(0, 1)]).is_empty());
    }
}

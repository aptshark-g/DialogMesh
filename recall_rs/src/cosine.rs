//! 余弦 top-k（RECALL_RUST_DESIGN §三）: 全库向量 × query 点积, rayon 并行。
use rayon::prelude::*;

/// 计算 query 与全部块向量的余弦相似度, 返回 top-k 的 (index, score)。
///
/// vecs: 扁平化 (n_blocks, dim) 行优先; query: dim 维。向量假定已 L2 归一
/// （编码层 normalize=True）, 余弦 = 点积。
pub fn cosine_topk(vecs: &[f64], dim: usize, query: &[f64], k: usize)
    -> Vec<(usize, f64)> {
    if vecs.is_empty() || dim == 0 || query.len() != dim {
        return Vec::new();
    }
    let n = vecs.len() / dim;
    let q_norm = dot(query, query).sqrt().max(1e-12);
    // 并行分块计算相似度
    let mut scores: Vec<(usize, f64)> = (0..n).into_par_iter()
        .map(|i| {
            let start = i * dim;
            let block = &vecs[start..start + dim];
            let v_norm = dot(block, block).sqrt().max(1e-12);
            (i, dot(block, query) / (q_norm * v_norm))
        })
        .collect();
    // 部分排序取 top-k（避免全排序）
    if k >= scores.len() {
        scores.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
        return scores;
    }
    scores.select_nth_unstable_by(k, |a, b| {
        b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal)
    });
    let mut top = scores[..k].to_vec();
    top.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
    top
}

/// 零拷贝版本: 直接接收 numpy bytes（f64 little-endian 扁平数组）,
/// 避免 Python list → Vec 转换（2026-08-11 优化）。
/// 规模感知: 小块顺序执行（省 rayon 调度）, 大块并行。
pub fn cosine_topk_bytes(data: &[u8], dim: usize, query_bytes: &[u8], k: usize)
    -> Vec<(usize, f64)> {
    if data.len() % 8 != 0 || query_bytes.len() != dim * 8 {
        return Vec::new();
    }
    // 零拷贝 reinterpret: numpy bytes 是 f64 LE, 内存对齐由 numpy 保证
    let vecs = unsafe {
        std::slice::from_raw_parts(data.as_ptr() as *const f64, data.len() / 8)
    };
    let query = unsafe {
        std::slice::from_raw_parts(query_bytes.as_ptr() as *const f64, dim)
    };
    let n = vecs.len() / dim;
    if n == 0 || dim == 0 {
        return Vec::new();
    }
    let q_norm = dot(query, query).sqrt().max(1e-12);
    let scores = if n < 2000 {
        // 小池顺序执行（省 rayon 线程调度开销）
        (0..n).map(|i| {
            let start = i * dim;
            let block = &vecs[start..start + dim];
            let v_norm = dot(block, block).sqrt().max(1e-12);
            (i, dot(block, query) / (q_norm * v_norm))
        }).collect()
    } else {
        (0..n).into_par_iter().map(|i| {
            let start = i * dim;
            let block = &vecs[start..start + dim];
            let v_norm = dot(block, block).sqrt().max(1e-12);
            (i, dot(block, query) / (q_norm * v_norm))
        }).collect()
    };
    topk_of(scores, k)
}

fn topk_of(mut scores: Vec<(usize, f64)>, k: usize) -> Vec<(usize, f64)> {
    if k >= scores.len() {
        scores.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
        return scores;
    }
    scores.select_nth_unstable_by(k, |a, b| {
        b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal)
    });
    let mut top = scores[..k].to_vec();
    top.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
    top
}

#[inline]
fn dot(a: &[f64], b: &[f64]) -> f64 {
    a.iter().zip(b.iter()).map(|(x, y)| x * y).sum()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn topk_orders_by_similarity() {
        // 3 块, dim=2: [1,0] [0,1] [0.7,0.7], query [1,0]
        let vecs = vec![1.0, 0.0, 0.0, 1.0, 0.7, 0.7];
        let q = vec![1.0, 0.0];
        let top = cosine_topk(&vecs, 2, &q, 2);
        assert_eq!(top[0].0, 0);          // [1,0] 最相似
        assert!((top[0].1 - 1.0).abs() < 1e-9);
        assert_eq!(top[1].0, 2);          // [0.7,0.7] 次之
        assert!((top[1].1 - 0.7071).abs() < 1e-3);
    }

    #[test]
    fn empty_inputs_safe() {
        assert!(cosine_topk(&[], 2, &[1.0, 0.0], 3).is_empty());
    }

    #[test]
    fn bytes_version_matches_vec_version() {
        let vecs = vec![1.0, 0.0, 0.0, 1.0, 0.7, 0.7];
        let q = vec![1.0, 0.0];
        let mut bytes = Vec::new();
        for v in &vecs {
            bytes.extend_from_slice(&v.to_le_bytes());
        }
        let mut qb = Vec::new();
        for v in &q {
            qb.extend_from_slice(&v.to_le_bytes());
        }
        let a = cosine_topk(&vecs, 2, &q, 2);
        let b = cosine_topk_bytes(&bytes, 2, &qb, 2);
        assert_eq!(a, b);
    }
}

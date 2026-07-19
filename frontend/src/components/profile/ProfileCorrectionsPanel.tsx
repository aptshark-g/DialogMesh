// FILE: src/components/profile/ProfileCorrectionsPanel.tsx
// 修正历史 Tab —— before/after 对比列表 + LLM 回顾漂移

import { useCallback, useEffect, useState } from 'react';
import type { FC } from 'react';
import { motion } from 'framer-motion';
import { ArrowRight, History, Loader2, RefreshCw, ScanSearch } from 'lucide-react';
import { getProfileCorrections, reviewProfileCorrections } from '@/api/v6';
import type { V6ProfileCorrection, V6ProfileCorrectionsResponse } from '@/types/api';
import { Toast } from '@/components/ui/Toast';
import { cn, formatTimestamp } from '@/lib/utils';

type ToastState = {
  type: 'success' | 'error' | 'info' | 'warning';
  message: string;
} | null;

/** 兼容秒级 / 毫秒级时间戳 */
function normalizeTs(ts: number): number {
  return ts < 1e12 ? ts * 1000 : ts;
}

export const ProfileCorrectionsPanel: FC = () => {
  const [data, setData] = useState<V6ProfileCorrectionsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reviewing, setReviewing] = useState(false);
  const [reviewed, setReviewed] = useState<boolean | null>(null);
  const [toast, setToast] = useState<ToastState>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getProfileCorrections());
    } catch (err) {
      setError(err instanceof Error ? err.message : '获取修正历史失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleReview = async () => {
    if (reviewing) return;
    setReviewing(true);
    try {
      const res = await reviewProfileCorrections();
      setReviewed(res.reviewed);
      setToast({
        type: 'success',
        message: res.reviewed
          ? 'LLM 已完成画像漂移回顾'
          : 'LLM 回顾完成：本次未发现需要处理的漂移',
      });
    } catch (err) {
      setToast({
        type: 'error',
        message: err instanceof Error ? err.message : 'LLM 回顾漂移失败',
      });
    } finally {
      setReviewing(false);
    }
  };

  const corrections = data?.corrections ?? [];

  return (
    <div className="space-y-6">
      {/* 操作栏 */}
      <div className="bg-surface-card rounded-xl border border-border-subtle p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-text-primary">画像修正历史</h3>
          <p className="text-xs text-text-muted mt-0.5">
            共 {data?.total ?? corrections.length} 条修正记录
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={load}
            disabled={loading}
            className={cn(
              'flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium',
              'bg-surface-card border border-border-subtle text-text-secondary',
              'hover:bg-surface-card-hover hover:text-primary transition-colors',
              'disabled:opacity-50 disabled:cursor-not-allowed'
            )}
          >
            <RefreshCw className={cn('w-4 h-4', loading && 'animate-spin')} />
            刷新
          </button>
          <button
            type="button"
            onClick={handleReview}
            disabled={reviewing}
            className={cn(
              'flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium',
              'bg-primary text-white hover:opacity-90 transition-opacity',
              'disabled:opacity-50 disabled:cursor-not-allowed'
            )}
          >
            {reviewing ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <ScanSearch className="w-4 h-4" />
            )}
            LLM 回顾漂移
          </button>
        </div>
      </div>

      {/* LLM 回顾结果卡片 */}
      {reviewed !== null && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
          className={cn(
            'rounded-xl border p-4 flex items-center gap-3',
            reviewed
              ? 'bg-status-success/10 border-status-success/30'
              : 'bg-surface-card border-border-subtle'
          )}
        >
          <ScanSearch
            className={cn(
              'w-5 h-5 shrink-0',
              reviewed ? 'text-status-success' : 'text-text-muted'
            )}
          />
          <div>
            <p className="text-sm font-medium text-text-primary">
              {reviewed ? '漂移回顾已处理' : '未发现画像漂移'}
            </p>
            <p className="text-xs text-text-muted mt-0.5">
              reviewed: {String(reviewed)} · 由 /v6/profile/corrections/review 返回
            </p>
          </div>
        </motion.div>
      )}

      {/* 错误提示 */}
      {error && (
        <div className="rounded-xl border border-status-error/30 bg-status-error/10 p-4">
          <p className="text-sm text-status-error">{error}</p>
        </div>
      )}

      {/* 列表 */}
      {loading && corrections.length === 0 ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div
              key={i}
              className="bg-surface-card rounded-xl border border-border-subtle p-4"
            >
              <div className="skeleton h-4 w-32 rounded mb-3" />
              <div className="skeleton h-16 rounded" />
            </div>
          ))}
        </div>
      ) : corrections.length === 0 && !error ? (
        <div className="bg-surface-card rounded-xl border border-border-subtle p-10 flex flex-col items-center justify-center gap-2">
          <History className="w-8 h-8 text-text-muted" />
          <p className="text-sm text-text-muted">暂无画像修正记录</p>
        </div>
      ) : (
        <div className="space-y-3">
          {corrections.map((c: V6ProfileCorrection, idx: number) => (
            <motion.div
              key={c.id || idx}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: Math.min(idx * 0.04, 0.3) }}
              className="bg-surface-card rounded-xl border border-border-subtle p-4 space-y-3"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs px-2 py-1 rounded-full bg-surface-sidebar text-text-secondary font-medium">
                  {c.author || 'unknown'}
                </span>
                <span className="text-xs text-text-muted">
                  {formatTimestamp(normalizeTs(c.ts))}
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-[1fr_auto_1fr] gap-2 items-stretch">
                <div className="rounded-lg bg-status-error/10 border border-status-error/20 p-3">
                  <p className="text-[10px] font-medium text-status-error uppercase tracking-wide mb-1">
                    修正前 before
                  </p>
                  <p className="text-sm text-text-secondary break-all">{c.before || '—'}</p>
                </div>
                <div className="flex items-center justify-center">
                  <ArrowRight className="w-4 h-4 text-text-muted rotate-90 md:rotate-0" />
                </div>
                <div className="rounded-lg bg-status-success/10 border border-status-success/20 p-3">
                  <p className="text-[10px] font-medium text-status-success uppercase tracking-wide mb-1">
                    修正后 after
                  </p>
                  <p className="text-sm text-text-secondary break-all">{c.after || '—'}</p>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                <p className="text-text-muted">
                  <span className="font-medium text-text-secondary">修正原因：</span>
                  {c.reason || '—'}
                </p>
                <p className="text-text-muted">
                  <span className="font-medium text-text-secondary">验证方式：</span>
                  {c.verify || '—'}
                </p>
              </div>
            </motion.div>
          ))}
        </div>
      )}

      {toast && (
        <Toast type={toast.type} message={toast.message} onClose={() => setToast(null)} />
      )}
    </div>
  );
};

export default ProfileCorrectionsPanel;

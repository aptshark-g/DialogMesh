// FILE: src/components/profile/ProfileInertiaPanel.tsx
// 惯性权重 Tab —— 画像维度惯性视角:统计卡 + by_weight 条形 + constraints 列表

import { useCallback, useEffect, useState } from 'react';
import type { FC } from 'react';
import { motion } from 'framer-motion';
import { Anchor, RefreshCw, ShieldCheck } from 'lucide-react';
import { getInertia } from '@/api/v6';
import type { V6InertiaResponse } from '@/types/api';
import { Toast } from '@/components/ui/Toast';
import { cn } from '@/lib/utils';

type ToastState = {
  type: 'success' | 'error' | 'info' | 'warning';
  message: string;
} | null;

const WEIGHT_COLORS = [
  'bg-status-success',
  'bg-primary',
  'bg-status-warning',
  'bg-status-error',
  'bg-[#8B5CF6]',
];

export const ProfileInertiaPanel: FC = () => {
  const [data, setData] = useState<V6InertiaResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<ToastState>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getInertia());
    } catch (err) {
      const msg = err instanceof Error ? err.message : '获取惯性权重失败';
      setError(msg);
      setToast({ type: 'error', message: msg });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const statCards = data
    ? [
        { label: '模式总数', value: data.total_patterns, tone: 'text-text-primary' },
        { label: '稳定 stable', value: data.stable, tone: 'text-status-success' },
        { label: '已确认 confirmed', value: data.confirmed, tone: 'text-primary' },
        { label: '打破 breaking', value: data.breaking, tone: 'text-status-error' },
      ]
    : [];

  const weightEntries = data ? Object.entries(data.by_weight) : [];
  const weightMax = Math.max(1, ...weightEntries.map(([, v]) => v));

  return (
    <div className="space-y-6">
      {/* 操作栏 */}
      <div className="bg-surface-card rounded-xl border border-border-subtle p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-text-primary">画像维度惯性</h3>
          <p className="text-xs text-text-muted mt-0.5">
            画像维度在持续交互中表现出的惯性权重与约束
          </p>
        </div>
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
      </div>

      {error && (
        <div className="rounded-xl border border-status-error/30 bg-status-error/10 p-4">
          <p className="text-sm text-status-error">{error}</p>
        </div>
      )}

      {/* 统计卡 */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {(data ? statCards : [{ label: '模式总数' }, { label: '稳定 stable' }, { label: '已确认 confirmed' }, { label: '打破 breaking' }] as { label: string; value?: number; tone?: string }[]).map(
          (card, i) => (
            <motion.div
              key={card.label}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: i * 0.05 }}
              className="bg-surface-card rounded-xl border border-border-subtle p-4"
            >
              <span className="text-xs text-text-muted">{card.label}</span>
              {card.value !== undefined ? (
                <p className={cn('mt-1 text-2xl font-bold tabular-nums', card.tone)}>
                  {card.value}
                </p>
              ) : (
                <div className="skeleton h-8 w-14 rounded mt-1" />
              )}
            </motion.div>
          )
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* by_weight 条形 */}
        <div className="bg-surface-card rounded-xl border border-border-subtle p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-text-primary">权重分布 by_weight</h3>
            <span className="text-xs text-text-muted">
              共 {weightEntries.reduce((s, [, v]) => s + v, 0)} 条
            </span>
          </div>
          {weightEntries.length === 0 ? (
            <div className="h-32 flex items-center justify-center">
              <p className="text-sm text-text-muted">
                {loading ? '加载中…' : '暂无权重分布数据'}
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {weightEntries.map(([key, value], i) => (
                <div key={key}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-medium text-text-primary">{key}</span>
                    <span className="text-sm font-semibold text-text-primary tabular-nums">
                      {value}
                    </span>
                  </div>
                  <div className="h-2 rounded-full bg-surface-sidebar overflow-hidden">
                    <motion.div
                      className={cn(
                        'h-full rounded-full',
                        WEIGHT_COLORS[i % WEIGHT_COLORS.length]
                      )}
                      initial={{ width: 0 }}
                      animate={{ width: `${(value / weightMax) * 100}%` }}
                      transition={{ duration: 0.6, delay: i * 0.05, ease: 'easeOut' }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* constraints 列表 */}
        <div className="bg-surface-card rounded-xl border border-border-subtle p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-text-primary">惯性约束 constraints</h3>
            <span className="text-xs text-text-muted">
              {data?.constraints.length ?? 0} 条
            </span>
          </div>
          {!data || data.constraints.length === 0 ? (
            <div className="h-32 flex flex-col items-center justify-center gap-2">
              <Anchor className="w-6 h-6 text-text-muted" />
              <p className="text-sm text-text-muted">
                {loading ? '加载中…' : '暂无惯性约束'}
              </p>
            </div>
          ) : (
            <ul className="space-y-2">
              {data.constraints.map((c, i) => (
                <motion.li
                  key={i}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.3, delay: Math.min(i * 0.04, 0.3) }}
                  className="flex items-start gap-2 rounded-lg bg-surface-sidebar px-3 py-2"
                >
                  <ShieldCheck className="w-4 h-4 text-primary shrink-0 mt-0.5" />
                  <span className="text-sm text-text-secondary break-all">{c}</span>
                </motion.li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {toast && (
        <Toast type={toast.type} message={toast.message} onClose={() => setToast(null)} />
      )}
    </div>
  );
};

export default ProfileInertiaPanel;

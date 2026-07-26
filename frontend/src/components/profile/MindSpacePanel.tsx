// FILE: src/components/profile/MindSpacePanel.tsx
// Mind 空间 Tab —— 摘要卡 + 展开全量 + ABC 层统计小卡

import { useMemo, useState } from 'react';
import type { FC } from 'react';
import { motion } from 'framer-motion';
import { Brain, Layers, Loader2, UnfoldVertical } from 'lucide-react';
import { getMindFull } from '@/api/v6';
import type { V6AbcResponse, V6MindFullResponse, V6MindResponse } from '@/types/api';
import { Toast } from '@/components/ui/Toast';
import { JsonTree, previewValue } from './JsonTree';
import { cn } from '@/lib/utils';

type ToastState = {
  type: 'success' | 'error' | 'info' | 'warning';
  message: string;
} | null;

interface MindSpacePanelProps {
  mind: V6MindResponse | null;
  abc: V6AbcResponse | null;
}

function asNumber(v: unknown): number | null {
  if (typeof v === 'number' && Number.isFinite(v)) return v;
  if (typeof v === 'string' && v.trim() !== '' && !Number.isNaN(Number(v))) {
    return Number(v);
  }
  return null;
}

export const MindSpacePanel: FC<MindSpacePanelProps> = ({ mind, abc }) => {
  const [full, setFull] = useState<V6MindFullResponse | null>(null);
  const [expanding, setExpanding] = useState(false);
  const [toast, setToast] = useState<ToastState>(null);

  const handleExpandFull = async () => {
    if (expanding) return;
    setExpanding(true);
    try {
      const res = await getMindFull();
      setFull(res);
      setToast({ type: 'success', message: '已加载全量心智空间' });
    } catch (err) {
      setToast({
        type: 'error',
        message: err instanceof Error ? err.message : '获取全量心智空间失败',
      });
    } finally {
      setExpanding(false);
    }
  };

  // ABC 层统计:数值型顶层字段 → 统计小卡;其余 → 键值行
  const abcNumeric = useMemo(() => {
    if (!abc) return [] as { key: string; value: number }[];
    return Object.entries(abc || {})
      .map(([key, v]) => ({ key, value: asNumber(v) }))
      .filter((e): e is { key: string; value: number } => e.value !== null);
  }, [abc]);

  const abcRest = useMemo(() => {
    if (!abc) return [] as [string, unknown][];
    return Object.entries(abc || {}).filter(([, v]) => asNumber(v) === null);
  }, [abc]);

  const mindEntries = useMemo(() => (mind ? Object.entries(mind || {}) : []), [mind]);

  return (
    <div className="space-y-6">
      {/* ABC 层统计小卡 */}
      <div className="bg-surface-card rounded-xl border border-border-subtle p-6">
        <div className="flex items-center gap-2 mb-4">
          <Layers className="w-4 h-4 text-primary" />
          <h3 className="text-sm font-semibold text-text-primary">ABC 层统计</h3>
        </div>
        {!abc ? (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="rounded-lg bg-surface-sidebar p-3">
                <div className="skeleton h-3 w-14 rounded mb-2" />
                <div className="skeleton h-6 w-10 rounded" />
              </div>
            ))}
          </div>
        ) : (
          <div className="space-y-4">
            {abcNumeric.length > 0 && (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {abcNumeric.map((e, i) => (
                  <motion.div
                    key={e.key}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.3, delay: i * 0.04 }}
                    className="rounded-lg bg-surface-sidebar p-3"
                  >
                    <p className="text-xs text-text-muted truncate" title={e.key}>
                      {e.key}
                    </p>
                    <p className="mt-1 text-xl font-bold text-text-primary tabular-nums">
                      {Number.isInteger(e.value) ? e.value : e.value.toFixed(2)}
                    </p>
                  </motion.div>
                ))}
              </div>
            )}
            {abcRest.length > 0 && (
              <div className="space-y-1.5">
                {abcRest.map(([k, v]) => (
                  <div key={k} className="flex items-baseline gap-2">
                    <span className="text-xs font-medium text-text-muted shrink-0">{k}</span>
                    <span className="text-xs text-text-secondary break-all">
                      {previewValue(v)}
                    </span>
                  </div>
                ))}
              </div>
            )}
            {abcNumeric.length === 0 && abcRest.length === 0 && (
              <p className="text-sm text-text-muted">ABC 层暂无统计数据</p>
            )}
          </div>
        )}
      </div>

      {/* Mind 摘要卡 */}
      <div className="bg-surface-card rounded-xl border border-border-subtle p-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
          <div className="flex items-center gap-2">
            <Brain className="w-4 h-4 text-primary" />
            <h3 className="text-sm font-semibold text-text-primary">心智空间摘要</h3>
            <span className="text-xs text-text-muted">
              {mind ? `${mindEntries.length} 个顶层字段` : '加载中'}
            </span>
          </div>
          <button
            type="button"
            onClick={handleExpandFull}
            disabled={expanding || full !== null}
            className={cn(
              'flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium',
              'bg-surface-card border border-border-subtle text-text-secondary',
              'hover:bg-surface-card-hover hover:text-primary transition-colors',
              'disabled:opacity-50 disabled:cursor-not-allowed'
            )}
          >
            {expanding ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <UnfoldVertical className="w-4 h-4" />
            )}
            {full ? '已展开全量' : '展开全量'}
          </button>
        </div>

        {!mind ? (
          <div className="space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="skeleton h-4 rounded" />
            ))}
          </div>
        ) : mindEntries.length === 0 ? (
          <p className="text-sm text-text-muted">心智空间暂无摘要数据</p>
        ) : (
          <div className="space-y-1.5">
            {mindEntries.map(([k, v]) => (
              <div key={k} className="flex items-baseline gap-2">
                <span className="text-xs font-medium text-text-muted shrink-0">{k}</span>
                <span className="text-xs text-text-secondary break-all">
                  {previewValue(v, 120)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 全量心智空间 */}
      {full && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="bg-surface-card rounded-xl border border-border-subtle p-6"
        >
          <h3 className="text-sm font-semibold text-text-primary mb-4">
            全量心智空间 /v6/mind/full
          </h3>
          <JsonTree value={full} />
        </motion.div>
      )}

      {toast && (
        <Toast type={toast.type} message={toast.message} onClose={() => setToast(null)} />
      )}
    </div>
  );
};

export default MindSpacePanel;

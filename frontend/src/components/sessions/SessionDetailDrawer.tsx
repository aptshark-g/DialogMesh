// FILE: frontend/src/components/sessions/SessionDetailDrawer.tsx
// 会话详情抽屉 — 按 JSONL 记录类型渲染对话轮次与系统事件

import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { AlertCircle, MessageSquare, X, Zap } from 'lucide-react';
import { fetchSessionDetail } from '../../hooks/useV6Sessions';
import type { V6SessionData } from '../../types/api';
import { cn } from '../../lib/utils';
import { Skeleton } from '../ui/Skeleton';

interface SessionDetailDrawerProps {
  filename: string | null;
  onClose: () => void;
}

// ─── JSONL 记录解析 ──────────────────────────────────────────────────────────

interface TurnEntry {
  turn: number;
  timestamp?: number;
  text?: string;
  response_len?: number;
  trace_conf?: number;
  abc_hits?: Record<string, unknown>;
  trackB_tags?: unknown[];
  [key: string]: unknown;
}

interface TypedEntry {
  type: string;
  ts?: number;
  scenario?: string;
  data?: unknown;
  [key: string]: unknown;
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

function isTurnEntry(v: unknown): v is TurnEntry {
  return isRecord(v) && typeof v.turn === 'number';
}

function isTypedEntry(v: unknown): v is TypedEntry {
  return isRecord(v) && typeof v.type === 'string';
}

function formatTs(sec?: number): string {
  if (typeof sec !== 'number' || !Number.isFinite(sec)) return '—';
  return new Date(sec * 1000).toLocaleString('zh-CN', { hour12: false });
}

function summarizeData(data: unknown): string {
  if (data == null) return '';
  const s = JSON.stringify(data, null, 2);
  return s.length > 600 ? `${s.slice(0, 600)}…` : s;
}

// ─── 子视图 ──────────────────────────────────────────────────────────────────

function TurnCard({ entry, index }: { entry: TurnEntry; index: number }) {
  const abc = isRecord(entry.abc_hits) ? entry.abc_hits : null;
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, delay: Math.min(index * 0.04, 0.4) }}
      className="bg-surface-sidebar rounded-lg border border-subtle p-3.5"
    >
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-xs font-semibold text-primary">
          轮次 {entry.turn}
        </span>
        <span className="text-[11px] text-text-muted">
          {formatTs(entry.timestamp)}
        </span>
      </div>
      {entry.text && (
        <p className="text-sm text-text-primary whitespace-pre-wrap break-words">
          {entry.text}
        </p>
      )}
      <div className="flex flex-wrap gap-1.5 mt-2">
        {typeof entry.response_len === 'number' && (
          <span className="px-1.5 py-0.5 rounded bg-surface-card-hover text-[11px] text-text-secondary">
            回复 {entry.response_len} 字符
          </span>
        )}
        {typeof entry.trace_conf === 'number' && (
          <span className="px-1.5 py-0.5 rounded bg-surface-card-hover text-[11px] text-text-secondary">
            置信度 {entry.trace_conf.toFixed(2)}
          </span>
        )}
        {abc && (
          <span className="px-1.5 py-0.5 rounded bg-surface-card-hover text-[11px] text-text-secondary font-mono">
            ABC {['A', 'B', 'C']
              .map((k) => `${k}:${String(abc[k] ?? 0)}`)
              .join(' ')}
          </span>
        )}
      </div>
    </motion.div>
  );
}

function TypedRow({ entry }: { entry: TypedEntry }) {
  return (
    <div className="bg-surface-sidebar rounded-lg border border-subtle p-3">
      <div className="flex items-center gap-2 mb-1">
        <span className="px-1.5 py-0.5 rounded bg-primary/10 text-primary text-[11px] font-medium font-mono">
          {entry.type}
        </span>
        <span className="text-[11px] text-text-muted ml-auto">
          {formatTs(entry.ts)}
        </span>
      </div>
      {entry.data != null && (
        <pre className="text-[11px] text-text-secondary font-mono whitespace-pre-wrap break-all max-h-32 overflow-y-auto">
          {summarizeData(entry.data)}
        </pre>
      )}
    </div>
  );
}

// ─── 抽屉主体 ────────────────────────────────────────────────────────────────

export function SessionDetailDrawer({
  filename,
  onClose,
}: SessionDetailDrawerProps) {
  const [data, setData] = useState<V6SessionData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!filename) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);
    fetchSessionDetail(filename)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : '加载会话详情失败');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [filename]);

  const entries = Array.isArray(data) ? data : [];
  const turns = entries.filter(isTurnEntry);
  const typed = entries.filter(
    (e): e is TypedEntry => isTypedEntry(e) && !isTurnEntry(e)
  );
  const others = entries.filter((e) => !isTypedEntry(e) && !isTurnEntry(e));

  return (
    <AnimatePresence>
      {filename && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 bg-surface-overlay z-drawer"
            onClick={onClose}
            role="presentation"
          />
          <motion.aside
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ duration: 0.3, ease: 'easeOut' }}
            className="fixed inset-y-0 right-0 z-drawer w-full max-w-xl bg-surface-card border-l border-subtle shadow-modal flex flex-col"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-subtle shrink-0">
              <div className="min-w-0">
                <h3 className="text-base font-semibold text-text-primary truncate">
                  {filename}
                </h3>
                <p className="text-xs text-text-muted mt-0.5">
                  {loading
                    ? '加载中…'
                    : `${entries.length} 条记录 · ${turns.length} 个对话轮次`}
                </p>
              </div>
              <button
                type="button"
                onClick={onClose}
                className="p-1.5 rounded-md hover:bg-surface-card-hover text-text-muted hover:text-text-primary transition-colors shrink-0"
                aria-label="关闭详情"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Body */}
            <div className="flex-1 overflow-y-auto p-5 space-y-5">
              {loading && (
                <div className="space-y-3">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <Skeleton key={i} height={72} className="rounded-lg" />
                  ))}
                </div>
              )}

              {error && (
                <div className="flex items-start gap-2 px-4 py-3 rounded-lg bg-status-error/10 text-status-error text-sm">
                  <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
                  <span className="break-all">{error}</span>
                </div>
              )}

              {!loading && !error && entries.length === 0 && (
                <div className="py-16 text-center">
                  <MessageSquare className="h-8 w-8 text-text-muted mx-auto mb-2" />
                  <p className="text-sm text-text-secondary">该会话暂无记录</p>
                </div>
              )}

              {turns.length > 0 && (
                <section>
                  <div className="flex items-center gap-2 mb-2.5">
                    <MessageSquare className="h-3.5 w-3.5 text-text-muted" />
                    <h4 className="text-xs font-semibold text-text-secondary">
                      对话轮次 ({turns.length})
                    </h4>
                  </div>
                  <div className="space-y-2.5">
                    {turns.map((t, i) => (
                      <TurnCard key={`turn-${t.turn}-${i}`} entry={t} index={i} />
                    ))}
                  </div>
                </section>
              )}

              {(typed.length > 0 || others.length > 0) && (
                <section>
                  <div className="flex items-center gap-2 mb-2.5">
                    <Zap className="h-3.5 w-3.5 text-text-muted" />
                    <h4 className="text-xs font-semibold text-text-secondary">
                      系统事件 ({typed.length + others.length})
                    </h4>
                  </div>
                  <div className="space-y-2">
                    {typed.map((e, i) => (
                      <TypedRow key={`typed-${e.type}-${i}`} entry={e} />
                    ))}
                    {others.map((e, i) => (
                      <pre
                        key={`raw-${i}`}
                        className={cn(
                          'bg-surface-sidebar rounded-lg border border-subtle p-3',
                          'text-[11px] text-text-secondary font-mono',
                          'whitespace-pre-wrap break-all max-h-32 overflow-y-auto'
                        )}
                      >
                        {summarizeData(e)}
                      </pre>
                    ))}
                  </div>
                </section>
              )}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

import { useCallback, useEffect, useState } from 'react';
import { MessageSquare, RefreshCw, Send, StickyNote } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Toast } from '@/components/ui/Toast';
import { formatRelativeTime } from '@/lib/utils';
import { getAnnotations, addAnnotation, getAnnotationStats } from '@/api/v6';
import type { V6Annotation, V6AnnotationStatsResponse } from '@/types/api';

interface ToastState {
  key: number;
  type: 'success' | 'error';
  message: string;
}

export function AnnotationsView() {
  const [annotations, setAnnotations] = useState<V6Annotation[]>([]);
  const [stats, setStats] = useState<V6AnnotationStatsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [toast, setToast] = useState<ToastState | null>(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [ann, st] = await Promise.all([
        getAnnotations(),
        getAnnotationStats().catch(() => null),
      ]);
      setAnnotations(ann.annotations);
      setStats(st);
    } catch (err) {
      setError(err instanceof Error ? err.message : '获取注释失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  const handleAdd = async () => {
    const value = text.trim();
    if (!value || submitting) return;
    setSubmitting(true);
    try {
      await addAnnotation(value);
      setText('');
      setToast({ key: Date.now(), type: 'success', message: '注释已添加' });
      await fetchAll();
    } catch (err) {
      setToast({
        key: Date.now(),
        type: 'error',
        message: err instanceof Error ? err.message : '添加注释失败',
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-3xl space-y-4">
      {/* Stats card */}
      <div className="rounded-xl bg-surface-card border border-subtle shadow-card p-4">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-text-primary">注释统计</span>
          <button
            type="button"
            onClick={fetchAll}
            disabled={loading}
            className="p-1.5 rounded-md text-text-muted hover:text-text-primary hover:bg-surface-card-hover transition-colors disabled:opacity-50"
            aria-label="刷新"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
        {stats ? (
          <div className="mt-3 grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="rounded-lg bg-surface border border-subtle px-3 py-2">
              <p className="text-[10px] text-text-muted">总数</p>
              <p className="text-lg font-semibold text-text-primary tabular-nums">{stats.total}</p>
            </div>
            <div className="rounded-lg bg-surface border border-subtle px-3 py-2">
              <p className="text-[10px] text-text-muted">按作者</p>
              <div className="mt-1 space-y-0.5">
                {Object.entries(stats.by_author).length > 0 ? (
                  Object.entries(stats.by_author).map(([author, count]) => (
                    <div key={author} className="flex justify-between text-xs">
                      <span className="text-text-secondary truncate">{author}</span>
                      <span className="text-text-primary tabular-nums">{count}</span>
                    </div>
                  ))
                ) : (
                  <p className="text-xs text-text-muted">暂无</p>
                )}
              </div>
            </div>
            <div className="rounded-lg bg-surface border border-subtle px-3 py-2">
              <p className="text-[10px] text-text-muted">按日期</p>
              <div className="mt-1 space-y-0.5">
                {Object.entries(stats.by_date).length > 0 ? (
                  Object.entries(stats.by_date).map(([date, count]) => (
                    <div key={date} className="flex justify-between text-xs">
                      <span className="text-text-secondary">{date}</span>
                      <span className="text-text-primary tabular-nums">{count}</span>
                    </div>
                  ))
                ) : (
                  <p className="text-xs text-text-muted">暂无</p>
                )}
              </div>
            </div>
          </div>
        ) : (
          <p className="mt-3 text-xs text-text-muted">{loading ? '加载中…' : '暂无统计数据'}</p>
        )}
      </div>

      {/* Add input */}
      <div className="rounded-xl bg-surface-card border border-subtle shadow-card p-4">
        <label className="block text-xs font-semibold text-text-primary mb-2" htmlFor="annotation-input">
          添加注释
        </label>
        <div className="flex items-start gap-2">
          <textarea
            id="annotation-input"
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={2}
            placeholder="记录对当前图谱 / 对话的观察…"
            className="flex-1 px-3 py-2 rounded-md bg-surface border border-subtle text-sm text-text-primary placeholder:text-text-muted outline-none focus:border-primary transition-colors resize-y"
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                handleAdd();
              }
            }}
          />
          <Button size="sm" onClick={handleAdd} loading={submitting} disabled={!text.trim()}>
            <Send className="w-3.5 h-3.5 mr-1" />
            提交
          </Button>
        </div>
        <p className="text-[10px] text-text-muted mt-1.5">Ctrl + Enter 快速提交</p>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-xl border border-red-200 dark:border-red-900 bg-surface-card px-4 py-3">
          <p className="text-sm text-text-secondary">加载失败</p>
          <p className="text-xs text-text-muted mt-1">{error}</p>
        </div>
      )}

      {/* List */}
      <div className="space-y-2">
        {annotations.length === 0 && !loading && !error ? (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <StickyNote className="w-8 h-8 text-text-muted mb-3" />
            <p className="text-sm text-text-secondary">暂无注释</p>
            <p className="text-xs text-text-muted mt-1">在上方输入框添加第一条注释</p>
          </div>
        ) : (
          annotations.map((annotation) => (
            <div
              key={annotation.id}
              className="rounded-xl bg-surface-card border border-subtle shadow-card px-4 py-3"
            >
              <p className="text-sm text-text-primary whitespace-pre-wrap break-words">
                {annotation.text}
              </p>
              <div className="mt-2 flex items-center gap-3 text-[10px] text-text-muted">
                <span className="flex items-center gap-1">
                  <MessageSquare className="w-3 h-3" />
                  {annotation.author}
                </span>
                <span>{formatRelativeTime(annotation.timestamp)}</span>
                <span className="font-mono">{annotation.id}</span>
              </div>
            </div>
          ))
        )}
      </div>

      {toast && (
        <Toast
          key={toast.key}
          type={toast.type}
          message={toast.message}
          onClose={() => setToast(null)}
        />
      )}
    </div>
  );
}

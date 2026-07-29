// FILE: frontend/src/pages/SessionsPage.tsx
// Session 管理 — 持久化概览 + 会话列表 + 详情抽屉 + 文档导入

import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  AlertCircle,
  ChevronRight,
  FileUp,
  MessageSquare,
  Plus,
  RefreshCw,
} from 'lucide-react';
import { cn } from '../lib/utils';
import { getPersistenceGraphs } from '../api/v6';
import type { V6PersistenceGraphsResponse } from '../types/api';
import { useV6Sessions } from '../hooks/useV6Sessions';
import { Toast } from '../components/ui/Toast';
import { Skeleton } from '../components/ui/Skeleton';
import { PersistenceOverview } from '../components/sessions/PersistenceOverview';
import { SessionDetailDrawer } from '../components/sessions/SessionDetailDrawer';
import { IngestDocumentModal } from '../components/sessions/IngestDocumentModal';

interface ToastState {
  type: 'success' | 'error' | 'info';
  message: string;
}

export function SessionsPage() {
  const navigate = useNavigate();
  const { sessions, persistence, loading, error, refresh } = useV6Sessions();

  const [graphs, setGraphs] = useState<V6PersistenceGraphsResponse | null>(null);
  const [graphsLoading, setGraphsLoading] = useState(false);

  const [selected, setSelected] = useState<string | null>(null);
  const [ingestOpen, setIngestOpen] = useState(false);
  const [toast, setToast] = useState<ToastState | null>(null);

  const fetchGraphs = useCallback(async () => {
    setGraphsLoading(true);
    try {
      setGraphs(await getPersistenceGraphs());
    } catch {
      setGraphs(null);
    } finally {
      setGraphsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchGraphs();
  }, [fetchGraphs]);

  const handleRefresh = useCallback(() => {
    refresh();
    fetchGraphs();
  }, [refresh, fetchGraphs]);

  const refreshing = loading || graphsLoading;

  const handleIngestSuccess = useCallback(
    (message: string) => {
      setToast({ type: 'success', message });
      handleRefresh();
    },
    [handleRefresh]
  );

  return (
    <div className="min-h-full flex flex-col max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Session 管理</h1>
          <p className="text-sm text-text-secondary mt-1">
            查看持久化状态与历史会话记录
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleRefresh}
            disabled={refreshing}
            className="p-2 rounded-lg border border-subtle text-text-secondary hover:text-primary hover:border-primary transition-colors disabled:opacity-50"
            aria-label="刷新"
            title="刷新"
          >
            <RefreshCw className={cn('w-4 h-4', refreshing && 'animate-spin')} />
          </button>
          <button
            type="button"
            onClick={() => navigate('/chat')}
            className={[
              'px-4 py-2 rounded-lg border border-primary text-primary',
              'text-sm font-medium hover:bg-primary/10',
              'transition-colors flex items-center gap-2',
            ].join(' ')}
          >
            <Plus className="w-4 h-4" />
            新建 Session
          </button>
          <button
            type="button"
            onClick={() => setIngestOpen(true)}
            className={[
              'px-4 py-2 rounded-lg bg-primary text-white',
              'text-sm font-medium hover:bg-primary-dark',
              'transition-colors flex items-center gap-2',
            ].join(' ')}
          >
            <FileUp className="w-4 h-4" />
            导入文档
          </button>
        </div>
      </div>

      {/* 持久化状态卡 */}
      <PersistenceOverview
        persistence={persistence}
        graphs={graphs}
        loading={loading}
        graphsLoading={graphsLoading}
      />

      {/* 会话列表 */}
      <div className="bg-surface-card rounded-xl border border-subtle shadow-card overflow-hidden">
        <div className="px-5 py-4 border-b border-subtle flex items-center justify-between">
          <h2 className="text-sm font-semibold text-text-primary">
            会话列表
            {!loading && (
              <span className="ml-2 text-xs font-normal text-text-muted">
                共 {sessions.length} 个
              </span>
            )}
          </h2>
          <button
            type="button"
            onClick={handleRefresh}
            disabled={refreshing}
            className="flex items-center gap-1.5 text-xs text-text-secondary hover:text-primary transition-colors disabled:opacity-50"
          >
            <RefreshCw className={cn('h-3.5 w-3.5', refreshing && 'animate-spin')} />
            刷新
          </button>
        </div>

        {error && (
          <div className="flex items-start gap-2 px-5 py-3 bg-status-error/10 text-status-error text-sm">
            <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
            <span className="break-all">{error}</span>
          </div>
        )}

        {loading && sessions.length === 0 ? (
          <div className="p-5 space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} height={60} className="rounded-lg" />
            ))}
          </div>
        ) : sessions.length === 0 ? (
          <div className="px-5 py-16 text-center">
            <MessageSquare className="h-10 w-10 text-text-muted mx-auto mb-3" />
            <p className="text-sm text-text-secondary">暂无会话记录</p>
            <p className="text-xs text-text-muted mt-1">
              点击"新建 Session"开始对话,或"导入文档"写入外部知识
            </p>
          </div>
        ) : (
          <div className="divide-y divide-border-subtle">
            {sessions.map((session, idx) => {
              const active = selected === session.name;
              return (
                <motion.button
                  key={session.name}
                  type="button"
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.3, delay: Math.min(idx * 0.05, 0.5) }}
                  onClick={() => setSelected(session.name)}
                  className={cn(
                    'w-full flex items-center gap-4 px-5 py-4 text-left transition-colors group',
                    active ? 'bg-primary/10' : 'hover:bg-surface-card-hover'
                  )}
                >
                  <div
                    className={cn(
                      'h-9 w-9 rounded-lg flex items-center justify-center shrink-0',
                      active ? 'bg-primary/20' : 'bg-surface-sidebar'
                    )}
                  >
                    <MessageSquare className="h-4 w-4 text-primary" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-text-primary truncate">
                      {session.name}
                    </p>
                    <p className="text-xs text-text-muted mt-0.5">
                      {(session.size / 1024).toFixed(1)} KB
                    </p>
                  </div>
                  <ChevronRight
                    className={cn(
                      'h-4 w-4 shrink-0 transition-colors',
                      active
                        ? 'text-primary'
                        : 'text-text-muted group-hover:text-primary'
                    )}
                  />
                </motion.button>
              );
            })}
          </div>
        )}
      </div>

      {/* 会话详情抽屉 */}
      <SessionDetailDrawer filename={selected} onClose={() => setSelected(null)} />

      {/* 文档导入 Modal */}
      <IngestDocumentModal
        isOpen={ingestOpen}
        onClose={() => setIngestOpen(false)}
        onSuccess={handleIngestSuccess}
      />

      {/* Toast */}
      {toast && (
        <Toast
          key={`${toast.type}-${toast.message}`}
          type={toast.type}
          message={toast.message}
          onClose={() => setToast(null)}
        />
      )}
    </div>
  );
}

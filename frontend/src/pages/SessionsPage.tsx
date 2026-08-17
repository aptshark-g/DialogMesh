// FILE: frontend/src/pages/SessionsPage.tsx
// Session 管理 — 持久化概览 + 会话列表 + 详情抽屉 + 文档导入

import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { specMove } from '@/lib/spec';
import { motion } from 'framer-motion';
import {
  AlertCircle,
  ChevronRight,
  FileUp,
  FolderPlus,
  MessageSquare,
  Plus,
  RefreshCw,
  X,
} from 'lucide-react';
import { cn } from '../lib/utils';
import { getPersistenceGraphs } from '../api/v6';
import type { V6PersistenceGraphsResponse } from '../types/api';
import { useV6Sessions } from '../hooks/useV6Sessions';
import { useProjectStore } from '../stores/projectStore';
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

  // P2 项目组:激活项目过滤 + 会话归属(localStorage, 后端落地见 B15/B16)
  const projects = useProjectStore((s) => s.projects);
  const sessionProject = useProjectStore((s) => s.sessionProject);
  const activeProjectId = useProjectStore((s) => s.activeProjectId);
  const setActiveProject = useProjectStore((s) => s.setActiveProject);
  const assignSession = useProjectStore((s) => s.assignSession);
  const [assignFor, setAssignFor] = useState<string | null>(null);

  const activeProject = projects.find((p) => p.id === activeProjectId) ?? null;
  const visibleSessions = activeProject
    ? sessions.filter((s) => sessionProject[s.name] === activeProject.id)
    : sessions;

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
    <div className="min-h-full flex flex-col max-w-5xl mx-auto px-6 lg:px-10 pt-6 pb-10 overflow-y-auto">
      {assignFor && (
        <div className="fixed inset-0 z-10" onClick={() => setAssignFor(null)} aria-hidden="true" />
      )}
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
            onClick={() => navigate('/chat/new')}
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
      <div className="card-liquid shadow-card rounded-xl">
        <div className="px-5 py-4 border-b border-subtle flex items-center justify-between">
          <h2 className="text-sm font-semibold text-text-primary flex items-center">会话列表
            {!loading && (<span className="ml-2 text-xs font-normal text-text-muted">共 {visibleSessions.length} 个</span>)}
            {activeProject && (
              <span className="ml-2 flex items-center gap-1.5 text-[11px] font-normal text-text-secondary bg-wash rounded-full pl-2 pr-1 py-0.5">
                <span className="w-2 h-2 rounded-[3px] shrink-0" style={{ background: activeProject.color }} />
                {activeProject.name}
                <button
                  type="button"
                  onClick={() => setActiveProject(null)}
                  aria-label="清除项目过滤"
                  className="p-0.5 rounded-full text-text-muted hover:text-text-primary transition-colors"
                >
                  <X className="w-3 h-3" />
                </button>
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
        ) : visibleSessions.length === 0 ? (
          <div className="px-5 py-16 text-center">
            <MessageSquare className="h-10 w-10 text-text-muted mx-auto mb-3" />
            <p className="text-sm text-text-secondary">「{activeProject?.name}」下暂无会话</p>
            <p className="text-xs text-text-muted mt-1">在会话行上点归入按钮,可把会话放进该项目</p>
          </div>
        ) : (
          <div className="divide-y divide-border-subtle">
            {visibleSessions.map((session, idx) => {
              const active = selected === session.name;
              return (
                <motion.div
                  key={session.name}
                  role="button"
                  tabIndex={0}
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
                    <p className="text-xs text-text-muted mt-0.5 flex items-center gap-1.5">
                      {sessionProject[session.name] && projects.find((p) => p.id === sessionProject[session.name]) && (
                        <span
                          className="w-2 h-2 rounded-[3px] shrink-0"
                          style={{ background: projects.find((p) => p.id === sessionProject[session.name])!.color }}
                        />
                      )}
                      {(session.size / 1024).toFixed(1)} KB
                    </p>
                  </div>
                  {/* P2: 归入项目 */}
                  <div className="relative shrink-0" onClick={(e) => e.stopPropagation()}>
                    <button
                      type="button"
                      onClick={() => setAssignFor(assignFor === session.name ? null : session.name)}
                      aria-label={`把 ${session.name} 归入项目`}
                      title="归入项目"
                      className={cn(
                        'p-1.5 rounded-md transition-colors hover:bg-wash',
                        sessionProject[session.name]
                          ? 'text-primary'
                          : 'text-text-muted hover:text-primary'
                      )}
                    >
                      <FolderPlus className="h-4 w-4" />
                    </button>
                    {assignFor === session.name && (
                      <div onPointerMove={specMove}
                      className="spec-panel absolute right-0 top-8 z-dropdown w-44 rounded-xl glass-panel overflow-hidden">
                        {projects.length === 0 && (
                          <div className="px-3 py-2.5 text-[11px] text-text-muted">暂无项目,请先在侧栏新建</div>
                        )}
                        {projects.map((p) => (
                          <button
                            key={p.id}
                            type="button"
                            onClick={() => { assignSession(session.name, p.id); setAssignFor(null); }}
                            className="w-full flex items-center gap-2 px-3 py-2 text-left text-xs text-text-secondary hover:bg-wash hover:text-text-primary transition-colors"
                          >
                            <span className="w-2.5 h-2.5 rounded-[4px] shrink-0" style={{ background: p.color }} />
                            <span className="truncate">{p.name}</span>
                            {sessionProject[session.name] === p.id && <span className="ml-auto text-primary">✓</span>}
                          </button>
                        ))}
                        {sessionProject[session.name] && (
                          <button
                            type="button"
                            onClick={() => { assignSession(session.name, null); setAssignFor(null); }}
                            className="w-full px-3 py-2 text-left text-xs text-text-muted hover:bg-wash hover:text-text-primary transition-colors border-t border-hairline"
                          >
                            移出项目
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                  <ChevronRight
                    className={cn(
                      'h-4 w-4 shrink-0 transition-colors',
                      active
                        ? 'text-primary'
                        : 'text-text-muted group-hover:text-primary'
                    )}
                  />
                </motion.div>
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

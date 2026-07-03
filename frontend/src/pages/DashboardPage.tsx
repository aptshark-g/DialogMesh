// FILE: frontend/src/pages/DashboardPage.tsx

import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { cn, formatRelativeTime } from '../lib/utils';
import { createSession, getHealth, getSessionStatus } from '../lib/api';
import type { SessionStatusResponse } from '../types/api';
import { StatusBadge } from '../components/StatusBadge';
import {
  Plus,
  MessageSquare,
  Activity,
  Server,
  ArrowRight,
  Loader2,
  RefreshCw,
  Trash2,
  BarChart3,
} from 'lucide-react';
import {
  TrendChart,
  IntentDistribution,
  WordCloud,
} from '../components/analytics';
import { useAnalyticsStore } from '../stores/analyticsStore';

interface SessionMeta {
  sessionId: string;
  createdAt: string;
  status?: SessionStatusResponse;
}

export function DashboardPage() {
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<SessionMeta[]>([]);
  const [health, setHealth] = useState<{ ok: boolean; info?: Record<string, unknown> } | null>(null);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);

  const computeAnalytics = useAnalyticsStore((s) => s.computeAnalytics);
  const trendData = useAnalyticsStore((s) => s.trendData);
  const intentDistribution = useAnalyticsStore((s) => s.intentDistribution);
  const wordCloud = useAnalyticsStore((s) => s.wordCloud);

  // 从 localStorage 读取会话列表
  const loadStoredSessions = useCallback(() => {
    try {
      const raw = localStorage.getItem('dialogmesh_sessions');
      if (raw) {
        const ids: string[] = JSON.parse(raw);
        const metas: SessionMeta[] = ids.map((id) => {
          const created = localStorage.getItem(`dialogmesh_session_${id}_created`) || '';
          return { sessionId: id, createdAt: created };
        });
        setSessions(metas);
      }
    } catch {
      // 忽略解析错误
    }
  }, []);

  const fetchHealth = useCallback(async () => {
    try {
      const info = await getHealth();
      setHealth({ ok: true, info });
    } catch {
      setHealth({ ok: false });
    }
  }, []);

  const fetchSessionStatuses = useCallback(async () => {
    setLoading(true);
    const updated = await Promise.all(
      sessions.map(async (meta) => {
        try {
          const status = await getSessionStatus(meta.sessionId);
          return { ...meta, status };
        } catch {
          return meta;
        }
      })
    );
    setSessions(updated);
    setLoading(false);
  }, [sessions]);

  useEffect(() => {
    loadStoredSessions();
    fetchHealth();
  }, [loadStoredSessions, fetchHealth]);

  // Compute analytics whenever sessions change
  useEffect(() => {
    computeAnalytics();
  }, [computeAnalytics, sessions.length]);

  const handleCreateSession = async () => {
    setCreating(true);
    try {
      const resp = await createSession();
      const stored = JSON.parse(localStorage.getItem('dialogmesh_sessions') || '[]') as string[];
      stored.push(resp.session_id);
      localStorage.setItem('dialogmesh_sessions', JSON.stringify(stored));
      localStorage.setItem(`dialogmesh_session_${resp.session_id}_created`, resp.created_at);
      loadStoredSessions();
      navigate(`/chat/${resp.session_id}`);
    } catch (err) {
      alert(err instanceof Error ? err.message : '创建会话失败');
    } finally {
      setCreating(false);
    }
  };

  const handleDeleteSession = (sessionId: string) => {
    if (!confirm('确定要删除此会话记录吗？')) return;
    const stored = JSON.parse(localStorage.getItem('dialogmesh_sessions') || '[]') as string[];
    const filtered = stored.filter((id) => id !== sessionId);
    localStorage.setItem('dialogmesh_sessions', JSON.stringify(filtered));
    localStorage.removeItem(`dialogmesh_session_${sessionId}_created`);
    loadStoredSessions();
  };

  const activeCount = sessions.filter((s) => s.status?.state === 'active' || s.status?.state === 'processing').length;
  const totalTurns = sessions.reduce((sum, s) => sum + (s.status?.current_turn || 0), 0);

  return (
    <div className="min-h-screen bg-surface-main">
      {/* Header */}
      <header className="bg-surface-card border-b border-gray-200">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-xl bg-primary flex items-center justify-center">
              <MessageSquare className="h-5 w-5 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-text-primary">DialogMesh</h1>
              <p className="text-xs text-text-muted">v3.0 多层 LLM 认知架构</p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {health && (
              <div className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium',
                health.ok ? 'bg-status-success/10 text-status-success' : 'bg-status-error/10 text-status-error'
              )}>
                <Server className="h-3.5 w-3.5" />
                {health.ok ? 'API 正常' : 'API 离线'}
              </div>
            )}
            <button
              onClick={handleCreateSession}
              disabled={creating}
              className="flex items-center gap-2 rounded-lg bg-primary text-white px-4 py-2.5 text-sm font-medium hover:bg-primary-dark transition-colors disabled:opacity-50"
            >
              {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              新建会话
            </button>
          </div>
        </div>
      </header>

      {/* Stats */}
      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.1 }}
            className="bg-surface-card rounded-xl border border-gray-200 p-5"
          >
            <div className="flex items-center gap-2 text-text-muted mb-2">
              <MessageSquare className="h-4 w-4" />
              <span className="text-xs font-medium">总会话数</span>
            </div>
            <p className="text-2xl font-bold text-text-primary">{sessions.length}</p>
          </motion.div>
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.2 }}
            className="bg-surface-card rounded-xl border border-gray-200 p-5"
          >
            <div className="flex items-center gap-2 text-text-muted mb-2">
              <Activity className="h-4 w-4" />
              <span className="text-xs font-medium">活跃会话</span>
            </div>
            <p className="text-2xl font-bold text-text-primary">{activeCount}</p>
          </motion.div>
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.3 }}
            className="bg-surface-card rounded-xl border border-gray-200 p-5"
          >
            <div className="flex items-center gap-2 text-text-muted mb-2">
              <Server className="h-4 w-4" />
              <span className="text-xs font-medium">总对话轮次</span>
            </div>
            <p className="text-2xl font-bold text-text-primary">{totalTurns}</p>
          </motion.div>
        </div>

        {/* Analytics Grid */}
        <div className="mb-8">
          <div className="flex items-center gap-2 mb-4">
            <BarChart3 className="h-4 w-4 text-text-muted" />
            <h2 className="text-sm font-semibold text-text-primary">数据分析</h2>
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* Trend Chart - takes full width on mobile, 1 col on lg */}
            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: 0.15 }}
              className="lg:col-span-2 bg-surface-card rounded-xl border border-gray-200 p-5"
            >
              <TrendChart data={trendData} className="h-full" />
            </motion.div>
            {/* Intent Distribution */}
            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: 0.25 }}
              className="bg-surface-card rounded-xl border border-gray-200 p-5"
            >
              <IntentDistribution data={intentDistribution} className="h-full" />
            </motion.div>
            {/* Word Cloud - spans full width */}
            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: 0.35 }}
              className="lg:col-span-3 bg-surface-card rounded-xl border border-gray-200 p-5"
            >
              <WordCloud data={wordCloud} className="h-full" />
            </motion.div>
          </div>
        </div>

        {/* Sessions */}
        <div className="bg-surface-card rounded-xl border border-gray-200 overflow-hidden">
          <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-text-primary">会话列表</h2>
            <button
              onClick={fetchSessionStatuses}
              disabled={loading || sessions.length === 0}
              className="flex items-center gap-1.5 text-xs text-text-secondary hover:text-primary transition-colors disabled:opacity-50"
            >
              <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin')} />
              刷新状态
            </button>
          </div>

          {sessions.length === 0 ? (
            <div className="px-5 py-16 text-center">
              <MessageSquare className="h-10 w-10 text-text-muted mx-auto mb-3" />
              <p className="text-sm text-text-secondary">暂无会话</p>
              <p className="text-xs text-text-muted mt-1">点击右上角"新建会话"开始对话</p>
            </div>
          ) : (
            <div className="divide-y divide-gray-100">
              {sessions.map((session, idx) => (
                <motion.div
                  key={session.sessionId}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.3, delay: idx * 0.05 }}
                  className="flex items-center gap-4 px-5 py-4 hover:bg-gray-50/50 transition-colors group"
                >
                  <div className="h-9 w-9 rounded-lg bg-surface-sidebar flex items-center justify-center shrink-0">
                    <MessageSquare className="h-4 w-4 text-primary" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-text-primary truncate">
                        {session.sessionId}
                      </span>
                      <StatusBadge state={session.status?.state || 'idle'} showLabel={false} />
                    </div>
                    <div className="flex items-center gap-3 mt-0.5">
                      <span className="text-xs text-text-muted">
                        Turn {session.status?.current_turn || 0}
                      </span>
                      {session.createdAt && (
                        <span className="text-xs text-text-muted">
                          {formatRelativeTime(session.createdAt)}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleDeleteSession(session.sessionId)}
                      className="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg text-text-muted hover:text-status-error hover:bg-status-error/10 transition-all"
                      title="删除"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                    <button
                      onClick={() => navigate(`/chat/${session.sessionId}`)}
                      className="flex items-center gap-1 rounded-lg bg-primary/10 text-primary px-3 py-1.5 text-xs font-medium hover:bg-primary/20 transition-colors"
                    >
                      进入
                      <ArrowRight className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </motion.div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

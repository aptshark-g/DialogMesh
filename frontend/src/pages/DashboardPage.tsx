// FILE: frontend/src/pages/DashboardPage.tsx

import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { cn } from '../lib/utils';
import { getHealth } from '../api/v4';
import { useV6Sessions } from '../hooks/useV6Sessions';
import {
  Plus,
  MessageSquare,
  Server,
  ArrowRight,
  RefreshCw,
  BarChart3,
  Search,
} from 'lucide-react';
import {
  TrendChart,
  IntentDistribution,
  WordCloud,
} from '../components/analytics';
import { useAnalyticsStore } from '../stores/analyticsStore';

export function DashboardPage() {
  const navigate = useNavigate();
  const { sessions, loading, error, refresh } = useV6Sessions();
  const [health, setHealth] = useState<{ ok: boolean; status?: string } | null>(null);
  // 2026-08-17: 会话列表关键词搜索 + 滚动增量加载（电商式懒加载, 防全量渲染卡死）
  const [query, setQuery] = useState('');
  const [visibleCount, setVisibleCount] = useState(20);
  const PAGE_STEP = 20;
  const loadMoreRef = useRef<HTMLDivElement>(null);

  const filteredSessions = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return sessions;
    return sessions.filter((s) => s.name.toLowerCase().includes(q));
  }, [sessions, query]);

  useEffect(() => {
    setVisibleCount(PAGE_STEP);
  }, [query]);

  useEffect(() => {
    const el = loadMoreRef.current;
    if (!el || filteredSessions.length <= visibleCount) return;
    const obs = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          setVisibleCount((c) => Math.min(c + PAGE_STEP, filteredSessions.length));
        }
      },
      { rootMargin: '240px' }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [filteredSessions.length, visibleCount]);

  const computeAnalytics = useAnalyticsStore((s) => s.computeAnalytics);
  const trendData = useAnalyticsStore((s) => s.trendData);
  const intentDistribution = useAnalyticsStore((s) => s.intentDistribution);
  const wordCloud = useAnalyticsStore((s) => s.wordCloud);

  const fetchHealth = useCallback(async () => {
    try {
      const resp = await getHealth();
      setHealth({ ok: true, status: resp.status });
    } catch {
      setHealth({ ok: false });
    }
  }, []);

  useEffect(() => {
    fetchHealth();
  }, [fetchHealth]);

  // Compute analytics whenever sessions change
  useEffect(() => {
    computeAnalytics();
  }, [computeAnalytics, sessions.length]);

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
              <p className="text-xs text-text-muted">多层 LLM 认知架构</p>
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
              onClick={() => navigate('/chat/new')}
              className="flex items-center gap-2 rounded-lg bg-primary text-white px-4 py-2.5 text-sm font-medium hover:bg-primary-dark transition-colors"
            >
              <Plus className="h-4 w-4" />
              新建会话
            </button>
          </div>
        </div>
      </header>

      {/* Stats */}
      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-8">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.1 }}
            className="card-liquid shadow-card rounded-xl p-5"
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
            className="card-liquid shadow-card rounded-xl p-5"
          >
            <div className="flex items-center gap-2 text-text-muted mb-2">
              <Server className="h-4 w-4" />
              <span className="text-xs font-medium">API 状态</span>
            </div>
            <p className="text-2xl font-bold text-text-primary">
              {health?.ok ? '在线' : '离线'}
            </p>
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
              className="lg:col-span-2 card-liquid shadow-card rounded-xl p-5"
            >
              <TrendChart data={trendData} className="h-full" />
            </motion.div>
            {/* Intent Distribution */}
            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: 0.25 }}
              className="card-liquid shadow-card rounded-xl p-5"
            >
              <IntentDistribution data={intentDistribution} className="h-full" />
            </motion.div>
            {/* Word Cloud - spans full width */}
            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: 0.35 }}
              className="lg:col-span-3 card-liquid shadow-card rounded-xl p-5"
            >
              <WordCloud data={wordCloud} className="h-full" />
            </motion.div>
          </div>
        </div>

        {/* Sessions */}
        <div className="card-liquid shadow-card rounded-xl overflow-hidden">
          <div className="px-5 py-4 border-b border-gray-100 space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-text-primary">
                会话列表
                {!loading && (
                  <span className="ml-2 text-xs font-normal text-text-muted">
                    共 {filteredSessions.length} 个{query && `（匹配 "${query.trim()}"）`}
                  </span>
                )}
              </h2>
              <button
                onClick={refresh}
                disabled={loading}
                className="flex items-center gap-1.5 text-xs text-text-secondary hover:text-primary transition-colors disabled:opacity-50"
              >
                <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin')} />
                刷新
              </button>
            </div>
            <div className="relative">
              <Search className="h-3.5 w-3.5 text-text-muted absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="搜索会话关键词…"
                aria-label="搜索会话"
                className="w-full bg-wash rounded-lg pl-8 pr-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-1 focus:ring-primary/40"
              />
            </div>
          </div>

          {error && (
            <div className="px-5 py-4 bg-status-error/5 text-status-error text-sm">
              {error}
            </div>
          )}

          {sessions.length === 0 ? (
            <div className="px-5 py-16 text-center">
              <MessageSquare className="h-10 w-10 text-text-muted mx-auto mb-3" />
              <p className="text-sm text-text-secondary">暂无会话</p>
              <p className="text-xs text-text-muted mt-1">点击右上角"新建会话"开始对话</p>
            </div>
          ) : filteredSessions.length === 0 ? (
            <div className="px-5 py-16 text-center">
              <Search className="h-10 w-10 text-text-muted mx-auto mb-3" />
              <p className="text-sm text-text-secondary">未找到匹配「{query.trim()}」的会话</p>
            </div>
          ) : (
            <div className="divide-y divide-gray-100">
              {filteredSessions.slice(0, visibleCount).map((session, idx) => (
                <motion.div
                  key={session.name}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.25, delay: Math.min(idx * 0.02, 0.3) }}
                  className="flex items-center gap-4 px-5 py-4 hover:bg-gray-50/50 transition-colors group"
                >
                  <div className="h-9 w-9 rounded-lg bg-surface-sidebar flex items-center justify-center shrink-0">
                    <MessageSquare className="h-4 w-4 text-primary" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-text-primary truncate">
                        {session.name}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 mt-0.5">
                      <span className="text-xs text-text-muted">
                        {(session.size / 1024).toFixed(1)} KB
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => navigate('/chat')}
                      className="flex items-center gap-1 rounded-lg bg-primary/10 text-primary px-3 py-1.5 text-xs font-medium hover:bg-primary/20 transition-colors"
                    >
                      进入
                      <ArrowRight className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </motion.div>
              ))}
              {filteredSessions.length > visibleCount && (
                <div
                  ref={loadMoreRef}
                  className="flex items-center justify-center py-4 text-xs text-text-muted"
                >
                  滚动加载更多…（{visibleCount}/{filteredSessions.length}）
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

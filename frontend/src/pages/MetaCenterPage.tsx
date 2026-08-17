// FILE: src/pages/MetaCenterPage.tsx
// 元认知中心 — 概览(统计/扫描/复盘) · 审核队列 · 版本控制(回滚)

import { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import {
  Brain,
  LayoutDashboard,
  ListChecks,
  GitBranch,
  RefreshCw,
  ScanSearch,
  FileText,
  Loader2,
  TrendingUp,
  TrendingDown,
  Minus,
  RotateCcw,
  Inbox,
  GitCommit,
  Search,
  ShieldCheck,
  Gavel,
  Trees,
} from 'lucide-react';
import {
  getMetaStats,
  getMetaQueue,
  triggerMetaScan,
  triggerMetaRetrospect,
  getVersions,
  rollbackVersion,
  getAgentTrees,
} from '../api/v6';
import type {
  V6MetaStatsResponse,
  V6MetaQueueResponse,
  V6MetaRetrospectResponse,
  V6VersionCommit,
  V6VersionsResponse,
  V6AgentTreesResponse,
} from '../types/api';
import { useUIStore } from '../stores/uiStore';
import { Toast } from '../components/ui/Toast';
import { Badge } from '../components/ui/Badge';
import { Skeleton } from '../components/ui/Skeleton';
import { GovernancePanel } from '../components/meta/GovernancePanel';
import { cn } from '../lib/utils';

// ─── 8 类可版本化数据 ───
const VERSION_CATEGORIES = [
  'profile',
  'graph',
  'tree',
  'objects',
  'relations',
  'rules',
  'annotations',
  'config',
] as const;

type MetaTab = 'overview' | 'queue' | 'versions' | 'trees' | 'governance';

interface ToastState {
  id: number;
  type: 'success' | 'error' | 'warning' | 'info';
  message: string;
}

const VERDICT_STYLE: Record<string, { bar: string; text: string; badge: string }> = {
  approved: { bar: 'bg-status-success', text: 'text-status-success', badge: 'success' },
  rejected: { bar: 'bg-status-error', text: 'text-status-error', badge: 'error' },
  escalate: { bar: 'bg-status-warning', text: 'text-status-warning', badge: 'warning' },
};

const verdictStyle = (verdict: string) =>
  VERDICT_STYLE[verdict] ?? { bar: 'bg-status-info', text: 'text-status-info', badge: 'info' };

const isRecord = (v: unknown): v is Record<string, unknown> =>
  typeof v === 'object' && v !== null && !Array.isArray(v);

const fmtValue = (v: unknown): string =>
  isRecord(v) || Array.isArray(v) ? JSON.stringify(v) : String(v);

// ts 可能是秒或毫秒
const formatTs = (ts: number): string => {
  const ms = ts < 1e12 ? ts * 1000 : ts;
  const d = new Date(ms);
  if (Number.isNaN(d.getTime())) return String(ts);
  return d.toLocaleString('zh-CN', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

// accuracy 可能是 0-1 或 0-100
const normalizeAccuracy = (acc: number): number =>
  acc <= 1 ? Math.round(acc * 100) : Math.round(acc);

const fadeIn = (delay: number) => ({
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.35, delay },
});

// ─── 统计小卡 ───
const StatTile = ({ label, value, accent }: { label: string; value: string | number; accent?: string }) => (
  <div className="card-liquid shadow-card rounded-xl p-5">
    <span className="text-xs text-text-muted">{label}</span>
    <p className={cn('mt-2 text-2xl font-semibold', accent ?? 'text-text-primary')}>{value}</p>
  </div>
);

// ─── 通用键值行 ───
const KvRows = ({ data }: { data: Record<string, unknown> }) => (
  <div className="space-y-2">
    {Object.entries(data).map(([k, v]) => (
      <div key={k} className="flex items-start justify-between gap-2">
        <span className="text-xs text-text-muted shrink-0">{k}</span>
        <span className="text-sm text-text-primary font-mono text-right break-all">{fmtValue(v)}</span>
      </div>
    ))}
  </div>
);

export function MetaCenterPage() {
  const confirm = useUIStore((s) => s.confirm);

  const [activeTab, setActiveTab] = useState<MetaTab>('overview');

  // ─── 概览 / 队列数据(30s 轮询) ───
  const [stats, setStats] = useState<V6MetaStatsResponse | null>(null);
  const [queue, setQueue] = useState<V6MetaQueueResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ─── 动作状态 ───
  const [scanLoading, setScanLoading] = useState(false);
  const [retrospectLoading, setRetrospectLoading] = useState(false);
  const [retroTarget, setRetroTarget] = useState('');
  const [retroCategory, setRetroCategory] = useState('');
  const [retrospect, setRetrospect] = useState<V6MetaRetrospectResponse | null>(null);

  // ─── 版本控制 ───
  const [versionCategory, setVersionCategory] = useState<string>(VERSION_CATEGORIES[0]);
  const [versionTarget, setVersionTarget] = useState('');
  const [appliedTarget, setAppliedTarget] = useState('');
  const [versions, setVersions] = useState<V6VersionsResponse | null>(null);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [versionsError, setVersionsError] = useState<string | null>(null);
  const [rollbackId, setRollbackId] = useState<string | null>(null);

  // ─── 七树白盒 ───
  const [trees, setTrees] = useState<V6AgentTreesResponse | null>(null);
  const [treesLoading, setTreesLoading] = useState(false);
  const [treesError, setTreesError] = useState<string | null>(null);
  const [treeQuery, setTreeQuery] = useState('');
  const [treeHits, setTreeHits] = useState<V6AgentTreesResponse | null>(null);
  const [treesSearching, setTreesSearching] = useState(false);

  // ─── Toast ───
  const [toast, setToast] = useState<ToastState | null>(null);
  const showToast = useCallback((type: ToastState['type'], message: string) => {
    setToast({ id: Date.now(), type, message });
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [statsRes, queueRes] = await Promise.all([
        getMetaStats().catch(() => null),
        getMetaQueue().catch(() => null),
      ]);
      if (!statsRes && !queueRes) {
        setError('无法连接元认知服务,请检查 DialogMesh API 是否运行');
      }
      setStats(statsRes);
      setQueue(queueRes);
    } catch (err) {
      setError(err instanceof Error ? err.message : '获取元认知数据失败');
    } finally {
      setLoading(false);
    }
  }, []);

  // 首次加载 + 30s 轮询(参考 useV6Profile 的轮询写法)
  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 30000);
    return () => clearInterval(timer);
  }, [refresh]);

  const fetchVersions = useCallback(async (category: string, target: string) => {
    setVersionsLoading(true);
    setVersionsError(null);
    try {
      const trimmed = target.trim();
      const res = await getVersions(category, trimmed ? trimmed : undefined);
      setVersions(res);
    } catch (err) {
      setVersions(null);
      setVersionsError(err instanceof Error ? err.message : '获取版本列表失败');
    } finally {
      setVersionsLoading(false);
    }
  }, []);

  // category / 已应用 target 变化时加载版本列表
  useEffect(() => {
    fetchVersions(versionCategory, appliedTarget);
  }, [versionCategory, appliedTarget, fetchVersions]);

  // ─── 七树加载 / 联邦查询 ───
  const fetchTrees = useCallback(async () => {
    setTreesLoading(true);
    setTreesError(null);
    try {
      const res = await getAgentTrees();
      setTrees(res);
    } catch (err) {
      setTreesError(err instanceof Error ? err.message : '获取七树数据失败');
    } finally {
      setTreesLoading(false);
    }
  }, []);

  const searchTrees = useCallback(async () => {
    const q = treeQuery.trim();
    if (!q) {
      setTreeHits(null);
      return;
    }
    setTreesSearching(true);
    try {
      const res = await getAgentTrees(undefined, q);
      setTreeHits(res);
    } catch (err) {
      setTreeHits({
        error: err instanceof Error ? err.message : '联邦查询失败',
      });
    } finally {
      setTreesSearching(false);
    }
  }, [treeQuery]);

  // 进入七树 tab 时加载一次
  useEffect(() => {
    if (activeTab === 'trees' && !trees) {
      fetchTrees();
    }
  }, [activeTab, trees, fetchTrees]);

  // ─── 主动扫描 ───
  const handleScan = useCallback(async () => {
    setScanLoading(true);
    try {
      const res = await triggerMetaScan();
      showToast(res.triggered ? 'success' : 'info', res.triggered ? '元认知扫描已触发' : '扫描请求已提交');
      refresh();
    } catch (err) {
      showToast('error', err instanceof Error ? err.message : '触发扫描失败');
    } finally {
      setScanLoading(false);
    }
  }, [refresh, showToast]);

  // ─── 生成复盘报告 ───
  const handleRetrospect = useCallback(async () => {
    setRetrospectLoading(true);
    try {
      const res = await triggerMetaRetrospect(
        retroTarget.trim() || undefined,
        retroCategory || undefined,
      );
      setRetrospect(res);
      showToast('success', '复盘报告已生成');
    } catch (err) {
      showToast('error', err instanceof Error ? err.message : '生成复盘报告失败');
    } finally {
      setRetrospectLoading(false);
    }
  }, [retroTarget, retroCategory, showToast]);

  // ─── 回滚 ───
  const doRollback = useCallback(async (commitId: string) => {
    setRollbackId(commitId);
    try {
      const res = await rollbackVersion(versionCategory, commitId);
      if (res.rolled_back) {
        showToast('success', `已回滚到 ${commitId}`);
      } else {
        showToast('warning', '回滚请求已提交,但服务端未确认');
      }
      fetchVersions(versionCategory, appliedTarget);
    } catch (err) {
      showToast('error', err instanceof Error ? err.message : '回滚失败');
    } finally {
      setRollbackId(null);
    }
  }, [versionCategory, appliedTarget, fetchVersions, showToast]);

  const handleRollback = useCallback((commit: V6VersionCommit) => {
    confirm({
      title: '确认回滚',
      message: `确定将 ${versionCategory} 回滚到 commit "${commit.id}" 吗?当前状态将被该版本覆盖。`,
      confirmText: '回滚',
      cancelText: '取消',
      onConfirm: () => { void doRollback(commit.id); },
    });
  }, [confirm, versionCategory, doRollback]);

  // ─── 队列数据整形(响应为开放字典,做防御性解析) ───
  const queueItems: unknown[] | null = (() => {
    if (!queue) return null;
    if (Array.isArray(queue)) return queue;
    for (const key of ['items', 'queue', 'pending', 'reviews', 'entries']) {
      const v = queue[key];
      if (Array.isArray(v)) return v;
    }
    return null;
  })();
  const queueScalars: [string, unknown][] = queue && !Array.isArray(queue)
    ? Object.entries(queue).filter(([, v]) => !Array.isArray(v) && !isRecord(v))
    : [];

  const verdictEntries = Object.entries(stats?.self_audit?.by_verdict ?? {});
  const verdictTotal = verdictEntries.reduce((sum, [, n]) => sum + n, 0);
  const accuracy = stats ? normalizeAccuracy(stats.self_audit?.accuracy ?? 0) : null;

  return (
    <div className="min-h-screen bg-surface-main">
      {/* Header */}
      <header className="bg-surface-card border-b border-gray-200">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-xl bg-primary flex items-center justify-center">
              <Brain className="h-5 w-5 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-text-primary">元认知中心</h1>
              <p className="text-xs text-text-muted">自审统计 · 审核队列 · 版本控制 · 复盘报告</p>
            </div>
          </div>
          <button
            onClick={refresh}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-lg bg-surface-sidebar border border-subtle px-3 py-2 text-xs font-medium text-text-secondary hover:text-primary hover:border-primary/30 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin')} />
            刷新
          </button>
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6 space-y-6">
        {error && (
          <div className="rounded-xl bg-status-error/5 text-status-error text-sm px-4 py-3">
            {error}
          </div>
        )}

        {/* Tabs */}
        <motion.div {...fadeIn(0.05)} className="flex gap-1 overflow-x-auto pb-1">
          {[
            { key: 'overview' as const, label: '概览', icon: LayoutDashboard },
            { key: 'queue' as const, label: '审核队列', icon: ListChecks },
            { key: 'versions' as const, label: '版本控制', icon: GitBranch },
            { key: 'trees' as const, label: '七树', icon: Trees },
            { key: 'governance' as const, label: '治理', icon: ShieldCheck },
          ].map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.key;
            return (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={cn(
                  'flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap',
                  isActive
                    ? 'bg-primary text-white'
                    : 'bg-surface-card text-text-secondary hover:text-text-primary border border-gray-200'
                )}
              >
                <Icon className="h-4 w-4" />
                {tab.label}
                {tab.key === 'queue' && (stats?.pending ?? 0) > 0 && (
                  <span className={cn(
                    'ml-1 text-xs px-1.5 py-0.5 rounded',
                    isActive ? 'bg-white/20 text-white' : 'bg-status-warning/10 text-status-warning'
                  )}>
                    {stats?.pending}
                  </span>
                )}
              </button>
            );
          })}
        </motion.div>

        {/* ─── 概览 Tab ─── */}
        {activeTab === 'overview' && (
          <motion.section
            key="overview"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
            className="space-y-4"
          >
            {/* Stats Tiles */}
            {loading && !stats ? (
              <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} height={86} className="rounded-xl" />
                ))}
              </div>
            ) : (
              <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                <StatTile label="队列大小" value={stats?.queue_size ?? '—'} />
                <StatTile
                  label="待审"
                  value={stats?.pending ?? '—'}
                  accent={(stats?.pending ?? 0) > 0 ? 'text-status-warning' : undefined}
                />
                <StatTile label="已审" value={stats?.reviewed ?? '—'} />
                <StatTile label="决策总数" value={stats?.decisions_total ?? '—'} />
                <StatTile
                  label="自审准确率"
                  value={accuracy !== null ? `${accuracy}%` : '—'}
                  accent={accuracy !== null && accuracy >= 80 ? 'text-status-success' : accuracy !== null && accuracy < 50 ? 'text-status-error' : undefined}
                />
              </div>
            )}

            {/* Verdict 分布 */}
            <div className="card-liquid shadow-card rounded-xl p-5">
              <div className="flex items-center gap-2 text-text-muted mb-4">
                <Gavel className="h-4 w-4" />
                <span className="text-xs font-semibold">自审 Verdict 分布</span>
              </div>
              {loading && !stats ? (
                <div className="space-y-3">
                  <Skeleton height={28} />
                  <Skeleton height={28} />
                  <Skeleton height={28} />
                </div>
              ) : verdictEntries.length > 0 ? (
                <div className="space-y-3">
                  {verdictEntries.map(([verdict, count]) => {
                    const style = verdictStyle(verdict);
                    const pct = verdictTotal > 0 ? Math.round((count / verdictTotal) * 100) : 0;
                    return (
                      <div key={verdict}>
                        <div className="flex items-center justify-between mb-1">
                          <span className={cn('text-xs font-medium', style.text)}>{verdict}</span>
                          <span className="text-xs text-text-muted">{count} · {pct}%</span>
                        </div>
                        <div className="h-2 rounded-full bg-surface-sidebar overflow-hidden">
                          <motion.div
                            initial={{ width: 0 }}
                            animate={{ width: `${pct}%` }}
                            transition={{ duration: 0.5 }}
                            className={cn('h-full rounded-full', style.bar)}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="text-sm text-text-secondary py-2">暂无自审数据</div>
              )}
            </div>

            {/* 动作: 主动扫描 + 复盘报告 */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="card-liquid shadow-card rounded-xl p-5">
                <div className="flex items-center gap-2 text-text-muted mb-4">
                  <ScanSearch className="h-4 w-4" />
                  <span className="text-xs font-semibold">主动扫描</span>
                </div>
                <p className="text-xs text-text-muted mb-3">
                  立即触发一轮元认知扫描,检查待审决策与自审一致性。
                </p>
                <button
                  onClick={handleScan}
                  disabled={scanLoading}
                  className="flex items-center gap-1.5 rounded-lg bg-primary text-white px-3 py-2 text-xs font-medium hover:bg-primary-dark transition-colors disabled:opacity-50"
                >
                  {scanLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ScanSearch className="h-3.5 w-3.5" />}
                  {scanLoading ? '扫描中...' : '主动扫描'}
                </button>
              </div>

              <div className="card-liquid shadow-card rounded-xl p-5">
                <div className="flex items-center gap-2 text-text-muted mb-4">
                  <FileText className="h-4 w-4" />
                  <span className="text-xs font-semibold">复盘报告</span>
                </div>
                <div className="space-y-2">
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={retroTarget}
                      onChange={(e) => setRetroTarget(e.target.value)}
                      placeholder="target (可选)"
                      className="flex-1 min-w-0 rounded-lg border border-gray-200 bg-surface-sidebar px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:border-primary"
                    />
                    <select
                      value={retroCategory}
                      onChange={(e) => setRetroCategory(e.target.value)}
                      className="rounded-lg border border-gray-200 bg-surface-sidebar px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:border-primary"
                    >
                      <option value="">全部 category</option>
                      {VERSION_CATEGORIES.map((c) => (
                        <option key={c} value={c}>{c}</option>
                      ))}
                    </select>
                  </div>
                  <button
                    onClick={handleRetrospect}
                    disabled={retrospectLoading}
                    className="flex items-center gap-1.5 rounded-lg bg-primary text-white px-3 py-2 text-xs font-medium hover:bg-primary-dark transition-colors disabled:opacity-50"
                  >
                    {retrospectLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FileText className="h-3.5 w-3.5" />}
                    {retrospectLoading ? '生成中...' : '生成复盘报告'}
                  </button>
                </div>
              </div>
            </div>

            {/* 复盘结果 */}
            {retrospect && (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.25 }}
                className="card-liquid shadow-card rounded-xl p-5"
              >
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2 text-text-muted">
                    <ShieldCheck className="h-4 w-4" />
                    <span className="text-xs font-semibold">复盘结果</span>
                  </div>
                  <button
                    onClick={() => setRetrospect(null)}
                    className="text-xs text-text-muted hover:text-text-primary transition-colors"
                  >
                    清除
                  </button>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                  <div className="bg-surface-sidebar rounded-lg p-3">
                    <span className="text-xs text-text-muted">Target</span>
                    <p className="text-sm font-mono text-text-primary break-all">{retrospect.target || '—'}</p>
                  </div>
                  <div className="bg-surface-sidebar rounded-lg p-3">
                    <span className="text-xs text-text-muted">Verdict</span>
                    <p className="mt-1">
                      <Badge variant="status" color={verdictStyle(retrospect.verdict).badge}>
                        {retrospect.verdict || '—'}
                      </Badge>
                    </p>
                  </div>
                  <div className="bg-surface-sidebar rounded-lg p-3">
                    <span className="text-xs text-text-muted">Delta (value_change)</span>
                    <p className={cn(
                      'flex items-center gap-1 text-sm font-semibold',
                      retrospect.delta.direction === 'increase' ? 'text-status-success'
                        : retrospect.delta.direction === 'decrease' ? 'text-status-error'
                        : 'text-text-primary'
                    )}>
                      {retrospect.delta.direction === 'increase' ? (
                        <TrendingUp className="h-4 w-4" />
                      ) : retrospect.delta.direction === 'decrease' ? (
                        <TrendingDown className="h-4 w-4" />
                      ) : (
                        <Minus className="h-4 w-4" />
                      )}
                      {retrospect.delta.value_change}
                    </p>
                  </div>
                </div>
              </motion.div>
            )}
          </motion.section>
        )}

        {/* ─── 审核队列 Tab ─── */}
        {activeTab === 'queue' && (
          <motion.section
            key="queue"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
            className="space-y-4"
          >
            {loading && !queue ? (
              <div className="space-y-3">
                <Skeleton height={96} className="rounded-xl" />
                <Skeleton height={96} className="rounded-xl" />
                <Skeleton height={96} className="rounded-xl" />
              </div>
            ) : queueItems && queueItems.length > 0 ? (
              <>
                {queueScalars.length > 0 && (
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    {queueScalars.map(([k, v]) => (
                      <div key={k} className="card-liquid shadow-card rounded-xl p-3">
                        <span className="text-xs text-text-muted">{k}</span>
                        <p className="text-lg font-semibold text-text-primary">{fmtValue(v)}</p>
                      </div>
                    ))}
                  </div>
                )}
                <div className="space-y-3">
                  {queueItems.map((item, idx) => {
                    const rec = isRecord(item) ? item : { value: item };
                    const itemId = isRecord(item) && item.id !== undefined ? String(item.id) : null;
                    const verdict = isRecord(item) && typeof item.verdict === 'string' ? item.verdict : null;
                    return (
                      <div
                        key={itemId ?? idx}
                        className="card-liquid shadow-card rounded-xl p-5"
                      >
                        <div className="flex items-center justify-between mb-3">
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-medium px-1.5 py-0.5 rounded bg-surface-sidebar text-text-muted">
                              #{idx + 1}
                            </span>
                            {itemId && (
                              <span className="text-xs font-mono text-text-secondary break-all">{itemId}</span>
                            )}
                          </div>
                          {verdict && (
                            <Badge variant="status" color={verdictStyle(verdict).badge}>
                              {verdict}
                            </Badge>
                          )}
                        </div>
                        <KvRows data={rec} />
                      </div>
                    );
                  })}
                </div>
              </>
            ) : queue && Object.keys(queue).length > 0 ? (
              <div className="card-liquid shadow-card rounded-xl p-5">
                <KvRows data={queue} />
              </div>
            ) : (
              <div className="text-center py-12 text-sm text-text-muted">
                <Inbox className="h-8 w-8 mx-auto mb-2" />
                暂无待审项
              </div>
            )}
          </motion.section>
        )}

        {/* ─── 版本控制 Tab ─── */}
        {activeTab === 'versions' && (
          <motion.section
            key="versions"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
            className="space-y-4"
          >
            {/* Category 选择器 + Target 过滤 */}
            <div className="card-liquid shadow-card rounded-xl p-5 space-y-3">
              <div className="flex items-center gap-2 text-text-muted">
                <GitBranch className="h-4 w-4" />
                <span className="text-xs font-semibold">数据类别</span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {VERSION_CATEGORIES.map((c) => {
                  const isActive = versionCategory === c;
                  return (
                    <button
                      key={c}
                      onClick={() => setVersionCategory(c)}
                      className={cn(
                        'px-3 py-1.5 rounded-lg text-xs font-medium font-mono transition-colors',
                        isActive
                          ? 'bg-primary text-white'
                          : 'bg-surface-sidebar border border-subtle text-text-secondary hover:text-primary hover:border-primary/30'
                      )}
                    >
                      {c}
                    </button>
                  );
                })}
              </div>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={versionTarget}
                  onChange={(e) => setVersionTarget(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') setAppliedTarget(versionTarget.trim()); }}
                  placeholder="target 过滤 (可选,回车查询)"
                  className="flex-1 min-w-0 rounded-lg border border-gray-200 bg-surface-sidebar px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:border-primary"
                />
                <button
                  onClick={() => setAppliedTarget(versionTarget.trim())}
                  disabled={versionsLoading}
                  className="flex items-center gap-1.5 rounded-lg bg-surface-sidebar border border-subtle px-3 py-1.5 text-xs font-medium text-text-secondary hover:text-primary hover:border-primary/30 transition-colors disabled:opacity-50"
                >
                  {versionsLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Search className="h-3.5 w-3.5" />}
                  查询
                </button>
              </div>
            </div>

            {versionsError && (
              <div className="rounded-xl bg-status-error/5 text-status-error text-sm px-4 py-3">
                {versionsError}
              </div>
            )}

            {/* Commit 列表 */}
            {versionsLoading && !versions ? (
              <div className="space-y-3">
                <Skeleton height={110} className="rounded-xl" />
                <Skeleton height={110} className="rounded-xl" />
              </div>
            ) : versions && versions.commits.length > 0 ? (
              <div className="space-y-3">
                {versions.target && (
                  <div className="text-xs text-text-muted">
                    target: <span className="font-mono text-text-secondary">{versions.target}</span>
                    {' '}· {versions.commits.length} 个 commit
                  </div>
                )}
                {versions.commits.map((commit) => (
                  <div
                    key={commit.id}
                    className="card-liquid shadow-card rounded-xl p-5"
                  >
                    <div className="flex items-start justify-between gap-3 mb-3">
                      <div className="flex items-center gap-2 min-w-0">
                        <GitCommit className="h-4 w-4 text-text-muted shrink-0" />
                        <span className="text-sm font-mono text-text-primary break-all">{commit.id}</span>
                      </div>
                      <button
                        onClick={() => handleRollback(commit)}
                        disabled={rollbackId !== null}
                        className="flex items-center gap-1 rounded-lg bg-surface-sidebar border border-subtle px-3 py-1.5 text-xs font-medium text-text-secondary hover:text-status-error hover:border-status-error/30 transition-colors disabled:opacity-50 shrink-0"
                      >
                        {rollbackId === commit.id ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <RotateCcw className="h-3.5 w-3.5" />
                        )}
                        {rollbackId === commit.id ? '回滚中...' : '回滚'}
                      </button>
                    </div>
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mb-3 text-xs text-text-muted">
                      <span>{formatTs(commit.ts)}</span>
                      <span>author: <span className="text-text-secondary">{commit.author}</span></span>
                      <span>verify: <span className="font-mono text-text-secondary">{commit.verify}</span></span>
                    </div>
                    {commit.reason && (
                      <p className="text-sm text-text-secondary mb-3">{commit.reason}</p>
                    )}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      <div className="rounded-lg bg-surface-sidebar p-3">
                        <span className="text-xs text-text-muted">Before</span>
                        <p className="mt-1 text-xs font-mono text-text-secondary break-all whitespace-pre-wrap">{commit.before || '—'}</p>
                      </div>
                      <div className="rounded-lg bg-surface-sidebar p-3">
                        <span className="text-xs text-text-muted">After</span>
                        <p className="mt-1 text-xs font-mono text-text-primary break-all whitespace-pre-wrap">{commit.after || '—'}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-12 text-sm text-text-muted">
                <GitBranch className="h-8 w-8 mx-auto mb-2" />
                {versionsError ? '加载失败' : '暂无版本记录'}
              </div>
            )}
          </motion.section>
        )}

        {/* ─── 七树 Tab ─── */}
        {activeTab === 'trees' && (
          <motion.section key="trees" {...fadeIn(0.05)} className="space-y-6">
            {/* 联邦查询 */}
            <div className="card-liquid shadow-card rounded-xl p-5">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                  <Search className="h-4 w-4 text-text-muted" />
                  跨会话联邦查询
                </h2>
                <button
                  onClick={fetchTrees}
                  disabled={treesLoading}
                  className="flex items-center gap-1 rounded-lg bg-surface-sidebar border border-subtle px-3 py-1.5 text-xs font-medium text-text-secondary hover:text-text-primary transition-colors disabled:opacity-50"
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${treesLoading ? 'animate-spin' : ''}`} />
                  刷新
                </button>
              </div>
              <div className="flex gap-2">
                <input
                  value={treeQuery}
                  onChange={(e) => setTreeQuery(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') searchTrees(); }}
                  placeholder="跨七树检索关键字, 如: run_shell / exec_tree_audit / hello.py"
                  className="flex-1 rounded-lg border border-subtle bg-surface-sidebar px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-primary"
                />
                <button
                  onClick={searchTrees}
                  disabled={treesSearching || !treeQuery.trim()}
                  className="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                >
                  {treesSearching ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Search className="h-3.5 w-3.5" />}
                  查询
                </button>
              </div>
              {treeHits?.error && (
                <div className="mt-3 rounded-lg bg-status-error/5 text-status-error text-sm px-4 py-2">
                  {treeHits.error}
                </div>
              )}
              {treeHits?.hits && (
                <div className="mt-3 space-y-2 max-h-72 overflow-y-auto">
                  {treeHits.hits.length === 0 ? (
                    <div className="text-center py-6 text-sm text-text-muted">无命中</div>
                  ) : (
                    treeHits.hits.map((hit, i) => (
                      <div key={`${hit.session_id ?? '?'}-${hit.node_id}-${i}`}
                        className="rounded-lg bg-surface-sidebar border border-subtle p-3">
                        <div className="flex items-center gap-2 mb-1 text-xs">
                          <span className="font-mono text-text-secondary">{hit.tree}</span>
                          {hit.session_id && (
                            <span className="text-text-muted">session: {hit.session_id}</span>
                          )}
                          <span className="text-text-muted truncate font-mono">{hit.node_id}</span>
                        </div>
                        <p className="text-xs text-text-secondary break-all whitespace-pre-wrap font-mono line-clamp-3">
                          {hit.content}
                        </p>
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>

            {/* 会话聚合统计 */}
            {treesError && (
              <div className="rounded-xl bg-status-error/5 text-status-error text-sm px-4 py-3">
                {treesError}
              </div>
            )}
            {treesLoading && !trees ? (
              <div className="space-y-3">
                <Skeleton height={90} className="rounded-xl" />
                <Skeleton height={200} className="rounded-xl" />
              </div>
            ) : trees?.sessions ? (
              <>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className="card-liquid shadow-card rounded-xl p-4">
                    <div className="text-xs text-text-muted">会话树</div>
                    <div className="mt-1 text-2xl font-semibold text-text-primary">
                      {trees.session_count ?? trees.sessions.length}
                    </div>
                  </div>
                  <div className="card-liquid shadow-card rounded-xl p-4">
                    <div className="text-xs text-text-muted">节点总数</div>
                    <div className="mt-1 text-2xl font-semibold text-text-primary">
                      {trees.total_nodes ?? 0}
                    </div>
                  </div>
                </div>
                {trees.sessions.length === 0 ? (
                  <div className="card-liquid shadow-card rounded-xl p-10 text-center text-sm text-text-muted">
                    <Trees className="h-8 w-8 mx-auto mb-2" />
                    暂无七树数据 —— 执行过任务后这里会显示执行/行为/元认知等树
                  </div>
                ) : (
                  trees.sessions.map((sess) => (
                    <div key={sess.session_id}
                      className="card-liquid shadow-card rounded-xl p-5">
                      <div className="flex items-center justify-between mb-3">
                        <span className="text-sm font-mono text-text-primary break-all">
                          {sess.session_id}
                        </span>
                        <span className="text-xs text-text-muted">
                          {sess.loaded ? '内存' : '盘上'} · {sess.stats.reduce((s, t) => s + t.total_nodes, 0)} 节点
                        </span>
                      </div>
                      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2">
                        {sess.stats.map((t) => (
                          <div key={t.tree_name}
                            className="rounded-lg bg-surface-sidebar border border-subtle p-3">
                            <div className="text-xs font-medium text-text-secondary">{t.tree_name}</div>
                            <div className="mt-1 text-lg font-semibold text-text-primary">{t.total_nodes}</div>
                            <div className="mt-1 flex flex-wrap gap-x-2 text-[10px] text-text-muted">
                              <span>活跃 {t.active}</span>
                              <span>完成 {t.completed}</span>
                              <span>归档 {t.archived}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))
                )}
              </>
            ) : null}
          </motion.section>
        )}

        {/* ─── 治理 Tab（2026-08-17 前端绑定: 高可用/自修/体检/观测）─── */}
        {activeTab === 'governance' && (
          <motion.section
            key="governance"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
          >
            <GovernancePanel />
          </motion.section>
        )}
      </div>

      {/* Toast 提示 */}
      {toast && (
        <Toast
          key={toast.id}
          type={toast.type}
          message={toast.message}
          onClose={() => setToast(null)}
        />
      )}
    </div>
  );
}

// FILE: src/pages/BehaviorPage.tsx
// 行为发现: 行为模式审核 + 行为预测 + 惯性权重 面板

import { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import {
  BrainCircuit,
  RefreshCw,
  ListChecks,
  Sparkles,
  Scale,
  Check,
  X,
  Play,
  History,
  Zap,
  ShieldAlert,
  ArrowRight,
  Inbox,
} from 'lucide-react';
import {
  getBehaviorPatterns,
  submitBehaviorFeedback,
  getBehaviorPredictions,
  getInertia,
} from '../api/v6';
import type {
  V6BehaviorPattern,
  V6BehaviorPatternsResponse,
  V6BehaviorPredictResponse,
  V6InertiaResponse,
} from '../types/api';
import { Badge } from '../components/ui/Badge';
import { Toast } from '../components/ui/Toast';
import { cn } from '../lib/utils';

type TabKey = 'patterns' | 'predict' | 'inertia';

const tabs: { key: TabKey; label: string; icon: typeof ListChecks }[] = [
  { key: 'patterns', label: '行为模式审核', icon: ListChecks },
  { key: 'predict', label: '行为预测', icon: Sparkles },
  { key: 'inertia', label: '惯性权重', icon: Scale },
];

/** 后端 _patterns 的 key 为 "trigger→predicted" */
function patternKey(p: V6BehaviorPattern): string {
  return `${p.trigger}→${p.predicted}`;
}

type VerdictKind = 'approved' | 'rejected' | 'pending';

function parseVerdict(verdict: string): VerdictKind {
  if (verdict.includes('approved')) return 'approved';
  if (verdict.includes('rejected')) return 'rejected';
  return 'pending';
}

function confBarColor(conf: number): string {
  if (conf >= 0.75) return 'bg-status-success';
  if (conf >= 0.5) return 'bg-status-warning';
  return 'bg-status-error';
}

interface ToastState {
  id: number;
  type: 'success' | 'error' | 'warning' | 'info';
  message: string;
}

// ─── Component ────────────────────────────────────────────────────────────────

export function BehaviorPage() {
  const [activeTab, setActiveTab] = useState<TabKey>('patterns');
  const [patterns, setPatterns] = useState<V6BehaviorPatternsResponse | null>(null);
  const [inertia, setInertia] = useState<V6InertiaResponse | null>(null);
  const [predict, setPredict] = useState<V6BehaviorPredictResponse | null>(null);
  const [predictRequested, setPredictRequested] = useState(false);
  const [loading, setLoading] = useState(false);
  const [predictLoading, setPredictLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [feedbackPending, setFeedbackPending] = useState<Set<string>>(new Set());
  const [toast, setToast] = useState<ToastState | null>(null);

  const showToast = useCallback((type: ToastState['type'], message: string) => {
    setToast({ id: Date.now(), type, message });
  }, []);

  // ── 数据获取: 模式 + 惯性(挂载 + 30s 轮询) ─────────────────
  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [patternsRes, inertiaRes] = await Promise.all([
        getBehaviorPatterns().catch(() => null),
        getInertia().catch(() => null),
      ]);
      setPatterns(patternsRes);
      setInertia(inertiaRes);
      if (!patternsRes && !inertiaRes) {
        setError('无法获取行为数据,请确认后端服务已启动');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '获取行为数据失败');
    } finally {
      setLoading(false);
    }
  }, []);

  // ── 行为预测(手动触发) ──────────────────────────────────────
  const fetchPredict = useCallback(async () => {
    setPredictRequested(true);
    setPredictLoading(true);
    try {
      const res = await getBehaviorPredictions();
      setPredict(res);
    } catch (err) {
      showToast('error', err instanceof Error ? err.message : '获取行为预测失败');
    } finally {
      setPredictLoading(false);
    }
  }, [showToast]);

  const handleRefresh = useCallback(() => {
    fetchAll();
    if (predictRequested) fetchPredict();
  }, [fetchAll, fetchPredict, predictRequested]);

  useEffect(() => {
    fetchAll();
    const timer = setInterval(fetchAll, 30000);
    return () => clearInterval(timer);
  }, [fetchAll]);

  // ── ✓/✗ 反馈 ────────────────────────────────────────────────
  const handleFeedback = useCallback(async (pattern: V6BehaviorPattern, correct: boolean) => {
    const key = patternKey(pattern);
    setFeedbackPending(prev => new Set(prev).add(key));
    try {
      await submitBehaviorFeedback({ pattern_id: key, correct });
      // 本地更新 verdict / confidence / stats,与后端置信度调整幅度保持一致
      setPatterns(prev => {
        if (!prev) return prev;
        const wasApproved = pattern.verdict.includes('approved');
        const delta = correct ? (wasApproved ? 0 : 1) : (wasApproved ? -1 : 0);
        return {
          patterns: prev.patterns.map(p =>
            patternKey(p) === key
              ? {
                  ...p,
                  verdict: correct ? 'user_approved' : 'user_rejected',
                  confidence: correct
                    ? Math.min(1, p.confidence + 0.05)
                    : Math.max(0.1, p.confidence - 0.1),
                }
              : p
          ),
          stats: {
            ...prev.stats,
            user_approved: Math.max(0, prev.stats.user_approved + delta),
          },
        };
      });
      showToast('success', correct ? `已批准模式「${key}」` : `已拒绝模式「${key}」`);
    } catch (err) {
      showToast('error', err instanceof Error ? err.message : '提交反馈失败');
    } finally {
      setFeedbackPending(prev => {
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
    }
  }, [showToast]);

  const fadeIn = (delay: number) => ({
    initial: { opacity: 0, y: 12 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.35, delay },
  });

  // ── 派生数据 ─────────────────────────────────────────────────
  const sortedPatterns = patterns
    ? [...patterns.patterns].sort((a, b) => b.confidence - a.confidence)
    : [];
  const pendingCount = patterns
    ? patterns.patterns.filter(p => parseVerdict(p.verdict) === 'pending').length
    : 0;
  const avgConfidence = patterns && patterns.patterns.length > 0
    ? patterns.patterns.reduce((sum, p) => sum + p.confidence, 0) / patterns.patterns.length
    : 0;
  const weightEntries = inertia
    ? Object.entries(inertia.by_weight).sort(([, a], [, b]) => b - a)
    : [];
  const maxWeight = Math.max(0.01, ...weightEntries.map(([, w]) => w));

  return (
    <div className="min-h-screen bg-surface-main">
      {/* Toast 通知 */}
      {toast && (
        <Toast
          key={toast.id}
          type={toast.type}
          message={toast.message}
          onClose={() => setToast(null)}
        />
      )}

      {/* Header */}
      <header className="bg-surface-card border-b border-gray-200">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-xl bg-primary flex items-center justify-center">
              <BrainCircuit className="h-5 w-5 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-text-primary">行为发现</h1>
              <p className="text-xs text-text-muted">模式审核 · 行为预测 · 惯性权重</p>
            </div>
          </div>
          <button
            onClick={handleRefresh}
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
          {tabs.map((tab) => {
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
              </button>
            );
          })}
        </motion.div>

        {/* ══ Tab 1: 行为模式审核 ══ */}
        {activeTab === 'patterns' && (
          <motion.section
            key="patterns"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
            className="space-y-4"
          >
            {/* Stats */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <StatCard label="模式总数" value={patterns?.stats.total_patterns ?? '—'} />
              <StatCard label="已批准" value={patterns?.stats.user_approved ?? '—'} accent="text-status-success" />
              <StatCard label="待审核" value={patterns ? pendingCount : '—'} accent="text-status-warning" />
              <StatCard label="平均置信度" value={patterns ? `${(avgConfidence * 100).toFixed(1)}%` : '—'} />
            </div>

            {/* 模式表格 */}
            <div className="card-liquid shadow-card rounded-xl p-5">
              <div className="flex items-center gap-2 text-text-muted mb-4">
                <ListChecks className="h-4 w-4" />
                <span className="text-xs font-semibold">行为模式(Trigger → Predicted)</span>
              </div>

              {sortedPatterns.length === 0 ? (
                <EmptyState text="暂无行为模式" hint="后端可能尚未发现重复行为序列" />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-subtle">
                        <th className="text-left py-2 pr-4 text-xs font-medium text-text-muted">Trigger → Predicted</th>
                        <th className="text-left py-2 pr-4 text-xs font-medium text-text-muted w-36">置信度</th>
                        <th className="text-right py-2 pr-4 text-xs font-medium text-text-muted">Support</th>
                        <th className="text-left py-2 pr-4 text-xs font-medium text-text-muted">Verdict</th>
                        <th className="text-right py-2 text-xs font-medium text-text-muted">反馈</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sortedPatterns.map((p) => {
                        const key = patternKey(p);
                        const pending = feedbackPending.has(key);
                        return (
                          <tr
                            key={key}
                            className="border-b border-gray-50 last:border-0 hover:bg-surface-sidebar/50 transition-colors"
                          >
                            <td className="py-3 pr-4">
                              <div className="flex items-center gap-1.5 flex-wrap">
                                <span className="font-mono text-xs px-1.5 py-0.5 rounded bg-surface-sidebar text-text-primary">
                                  {p.trigger}
                                </span>
                                <ArrowRight className="h-3 w-3 text-text-muted shrink-0" />
                                <span className="font-mono text-xs px-1.5 py-0.5 rounded bg-primary/10 text-primary">
                                  {p.predicted}
                                </span>
                              </div>
                            </td>
                            <td className="py-3 pr-4">
                              <div className="flex items-center gap-2">
                                <div className="h-1.5 flex-1 rounded-full bg-surface-sidebar overflow-hidden">
                                  <div
                                    className={cn('h-full rounded-full transition-all', confBarColor(p.confidence))}
                                    style={{ width: `${Math.round(p.confidence * 100)}%` }}
                                  />
                                </div>
                                <span className="w-10 text-right text-xs font-mono text-text-secondary">
                                  {(p.confidence * 100).toFixed(0)}%
                                </span>
                              </div>
                            </td>
                            <td className="py-3 pr-4 text-right">
                              <span className="text-sm font-mono text-text-primary">{p.support}</span>
                            </td>
                            <td className="py-3 pr-4">
                              <VerdictBadge verdict={p.verdict} />
                            </td>
                            <td className="py-3 text-right">
                              <div className="inline-flex items-center gap-1.5">
                                <button
                                  onClick={() => handleFeedback(p, true)}
                                  disabled={pending}
                                  title="批准该模式"
                                  className="h-7 w-7 rounded-md border border-subtle flex items-center justify-center text-status-success hover:bg-status-success/10 hover:border-status-success/40 transition-colors disabled:opacity-40"
                                >
                                  <Check className="h-3.5 w-3.5" />
                                </button>
                                <button
                                  onClick={() => handleFeedback(p, false)}
                                  disabled={pending}
                                  title="拒绝该模式"
                                  className="h-7 w-7 rounded-md border border-subtle flex items-center justify-center text-status-error hover:bg-status-error/10 hover:border-status-error/40 transition-colors disabled:opacity-40"
                                >
                                  <X className="h-3.5 w-3.5" />
                                </button>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </motion.section>
        )}

        {/* ══ Tab 2: 行为预测 ══ */}
        {activeTab === 'predict' && (
          <motion.section
            key="predict"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
            className="card-liquid shadow-card rounded-xl p-5 space-y-5"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-text-muted">
                <Sparkles className="h-4 w-4" />
                <span className="text-xs font-semibold">下一步动作预测</span>
              </div>
              <button
                onClick={fetchPredict}
                disabled={predictLoading}
                className="flex items-center gap-1.5 rounded-lg bg-primary text-white px-3 py-1.5 text-xs font-medium hover:bg-primary-dark transition-colors disabled:opacity-50"
              >
                <Play className="h-3.5 w-3.5" />
                {predictLoading ? '预测中...' : '触发预测'}
              </button>
            </div>

            {!predict ? (
              <EmptyState
                text={predictLoading ? '正在分析行为序列...' : '尚未触发预测'}
                hint="点击「触发预测」基于最近动作历史生成预测"
              />
            ) : (
              <>
                {/* 最近动作历史 */}
                <div>
                  <div className="flex items-center gap-2 text-text-muted mb-2">
                    <History className="h-3.5 w-3.5" />
                    <span className="text-xs font-medium">最近动作历史({predict.recent_actions.length})</span>
                  </div>
                  {predict.recent_actions.length === 0 ? (
                    <p className="text-sm text-text-muted">暂无动作历史</p>
                  ) : (
                    <div className="flex items-center gap-1.5 flex-wrap rounded-lg bg-surface-sidebar border border-subtle p-3">
                      {predict.recent_actions.map((action, idx) => (
                        <span key={`${action}-${idx}`} className="flex items-center gap-1.5">
                          <span
                            className={cn(
                              'font-mono text-xs px-2 py-1 rounded-md',
                              idx === predict.recent_actions.length - 1
                                ? 'bg-primary/10 text-primary'
                                : 'bg-surface-card text-text-secondary'
                            )}
                          >
                            {action}
                          </span>
                          {idx < predict.recent_actions.length - 1 && (
                            <ArrowRight className="h-3 w-3 text-text-muted" />
                          )}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                {/* 预测结果 */}
                <div>
                  <div className="flex items-center gap-2 text-text-muted mb-2">
                    <Zap className="h-3.5 w-3.5" />
                    <span className="text-xs font-medium">预测下一步({Object.keys(predict.predictions).length})</span>
                  </div>
                  {Object.keys(predict.predictions).length === 0 ? (
                    <p className="text-sm text-text-muted">暂无置信度高于阈值的预测</p>
                  ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      {Object.entries(predict?.predictions ?? {})
                        .sort(([, a], [, b]) => b.conf - a.conf)
                        .map(([key, pred]) => (
                          <div key={key} className="rounded-lg border border-subtle bg-surface-sidebar p-3">
                            <div className="flex items-center gap-1.5 mb-2 flex-wrap">
                              <span className="font-mono text-xs px-1.5 py-0.5 rounded bg-surface-card text-text-primary">
                                {pred.trigger}
                              </span>
                              <ArrowRight className="h-3 w-3 text-text-muted shrink-0" />
                              <span className="font-mono text-xs px-1.5 py-0.5 rounded bg-primary/10 text-primary">
                                {pred.predicted}
                              </span>
                              <span className="ml-auto text-xs font-mono text-text-secondary">
                                {(pred.conf * 100).toFixed(0)}%
                              </span>
                            </div>
                            <div className="h-1.5 rounded-full bg-surface-card overflow-hidden">
                              <div
                                className={cn('h-full rounded-full', confBarColor(pred.conf))}
                                style={{ width: `${Math.round(pred.conf * 100)}%` }}
                              />
                            </div>
                          </div>
                        ))}
                    </div>
                  )}
                </div>
              </>
            )}
          </motion.section>
        )}

        {/* ══ Tab 3: 惯性权重 ══ */}
        {activeTab === 'inertia' && (
          <motion.section
            key="inertia"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
            className="space-y-4"
          >
            {/* 统计卡 */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <StatCard label="惯性模式" value={inertia?.total_patterns ?? '—'} />
              <StatCard label="Stable" value={inertia?.stable ?? '—'} accent="text-status-success" />
              <StatCard label="Confirmed" value={inertia?.confirmed ?? '—'} accent="text-status-info" />
              <StatCard label="Breaking" value={inertia?.breaking ?? '—'} accent="text-status-error" />
            </div>

            {/* 权重条形图 */}
            <div className="card-liquid shadow-card rounded-xl p-5">
              <div className="flex items-center gap-2 text-text-muted mb-4">
                <Scale className="h-4 w-4" />
                <span className="text-xs font-semibold">惯性权重分布(by_weight)</span>
              </div>
              {weightEntries.length === 0 ? (
                <EmptyState text="暂无惯性数据" hint="后端可能尚未积累惯性模式" />
              ) : (
                <div className="space-y-2.5">
                  {weightEntries.map(([pid, weight]) => (
                    <div key={pid} className="flex items-center gap-3">
                      <span
                        className="w-36 sm:w-48 shrink-0 truncate font-mono text-xs text-text-secondary"
                        title={pid}
                      >
                        {pid}
                      </span>
                      <div className="h-2 flex-1 rounded-full bg-surface-sidebar overflow-hidden">
                        <motion.div
                          initial={{ width: 0 }}
                          animate={{ width: `${Math.max(2, (weight / maxWeight) * 100)}%` }}
                          transition={{ duration: 0.5 }}
                          className="h-full rounded-full bg-primary"
                        />
                      </div>
                      <span className="w-12 shrink-0 text-right text-xs font-mono text-text-primary">
                        {weight.toFixed(2)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* 设计约束 */}
            <div className="card-liquid shadow-card rounded-xl p-5">
              <div className="flex items-center gap-2 text-text-muted mb-4">
                <ShieldAlert className="h-4 w-4" />
                <span className="text-xs font-semibold">设计约束(constraints)</span>
              </div>
              {!inertia || inertia.constraints.length === 0 ? (
                <p className="text-sm text-text-muted">暂无约束</p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {inertia.constraints.map((c, idx) => (
                    <Badge key={`${c}-${idx}`} variant="status" color="warning" className="px-2.5 py-1">
                      {c}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          </motion.section>
        )}
      </div>
    </div>
  );
}

// ─── 内部组件 ──────────────────────────────────────────────────────────────────

function StatCard({ label, value, accent }: { label: string; value: number | string; accent?: string }) {
  return (
    <div className="card-liquid shadow-card rounded-lg p-3">
      <span className="text-xs text-text-muted">{label}</span>
      <p className={cn('text-lg font-semibold', accent ?? 'text-text-primary')}>{value}</p>
    </div>
  );
}

function VerdictBadge({ verdict }: { verdict: string }) {
  const kind = parseVerdict(verdict);
  if (kind === 'approved') {
    return <Badge variant="status" color="success">已批准</Badge>;
  }
  if (kind === 'rejected') {
    return <Badge variant="status" color="error">已拒绝</Badge>;
  }
  return <Badge>待审核</Badge>;
}

function EmptyState({ text, hint }: { text: string; hint?: string }) {
  return (
    <div className="text-center py-12">
      <Inbox className="h-8 w-8 text-text-muted mx-auto mb-2" />
      <p className="text-sm text-text-secondary">{text}</p>
      {hint && <p className="text-xs text-text-muted mt-1">{hint}</p>}
    </div>
  );
}

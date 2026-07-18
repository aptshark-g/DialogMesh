// FILE: src/pages/CognitiveProfilePage.tsx

import { useMemo, useState, useCallback } from 'react';
import { motion } from 'framer-motion';
import {
  RefreshCw,
  UserCircle,
  TrendingUp,
  TrendingDown,
  Minus,
  Calendar,
  Hash,
} from 'lucide-react';
import { CognitiveRadarChart } from '../components/CognitiveRadarChart';
import { MetricCards } from '../components/MetricCards';
import {
  DimensionBreakdown,
  IntentDistributionChart,
  ProfileStatsGrid,
} from '../components/profile';
import { useV6Profile } from '../hooks/useV6Profile';
import { cn, formatTimestamp } from '../lib/utils';
import type { ProfileStats, IntentDistribution } from '../types/profile';
import type { MetricCardData } from '../components/MetricCards';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function confidenceBadge(avgConfidence: number) {
  if (avgConfidence >= 0.7) {
    return { label: '高置信度', color: 'bg-status-success/10 text-status-success', icon: TrendingUp };
  }
  if (avgConfidence >= 0.4) {
    return { label: '中等置信度', color: 'bg-status-warning/10 text-status-warning', icon: Minus };
  }
  return { label: '低置信度', color: 'bg-status-error/10 text-status-error', icon: TrendingDown };
}

// ─── Component ────────────────────────────────────────────────────────────────

export function CognitiveProfilePage() {
  const { profile, trace, loading: apiLoading, error, refresh } = useV6Profile();
  const [isRefreshing, setIsRefreshing] = useState(false);

  const handleRefresh = useCallback(() => {
    setIsRefreshing(true);
    refresh().finally(() => setIsRefreshing(false));
  }, [refresh]);

  const isLoading = apiLoading || isRefreshing;

  // Overall score = average of OCEAN dimensions
  const overallScore = useMemo(() => {
    if (!profile) return 0;
    const dims = Object.values(profile.oceAN_dims);
    if (dims.length === 0) return 0;
    return Math.round((dims.reduce((a, b) => a + b, 0) / dims.length) * 100);
  }, [profile]);

  // Radar data: map OCEAN dimensions
  const radarData = useMemo(() => {
    if (!profile) return undefined;
    return Object.entries(profile.oceAN_dims).map(([dimension, value]) => ({
      dimension,
      value: Math.round(value * 100),
      fullMark: 100,
    }));
  }, [profile]);

  // Metric cards: top 3 dimensions sorted by value
  const metricCards = useMemo<MetricCardData[]>(() => {
    if (!profile) return [];
    return Object.entries(profile.oceAN_dims)
      .sort(([, a], [, b]) => b - a)
      .slice(0, 3)
      .map(([label, value]) => ({
        label,
        value: Math.round(value * 100),
        trend: 0,
      }));
  }, [profile]);

  // Dimensions for breakdown
  const dimensions = useMemo(() => {
    if (!profile) return [];
    return Object.entries(profile.oceAN_dims).map(([key, value]) => ({
      key,
      label: key,
      value: Math.round(value * 100),
      max: 100,
      description: undefined,
    }));
  }, [profile]);

  // Confidence badge from trace avg_confidence
  const confBadge = useMemo(
    () => confidenceBadge(trace?.avg_confidence ?? 0),
    [trace]
  );
  const ConfIcon = confBadge.icon;

  // Stats grid
  const currentStats: ProfileStats | null = useMemo(() => {
    if (!profile && !trace) return null;
    const dims = profile?.oceAN_dims ?? {};
    return {
      reasoningDepth: trace ? Math.round(trace.avg_confidence * 100) : 0,
      metacognition: Math.round((dims['Openness'] ?? dims['openness'] ?? 0) * 100),
      expressionClarity: Math.round((dims['Conscientiousness'] ?? dims['conscientiousness'] ?? 0) * 100),
      contextWindowUsage: Math.round((profile?.bfi_history ?? 0) * 100),
      entityCount: trace?.total ?? 0,
      topicTreeDepth: profile?.turn_count ?? 0,
      coherenceScore: trace ? Math.round(trace.avg_confidence * 100) : 0,
      responseLatencyMs: 0,
    };
  }, [profile, trace]);

  // Intent distribution from trace reason_distribution
  const currentIntents: IntentDistribution[] = useMemo(() => {
    if (!trace) return [];
    const total = trace.total || 1;
    const colors = ['#3B82F6', '#10B981', '#D97706', '#0D9488', '#8B5CF6', '#E11D48'];
    return Object.entries(trace.reason_distribution).map(([intent, count], idx) => ({
      intent,
      count,
      percentage: (count / total) * 100,
      color: colors[idx % colors.length],
      trend: 'stable' as const,
      trendValue: 0,
    }));
  }, [trace]);

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      {/* Header */}
      <header className="px-4 md:px-6 pt-4 md:pt-6 pb-4 shrink-0">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 sm:gap-0">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-xl bg-primary/10 flex items-center justify-center">
              <UserCircle className="h-5 w-5 text-primary" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-text-primary">认知画像</h1>
              <p className="text-xs text-text-muted mt-0.5">
                多维认知分析与意图分布可视化
              </p>
              {error && (
                <p className="text-xs text-status-error mt-0.5">{error}</p>
              )}
            </div>
          </div>
          <button
            type="button"
            onClick={handleRefresh}
            disabled={isLoading}
            className={cn(
              'flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium',
              'bg-surface-card border border-border-subtle text-text-secondary',
              'hover:bg-surface-card-hover hover:text-primary transition-colors',
              'disabled:opacity-50 disabled:cursor-not-allowed'
            )}
            aria-label="刷新画像数据"
          >
            <RefreshCw className={cn('w-4 h-4', isLoading && 'animate-spin')} />
            刷新
          </button>
        </div>
        <div className="mt-4 border-b border-border-subtle" />
      </header>

      {/* Content */}
      <div className="flex-1 px-4 md:px-6 py-4 md:py-6 space-y-6">
        {/* Top Row: Score + Radar + Metrics */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Overall Score Card */}
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
            className="lg:col-span-3 bg-surface-card rounded-xl border border-border-subtle p-6 flex flex-col justify-between"
          >
            <div>
              <span className="text-xs font-medium text-text-muted uppercase tracking-wide">
                综合评分
              </span>
              <div className="mt-3 flex items-baseline gap-2">
                <span className="text-4xl md:text-5xl font-bold text-text-primary">
                  {overallScore}
                </span>
                <span className="text-sm text-text-muted">/ 100</span>
              </div>
            </div>
            <div className="mt-6 space-y-3">
              <div
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium',
                  confBadge.color
                )}
              >
                <ConfIcon className="w-3.5 h-3.5" />
                {confBadge.label}
              </div>
              {profile?.mbti && (
                <p className="text-xs text-text-secondary leading-relaxed">
                  MBTI: {profile.mbti} · 轮次: {profile.turn_count}
                </p>
              )}
              <div className="flex items-center gap-4 pt-2">
                <div className="flex items-center gap-1.5 text-xs text-text-muted">
                  <Calendar className="w-3.5 h-3.5" />
                  {profile ? formatTimestamp(new Date().toISOString()) : '--'}
                </div>
                <div className="flex items-center gap-1.5 text-xs text-text-muted">
                  <Hash className="w-3.5 h-3.5" />
                  v6
                </div>
              </div>
            </div>
          </motion.div>

          {/* Radar Chart */}
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.05 }}
            className="lg:col-span-5 bg-surface-card rounded-xl border border-border-subtle p-6 flex flex-col items-center justify-center"
          >
            <h3 className="text-sm font-semibold text-text-primary mb-4 self-start">
              认知维度雷达
            </h3>
            <div className="w-full max-w-[220px] md:max-w-[260px] aspect-square mx-auto">
              <CognitiveRadarChart data={radarData} size={260} showLegend />
            </div>
          </motion.div>

          {/* Metric Cards */}
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.1 }}
            className="lg:col-span-4 bg-surface-card rounded-xl border border-border-subtle p-6 flex flex-col justify-center"
          >
            <h3 className="text-sm font-semibold text-text-primary mb-4">核心指标</h3>
            <MetricCards metrics={metricCards.length > 0 ? metricCards : undefined} />
          </motion.div>
        </div>

        {/* Stats Grid */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.15 }}
        >
          <ProfileStatsGrid stats={currentStats} />
        </motion.div>

        {/* Bottom Row: Dimension Breakdown + Intent Distribution */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.2 }}
          >
            <DimensionBreakdown dimensions={dimensions} />
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.25 }}
          >
            <IntentDistributionChart data={currentIntents} />
          </motion.div>
        </div>
      </div>
    </div>
  );
}

export default CognitiveProfilePage;

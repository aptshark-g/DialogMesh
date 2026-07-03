// FILE: src/pages/CognitiveProfilePage.tsx

import { useEffect, useMemo, useState, useCallback } from 'react';
import { motion } from 'framer-motion';
import {
  RefreshCw,
  UserCircle,
  TrendingUp,
  TrendingDown,
  Minus,
  AlertCircle,
  Calendar,
  Hash,
} from 'lucide-react';
import { CognitiveRadarChart } from '@/components/CognitiveRadarChart';
import { MetricCards } from '@/components/MetricCards';
import {
  DimensionBreakdown,
  IntentDistributionChart,
  ProfileStatsGrid,
} from '@/components/profile';
import {
  useProfileStore,
  useSelectedProfile,
  useProfileLoading,
  useAggregatedStats,
  useIntentDistribution,
} from '@/stores';
import { cn, formatTimestamp } from '@/lib/utils';
import type { CognitiveProfile, CognitiveDimension, ProfileStats, IntentDistribution } from '@/types/profile';
import type { MetricCardData } from '@/components/MetricCards';

// ─── Demo Data ────────────────────────────────────────────────────────────────

const demoProfile: CognitiveProfile = {
  id: 'profile_demo_001',
  sessionId: 'session_demo_001',
  timestamp: new Date().toISOString(),
  overallScore: 78,
  confidenceLevel: 'high',
  summary: '该会话展现出较强的元认知能力与推理深度，表达清晰度良好，但在发散性思维方面仍有提升空间。',
  dimensions: [
    { key: 'metacognition', label: '元认知', value: 84, max: 100, description: '对自身认知过程的觉察与调控' },
    { key: 'reasoning_depth', label: '推理深度', value: 76, max: 100, description: '逻辑链条的完整性与深度' },
    { key: 'confidence', label: '置信度', value: 68, max: 100, description: '结论的确定性与证据支撑' },
    { key: 'stability', label: '稳定性', value: 72, max: 100, description: '认知表现的一致性' },
    { key: 'divergence', label: '发散度', value: 58, max: 100, description: '思维的多角度与创造性' },
    { key: 'clarity', label: '清晰度', value: 81, max: 100, description: '表达与结构的可读性' },
    { key: 'coherence', label: '连贯性', value: 74, max: 100, description: '话题与逻辑的内在一致性' },
    { key: 'context_usage', label: '上下文利用', value: 69, max: 100, description: '对历史信息的引用与整合' },
  ],
};

const demoStats: ProfileStats = {
  reasoningDepth: 76,
  metacognition: 84,
  expressionClarity: 81,
  contextWindowUsage: 69,
  entityCount: 42,
  topicTreeDepth: 5,
  coherenceScore: 74,
  responseLatencyMs: 1240,
};

const demoIntents: IntentDistribution[] = [
  { intent: 'explain', count: 28, percentage: 35.0, color: '#3B82F6', trend: 'up', trendValue: 5 },
  { intent: 'provideCode', count: 18, percentage: 22.5, color: '#10B981', trend: 'stable', trendValue: 0 },
  { intent: 'scanMemory', count: 14, percentage: 17.5, color: '#D97706', trend: 'down', trendValue: 3 },
  { intent: 'readMemory', count: 10, percentage: 12.5, color: '#0D9488', trend: 'up', trendValue: 2 },
  { intent: 'writeMemory', count: 6, percentage: 7.5, color: '#8B5CF6', trend: 'stable', trendValue: 0 },
  { intent: 'hackValue', count: 4, percentage: 5.0, color: '#E11D48', trend: 'down', trendValue: 1 },
];

// ─── Helpers ──────────────────────────────────────────────────────────────────

function confidenceBadge(confidence: CognitiveProfile['confidenceLevel']) {
  switch (confidence) {
    case 'high':
      return { label: '高置信度', color: 'bg-status-success/10 text-status-success', icon: TrendingUp };
    case 'medium':
      return { label: '中等置信度', color: 'bg-status-warning/10 text-status-warning', icon: Minus };
    case 'low':
      return { label: '低置信度', color: 'bg-status-error/10 text-status-error', icon: TrendingDown };
    default:
      return { label: '未知', color: 'bg-text-muted/10 text-text-muted', icon: AlertCircle };
  }
}

function buildMetricCards(profile: CognitiveProfile | null): MetricCardData[] {
  if (!profile) {
    return [
      { label: '推理深度', value: 76, trend: 8 },
      { label: '元认知', value: 84, trend: 6 },
      { label: '表达清晰度', value: 71, trend: 5 },
    ];
  }
  const dims = new Map(profile.dimensions.map((d) => [d.key, d.value]));
  return [
    { label: '推理深度', value: Math.round(dims.get('reasoning_depth') ?? 76), trend: 8 },
    { label: '元认知', value: Math.round(dims.get('metacognition') ?? 84), trend: 6 },
    { label: '表达清晰度', value: Math.round(dims.get('clarity') ?? 71), trend: 5 },
  ];
}

// ─── Component ────────────────────────────────────────────────────────────────

export function CognitiveProfilePage() {
  const profileStore = useProfileStore();
  const selectedProfile = useSelectedProfile();
  const isLoading = useProfileLoading();
  const stats = useAggregatedStats();
  const intents = useIntentDistribution();

  const [activeProfile, setActiveProfile] = useState<CognitiveProfile | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Load demo data on mount if store is empty
  useEffect(() => {
    if (profileStore.profiles.length === 0 && !activeProfile) {
      profileStore.setProfiles([demoProfile]);
      profileStore.selectProfile(demoProfile.id);
      profileStore.setAggregatedStats(demoStats);
      profileStore.setIntentDistribution(demoIntents);
      profileStore.setRadarData(
        demoProfile.dimensions.map((d) => ({
          dimension: d.label,
          value: d.value,
          fullMark: d.max,
        }))
      );
      setActiveProfile(demoProfile);
    }
  }, [profileStore, activeProfile]);

  // Sync from store when selected profile changes
  useEffect(() => {
    if (selectedProfile) {
      setActiveProfile(selectedProfile);
    }
  }, [selectedProfile]);

  const handleRefresh = useCallback(() => {
    setIsRefreshing(true);
    // Simulate refresh delay
    setTimeout(() => {
      setIsRefreshing(false);
    }, 800);
  }, []);

  const metricCards = useMemo(() => buildMetricCards(activeProfile), [activeProfile]);

  const dimensions: CognitiveDimension[] = useMemo(
    () => activeProfile?.dimensions ?? [],
    [activeProfile]
  );

  const radarData = useMemo(
    () =>
      dimensions.map((d) => ({
        dimension: d.label,
        value: d.value,
        fullMark: d.max,
      })),
    [dimensions]
  );

  const confBadge = useMemo(
    () => confidenceBadge(activeProfile?.confidenceLevel ?? 'medium'),
    [activeProfile]
  );
  const ConfIcon = confBadge.icon;

  const currentStats: ProfileStats | null = useMemo(() => {
    if (stats) return stats;
    if (!activeProfile) return null;
    return {
      reasoningDepth: activeProfile.dimensions.find((d) => d.key === 'reasoning_depth')?.value ?? 0,
      metacognition: activeProfile.dimensions.find((d) => d.key === 'metacognition')?.value ?? 0,
      expressionClarity: activeProfile.dimensions.find((d) => d.key === 'clarity')?.value ?? 0,
      contextWindowUsage: activeProfile.dimensions.find((d) => d.key === 'context_usage')?.value ?? 0,
      entityCount: 0,
      topicTreeDepth: 0,
      coherenceScore: activeProfile.dimensions.find((d) => d.key === 'coherence')?.value ?? 0,
      responseLatencyMs: 0,
    };
  }, [stats, activeProfile]);

  const currentIntents: IntentDistribution[] = useMemo(() => {
    if (intents.length > 0) return intents;
    return [];
  }, [intents]);

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
            </div>
          </div>
          <button
            type="button"
            onClick={handleRefresh}
            disabled={isRefreshing || isLoading}
            className={cn(
              'flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium',
              'bg-surface-card border border-border-subtle text-text-secondary',
              'hover:bg-surface-card-hover hover:text-primary transition-colors',
              'disabled:opacity-50 disabled:cursor-not-allowed'
            )}
            aria-label="刷新画像数据"
          >
            <RefreshCw className={cn('w-4 h-4', (isRefreshing || isLoading) && 'animate-spin')} />
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
                  {activeProfile?.overallScore ?? 0}
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
              {activeProfile?.summary && (
                <p className="text-xs text-text-secondary leading-relaxed">
                  {activeProfile.summary}
                </p>
              )}
              <div className="flex items-center gap-4 pt-2">
                <div className="flex items-center gap-1.5 text-xs text-text-muted">
                  <Calendar className="w-3.5 h-3.5" />
                  {activeProfile ? formatTimestamp(activeProfile.timestamp) : '--'}
                </div>
                <div className="flex items-center gap-1.5 text-xs text-text-muted">
                  <Hash className="w-3.5 h-3.5" />
                  {activeProfile?.sessionId.slice(0, 8) ?? '--'}
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
              <CognitiveRadarChart data={radarData.length > 0 ? radarData : undefined} size={260} showLegend />
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
            <MetricCards metrics={metricCards} />
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

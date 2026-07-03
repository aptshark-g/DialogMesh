import type { FC } from 'react';
import { ArrowUp, ArrowDown, Minus } from 'lucide-react';
import type { ProfileStats } from '@/types/profile';
import { formatDuration } from '@/lib/utils';

interface ProfileStatsGridProps {
  stats: ProfileStats | null;
}

interface StatItemDef {
  key: keyof ProfileStats;
  label: string;
  unit?: string;
  formatter?: (v: number) => string;
}

const statDefs: StatItemDef[] = [
  { key: 'reasoningDepth', label: '推理深度', unit: '分' },
  { key: 'metacognition', label: '元认知', unit: '分' },
  { key: 'expressionClarity', label: '表达清晰度', unit: '分' },
  { key: 'contextWindowUsage', label: '上下文利用率', unit: '%' },
  { key: 'entityCount', label: '实体数量', unit: '个' },
  { key: 'topicTreeDepth', label: '话题树深度', unit: '层' },
  { key: 'coherenceScore', label: '连贯性评分', unit: '分' },
  {
    key: 'responseLatencyMs',
    label: '平均响应延迟',
    formatter: (v) => formatDuration(v),
  },
];

export const ProfileStatsGrid: FC<ProfileStatsGridProps> = ({ stats }) => {
  if (!stats) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {statDefs.map((def) => (
          <div
            key={def.key}
            className="bg-surface-card rounded-xl border border-border-subtle p-4"
          >
            <div className="skeleton h-4 w-12 rounded mb-2" />
            <div className="skeleton h-8 w-16 rounded" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {statDefs.map((def) => {
        const rawValue = stats[def.key];
        const value = typeof rawValue === 'number' ? rawValue : 0;
        const displayValue = def.formatter ? def.formatter(value) : `${Math.round(value)}${def.unit ?? ''}`;
        const trend = value > 70 ? 'up' : value < 40 ? 'down' : 'stable';

        return (
          <div
            key={def.key}
            className="bg-surface-card rounded-xl border border-border-subtle p-4 hover:border-border-medium transition-colors"
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs text-text-muted">{def.label}</span>
              <TrendIcon trend={trend} />
            </div>
            <span className="text-lg sm:text-xl font-bold text-text-primary">{displayValue}</span>
          </div>
        );
      })}
    </div>
  );
};

const TrendIcon: FC<{ trend: 'up' | 'down' | 'stable' }> = ({ trend }) => {
  if (trend === 'up') {
    return <ArrowUp className="w-3.5 h-3.5 text-status-success" />;
  }
  if (trend === 'down') {
    return <ArrowDown className="w-3.5 h-3.5 text-status-error" />;
  }
  return <Minus className="w-3.5 h-3.5 text-text-muted" />;
};

export default ProfileStatsGrid;

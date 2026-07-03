// FILE: frontend/src/components/analytics/IntentDistribution.tsx

import type { ReactElement } from 'react';
import { useMemo } from 'react';
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
} from 'recharts';
import { PieChartIcon } from 'lucide-react';
import type { IntentDistributionItem } from '../../types/analytics';
import { cn } from '../../lib/utils';

interface IntentDistributionProps {
  data: IntentDistributionItem[];
  className?: string;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: Array<{
    payload: IntentDistributionItem;
  }>;
}

function CustomTooltip({ active, payload }: CustomTooltipProps): ReactElement | null {
  if (!active || !payload || payload.length === 0) return null;
  const item = payload[0].payload;

  return (
    <div className="bg-surface-card border border-border-medium rounded-lg shadow-card px-3 py-2">
      <div className="flex items-center gap-2">
        <span
          className="w-2.5 h-2.5 rounded-full"
          style={{ backgroundColor: item.color }}
        />
        <span className="text-xs font-medium text-text-primary">{item.label}</span>
      </div>
      <div className="mt-1 text-xs text-text-secondary">
        {item.count} 次 · {item.percentage}%
      </div>
    </div>
  );
}

export function IntentDistribution({ data, className }: IntentDistributionProps) {
  const total = useMemo(
    () => data.reduce((sum, d) => sum + d.count, 0),
    [data]
  );

  return (
    <div className={cn('flex flex-col', className)}>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-md bg-primary/10">
            <PieChartIcon className="w-4 h-4 text-primary" />
          </div>
          <h3 className="text-sm font-semibold text-text-primary">意图分布</h3>
        </div>
        <span className="text-xs text-text-muted">{total} 次识别</span>
      </div>

      {/* Chart + Legend */}
      <div className="flex-1 min-h-[240px] flex flex-col">
        {data.length > 0 ? (
          <>
            <div className="flex-1 min-h-[180px]">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={data}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={85}
                    paddingAngle={3}
                    dataKey="count"
                    nameKey="label"
                    stroke="none"
                  >
                    {data.map((entry) => (
                      <Cell key={entry.intent} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip content={<CustomTooltip />} />
                </PieChart>
              </ResponsiveContainer>
            </div>

            {/* Legend */}
            <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1.5">
              {data.slice(0, 6).map((item) => (
                <div
                  key={item.intent}
                  className="flex items-center justify-between text-xs"
                >
                  <div className="flex items-center gap-1.5 min-w-0">
                    <span
                      className="w-2 h-2 rounded-full shrink-0"
                      style={{ backgroundColor: item.color }}
                    />
                    <span className="text-text-secondary truncate">{item.label}</span>
                  </div>
                  <span className="text-text-muted ml-1">{item.percentage}%</span>
                </div>
              ))}
            </div>
          </>
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-text-muted">
            <PieChartIcon className="w-10 h-10 mb-3 opacity-30" />
            <p className="text-sm">暂无意图数据</p>
            <p className="text-xs mt-1 opacity-60">对话后将显示意图识别分布</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default IntentDistribution;

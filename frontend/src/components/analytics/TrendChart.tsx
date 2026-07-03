// FILE: frontend/src/components/analytics/TrendChart.tsx

import { useMemo } from 'react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import { TrendingUp, MessageSquare, Clock } from 'lucide-react';
import type { TrendDataPoint } from '../../types/analytics';
import { cn } from '../../lib/utils';

interface TrendChartProps {
  data: TrendDataPoint[];
  className?: string;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: Array<{
    name: string;
    value: number;
    color: string;
  }>;
  label?: string;
}

function CustomTooltip({ active, payload, label }: CustomTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;

  return (
    <div className="bg-surface-card border border-border-medium rounded-lg shadow-card px-4 py-3 min-w-[180px]">
      <p className="text-sm font-semibold text-text-primary mb-2">{label}</p>
      <div className="space-y-1.5">
        {payload.map((entry) => (
          <div key={entry.name} className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <span
                className="w-2.5 h-2.5 rounded-full"
                style={{ backgroundColor: entry.color }}
              />
              <span className="text-xs text-text-secondary">{entry.name}</span>
            </div>
            <span className="text-xs font-medium text-text-primary">
              {entry.value}
              {entry.name === '平均延迟' ? 'ms' : ''}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function TrendChart({ data, className }: TrendChartProps) {
  const hasData = data.length > 0 && data.some((d) => d.turns > 0 || d.messages > 0);

  const stats = useMemo(() => {
    if (data.length === 0) {
      return { totalTurns: 0, totalMessages: 0, avgLatency: 0 };
    }
    const totalTurns = data.reduce((s, d) => s + d.turns, 0);
    const totalMessages = data.reduce((s, d) => s + d.messages, 0);
    const avgLatency =
      data.length > 0
        ? Math.round(data.reduce((s, d) => s + d.avgLatency, 0) / data.length)
        : 0;
    return { totalTurns, totalMessages, avgLatency };
  }, [data]);

  return (
    <div className={cn('flex flex-col', className)}>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-md bg-primary/10">
            <TrendingUp className="w-4 h-4 text-primary" />
          </div>
          <h3 className="text-sm font-semibold text-text-primary">会话趋势</h3>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5 text-xs text-text-muted">
            <MessageSquare className="w-3 h-3" />
            <span>{stats.totalMessages} 消息</span>
          </div>
          <div className="flex items-center gap-1.5 text-xs text-text-muted">
            <Clock className="w-3 h-3" />
            <span>{stats.avgLatency}ms 平均延迟</span>
          </div>
        </div>
      </div>

      {/* Chart */}
      <div className="flex-1 min-h-[240px]">
        {hasData ? (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="colorTurns" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#D97706" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="#D97706" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="colorMessages" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#0D9488" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="#0D9488" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="var(--border-subtle)"
                vertical={false}
              />
              <XAxis
                dataKey="label"
                tick={{ fill: '#6B6680', fontSize: 11 }}
                axisLine={{ stroke: 'var(--border-subtle)' }}
                tickLine={false}
              />
              <YAxis
                tick={{ fill: '#6B6680', fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                allowDecimals={false}
              />
              <Tooltip content={<CustomTooltip />} />
              <Legend
                wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
                iconType="circle"
                iconSize={8}
              />
              <Area
                type="monotone"
                dataKey="turns"
                name="对话轮次"
                stroke="#D97706"
                strokeWidth={2}
                fillOpacity={1}
                fill="url(#colorTurns)"
                dot={{ r: 3, fill: '#D97706', strokeWidth: 0 }}
                activeDot={{ r: 5, fill: '#F59E0B', stroke: '#D97706', strokeWidth: 2 }}
              />
              <Area
                type="monotone"
                dataKey="messages"
                name="消息总量"
                stroke="#0D9488"
                strokeWidth={2}
                fillOpacity={1}
                fill="url(#colorMessages)"
                dot={{ r: 3, fill: '#0D9488', strokeWidth: 0 }}
                activeDot={{ r: 5, fill: '#14B8A6', stroke: '#0D9488', strokeWidth: 2 }}
              />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-text-muted">
            <TrendingUp className="w-10 h-10 mb-3 opacity-30" />
            <p className="text-sm">暂无趋势数据</p>
            <p className="text-xs mt-1 opacity-60">开始对话后将自动生成趋势图表</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default TrendChart;

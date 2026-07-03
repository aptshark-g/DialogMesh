import type { FC } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import type { IntentDistribution } from '@/types/profile';

interface IntentDistributionChartProps {
  data: IntentDistribution[];
  title?: string;
}

export const IntentDistributionChart: FC<IntentDistributionChartProps> = ({
  data,
  title = '意图分布',
}) => {
  if (data.length === 0) {
    return (
      <div className="bg-surface-card rounded-xl border border-border-subtle p-6">
        <h3 className="text-sm font-semibold text-text-primary mb-4">{title}</h3>
        <div className="h-48 flex items-center justify-center">
          <p className="text-sm text-text-muted">暂无意图数据</p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-surface-card rounded-xl border border-border-subtle p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-text-primary">{title}</h3>
        <span className="text-xs text-text-muted">
          共 {data.reduce((sum, d) => sum + d.count, 0)} 条记录
        </span>
      </div>
      <div className="h-48 sm:h-56">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={data}
            layout="vertical"
            margin={{ top: 0, right: 24, left: 0, bottom: 0 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#2A2635" horizontal={false} />
            <XAxis
              type="number"
              domain={[0, 100]}
              tick={{ fill: '#6B6680', fontSize: 11 }}
              tickFormatter={(v: number) => `${v}%`}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              type="category"
              dataKey="intent"
              tick={{ fill: '#A9A5B8', fontSize: 12 }}
              width={80}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#1A1724',
                border: '1px solid #2A2635',
                borderRadius: '8px',
                fontSize: '12px',
                color: '#E8E6F0',
              }}
              formatter={(value) => [`${typeof value === 'number' ? value.toFixed(1) : value}%`, '占比']}
              cursor={{ fill: 'rgba(217, 119, 6, 0.05)' }}
            />
            <Bar dataKey="percentage" radius={[0, 4, 4, 0]} barSize={20}>
              {data.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.color} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default IntentDistributionChart;

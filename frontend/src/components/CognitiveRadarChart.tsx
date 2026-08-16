import type { FC } from 'react';
import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  ResponsiveContainer,
} from 'recharts';

export interface RadarDataPoint {
  dimension: string;
  value: number;
  fullMark: number;
}

interface CognitiveRadarChartProps {
  data?: RadarDataPoint[];
  size?: number;
  showLegend?: boolean;
}

/* 去示范数据:无数据时呈现虚线占位, 不渲染假雷达 */
export const CognitiveRadarChart: FC<CognitiveRadarChartProps> = ({
  data,
  size: _size,
  showLegend = false,
}) => {
  if (!data || data.length === 0) {
    return (
      <div className="mx-auto w-full h-full min-h-[180px] flex items-center justify-center rounded-lg border border-dashed border-border-subtle text-xs text-text-muted">
        暂无画像数据
      </div>
    );
  }
  return (
    <div className="mx-auto w-full h-full">
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart cx="50%" cy="50%" outerRadius="70%" data={data}>
          <PolarGrid
            stroke="#3A3548"
            strokeWidth={1}
          />
          <PolarAngleAxis
            dataKey="dimension"
            tick={{ fill: '#6B6680', fontSize: 12, fontFamily: 'Inter, Noto Sans SC, sans-serif' }}
          />
          <PolarRadiusAxis
            angle={90}
            domain={[0, 100]}
            tick={{ fill: '#6B6680', fontSize: 10 }}
            tickCount={4}
            axisLine={false}
          />
          <Radar
            name="认知维度"
            dataKey="value"
            stroke="#D97706"
            strokeWidth={2}
            fill="rgba(217, 119, 6, 0.15)"
            fillOpacity={1}
            dot={{ fill: '#F59E0B', strokeWidth: 0, r: 4 }}
            activeDot={{ fill: '#F59E0B', stroke: '#D97706', strokeWidth: 2, r: 5 }}
          />
        </RadarChart>
      </ResponsiveContainer>
      {showLegend && (
        <div className="text-center mt-2 text-xs text-text-muted">
          认知维度评分
        </div>
      )}
    </div>
  );
};

export default CognitiveRadarChart;

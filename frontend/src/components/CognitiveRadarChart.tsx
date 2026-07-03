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

const defaultData: RadarDataPoint[] = [
  { dimension: '元认知', value: 84, fullMark: 100 },
  { dimension: '推理深度', value: 76, fullMark: 100 },
  { dimension: '置信度', value: 68, fullMark: 100 },
  { dimension: '稳定性', value: 72, fullMark: 100 },
  { dimension: '发散度', value: 58, fullMark: 100 },
];

export const CognitiveRadarChart: FC<CognitiveRadarChartProps> = ({
  data = defaultData,
  size: _size,
  showLegend = false,
}) => {
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

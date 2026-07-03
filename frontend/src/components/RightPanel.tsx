import { useState } from 'react';
import type { FC } from 'react';
import {
  Info,
  ChevronLeft,
  RefreshCw,
} from 'lucide-react';
import { CognitiveRadarChart } from './CognitiveRadarChart';
import { MetricCards } from './MetricCards';
import { StatusProgress } from './StatusProgress';
import { useUIStore } from '@/stores/uiStore';

export interface RightPanelProps {
  lastUpdated?: string;
  onRefresh?: () => void;
}

export const RightPanel: FC<RightPanelProps> = ({
  lastUpdated = '14:32:18',
  onRefresh,
}) => {
  const [isRefreshing, setIsRefreshing] = useState(false);
  const closeSidePanel = useUIStore((s) => s.closeSidePanel);

  const handleRefresh = () => {
    setIsRefreshing(true);
    onRefresh?.();
    setTimeout(() => setIsRefreshing(false), 800);
  };

  return (
    <div className="w-full h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-subtle shrink-0">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-text-primary">
            认知画像
          </h2>
          <div className="group relative">
            <Info className="w-4 h-4 text-text-muted cursor-help" />
            <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 rounded-md bg-surface-card border border-medium shadow-card opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200 w-48 z-50">
              <p className="text-xs text-text-secondary leading-relaxed">
                实时展示当前会话的认知维度分析，包括元认知、推理深度、置信度等指标
              </p>
            </div>
          </div>
        </div>
        <button
          type="button"
          onClick={closeSidePanel}
          className="p-1.5 rounded-md hover:bg-surface-card-hover transition-colors"
          aria-label="收起右侧面板"
        >
          <ChevronLeft className="w-4 h-4 text-text-muted" />
        </button>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-5 scrollbar-hide">
        {/* Cognitive Radar Chart */}
        <div className="flex flex-col items-center">
          <CognitiveRadarChart size={200} />
        </div>

        {/* Metric Cards */}
        <MetricCards />

        {/* Status Progress */}
        <StatusProgress />
      </div>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-subtle flex items-center justify-between shrink-0">
        <span className="text-xs text-text-muted">
          数据更新于 {lastUpdated}
        </span>
        <button
          type="button"
          onClick={handleRefresh}
          className="p-1.5 rounded-md hover:bg-surface-card-hover transition-colors"
          aria-label="刷新数据"
        >
          <RefreshCw
            className={`w-3.5 h-3.5 text-text-muted ${
              isRefreshing ? 'animate-spin' : ''
            }`}
          />
        </button>
      </div>
    </div>
  );
};

export default RightPanel;

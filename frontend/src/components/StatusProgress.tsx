import type { FC } from 'react';
import { motion } from 'framer-motion';
import { Shield, AlertTriangle } from 'lucide-react';

export interface StatusProgressItem {
  icon: 'success' | 'risk';
  label: string;
  percentage: number;
  description: string;
}

interface StatusProgressProps {
  items?: StatusProgressItem[];
}

/* 去示范数据:成功/风险指标尚无后端数据源(见 UI_REFACTOR_PLAN B6),无数据时呈现空态 */
export const StatusProgress: FC<StatusProgressProps> = ({ items }) => {
  if (!items || items.length === 0) {
    return (
      <div className="py-4 text-center text-xs text-text-muted">
        暂无状态数据
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-4">
      {items.map((item) => {
        const isSuccess = item.icon === 'success';
        const Icon = isSuccess ? Shield : AlertTriangle;
        const iconColor = isSuccess ? 'text-primary' : 'text-status-error';
        const fillColor = isSuccess ? 'bg-primary' : 'bg-status-error';
        const fillOpacity = isSuccess ? 'bg-primary/10' : 'bg-status-error/10';

        return (
          <div
            key={item.label}
            className="flex flex-col gap-2 p-3 rounded-lg bg-surface-card border border-border-subtle"
          >
            {/* Top row: icon + label + percentage */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className={`p-1 rounded-md ${fillOpacity}`}>
                  <Icon className={`w-4 h-4 ${iconColor}`} />
                </div>
                <span className="text-sm font-medium text-text-primary">
                  {item.label}
                </span>
              </div>
              <span className={`text-sm font-bold ${iconColor}`}>
                {item.percentage}%
              </span>
            </div>

            {/* Progress bar */}
            <div className="status-progress-bar">
              <motion.div
                className={`status-progress-fill ${fillColor}`}
                initial={{ width: 0 }}
                animate={{ width: `${item.percentage}%` }}
                transition={{ duration: 0.8, ease: 'easeOut', delay: 0.2 }}
              />
            </div>

            {/* Description */}
            <p className="text-xs text-text-muted leading-relaxed">
              {item.description}
            </p>
          </div>
        );
      })}
    </div>
  );
};

export default StatusProgress;

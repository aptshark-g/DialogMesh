import type { FC } from 'react';
import { motion } from 'framer-motion';
import { ArrowUp } from 'lucide-react';

export interface MetricCardData {
  label: string;
  value: number;
  trend: number;
}

interface MetricCardsProps {
  metrics?: MetricCardData[];
}

/* 去示范数据:无数据时呈现诚实空态(第一次使用/后端未连接), 不放 76/84/71 之类的假精度 */
export const MetricCards: FC<MetricCardsProps> = ({ metrics }) => {
  if (!metrics || metrics.length === 0) {
    return (
      <div className="py-4 text-center text-xs text-text-muted">
        暂无指标数据
      </div>
    );
  }
  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
      {metrics.map((metric, idx) => (
        <motion.div
          key={metric.label}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: idx * 0.1 }}
          whileHover={{ scale: 1.02, y: -2 }}
          className="flex flex-col items-center p-3 rounded-lg bg-surface-card border border-border-subtle cursor-default"
        >
          <motion.span
            className="text-3xl font-bold text-primary-light"
            initial={{ opacity: 0, scale: 0.5 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.4, delay: idx * 0.1 + 0.2, type: 'spring', stiffness: 200 }}
          >
            {metric.value}
          </motion.span>
          <span className="text-xs text-text-muted mt-1">{metric.label}</span>
          {/* 趋势仅非 0 时显示 — 接线前 trend 恒为 0, 显示 ↑0 是假精度 */}
          {metric.trend !== 0 && (
            <div className="flex items-center gap-0.5 mt-1 text-status-success text-xs font-medium">
              <ArrowUp className="w-3 h-3" />
              <span>{metric.trend}</span>
            </div>
          )}
        </motion.div>
      ))}
    </div>
  );
};

export default MetricCards;

import type { FC } from 'react';
import { motion } from 'framer-motion';
import type { CognitiveDimension } from '@/types/profile';

interface DimensionBreakdownProps {
  dimensions: CognitiveDimension[];
}

export const DimensionBreakdown: FC<DimensionBreakdownProps> = ({ dimensions }) => {
  if (dimensions.length === 0) {
    return (
      <div className="bg-surface-card rounded-xl border border-border-subtle p-6">
        <h3 className="text-sm font-semibold text-text-primary mb-4">维度细分</h3>
        <div className="space-y-4">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="skeleton h-12 rounded-lg" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="bg-surface-card rounded-xl border border-border-subtle p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-text-primary">维度细分</h3>
        <span className="text-xs text-text-muted">满分 100</span>
      </div>
      <div className="space-y-4">
        {dimensions.map((dim, index) => (
          <DimensionRow key={dim.key} dim={dim} index={index} />
        ))}
      </div>
    </div>
  );
};

interface DimensionRowProps {
  dim: CognitiveDimension;
  index: number;
}

const DimensionRow: FC<DimensionRowProps> = ({ dim, index }) => {
  const percentage = Math.min(100, Math.max(0, (dim.value / dim.max) * 100));
  const barColor =
    percentage >= 80
      ? 'bg-status-success'
      : percentage >= 60
        ? 'bg-primary'
        : percentage >= 40
          ? 'bg-status-warning'
          : 'bg-status-error';

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: index * 0.05 }}
    >
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-text-primary">{dim.label}</span>
          {dim.description && (
            <span className="text-xs text-text-muted hidden sm:inline">
              {dim.description}
            </span>
          )}
        </div>
        <span className="text-sm font-semibold text-text-primary">
          {Math.round(dim.value)}
        </span>
      </div>
      <div className="h-2 rounded-full bg-surface-sidebar overflow-hidden">
        <motion.div
          className={`h-full rounded-full ${barColor}`}
          initial={{ width: 0 }}
          animate={{ width: `${percentage}%` }}
          transition={{ duration: 0.6, delay: index * 0.05, ease: 'easeOut' }}
        />
      </div>
    </motion.div>
  );
};

export default DimensionBreakdown;

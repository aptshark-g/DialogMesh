import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { cn } from '@/lib/utils';
import { Eye, EyeOff, ChevronDown, ChevronUp } from 'lucide-react';
import { Tooltip } from '@/components/ui/Tooltip';
import { INTENT_COLOR_MAP } from '@/types/graph';

export interface GraphLegendProps {
  visible: boolean;
  onToggle: () => void;
  nodeCounts: Record<string, number>;
  activeFilters: string[];
  onFilterToggle: (intent: string) => void;
  totalNodes?: number;
  filteredNodes?: number;
  className?: string;
}

export function GraphLegend({
  visible,
  onToggle,
  nodeCounts,
  activeFilters,
  onFilterToggle,
  totalNodes = 0,
  filteredNodes = 0,
  className,
}: GraphLegendProps) {
  const [expanded, setExpanded] = useState(true);
  const allIntents = Object.entries(INTENT_COLOR_MAP);

  const totalCount = allIntents.reduce((sum, [key]) => sum + (nodeCounts[key] ?? 0), 0);

  return (
    <div
      className={cn(
        'absolute bottom-4 right-4 z-10 flex flex-col items-end gap-2',
        className
      )}
    >
      {/* Toggle button (visible when legend is collapsed) */}
      <AnimatePresence>
        {!visible && (
          <motion.button
            type="button"
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.8 }}
            onClick={onToggle}
            className="flex items-center gap-2 px-3 py-2 rounded-lg bg-surface-card border border-subtle shadow-card text-xs font-medium text-text-secondary hover:text-text-primary hover:bg-surface-card-hover transition-colors"
            aria-label="显示图例"
          >
            <Eye className="w-3.5 h-3.5" />
            <span>图例</span>
          </motion.button>
        )}
      </AnimatePresence>

      {/* Legend panel */}
      <AnimatePresence>
        {visible && (
          <motion.div
            initial={{ opacity: 0, y: 10, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.95 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            className="w-44 sm:w-52 rounded-xl bg-surface-card border border-subtle shadow-card overflow-hidden"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-3 py-2.5 border-b border-subtle">
              <span className="text-xs font-semibold text-text-primary">意图图例</span>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => setExpanded((prev) => !prev)}
                  className="p-1 rounded-md text-text-muted hover:text-text-primary hover:bg-surface-card-hover transition-colors"
                  aria-label={expanded ? '折叠' : '展开'}
                  title={expanded ? '折叠' : '展开'}
                >
                  {expanded ? (
                    <ChevronDown className="w-3.5 h-3.5" />
                  ) : (
                    <ChevronUp className="w-3.5 h-3.5" />
                  )}
                </button>
                <button
                  type="button"
                  onClick={onToggle}
                  className="p-1 rounded-md text-text-muted hover:text-text-primary hover:bg-surface-card-hover transition-colors"
                  aria-label="隐藏图例"
                  title="隐藏图例"
                >
                  <EyeOff className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            {/* Stats summary */}
            <div className="px-3 py-2 border-b border-subtle bg-surface/50">
              <div className="flex items-center justify-between text-[10px] text-text-muted">
                <span>总节点: <span className="text-text-secondary font-medium">{totalNodes}</span></span>
                <span>显示: <span className="text-text-secondary font-medium">{filteredNodes}</span></span>
              </div>
            </div>

            {/* Intent list */}
            <AnimatePresence initial={false}>
              {expanded && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.2, ease: 'easeInOut' }}
                  className="overflow-hidden"
                >
                  <div className="px-3 py-2 space-y-1">
                    {allIntents.map(([intentKey, config]) => {
                      const count = nodeCounts[intentKey] ?? 0;
                      const isActive = activeFilters.includes(intentKey);
                      const percentage = totalCount > 0 ? Math.round((count / totalCount) * 100) : 0;

                      return (
                        <Tooltip
                          key={intentKey}
                          content={`${config.label}: ${count} 节点 (${percentage}%)`}
                          position="left"
                          delay={300}
                        >
                          <button
                            type="button"
                            onClick={() => onFilterToggle(intentKey)}
                            className={cn(
                              'w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-xs transition-all',
                              isActive
                                ? 'bg-surface-card-hover'
                                : 'opacity-50 hover:opacity-80 hover:bg-surface-card-hover'
                            )}
                            aria-pressed={isActive}
                          >
                            <span
                              className="w-3 h-3 rounded-full shrink-0 border border-white/10"
                              style={{ backgroundColor: config.hex }}
                            />
                            <span className="flex-1 text-left text-text-secondary truncate">
                              {config.label}
                            </span>
                            <span className="text-text-muted tabular-nums">{count}</span>
                          </button>
                        </Tooltip>
                      );
                    })}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

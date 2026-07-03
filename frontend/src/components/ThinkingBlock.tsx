// FILE: frontend/src/components/ThinkingBlock.tsx
import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Brain, ChevronDown, ChevronRight, Loader, CheckCircle, Zap } from 'lucide-react';

export interface ThinkingStep {
  step_number: number;
  title: string;
  description: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  latency_ms?: number;
  sub_steps?: ThinkingStep[];
}

export interface ThinkingBlockProps {
  steps: ThinkingStep[];
  isActive: boolean;
  totalLatencyMs?: number;
  className?: string;
}

const statusIconMap = {
  pending: <span className="w-4 h-4 rounded-full border-2 border-gray-300" />,
  running: <Loader className="w-4 h-4 text-status-info animate-spin" />,
  completed: <CheckCircle className="w-4 h-4 text-status-success" />,
  failed: <span className="w-4 h-4 rounded-full bg-status-error" />,
};

const StepItem: React.FC<{ step: ThinkingStep; depth?: number }> = ({ step, depth = 0 }) => {
  const [expanded, setExpanded] = useState(true);
  const hasSubSteps = step.sub_steps && step.sub_steps.length > 0;

  return (
    <div className={`${depth > 0 ? 'ml-6 border-l-2 border-gray-200 pl-3' : ''}`}>
      <button
        type="button"
        onClick={() => hasSubSteps && setExpanded(!expanded)}
        className={`flex items-start gap-3 w-full text-left py-2 px-3 rounded-lg transition-colors ${
          hasSubSteps ? 'hover:bg-amber-50' : ''
        }`}
      >
        {hasSubSteps ? (
          expanded ? (
            <ChevronDown className="w-4 h-4 text-text-muted mt-0.5 shrink-0" />
          ) : (
            <ChevronRight className="w-4 h-4 text-text-muted mt-0.5 shrink-0" />
          )
        ) : (
          <span className="w-4 shrink-0" />
        )}
        <span className="shrink-0 mt-0.5">{statusIconMap[step.status]}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium text-text-primary text-sm">
              {step.step_number}. {step.title}
            </span>
            {step.latency_ms && step.status === 'completed' && (
              <span className="text-xs text-text-muted">{step.latency_ms}ms</span>
            )}
          </div>
          <p className="text-sm text-text-secondary mt-0.5">{step.description}</p>
        </div>
      </button>
      <AnimatePresence>
        {expanded && hasSubSteps && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: 'easeInOut' }}
            className="overflow-hidden"
          >
            <div className="mt-1">
              {step.sub_steps!.map((sub) => (
                <StepItem key={sub.step_number} step={sub} depth={depth + 1} />
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export const ThinkingBlock: React.FC<ThinkingBlockProps> = ({
  steps,
  isActive,
  totalLatencyMs,
  className = '',
}) => {
  const [collapsed, setCollapsed] = useState(false);
  const completedCount = steps.filter((s) => s.status === 'completed').length;
  const runningCount = steps.filter((s) => s.status === 'running').length;

  return (
    <div className={`bg-surface-thinking rounded-xl border border-amber-200 ${className}`}>
      <button
        type="button"
        onClick={() => setCollapsed(!collapsed)}
        className="flex items-center gap-3 w-full px-4 py-3 hover:bg-amber-100/50 rounded-xl transition-colors"
      >
        <Brain className={`w-5 h-5 text-primary ${isActive ? 'animate-pulse' : ''}`} />
        <div className="flex-1 text-left">
          <span className="font-semibold text-text-primary text-sm">
            AI 思考过程
          </span>
          <span className="text-xs text-text-muted ml-2">
            {completedCount}/{steps.length} 步骤
            {runningCount > 0 && ` · ${runningCount} 进行中`}
          </span>
        </div>
        {totalLatencyMs && (
          <span className="text-xs text-text-muted flex items-center gap-1">
            <Zap className="w-3 h-3" />
            {totalLatencyMs}ms
          </span>
        )}
        {collapsed ? (
          <ChevronRight className="w-4 h-4 text-text-muted" />
        ) : (
          <ChevronDown className="w-4 h-4 text-text-muted" />
        )}
      </button>

      <AnimatePresence>
        {!collapsed && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: 'easeInOut' }}
            className="overflow-hidden"
          >
            <div className="px-2 pb-3">
              <div className="h-px bg-amber-200 mx-2 mb-2" />
              {steps.length === 0 ? (
                <div className="flex items-center gap-2 px-4 py-4 text-text-muted text-sm">
                  <Loader className="w-4 h-4 animate-spin" />
                  等待思考步骤...
                </div>
              ) : (
                <div className="space-y-1">
                  {steps.map((step) => (
                    <StepItem key={step.step_number} step={step} />
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default ThinkingBlock;

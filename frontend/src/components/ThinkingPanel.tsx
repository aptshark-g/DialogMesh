// FILE: frontend/src/components/ThinkingPanel.tsx

import { useState } from 'react';
import { cn } from '../lib/utils';
import type { ThinkingStepPayload } from '../types/api';
import { Brain, ChevronDown, ChevronUp, Loader2 } from 'lucide-react';

interface ThinkingPanelProps {
  steps: ThinkingStepPayload[];
  isActive?: boolean;
  className?: string;
}

export function ThinkingPanel({ steps, isActive = false, className }: ThinkingPanelProps) {
  const [expanded, setExpanded] = useState(true);

  if (steps.length === 0 && !isActive) return null;

  return (
    <div className={cn('rounded-xl bg-surface-thinking/40 border border-primary-light/30 overflow-hidden', className)}>
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-surface-thinking/60 transition-colors"
      >
        <div className="flex items-center gap-2 text-sm font-medium text-primary">
          <Brain className="h-4 w-4" />
          <span>认知推理过程</span>
          {isActive && (
            <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
          )}
        </div>
        {expanded ? (
          <ChevronUp className="h-4 w-4 text-text-muted" />
        ) : (
          <ChevronDown className="h-4 w-4 text-text-muted" />
        )}
      </button>

      {expanded && (
        <div className="px-4 pb-3 space-y-2">
          {steps.map((step, idx) => (
            <div key={idx} className="flex gap-3">
              <div className="flex flex-col items-center pt-0.5">
                <div className="h-5 w-5 rounded-full bg-primary/10 flex items-center justify-center text-xs font-semibold text-primary">
                  {step.step}
                </div>
                {idx < steps.length - 1 && (
                  <div className="w-px h-full bg-primary/20 mt-1" />
                )}
              </div>
              <div className="flex-1 pb-2">
                <p className="text-sm text-text-primary">{step.description}</p>
                {step.detail && (
                  <p className="text-xs text-text-secondary mt-0.5">{step.detail}</p>
                )}
              </div>
            </div>
          ))}
          {isActive && steps.length === 0 && (
            <div className="flex items-center gap-2 py-2 text-sm text-text-secondary">
              <Loader2 className="h-4 w-4 animate-spin" />
              正在初始化推理...
            </div>
          )}
        </div>
      )}
    </div>
  );
}

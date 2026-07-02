// FILE: frontend/src/components/TaskGraphView.tsx

import type { ReactNode } from 'react';
import { cn } from '../lib/utils';
import type { TaskGraphNode } from '../types/api';
import {
  CheckCircle2,
  XCircle,
  Loader2,
  Clock,
  GitBranch,
} from 'lucide-react';

interface TaskGraphViewProps {
  nodes: TaskGraphNode[];
  className?: string;
}

const STATUS_ICON: Record<TaskGraphNode['status'], ReactNode> = {
  pending: <Clock className="h-3.5 w-3.5 text-text-muted" />,
  running: <Loader2 className="h-3.5 w-3.5 animate-spin text-status-info" />,
  completed: <CheckCircle2 className="h-3.5 w-3.5 text-status-success" />,
  failed: <XCircle className="h-3.5 w-3.5 text-status-error" />,
};

const STATUS_LABEL: Record<TaskGraphNode['status'], string> = {
  pending: '待执行',
  running: '执行中',
  completed: '已完成',
  failed: '失败',
};

export function TaskGraphView({ nodes, className }: TaskGraphViewProps) {
  if (!nodes || nodes.length === 0) return null;

  const completed = nodes.filter((n) => n.status === 'completed').length;
  const progress = Math.round((completed / nodes.length) * 100);

  return (
    <div className={cn('rounded-xl bg-surface-card border border-gray-200 overflow-hidden', className)}>
      <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-medium text-text-primary">
          <GitBranch className="h-4 w-4 text-primary" />
          <span>Task Graph</span>
          <span className="text-xs text-text-muted">({nodes.length} 节点)</span>
        </div>
        <span className="text-xs font-medium text-primary">{progress}%</span>
      </div>

      <div className="h-1.5 bg-gray-100">
        <div
          className="h-full bg-primary transition-all duration-500 rounded-r-full"
          style={{ width: `${progress}%` }}
        />
      </div>

      <div className="px-4 py-3 space-y-2 max-h-48 overflow-y-auto">
        {nodes.map((node) => (
          <div
            key={node.id}
            className={cn(
              'flex items-center gap-3 rounded-lg px-3 py-2 text-sm',
              node.status === 'running' && 'bg-status-info/5',
              node.status === 'failed' && 'bg-status-error/5'
            )}
          >
            {STATUS_ICON[node.status]}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-medium text-text-primary truncate">{node.id}</span>
                <span className="text-[10px] uppercase tracking-wider text-text-muted bg-gray-100 rounded px-1.5 py-0.5">
                  {node.type}
                </span>
              </div>
              {node.result && (
                <p className="text-xs text-text-secondary mt-0.5 truncate">{node.result}</p>
              )}
            </div>
            <span className="text-xs text-text-muted whitespace-nowrap">{STATUS_LABEL[node.status]}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

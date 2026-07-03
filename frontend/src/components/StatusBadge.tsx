// FILE: frontend/src/components/StatusBadge.tsx

import type { ReactNode } from 'react';
import type { SessionState } from '../types/api';
import { motion } from 'framer-motion';
import { cn } from '../lib/utils';
import {
  Circle,
  Loader2,
  HelpCircle,
  AlertCircle,
  CheckCircle2,
  XCircle,
} from 'lucide-react';

interface StatusBadgeProps {
  state: SessionState;
  className?: string;
  showLabel?: boolean;
}

const STATE_CONFIG: Record<
  SessionState,
  { label: string; color: string; icon: ReactNode }
> = {
  idle: {
    label: '空闲',
    color: 'bg-gray-100 text-text-muted',
    icon: <Circle className="h-3.5 w-3.5" />,
  },
  active: {
    label: '活跃',
    color: 'bg-status-success/10 text-status-success',
    icon: <CheckCircle2 className="h-3.5 w-3.5" />,
  },
  waiting_clarification: {
    label: '等待澄清',
    color: 'bg-status-warning/10 text-status-warning',
    icon: <HelpCircle className="h-3.5 w-3.5" />,
  },
  processing: {
    label: '处理中',
    color: 'bg-status-info/10 text-status-info',
    icon: <Loader2 className="h-3.5 w-3.5 animate-spin" />,
  },
  error: {
    label: '异常',
    color: 'bg-status-error/10 text-status-error',
    icon: <AlertCircle className="h-3.5 w-3.5" />,
  },
  closed: {
    label: '已关闭',
    color: 'bg-gray-100 text-text-muted',
    icon: <XCircle className="h-3.5 w-3.5" />,
  },
  initializing: {
    label: '初始化',
    color: 'bg-gray-100 text-text-muted',
    icon: <Loader2 className="h-3.5 w-3.5 animate-spin" />,
  },
  thinking: {
    label: '思考中',
    color: 'bg-status-info/10 text-status-info',
    icon: <Loader2 className="h-3.5 w-3.5 animate-spin" />,
  },
  clarifying: {
    label: '澄清中',
    color: 'bg-status-warning/10 text-status-warning',
    icon: <HelpCircle className="h-3.5 w-3.5" />,
  },
  responding: {
    label: '响应中',
    color: 'bg-status-success/10 text-status-success',
    icon: <Loader2 className="h-3.5 w-3.5 animate-spin" />,
  },
};

export function StatusBadge({ state, className, showLabel = true }: StatusBadgeProps) {
  const config = STATE_CONFIG[state] || STATE_CONFIG.idle;
  return (
    <motion.span
      key={state}
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.2 }}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium',
        config.color,
        className
      )}
    >
      {config.icon}
      {showLabel && config.label}
    </motion.span>
  );
}

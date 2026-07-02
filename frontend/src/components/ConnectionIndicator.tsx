// FILE: frontend/src/components/ConnectionIndicator.tsx

import type { ReactNode } from 'react';
import { cn, formatRelativeTime } from '../lib/utils';
import type { ConnectionStatus } from '../types/api';
import { Wifi, WifiOff, Loader2, AlertCircle } from 'lucide-react';

interface ConnectionIndicatorProps {
  status: ConnectionStatus;
  className?: string;
}

export function ConnectionIndicator({ status, className }: ConnectionIndicatorProps) {
  let icon: ReactNode;
  let text: string;
  let color: string;

  if (status.connecting) {
    icon = <Loader2 className="h-3.5 w-3.5 animate-spin" />;
    text = '连接中…';
    color = 'text-status-warning';
  } else if (status.connected) {
    icon = <Wifi className="h-3.5 w-3.5" />;
    text = '已连接';
    color = 'text-status-success';
  } else if (status.error) {
    icon = <AlertCircle className="h-3.5 w-3.5" />;
    text = '连接异常';
    color = 'text-status-error';
  } else {
    icon = <WifiOff className="h-3.5 w-3.5" />;
    text = '未连接';
    color = 'text-text-muted';
  }

  return (
    <div className={cn('inline-flex items-center gap-2 text-xs', color, className)}>
      {icon}
      <span>{text}</span>
      {status.lastPingAt && status.connected && (
        <span className="text-text-muted">
          心跳 {formatRelativeTime(status.lastPingAt)}
        </span>
      )}
    </div>
  );
}

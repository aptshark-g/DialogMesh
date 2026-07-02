import { memo } from 'react';
import { Wifi, WifiOff, Activity, AlertTriangle } from 'lucide-react';
import type { ConnectionState } from '../types/ui';

interface ConnectionStatusProps {
  state: ConnectionState;
}

const ConnectionStatus = memo(function ConnectionStatus({ state }: ConnectionStatusProps) {
  const configs = {
    open: { icon: Activity, color: 'text-status-success', bg: 'bg-green-50', label: '已连接' },
    connecting: { icon: Wifi, color: 'text-status-warning', bg: 'bg-amber-50', label: '连接中...' },
    closing: { icon: WifiOff, color: 'text-text-muted', bg: 'bg-gray-50', label: '断开中' },
    closed: { icon: WifiOff, color: 'text-text-muted', bg: 'bg-gray-50', label: '已断开' },
    error: { icon: AlertTriangle, color: 'text-status-error', bg: 'bg-red-50', label: '连接错误' },
  };

  const cfg = configs[state.status];
  const Icon = cfg.icon;

  return (
    <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full ${cfg.bg} border border-gray-200`}>
      <Icon size={14} className={cfg.color} />
      <span className={`text-xs font-medium ${cfg.color}`}>{cfg.label}</span>
      {state.latencyMs !== null && state.status === 'open' && (
        <span className="text-xs text-text-muted">{state.latencyMs}ms</span>
      )}
    </div>
  );
});

export default ConnectionStatus;

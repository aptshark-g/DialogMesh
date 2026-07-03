// FILE: frontend/src/components/StatusBar.tsx
import React, { useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Activity,
  Clock,
  Wifi,
  WifiOff,
  Zap,
  BrainCircuit,
  AlertTriangle,
  Layers,
  Radio,
  Server,
} from 'lucide-react';

export type SessionState = 'idle' | 'active' | 'thinking' | 'clarifying' | 'error' | 'closed';

export interface CognitiveProfile {
  reasoning_depth?: 'shallow' | 'standard' | 'deep';
  creativity_level?: number;
  domain_focus?: string[];
}

export interface FSMState {
  current_state: string;
  previous_state: string;
  transition_count: number;
}

export interface StatusBarProps {
  sessionId: string;
  state: SessionState;
  currentTurn: number;
  pendingClarification: boolean;
  lastActivityAt: string;
  expiresAt?: string;
  resolvedEntities: string[];
  cognitiveProfile?: CognitiveProfile;
  fsm?: FSMState;
  wsConnected: boolean;
  wsLatencyMs?: number;
  className?: string;
}

const stateConfig: Record<
  SessionState,
  { label: string; color: string; bg: string; icon: React.ReactNode }
> = {
  idle: {
    label: '空闲',
    color: 'text-text-secondary',
    bg: 'bg-gray-100',
    icon: <Activity className="w-3.5 h-3.5" />,
  },
  active: {
    label: '处理中',
    color: 'text-status-info',
    bg: 'bg-blue-50',
    icon: <Zap className="w-3.5 h-3.5" />,
  },
  thinking: {
    label: '思考中',
    color: 'text-primary',
    bg: 'bg-amber-50',
    icon: <BrainCircuit className="w-3.5 h-3.5" />,
  },
  clarifying: {
    label: '待澄清',
    color: 'text-status-warning',
    bg: 'bg-yellow-50',
    icon: <AlertTriangle className="w-3.5 h-3.5" />,
  },
  error: {
    label: '异常',
    color: 'text-status-error',
    bg: 'bg-red-50',
    icon: <AlertTriangle className="w-3.5 h-3.5" />,
  },
  closed: {
    label: '已关闭',
    color: 'text-text-muted',
    bg: 'bg-gray-100',
    icon: <Server className="w-3.5 h-3.5" />,
  },
};

export const StatusBar: React.FC<StatusBarProps> = ({
  sessionId,
  state,
  currentTurn,
  pendingClarification,
  lastActivityAt,
  expiresAt,
  resolvedEntities,
  cognitiveProfile,
  fsm,
  wsConnected,
  wsLatencyMs,
  className = '',
}) => {
  const config = stateConfig[state] || stateConfig.idle;

  const formattedLastActivity = useMemo(() => {
    try {
      const date = new Date(lastActivityAt);
      return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch {
      return lastActivityAt;
    }
  }, [lastActivityAt]);

  const timeUntilExpiry = useMemo(() => {
    if (!expiresAt) return null;
    try {
      const diff = new Date(expiresAt).getTime() - Date.now();
      if (diff <= 0) return '已过期';
      const mins = Math.floor(diff / 60000);
      const secs = Math.floor((diff % 60000) / 1000);
      return `${mins}分${secs}秒`;
    } catch {
      return null;
    }
  }, [expiresAt]);

  return (
    <div className={`bg-surface-sidebar border-b border-gray-200 ${className}`}>
      <div className="flex items-center justify-between px-4 py-2.5">
        <div className="flex items-center gap-4 flex-wrap">
          {/* 会话标识 */}
          <div className="flex items-center gap-2">
            <Layers className="w-3.5 h-3.5 text-text-muted" />
            <span className="text-xs text-text-muted font-mono">{sessionId.slice(0, 12)}</span>
          </div>

          <div className="w-px h-4 bg-gray-200" />

          {/* 状态指示器 */}
          <AnimatePresence mode="wait">
            <motion.div
              key={state}
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.2 }}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full ${config.bg}`}
            >
              <span className={config.color}>{config.icon}</span>
              <span className={`text-xs font-medium ${config.color}`}>{config.label}</span>
            </motion.div>
          </AnimatePresence>

          {/* 回合数 */}
          <div className="flex items-center gap-1.5">
            <Radio className="w-3.5 h-3.5 text-text-muted" />
            <span className="text-xs text-text-secondary">Turn {currentTurn}</span>
          </div>

          {/* 待澄清标记 */}
          <AnimatePresence>
            {pendingClarification && (
              <motion.div
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.9 }}
                transition={{ duration: 0.2 }}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-yellow-50 border border-yellow-200"
              >
                <AlertTriangle className="w-3.5 h-3.5 text-status-warning" />
                <span className="text-xs font-medium text-status-warning">待澄清</span>
              </motion.div>
            )}
          </AnimatePresence>

          {/* 已解析实体 */}
          {resolvedEntities.length > 0 && (
            <div className="flex items-center gap-1.5">
              <BrainCircuit className="w-3.5 h-3.5 text-text-muted" />
              <div className="flex gap-1">
                {resolvedEntities.slice(0, 3).map((entity, i) => (
                  <span
                    key={i}
                    className="px-1.5 py-0.5 rounded bg-gray-100 text-xs text-text-secondary"
                  >
                    {entity}
                  </span>
                ))}
                {resolvedEntities.length > 3 && (
                  <span className="px-1.5 py-0.5 rounded bg-gray-100 text-xs text-text-muted">
                    +{resolvedEntities.length - 3}
                  </span>
                )}
              </div>
            </div>
          )}
        </div>

        <div className="flex items-center gap-4 flex-wrap">
          {/* 认知档案 */}
          {cognitiveProfile && (
            <div className="flex items-center gap-2">
              {cognitiveProfile.reasoning_depth && (
                <span
                  className={`text-xs px-2 py-0.5 rounded ${
                    cognitiveProfile.reasoning_depth === 'deep'
                      ? 'bg-purple-50 text-purple-600'
                      : cognitiveProfile.reasoning_depth === 'standard'
                      ? 'bg-blue-50 text-status-info'
                      : 'bg-gray-100 text-text-muted'
                  }`}
                >
                  {cognitiveProfile.reasoning_depth}
                </span>
              )}
              {cognitiveProfile.creativity_level !== undefined && (
                <span className="text-xs text-text-muted">
                  创造力: {cognitiveProfile.creativity_level}
                </span>
              )}
            </div>
          )}

          {/* FSM 状态 */}
          {fsm && (
            <div className="flex items-center gap-1.5">
              <Zap className="w-3.5 h-3.5 text-text-muted" />
              <span className="text-xs text-text-muted font-mono">{fsm.current_state}</span>
            </div>
          )}

          <div className="w-px h-4 bg-gray-200" />

          {/* 连接状态 */}
          <div className="flex items-center gap-1.5">
            {wsConnected ? (
              <Wifi className="w-3.5 h-3.5 text-status-success" />
            ) : (
              <WifiOff className="w-3.5 h-3.5 text-status-error" />
            )}
            <span
              className={`text-xs ${wsConnected ? 'text-status-success' : 'text-status-error'}`}
            >
              {wsConnected ? '已连接' : '断开'}
            </span>
            {wsLatencyMs !== undefined && wsConnected && (
              <span className="text-xs text-text-muted">{wsLatencyMs}ms</span>
            )}
          </div>

          <div className="w-px h-4 bg-gray-200" />

          {/* 活动时间 */}
          <div className="flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5 text-text-muted" />
            <span className="text-xs text-text-muted">{formattedLastActivity}</span>
          </div>

          {/* 过期倒计时 */}
          <AnimatePresence>
            {timeUntilExpiry && (
              <motion.div
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 4 }}
                transition={{ duration: 0.2 }}
                className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-gray-100"
              >
                <Clock className="w-3 h-3 text-text-muted" />
                <span className="text-xs text-text-muted">{timeUntilExpiry}</span>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
};

export default StatusBar;

import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';
import type { TaskExecutionStatus } from '@/types/task';
import {
  Play,
  Pause,
  RotateCcw,
  LayoutGrid,
  Download,
  Settings,
} from 'lucide-react';

interface TaskExecutionControlsProps {
  status: TaskExecutionStatus;
  onPlay: () => void;
  onPause: () => void;
  onReset: () => void;
  onAutoLayout: () => void;
  onExport: () => void;
  onSettings?: () => void;
  taskName?: string;
  taskId?: string;
}

const statusDotColor: Record<TaskExecutionStatus, string> = {
  idle: 'bg-text-muted',
  running: 'bg-status-success',
  paused: 'bg-status-warning',
  completed: 'bg-status-success',
  failed: 'bg-status-error',
  cancelled: 'bg-text-muted',
};

export function TaskExecutionControls({
  status,
  onPlay,
  onPause,
  onReset,
  onAutoLayout,
  onExport,
  onSettings,
  taskName = '未命名任务',
  taskId,
}: TaskExecutionControlsProps) {
  const isRunning = status === 'running';
  const isPaused = status === 'paused';

  return (
    <div className="flex items-center justify-between px-4 py-3 border-b border-subtle bg-surface-card">
      {/* Title Area */}
      <div className="flex items-center gap-3">
        <h2 className="text-base font-semibold text-text-primary">任务规划</h2>
        <div className="flex items-center gap-2">
          <span className={cn('h-2 w-2 rounded-full', statusDotColor[status])} />
          <span className="text-sm text-text-secondary">{taskName}</span>
          {taskId && (
            <span className="text-xs text-text-muted font-mono">{taskId}</span>
          )}
        </div>
      </div>

      {/* Buttons */}
      <div className="flex items-center gap-2">
        <ControlButton
          onClick={onPlay}
          active={isRunning}
          label="播放"
          icon={<Play className="h-4 w-4" />}
          activeClassName="bg-primary text-white animate-executing-pulse"
        />
        <ControlButton
          onClick={onPause}
          disabled={!isRunning}
          active={isPaused}
          label="暂停"
          icon={<Pause className="h-4 w-4" />}
        />
        <ControlButton
          onClick={onReset}
          label="重置"
          icon={<RotateCcw className="h-4 w-4" />}
        />
        <ControlButton
          onClick={onAutoLayout}
          label="自动布局"
          icon={<LayoutGrid className="h-4 w-4" />}
        />
        <ControlButton
          onClick={onExport}
          label="导出"
          icon={<Download className="h-4 w-4" />}
        />
        <ControlButton
          onClick={() => {
            if (onSettings) {
              onSettings();
            } else {
              console.log('Settings clicked');
              alert('设置面板：功能开发中');
            }
          }}
          label="设置"
          icon={<Settings className="h-4 w-4" />}
        />
      </div>
    </div>
  );
}

interface ControlButtonProps {
  onClick?: () => void;
  disabled?: boolean;
  active?: boolean;
  label: string;
  icon: ReactNode;
  activeClassName?: string;
}

function ControlButton({
  onClick,
  disabled,
  active,
  label,
  icon,
  activeClassName,
}: ControlButtonProps) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      className={cn(
        'inline-flex items-center justify-center h-9 w-9 rounded-md transition-colors duration-200',
        'bg-surface-card border border-subtle',
        'text-text-secondary hover:text-text-primary hover:bg-surface-card-hover',
        disabled && !active && 'opacity-40 cursor-not-allowed',
        active && activeClassName
      )}
    >
      {icon}
    </button>
  );
}

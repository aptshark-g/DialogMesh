import { cn } from '@/lib/utils';

interface TaskStatsBarProps {
  total: number;
  completed: number;
  running: number;
  pending: number;
  failed: number;
}

interface StatItemProps {
  label: string;
  value: number;
  colorClass: string;
}

function StatItem({ label, value, colorClass }: StatItemProps) {
  return (
    <div className="flex flex-col items-center min-w-[4rem]">
      <span className={cn('text-xl font-bold', colorClass)}>{value}</span>
      <span className="text-xs text-text-muted mt-1">{label}</span>
    </div>
  );
}

export function TaskStatsBar({ total, completed, running, pending, failed }: TaskStatsBarProps) {
  return (
    <div className="flex items-center justify-between border-b border-subtle py-3 px-4 bg-surface-card">
      <StatItem label="总任务" value={total} colorClass="text-text-primary" />
      <StatItem label="已完成" value={completed} colorClass="text-status-success" />
      <StatItem label="执行中" value={running} colorClass="text-status-warning" />
      <StatItem label="待执行" value={pending} colorClass="text-text-muted" />
      <StatItem label="失败" value={failed} colorClass="text-status-error" />
    </div>
  );
}

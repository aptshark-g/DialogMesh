import { useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  X,
  CheckCircle,
  Circle,
  XCircle,
  AlertTriangle,
  Clock,
  Terminal,
  FileInput,
  FileOutput,
  List,
  Activity,
} from 'lucide-react';
import type { TaskNode, TaskNodeStatus } from '@/types/task';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { cn, formatDuration, formatTimestamp } from '@/lib/utils';

interface TaskDetailPanelProps {
  node: TaskNode | null;
  onClose: () => void;
  allNodes?: TaskNode[];
}

const statusIconMap: Record<TaskNodeStatus, React.ReactNode> = {
  completed: <CheckCircle className="h-3.5 w-3.5 text-status-success" />,
  running: <Circle className="h-3.5 w-3.5 text-status-warning animate-pulse" />,
  failed: <XCircle className="h-3.5 w-3.5 text-status-error" />,
  pending: <Circle className="h-3.5 w-3.5 text-text-muted" />,
  skipped: <Circle className="h-3.5 w-3.5 text-text-secondary" />,
  blocked: <AlertTriangle className="h-3.5 w-3.5 text-status-info" />,
};

const statusLabelMap: Record<TaskNodeStatus, string> = {
  completed: '已完成',
  running: '执行中',
  failed: '失败',
  pending: '待执行',
  skipped: '已跳过',
  blocked: '已阻塞',
};

function DetailSection({
  title,
  icon,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="mb-5">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-text-muted">{icon}</span>
        <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
          {title}
        </h4>
      </div>
      {children}
    </div>
  );
}

function ValueSpan({ value }: { value: string }) {
  const stripped = value.replace(/[,}\]]+$/, '');
  if (value.startsWith('"')) {
    return <span className="text-emerald">{value}</span>;
  }
  if (/^-?\d+(?:\.\d+)?$/.test(stripped)) {
    return <span className="text-status-warning">{value}</span>;
  }
  if (/^(true|false|null)$/.test(stripped)) {
    return <span className="text-primary">{value}</span>;
  }
  return <span className="text-text-secondary">{value}</span>;
}

function JsonDisplay({ data }: { data: unknown }) {
  const json = useMemo(() => JSON.stringify(data, null, 2), [data]);

  return (
    <pre className="bg-surface rounded-md border border-subtle p-3 font-mono text-xs overflow-x-auto whitespace-pre-wrap break-all">
      {json.split('\n').map((line, i) => {
        const trimmed = line.trimStart();
        const indent = line.slice(0, line.length - trimmed.length);

        const keyMatch = trimmed.match(/^("(?:\\.|[^"\\])*")\s*(:)\s*(.*)$/);
        if (keyMatch) {
          return (
            <div key={i}>
              <span className="text-text-muted">{indent}</span>
              <span className="text-teal">{keyMatch[1]}</span>
              <span className="text-text-secondary">{keyMatch[2]} </span>
              <ValueSpan value={keyMatch[3]} />
            </div>
          );
        }

        return (
          <div key={i}>
            <span className="text-text-muted">{indent}</span>
            <ValueSpan value={trimmed} />
          </div>
        );
      })}
    </pre>
  );
}

export function TaskDetailPanel({ node, onClose, allNodes }: TaskDetailPanelProps) {
  const hasDanger = node?.metadata?.isDangerous === true;

  const duration = useMemo(() => {
    if (!node?.startedAt || !node?.completedAt) return null;
    const start = new Date(node.startedAt).getTime();
    const end = new Date(node.completedAt).getTime();
    return formatDuration(end - start);
  }, [node?.startedAt, node?.completedAt]);

  const estimatedDuration = node?.latencyMs ? formatDuration(node.latencyMs) : null;

  const inputData = useMemo(() => {
    if (!node?.metadata) return null;
    const { input, ...rest } = node.metadata as Record<string, unknown>;
    return input ?? rest;
  }, [node?.metadata]);

  const outputData = useMemo(() => {
    if (node?.result) return node.result;
    if (node?.error) return { error: node.error };
    return null;
  }, [node?.result, node?.error]);

  return (
    <div className="w-[320px] h-full bg-surface-card border-l border-subtle flex flex-col flex-shrink-0">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-subtle">
        <div className="flex items-center gap-2 min-w-0">
          <h3 className="text-sm font-semibold text-text-primary truncate">
            {node ? node.name : '节点详情'}
          </h3>
          {hasDanger && (
            <AlertTriangle className="h-4 w-4 text-status-error flex-shrink-0" />
          )}
        </div>
        {node && (
          <button
            onClick={onClose}
            className="p-1 rounded-md hover:bg-surface-card-hover text-text-muted hover:text-text-primary transition-colors"
            aria-label="关闭"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4">
        <AnimatePresence mode="wait">
          {node ? (
            <motion.div
              key={node.id}
              initial={{ opacity: 0, x: 8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -8 }}
              transition={{ duration: 0.2 }}
            >
              {/* Status Badge */}
              <div className="flex items-center justify-between mb-4">
                <span className="text-xs text-text-muted font-mono">ID: {node.id}</span>
                <Badge
                  variant={
                    node.status === 'completed' || node.status === 'running' || node.status === 'failed'
                      ? 'status'
                      : 'default'
                  }
                  color={
                    node.status === 'completed'
                      ? 'success'
                      : node.status === 'running'
                      ? 'warning'
                      : node.status === 'failed'
                      ? 'error'
                      : undefined
                  }
                  className={cn(
                    node.status === 'pending' && 'text-text-muted',
                    node.status === 'skipped' && 'text-text-secondary'
                  )}
                >
                  <span className="flex items-center gap-1">
                    {statusIconMap[node.status]}
                    {statusLabelMap[node.status]}
                  </span>
                </Badge>
              </div>

              {/* Description */}
              <DetailSection title="描述" icon={<Terminal className="h-3.5 w-3.5" />}>
                <p className="text-sm text-text-secondary leading-relaxed">
                  {node.description}
                </p>
              </DetailSection>

              {/* Input */}
              <DetailSection title="输入参数" icon={<FileInput className="h-3.5 w-3.5" />}>
                {inputData ? (
                  <JsonDisplay data={inputData} />
                ) : (
                  <p className="text-xs text-text-muted italic">无输入参数</p>
                )}
              </DetailSection>

              {/* Output */}
              <DetailSection title="输出结果" icon={<FileOutput className="h-3.5 w-3.5" />}>
                {outputData ? (
                  <JsonDisplay data={outputData} />
                ) : (
                  <p className="text-xs text-text-muted italic">暂无输出</p>
                )}
              </DetailSection>

              {/* Execution Info */}
              <DetailSection title="执行信息" icon={<Clock className="h-3.5 w-3.5" />}>
                <div className="grid grid-cols-2 gap-2">
                  <Card className="p-2 bg-surface border-subtle">
                    <p className="text-xs text-text-muted">开始时间</p>
                    <p className="text-xs text-text-secondary font-mono mt-1">
                      {node.startedAt ? formatTimestamp(node.startedAt) : '—'}
                    </p>
                  </Card>
                  <Card className="p-2 bg-surface border-subtle">
                    <p className="text-xs text-text-muted">预计耗时</p>
                    <p className="text-xs text-text-secondary font-mono mt-1">
                      {estimatedDuration ?? '—'}
                    </p>
                  </Card>
                  <Card className="p-2 bg-surface border-subtle">
                    <p className="text-xs text-text-muted">执行时长</p>
                    <p className="text-xs text-text-secondary font-mono mt-1">
                      {duration ?? '—'}
                    </p>
                  </Card>
                  <Card className="p-2 bg-surface border-subtle">
                    <p className="text-xs text-text-muted">重试次数</p>
                    <p className="text-xs text-text-secondary font-mono mt-1">
                      {((node.metadata?.retryCount as number) ?? 0).toString()}
                    </p>
                  </Card>
                </div>
              </DetailSection>

              {/* Status & Progress */}
              <DetailSection title="状态信息" icon={<Activity className="h-3.5 w-3.5" />}>
                <div className="flex items-center gap-3 mb-2">
                  <div className="flex-1 h-2 bg-surface rounded-full overflow-hidden">
                    <motion.div
                      className="h-full bg-primary rounded-full"
                      initial={{ width: 0 }}
                      animate={{ width: `${node.progress ?? 0}%` }}
                      transition={{ duration: 0.5 }}
                    />
                  </div>
                  <span className="text-xs font-mono text-primary">
                    {node.progress ?? 0}%
                  </span>
                </div>
                <p className={cn('text-xs',
                  node.status === 'completed' ? 'text-status-success' :
                  node.status === 'running' ? 'text-status-warning' :
                  node.status === 'failed' ? 'text-status-error' :
                  'text-text-muted'
                )}>
                  {statusLabelMap[node.status]}
                </p>
              </DetailSection>

              {/* Dependencies */}
              <DetailSection title="依赖任务" icon={<List className="h-3.5 w-3.5" />}>
                {node.dependencies.length > 0 ? (
                  <ul className="space-y-1.5">
                    {node.dependencies.map((depId) => {
                      const depNode = allNodes?.find((n) => n.id === depId);
                      return (
                        <li
                          key={depId}
                          className="flex items-center gap-2 text-xs text-text-secondary"
                        >
                          {depNode ? (
                            statusIconMap[depNode.status]
                          ) : (
                            <Circle className="h-3 w-3 text-text-muted" />
                          )}
                          <span className="font-mono">
                            {depNode?.name ?? depId}
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                ) : (
                  <p className="text-xs text-text-muted italic">无依赖</p>
                )}
              </DetailSection>

              {/* Log Button */}
              <div className="mt-6">
                <Button
                  variant="outline"
                  className="w-full border-primary text-primary hover:bg-primary/10"
                  onClick={() => {
                    // eslint-disable-next-line no-console
                    console.log('查看日志:', node.id);
                    alert(`节点 ${node.id} 日志功能开发中`);
                  }}
                >
                  <Terminal className="h-4 w-4 mr-2" />
                  查看日志
                </Button>
              </div>
            </motion.div>
          ) : (
            <motion.div
              key="placeholder"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex flex-col items-center justify-center h-full text-text-muted py-12"
            >
              <Activity className="h-10 w-10 mb-3 opacity-40" />
              <p className="text-sm">选择一个节点查看详情</p>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

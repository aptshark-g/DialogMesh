import React from 'react';
import { Handle, Position } from '@reactflow/core';
import type { TaskNodeStatus } from '@/types/task';
import { Loader2, CheckCircle, XCircle, Clock, AlertTriangle } from 'lucide-react';

interface TaskNodeData {
  name: string;
  description: string;
  status: TaskNodeStatus;
  type: string;
  isDangerous?: boolean;
  progress?: number;
}

const statusConfig: Record<
  TaskNodeStatus,
  {
    border: string;
    text: string;
    badgeBg: string;
    badgeText: string;
    label: string;
  }
> = {
  pending: { border: '#6B6680', text: '#6B6680', badgeBg: 'bg-[#6B6680]/10', badgeText: 'text-[#6B6680]', label: '待执行' },
  running: { border: '#D97706', text: '#D97706', badgeBg: 'bg-[#D97706]/10', badgeText: 'text-[#D97706]', label: '执行中' },
  completed: { border: '#10B981', text: '#10B981', badgeBg: 'bg-[#10B981]/10', badgeText: 'text-[#10B981]', label: '已完成' },
  failed: { border: '#EF4444', text: '#EF4444', badgeBg: 'bg-[#EF4444]/10', badgeText: 'text-[#EF4444]', label: '失败' },
  skipped: { border: '#6B6680', text: '#6B6680', badgeBg: 'bg-[#6B6680]/10', badgeText: 'text-[#6B6680]', label: '已跳过' },
  blocked: { border: '#6B6680', text: '#6B6680', badgeBg: 'bg-[#6B6680]/10', badgeText: 'text-[#6B6680]', label: '已阻塞' },
};

const StatusIcon = React.memo(function StatusIcon({ status }: { status: TaskNodeStatus }) {
  const cls = 'w-4 h-4';
  switch (status) {
    case 'running':
      return <Loader2 className={`${cls} animate-spin`} />;
    case 'completed':
      return <CheckCircle className={cls} />;
    case 'failed':
      return <XCircle className={cls} />;
    default:
      return <Clock className={cls} />;
  }
});

const handleStyle: React.CSSProperties = {
  width: 8,
  height: 8,
  background: '#4A4560',
  border: 'none',
  borderRadius: '50%',
};

export const StartNode = React.memo(function StartNode({ data }: { id: string; data: TaskNodeData }) {
  return (
    <div className="rounded-lg border-2 border-[#10B981] bg-transparent px-6 py-3 min-w-[80px] text-center">
      <Handle type="target" position={Position.Top} style={handleStyle} />
      <span className="text-sm font-medium text-[#10B981]">{data.name || '开始'}</span>
      <Handle type="source" position={Position.Bottom} style={handleStyle} />
    </div>
  );
});

export const ProcessNode = React.memo(function ProcessNode({ data }: { id: string; data: TaskNodeData }) {
  const { name, description, status, isDangerous } = data;
  const cfg = statusConfig[status];
  const isRunning = status === 'running';

  return (
    <div
      className={`relative rounded-lg border bg-transparent px-4 py-3 min-w-[180px] max-w-[240px] ${isRunning ? 'animate-executing-pulse' : ''}`}
      style={{ borderColor: cfg.border }}
    >
      <Handle type="target" position={Position.Top} style={handleStyle} />
      <Handle type="target" position={Position.Left} style={handleStyle} />

      {isDangerous && (
        <div className="absolute -top-2 -right-2 w-5 h-5 rounded-full bg-[#EF4444] flex items-center justify-center z-10">
          <AlertTriangle className="w-3 h-3 text-white" />
        </div>
      )}

      <div className="flex items-start gap-3">
        <div className="mt-0.5 flex-shrink-0" style={{ color: cfg.text }}>
          <StatusIcon status={status} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-primary truncate">{name}</div>
          <div className="text-xs text-muted mt-0.5 truncate">{description}</div>
        </div>
      </div>

      <div className="flex justify-end mt-2">
        <span
          className={`inline-flex items-center text-xs font-medium px-2 py-0.5 rounded-sm ${cfg.badgeBg} ${cfg.badgeText}`}
        >
          {isRunning && <Loader2 className="w-3 h-3 mr-1 animate-spin" />}
          {cfg.label}
        </span>
      </div>

      <Handle type="source" position={Position.Bottom} style={handleStyle} />
      <Handle type="source" position={Position.Right} style={handleStyle} />
    </div>
  );
});

export const DecisionNode = React.memo(function DecisionNode({ data }: { id: string; data: TaskNodeData }) {
  return (
    <div className="relative flex flex-col items-center">
      <div className="relative">
        <div
          className="w-24 h-24 border border-[#3A3548] bg-transparent flex items-center justify-center"
          style={{ transform: 'rotate(45deg)', borderRadius: '4px' }}
        >
          <div style={{ transform: 'rotate(-45deg)' }} className="text-center px-1">
            <span className="text-xs text-secondary whitespace-nowrap">{data.name}</span>
          </div>
        </div>
        <Handle type="target" position={Position.Top} style={handleStyle} />
        <Handle type="source" position={Position.Bottom} style={handleStyle} />
        <Handle type="source" position={Position.Left} style={handleStyle} />
        <Handle type="source" position={Position.Right} style={handleStyle} />
      </div>
      <div className="mt-4 text-xs text-muted text-center">{data.name}</div>
    </div>
  );
});

export const EndNode = React.memo(function EndNode({ data }: { id: string; data: TaskNodeData }) {
  return (
    <div className="rounded-lg border-2 border-[#6B6680] bg-transparent px-6 py-3 min-w-[80px] text-center">
      <Handle type="target" position={Position.Top} style={handleStyle} />
      <span className="text-sm font-medium text-[#6B6680]">{data.name || '结束'}</span>
    </div>
  );
});

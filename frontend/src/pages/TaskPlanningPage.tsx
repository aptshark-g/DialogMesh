import React, { useState, useCallback, useMemo } from 'react';
import type { Node, Edge } from '@reactflow/core';
import { motion, AnimatePresence } from 'framer-motion';
import { TaskFlow } from '@/components/task/TaskFlow';
import { cn } from '@/lib/utils';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import {
  Play, Pause, RotateCcw, LayoutGrid, Download, Settings, X, AlertTriangle, FileText, Clock, CheckCircle2, Loader2, XCircle as XIcon,
} from 'lucide-react';
import type { TaskExecutionStatus } from '@/types/task';

/* ==================== Mock Data ==================== */

const reactFlowNodes: Node[] = [
  { id: 'start', type: 'start', position: { x: 0, y: 0 }, data: { name: '开始', description: '启动任务规划流程', status: 'completed', type: 'intent' } },
  { id: 'intent-understand', type: 'process', position: { x: 0, y: 80 }, data: { name: '理解查询意图', description: '解析用户查询的语义意图', status: 'completed', type: 'intent' } },
  { id: 'plan-retrieval', type: 'process', position: { x: 0, y: 160 }, data: { name: '生成检索计划', description: '根据意图生成检索策略', status: 'completed', type: 'execution' } },
  { id: 'exec-vector', type: 'process', position: { x: 0, y: 240 }, data: { name: '执行向量检索', description: '在向量数据库中执行相似性搜索', status: 'running', type: 'execution', progress: 65 } },
  { id: 'check-results', type: 'decision', position: { x: 0, y: 340 }, data: { name: '检查结果', description: '评估检索结果质量', status: 'running', type: 'decision' } },
  { id: 'dedup', type: 'process', position: { x: -200, y: 460 }, data: { name: '结果去重', description: '对检索结果进行去重处理', status: 'pending', type: 'validation' } },
  { id: 'extend', type: 'process', position: { x: 200, y: 460 }, data: { name: '扩展检索', description: '扩大检索范围重新搜索', status: 'pending', type: 'execution', isDangerous: true } },
  { id: 'verify', type: 'process', position: { x: 0, y: 580 }, data: { name: '验证', description: '验证结果的正确性和完整性', status: 'pending', type: 'validation' } },
  { id: 'integrate', type: 'process', position: { x: 0, y: 660 }, data: { name: '整合', description: '整合所有子任务结果', status: 'pending', type: 'execution' } },
  { id: 'update-memory', type: 'process', position: { x: 0, y: 740 }, data: { name: '更新记忆库', description: '将结果更新到长期记忆库', status: 'pending', type: 'execution' } },
  { id: 'generate-reply', type: 'process', position: { x: 0, y: 820 }, data: { name: '生成回复', description: '基于整合结果生成最终回复', status: 'pending', type: 'execution' } },
  { id: 'end', type: 'end', position: { x: 0, y: 900 }, data: { name: '结束', description: '任务规划流程结束', status: 'pending', type: 'intent' } },
];

const reactFlowEdges: Edge[] = [
  { id: 'e1', source: 'start', target: 'intent-understand', type: 'animated', data: { status: 'completed' } },
  { id: 'e2', source: 'intent-understand', target: 'plan-retrieval', type: 'animated', data: { status: 'completed' } },
  { id: 'e3', source: 'plan-retrieval', target: 'exec-vector', type: 'animated', data: { status: 'completed' } },
  { id: 'e4', source: 'exec-vector', target: 'check-results', type: 'animated', data: { status: 'running' } },
  { id: 'e5', source: 'check-results', target: 'dedup', sourceHandle: 'left', type: 'condition', label: 'if found > 0', data: { condition: 'if found > 0', status: 'pending' } },
  { id: 'e6', source: 'check-results', target: 'extend', sourceHandle: 'right', type: 'condition', label: 'if found = 0', data: { condition: 'if found = 0', status: 'pending' } },
  { id: 'e7', source: 'dedup', target: 'verify', type: 'animated', data: { status: 'pending' } },
  { id: 'e8', source: 'extend', target: 'verify', type: 'animated', data: { status: 'pending' } },
  { id: 'e9', source: 'verify', target: 'integrate', type: 'animated', data: { status: 'pending' } },
  { id: 'e10', source: 'integrate', target: 'update-memory', type: 'animated', data: { status: 'pending' } },
  { id: 'e11', source: 'update-memory', target: 'generate-reply', type: 'animated', data: { status: 'pending' } },
  { id: 'e12', source: 'generate-reply', target: 'end', type: 'animated', data: { status: 'pending' } },
];

/* ==================== Placeholder: TaskExecutionControls ==================== */

interface TaskExecutionControlsProps {
  status: TaskExecutionStatus;
  onPlay: () => void;
  onPause: () => void;
  onReset: () => void;
  onAutoLayout: () => void;
  onExport: () => void;
  onSettings: () => void;
}

function TaskExecutionControls({ status, onPlay, onPause, onReset, onAutoLayout, onExport, onSettings }: TaskExecutionControlsProps) {
  const statusDot: Record<TaskExecutionStatus, string> = {
    idle: 'bg-status-pending',
    running: 'bg-status-success',
    paused: 'bg-status-warning',
    completed: 'bg-status-success',
    failed: 'bg-status-error',
    cancelled: 'bg-status-error',
  };

  const statusLabel: Record<TaskExecutionStatus, string> = {
    idle: '空闲',
    running: '运行中',
    paused: '已暂停',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
  };

  return (
    <div className="flex items-center gap-2 lg:gap-3 px-3 lg:px-6 py-2 lg:py-3 border-b border-subtle">
      <div className="flex items-center gap-2 min-w-0">
        <h1 className="text-lg font-semibold text-primary">任务规划</h1>
        <div className="hidden lg:flex items-center gap-1.5 text-xs text-muted">
          <span className="truncate">查询意图理解与检索</span>
          <span className="text-border-medium">|</span>
          <span className="font-mono text-[10px]">task-plan-001</span>
        </div>
      </div>
      <div className="flex-1" />
      <div className="flex items-center gap-2">
        <motion.span
          className={cn('w-2 h-2 rounded-full', statusDot[status])}
          animate={status === 'running' ? { scale: [1, 1.3, 1] } : {}}
          transition={{ duration: 1.5, repeat: Infinity }}
        />
        <span className="text-xs text-secondary">{statusLabel[status]}</span>
      </div>
      <button
        type="button"
        onClick={status === 'running' ? onPause : onPlay}
        className={cn(
          'inline-flex items-center justify-center rounded-md h-8 w-8 border text-sm transition-colors',
          status === 'running'
            ? 'bg-primary text-white border-primary animate-executing-pulse'
            : 'bg-surface-card border-subtle text-secondary hover:text-primary hover:bg-surface-card-hover'
        )}
      >
        {status === 'running' ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
      </button>
      <button type="button" onClick={onReset} className="inline-flex items-center justify-center rounded-md h-8 w-8 border bg-surface-card border-subtle text-secondary hover:text-primary hover:bg-surface-card-hover transition-colors" title="Reset">
        <RotateCcw className="w-4 h-4" />
      </button>
      <button type="button" onClick={onAutoLayout} className="hidden lg:inline-flex items-center justify-center rounded-md h-8 px-3 border bg-surface-card border-subtle text-secondary hover:text-primary hover:bg-surface-card-hover transition-colors text-xs" title="Auto Layout">
        <LayoutGrid className="w-4 h-4 mr-1" />
        <span>自动布局</span>
      </button>
      <button type="button" onClick={onExport} className="hidden lg:inline-flex items-center justify-center rounded-md h-8 px-3 border bg-surface-card border-subtle text-secondary hover:text-primary hover:bg-surface-card-hover transition-colors text-xs" title="Export">
        <Download className="w-4 h-4 mr-1" />
        <span>导出</span>
      </button>
      <button type="button" onClick={onSettings} className="inline-flex items-center justify-center rounded-md h-8 w-8 border bg-surface-card border-subtle text-secondary hover:text-primary hover:bg-surface-card-hover transition-colors" title="Settings">
        <Settings className="w-4 h-4" />
      </button>
    </div>
  );
}

/* ==================== Placeholder: TaskStatsBar ==================== */

interface TaskStatsBarProps {
  total: number;
  completed: number;
  running: number;
  pending: number;
  failed: number;
}

function TaskStatsBar({ total, completed, running, pending, failed }: TaskStatsBarProps) {
  const items = [
    { label: '总任务', value: total, color: 'text-primary' },
    { label: '已完成', value: completed, color: 'text-status-success' },
    { label: '执行中', value: running, color: 'text-status-warning' },
    { label: '待执行', value: pending, color: 'text-status-pending' },
    { label: '失败', value: failed, color: 'text-status-error' },
  ];
  return (
    <div className="flex items-center gap-4 lg:gap-8 px-3 lg:px-6 py-2 lg:py-3 border-b border-subtle bg-surface-card/50 overflow-x-auto scrollbar-hide">
      {items.map((item, idx) => (
        <div key={item.label} className="flex flex-col shrink-0">
          <motion.span
            className={cn('text-xl font-bold leading-tight', item.color)}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: idx * 0.05 }}
          >
            {item.value}
          </motion.span>
          <span className="text-xs text-muted mt-0.5">{item.label}</span>
        </div>
      ))}
    </div>
  );
}

/* ==================== Placeholder: TaskDetailPanel ==================== */

interface TaskDetailPanelProps {
  node: Node | null;
  onClose: () => void;
}

function TaskDetailPanel({ node, onClose }: TaskDetailPanelProps) {
  const isDesktop = useMediaQuery('(min-width: 1024px)');

  const statusMap: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
    completed: { label: '已完成', color: 'bg-status-success/10 text-status-success', icon: <CheckCircle2 className="w-3.5 h-3.5" /> },
    running: { label: '执行中', color: 'bg-primary/10 text-primary', icon: <Loader2 className="w-3.5 h-3.5 animate-spin" /> },
    failed: { label: '失败', color: 'bg-status-error/10 text-status-error', icon: <XIcon className="w-3.5 h-3.5" /> },
    pending: { label: '待执行', color: 'bg-status-pending/10 text-status-pending', icon: <Clock className="w-3.5 h-3.5" /> },
  };

  const data = node?.data as Record<string, unknown> | undefined;
  const status = (data?.status as string) || 'pending';
  const statusInfo = statusMap[status] || statusMap.pending;

  return (
    <AnimatePresence>
      {node && (
        <>
          {!isDesktop && (
            <motion.div
              key="overlay"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="absolute inset-0 bg-black/30 z-20"
              onClick={onClose}
            />
          )}
          <motion.div
            key="panel"
            initial={isDesktop ? { width: 0, opacity: 0 } : { x: '100%', opacity: 0 }}
            animate={isDesktop ? { width: 320, opacity: 1 } : { x: 0, opacity: 1 }}
            exit={isDesktop ? { width: 0, opacity: 0 } : { x: '100%', opacity: 0 }}
            transition={{ duration: 0.3, ease: 'easeInOut' }}
            className={cn(
              'border-l border-subtle bg-surface-card overflow-hidden flex flex-col shrink-0 h-full',
              isDesktop ? 'relative' : 'absolute inset-y-0 right-0 w-full z-30'
            )}
          >
            <div className={cn('flex flex-col h-full', isDesktop ? 'w-[320px]' : 'w-full')}>
              <div className="flex items-center justify-between px-4 py-3 border-b border-subtle">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-sm font-medium text-primary truncate">{data?.name as string || '未选择'}</span>
                  {node && (
                    <span className={cn('text-[10px] px-1.5 py-0.5 rounded-sm font-medium inline-flex items-center gap-1', statusInfo.color)}>
                      {statusInfo.icon}
                      {statusInfo.label}
                    </span>
                  )}
                </div>
                <button type="button" onClick={onClose} className="p-1 rounded hover:bg-surface-card-hover text-secondary hover:text-primary transition-colors">
                  <X className="w-4 h-4" />
                </button>
              </div>

              <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {!node ? (
                  <div className="flex flex-col items-center justify-center h-full text-muted">
                    <FileText className="w-8 h-8 mb-2 opacity-50" />
                    <p className="text-sm">选择一个节点查看详情</p>
                  </div>
                ) : (
                  <>
                    <div>
                      <div className="text-xs text-muted mb-1">任务 ID</div>
                      <div className="text-xs font-mono text-secondary bg-surface p-2 rounded border border-subtle">{node.id}</div>
                    </div>
                    <div>
                      <div className="text-xs text-muted mb-1">描述</div>
                      <div className="text-sm text-secondary">{(data?.description as string) || '暂无描述'}</div>
                    </div>
                    <div>
                      <div className="text-xs text-muted mb-1">状态</div>
                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-2 bg-surface rounded-full overflow-hidden">
                          <div className="h-full bg-primary rounded-full transition-all" style={{ width: `${(data?.progress as number) || 0}%` }} />
                        </div>
                        <span className="text-xs text-secondary">{(data?.progress as number) || 0}%</span>
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-muted mb-1">类型</div>
                      <div className="text-xs text-secondary font-mono">{(data?.type as string) || 'unknown'}</div>
                    </div>
                    {data?.isDangerous && (
                      <div className="flex items-center gap-2 text-xs text-status-error bg-status-error/5 rounded-md px-3 py-2">
                        <AlertTriangle className="w-4 h-4" />
                        <span>该节点包含危险操作</span>
                      </div>
                    )}
                    <div>
                      <div className="text-xs text-muted mb-1">输入参数</div>
                      <div className="bg-surface p-2 rounded border border-subtle font-mono text-[10px] text-secondary overflow-x-auto">
                        <pre>{JSON.stringify({ query: '如何优化精密机床振动控制？', context: '制造业/振动控制' }, null, 2)}</pre>
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-muted mb-1">输出结果</div>
                      <div className="bg-surface p-2 rounded border border-subtle font-mono text-[10px] text-secondary overflow-x-auto">
                        <pre>{JSON.stringify({ result: status === 'completed' ? '检索成功' : status === 'running' ? '处理中...' : '等待执行' }, null, 2)}</pre>
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <div className="bg-surface p-2 rounded border border-subtle">
                        <div className="text-[10px] text-muted">开始时间</div>
                        <div className="text-xs text-secondary">2024-01-15 14:32:00</div>
                      </div>
                      <div className="bg-surface p-2 rounded border border-subtle">
                        <div className="text-[10px] text-muted">预计耗时</div>
                        <div className="text-xs text-secondary">~ 2.5s</div>
                      </div>
                      <div className="bg-surface p-2 rounded border border-subtle">
                        <div className="text-[10px] text-muted">执行时长</div>
                        <div className="text-xs text-secondary">1.2s</div>
                      </div>
                      <div className="bg-surface p-2 rounded border border-subtle">
                        <div className="text-[10px] text-muted">重试次数</div>
                        <div className="text-xs text-secondary">0</div>
                      </div>
                    </div>
                  </>
                )}
              </div>

              {node && (
                <div className="p-4 border-t border-subtle">
                  <button type="button" onClick={() => alert(`节点 ${node.id} 日志功能开发中`)} className="w-full py-2 px-3 rounded-md border border-primary text-primary text-sm hover:bg-primary/10 transition-colors">
                    查看日志
                  </button>
                </div>
              )}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

/* ==================== Main Page ==================== */

export function TaskPlanningPage() {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [executionStatus, setExecutionStatus] = useState<TaskExecutionStatus>('running');
  const [nodes, setNodes] = useState<Node[]>(reactFlowNodes);
  const [edges] = useState<Edge[]>(reactFlowEdges);

  const selectedNode = useMemo(() => {
    return nodes.find((n) => n.id === selectedNodeId) || null;
  }, [nodes, selectedNodeId]);

  const stats = useMemo(() => {
    const total = nodes.length;
    const completed = nodes.filter((n) => n.data.status === 'completed').length;
    const running = nodes.filter((n) => n.data.status === 'running').length;
    const pending = nodes.filter((n) => n.data.status === 'pending').length;
    const failed = nodes.filter((n) => n.data.status === 'failed').length;
    return { total, completed, running, pending, failed };
  }, [nodes]);

  const handleNodeClick = useCallback((nodeId: string) => {
    setSelectedNodeId((prev) => (prev === nodeId ? null : nodeId));
  }, []);

  const handleClosePanel = useCallback(() => {
    setSelectedNodeId(null);
  }, []);

  const handlePlay = useCallback(() => setExecutionStatus('running'), []);
  const handlePause = useCallback(() => setExecutionStatus('paused'), []);
  const handleReset = useCallback(() => setExecutionStatus('idle'), []);

  const handleAutoLayout = useCallback(() => {
    const adj = new Map<string, string[]>();
    const inDegree = new Map<string, number>();

    nodes.forEach((n) => {
      adj.set(n.id, []);
      inDegree.set(n.id, 0);
    });

    edges.forEach((e) => {
      adj.get(e.source)?.push(e.target);
      inDegree.set(e.target, (inDegree.get(e.target) || 0) + 1);
    });

    const layer = new Map<string, number>();
    const queue: string[] = [];

    nodes.forEach((n) => {
      if ((inDegree.get(n.id) || 0) === 0) {
        queue.push(n.id);
        layer.set(n.id, 0);
      }
    });

    while (queue.length > 0) {
      const curr = queue.shift()!;
      const currLayer = layer.get(curr)!;
      for (const neighbor of adj.get(curr) || []) {
        const newLayer = Math.max(layer.get(neighbor) || 0, currLayer + 1);
        layer.set(neighbor, newLayer);
        const newInDegree = (inDegree.get(neighbor) || 0) - 1;
        inDegree.set(neighbor, newInDegree);
        if (newInDegree === 0) {
          queue.push(neighbor);
        }
      }
    }

    const layerGroups = new Map<number, string[]>();
    layer.forEach((l, nodeId) => {
      if (!layerGroups.has(l)) layerGroups.set(l, []);
      layerGroups.get(l)!.push(nodeId);
    });

    const layerSpacing = 220;
    const nodeSpacing = 110;

    const newNodes = nodes.map((n) => {
      const l = layer.get(n.id) || 0;
      const layerNodeIds = layerGroups.get(l) || [];
      const indexInLayer = layerNodeIds.indexOf(n.id);
      const nodesInLayer = layerNodeIds.length;
      const x = l * layerSpacing;
      const totalHeight = (nodesInLayer - 1) * nodeSpacing;
      const y = indexInLayer * nodeSpacing - totalHeight / 2;
      return { ...n, position: { x, y } };
    });

    setNodes(newNodes);
  }, [nodes, edges]);

  const handleExport = useCallback(() => {
    const data = {
      nodes,
      edges,
      exportedAt: new Date().toISOString(),
    };
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `task-plan-${Date.now()}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, [nodes, edges]);

  const handleSettings = useCallback(() => {
    alert('设置面板（功能开发中）');
  }, []);

  return (
    <div className="flex flex-col h-full bg-surface">
      <TaskExecutionControls
        status={executionStatus}
        onPlay={handlePlay}
        onPause={handlePause}
        onReset={handleReset}
        onAutoLayout={handleAutoLayout}
        onExport={handleExport}
        onSettings={handleSettings}
      />
      <TaskStatsBar {...stats} />
      <div className="flex-1 flex overflow-hidden relative">
        <TaskFlow
          nodes={nodes}
          edges={edges}
          selectedNodeId={selectedNodeId}
          onNodeClick={handleNodeClick}
          onPaneClick={handleClosePanel}
        />
        <TaskDetailPanel node={selectedNode} onClose={handleClosePanel} />
      </div>
      <div className="flex items-center justify-between px-3 lg:px-4 py-2 border-t border-subtle text-[10px] text-muted">
        <span>React Flow DAG · {stats.total} nodes · {edges.length} edges</span>
        <span>DialogMesh v3.0</span>
      </div>
    </div>
  );
}

import React, { useState, useCallback, useMemo, useEffect } from 'react';
import type { Node, Edge, NodeChange, EdgeChange, Connection } from '@reactflow/core';
import { applyNodeChanges, applyEdgeChanges, addEdge } from '@reactflow/core';
import { motion, AnimatePresence } from 'framer-motion';
import { TaskFlow } from '@/components/task/TaskFlow';
import { cn } from '@/lib/utils';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import { useTaskStore } from '@/stores/taskStore';
import type { TaskNode } from '@/types/task';
import type { TaskEdge } from '@/types/task';
import {
  Play, Pause, RotateCcw, LayoutGrid, Download, Settings, X,
  AlertTriangle, FileText, Clock, CheckCircle2, Loader2, XCircle as XIcon, Plus,
} from 'lucide-react';
import type { TaskExecutionStatus } from '@/types/task';

/* ═══ Convert store TaskGraph ↔ ReactFlow Nodes/Edges ═══ */

function apiNodeToRF(apiNode: TaskNode, index: number): Node {
  return {
    id: apiNode.id,
    type: mapFlowType(apiNode.type),
    position: { x: (index % 3) * 260, y: Math.floor(index / 3) * 140 },
    data: {
      name: apiNode.name,
      description: apiNode.description || apiNode.type,
      status: apiNode.status,
      type: apiNode.type,
      isDangerous: false,
      progress: apiNode.progress,
    },
  };
}

function apiEdgesToRF(nodes: TaskNode[]): Edge[] {
  const edges: Edge[] = [];
  nodes.forEach(n => {
    (n.dependencies || []).forEach(depId => {
      edges.push({ id: `e_${depId}_${n.id}`, source: depId, target: n.id, type: 'animated', data: { status: 'pending' } });
    });
  });
  return edges;
}

function mapFlowType(t: string): string {
  const m: Record<string, string> = { intent: 'start', clarification: 'start', execution: 'process', validation: 'process', decision: 'decision', parallel: 'process', merge: 'process' };
  return m[t] || 'process';
}

/* ═══ Controls ═══ */

interface TaskExecutionControlsProps {
  status: TaskExecutionStatus;
  onPlay: () => void; onPause: () => void; onReset: () => void;
  onAutoLayout: () => void; onExport: () => void; onSettings: () => void; onAddNode: () => void;
}

function TaskExecutionControls({ status, onPlay, onPause, onReset, onAutoLayout, onExport, onSettings, onAddNode }: TaskExecutionControlsProps) {
  const sd: Record<TaskExecutionStatus, string> = { idle: 'bg-status-pending', running: 'bg-status-success', paused: 'bg-status-warning', completed: 'bg-status-success', failed: 'bg-status-error', cancelled: 'bg-status-pending' };
  return (
    <div className="flex items-center gap-2 px-4 py-2 border-b border-subtle bg-surface-card shrink-0">
      <div className={cn('w-2 h-2 rounded-full', sd[status] || 'bg-status-pending')} />
      <button onClick={onPlay} className="btn-control"><Play className="w-4 h-4" /></button>
      <button onClick={onPause} className="btn-control"><Pause className="w-4 h-4" /></button>
      <button onClick={onReset} className="btn-control"><RotateCcw className="w-4 h-4" /></button>
      <div className="w-px h-5 bg-border-subtle mx-1" />
      <button onClick={onAutoLayout} className="btn-control-text"><LayoutGrid className="w-4 h-4 mr-1" /><span>自动布局</span></button>
      <button onClick={onAddNode} className="btn-control-primary"><Plus className="w-4 h-4 mr-1" /><span>添加节点</span></button>
      <button onClick={onExport} className="btn-control-text"><Download className="w-4 h-4 mr-1" /><span>导出</span></button>
      <button onClick={onSettings} className="btn-control"><Settings className="w-4 h-4" /></button>
    </div>
  );
}

/* ═══ Stats Bar ═══ */

interface Stats { total: number; completed: number; running: number; progress: number }

function TaskStatsBar({ total, completed, running, progress }: Stats) {
  return (
    <div className="px-4 py-1.5 border-b border-subtle bg-surface-card text-xs text-text-secondary flex items-center gap-4">
      <span>节点 {total}</span><span className="text-status-success">完成 {completed}</span><span className="text-primary">运行 {running}</span>
      <div className="flex-1 h-1 bg-surface-input rounded-full overflow-hidden"><div className="h-full bg-primary transition-all" style={{ width: `${progress}%` }} /></div>
      <span>{progress}%</span>
    </div>
  );
}

/* ═══ Detail Panel ═══ */

interface TaskDetailPanelProps { node: Node | null; onClose: () => void }

function TaskDetailPanel({ node, onClose }: TaskDetailPanelProps) {
  if (!node) return null;
  const d = node.data;
  return (
    <div className="w-72 border-l border-subtle bg-surface-card p-4 overflow-y-auto shrink-0 z-20">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-text-primary">{d?.name as string || '节点'}</h3>
        <button onClick={onClose} className="text-text-muted hover:text-text-primary"><X size={16} /></button>
      </div>
      <p className="text-xs text-text-secondary mb-2">{d?.description as string || ''}</p>
      <div className="text-[11px] text-text-muted space-y-1">
        <div>ID: {node.id}</div><div>类型: {d?.type as string || '?'}</div><div>状态: {d?.status as string || 'pending'}</div>
        {d?.progress != null && <div>进度: {d.progress as number}%</div>}
      </div>
    </div>
  );
}

/* ═══ Main Page ═══ */

export function TaskPlanningPage() {
  const storeGraph = useTaskStore(s => s.taskGraph);
  const storeStatus = useTaskStore(s => s.executionStatus);

  // ── Controlled ReactFlow state ──
  const [rfNodes, setRfNodes] = useState<Node[]>([]);
  const [rfEdges, setRfEdges] = useState<Edge[]>([]);
  const [loaded, setLoaded] = useState(false);

  // Sync from store on first load
  useEffect(() => {
    if (!loaded && storeGraph && storeGraph.nodes.length > 0) {
      setRfNodes(storeGraph.nodes.map((n, i) => apiNodeToRF(n, i)));
      setRfEdges(apiEdgesToRF(storeGraph.nodes));
      setLoaded(true);
    }
  }, [storeGraph, loaded]);

  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const executionStatus: TaskExecutionStatus = (storeStatus as TaskExecutionStatus) || 'idle';

  const selectedNode = useMemo(() => rfNodes.find(n => n.id === selectedNodeId) || null, [rfNodes, selectedNodeId]);

  const stats: Stats = useMemo(() => {
    const total = rfNodes.length;
    const completed = rfNodes.filter(n => (n.data as any).status === 'completed').length;
    const running = rfNodes.filter(n => (n.data as any).status === 'running').length;
    return { total, completed, running, progress: total > 0 ? Math.round((completed / total) * 100) : 0 };
  }, [rfNodes]);

  // ═══ ReactFlow change handlers (controlled mode) ═══
  const handleNodesChange = useCallback((changes: NodeChange[]) => {
    setRfNodes((nds) => applyNodeChanges(changes, nds));
  }, []);

  const handleEdgesChange = useCallback((changes: EdgeChange[]) => {
    setRfEdges((eds) => applyEdgeChanges(changes, eds));
  }, []);

  const handleConnect = useCallback((conn: Connection) => {
    setRfEdges((eds) => addEdge(conn, eds));
    // Also update store
    const g = useTaskStore.getState().taskGraph;
    if (!g || !conn.source || !conn.target) return;
    const src = g.nodes.find(n => n.id === conn.source);
    const tgt = g.nodes.find(n => n.id === conn.target);
    if (src && !src.children.includes(conn.target)) src.children.push(conn.target);
    if (tgt && !tgt.dependencies.includes(conn.source)) tgt.dependencies.push(conn.source);
    useTaskStore.setState({ taskGraph: { ...g, edges: [...g.edges, { id: `e_${conn.source}_${conn.target}`, source: conn.source, target: conn.target, type: 'dependency' }] } });
  }, []);

  const handleNodesDelete = useCallback((ids: string[]) => {
    setRfNodes((nds) => nds.filter(n => !ids.includes(n.id)));
    setRfEdges((eds) => eds.filter(e => !ids.includes(e.source) && !ids.includes(e.target)));
    const g = useTaskStore.getState().taskGraph;
    if (g) useTaskStore.setState({ taskGraph: { ...g, nodes: g.nodes.filter(n => !ids.includes(n.id)), edges: g.edges.filter(e => !ids.includes(e.source) && !ids.includes(e.target)) } });
  }, []);

  const handleEdgesDelete = useCallback((ids: string[]) => {
    setRfEdges((eds) => eds.filter(e => !ids.includes(e.id)));
    const g = useTaskStore.getState().taskGraph;
    if (g) useTaskStore.setState({ taskGraph: { ...g, edges: g.edges.filter(e => !ids.includes(e.id)) } });
  }, []);

  const handleNodeClick = useCallback((nodeId: string) => {
    setSelectedNodeId(prev => (prev === nodeId ? null : nodeId));
  }, []);

  const handleAddNode = useCallback(() => {
    const g = useTaskStore.getState().taskGraph;
    const newId = `node_${Date.now()}`;
    const rfNode: Node = { id: newId, type: 'process', position: { x: 100 + Math.random() * 300, y: 100 + Math.random() * 200 }, data: { name: '新节点', description: '双击编辑', status: 'pending', type: 'execution' } };
    setRfNodes(nds => [...nds, rfNode]);
    if (g) {
      const tn: TaskNode = { id: newId, name: '新节点', description: '双击编辑', type: 'execution', status: 'pending', parentId: null, dependencies: [], children: [], progress: 0 };
      useTaskStore.setState({ taskGraph: { ...g, nodes: [...g.nodes, tn], updatedAt: new Date().toISOString() } });
    }
  }, []);

  const handlePlay = useCallback(() => {}, []);
  const handlePause = useCallback(() => {}, []);
  const handleReset = useCallback(() => {}, []);

  const handleAutoLayout = useCallback(() => {
    setRfNodes(nds => nds.map((n, i) => ({ ...n, position: { x: (i % 3) * 260, y: Math.floor(i / 3) * 140 } })));
  }, []);

  const handleExport = useCallback(() => {
    const data = JSON.stringify({ nodes: rfNodes, edges: rfEdges }, null, 2);
    const blob = new Blob([data], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'task-graph.json'; a.click();
    URL.revokeObjectURL(url);
  }, [rfNodes, rfEdges]);

  const handleSettings = useCallback(() => {}, []);

  return (
    <div className="flex flex-col h-full bg-surface">
      <TaskExecutionControls status={executionStatus} onPlay={handlePlay} onPause={handlePause} onReset={handleReset}
        onAutoLayout={handleAutoLayout} onExport={handleExport} onSettings={handleSettings} onAddNode={handleAddNode} />
      <TaskStatsBar {...stats} />
      <div className="flex-1 flex overflow-hidden relative">
        <TaskFlow
          nodes={rfNodes} edges={rfEdges} selectedNodeId={selectedNodeId}
          onNodeClick={handleNodeClick}
          onNodesChange={handleNodesChange} onEdgesChange={handleEdgesChange}
          onConnect={handleConnect}
          onNodesDelete={handleNodesDelete} onEdgesDelete={handleEdgesDelete}
          onPaneClick={() => setSelectedNodeId(null)}
        />
        <TaskDetailPanel node={selectedNode} onClose={() => setSelectedNodeId(null)} />
      </div>
    </div>
  );
}

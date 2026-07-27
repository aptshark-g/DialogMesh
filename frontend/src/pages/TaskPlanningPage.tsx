/** TEST: Pure frontend ReactFlow — no backend API calls */
import { useState, useCallback, useMemo } from 'react';
import type { Node, Edge, NodeChange, EdgeChange, Connection } from '@reactflow/core';
import { applyNodeChanges, applyEdgeChanges, addEdge } from '@reactflow/core';
import { TaskFlow } from '@/components/task/TaskFlow';

const MOCK_NODES: Node[] = [
  { id: 'start', type: 'start', position: { x: 250, y: 0 }, data: { name: '开始', status: 'completed' } },
  { id: 'analyze', type: 'process', position: { x: 250, y: 100 }, data: { name: '分析需求', description: '理解用户意图', status: 'completed' } },
  { id: 'design', type: 'process', position: { x: 250, y: 220 }, data: { name: '设计方案', description: '生成执行计划', status: 'running' } },
  { id: 'implement', type: 'process', position: { x: 250, y: 340 }, data: { name: '实现功能', description: '编写代码', status: 'pending' } },
  { id: 'test', type: 'process', position: { x: 250, y: 460 }, data: { name: '测试验证', description: '运行测试', status: 'pending' } },
  { id: 'end', type: 'end', position: { x: 250, y: 580 }, data: { name: '完成', status: 'pending' } },
];

const MOCK_EDGES: Edge[] = [
  { id: 'e1', source: 'start', target: 'analyze', type: 'animated' },
  { id: 'e2', source: 'analyze', target: 'design', type: 'animated' },
  { id: 'e3', source: 'design', target: 'implement', type: 'animated' },
  { id: 'e4', source: 'implement', target: 'test', type: 'animated' },
  { id: 'e5', source: 'test', target: 'end', type: 'animated' },
];

export function TaskPlanningPage() {
  const [nodes, setNodes] = useState<Node[]>(MOCK_NODES);
  const [edges, setEdges] = useState<Edge[]>(MOCK_EDGES);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const handleNodesChange = useCallback((changes: NodeChange[]) => {
    setNodes(nds => applyNodeChanges(changes, nds));
  }, []);

  const handleEdgesChange = useCallback((changes: EdgeChange[]) => {
    setEdges(eds => applyEdgeChanges(changes, eds));
  }, []);

  const handleConnect = useCallback((conn: Connection) => {
    if (conn.source && conn.target) {
      setEdges(eds => addEdge({ ...conn, type: 'animated' } as any, eds));
    }
  }, []);

  const handleNodesDelete = useCallback((ids: string[]) => {
    setNodes(nds => nds.filter(n => !ids.includes(n.id)));
    setEdges(eds => eds.filter(e => !ids.includes(e.source) && !ids.includes(e.target)));
  }, []);

  const handleEdgesDelete = useCallback((ids: string[]) => {
    setEdges(eds => eds.filter(e => !ids.includes(e.id)));
  }, []);

  const handleAddNode = useCallback(() => {
    const id = `n_${Date.now()}`;
    const newNode: Node = {
      id, type: 'process',
      position: { x: 100 + Math.random() * 400, y: 100 + Math.random() * 300 },
      data: { name: `新节点 ${id.slice(-4)}`, status: 'pending' },
    };
    setNodes(nds => [...nds, newNode]);
  }, []);

  const stats = useMemo(() => {
    const total = nodes.length;
    const completed = nodes.filter(n => (n.data as any).status === 'completed').length;
    const running = nodes.filter(n => (n.data as any).status === 'running').length;
    return { total, completed, running, pending: total - completed - running, failed: 0 };
  }, [nodes]);

  return (
    <div className="flex flex-col h-full bg-surface">
      {/* Toolbar */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-subtle">
        <h1 className="text-lg font-semibold text-primary">任务规划 (纯前端测试)</h1>
        <div className="flex-1" />
        <span className="text-xs text-secondary">节点: {nodes.length} | 连线: {edges.length}</span>
        <button onClick={handleAddNode} className="px-3 py-1.5 rounded bg-primary/20 text-primary text-sm font-medium hover:bg-primary/30">
          + 添加节点
        </button>
      </div>

      {/* Stats */}
      <div className="flex items-center gap-6 px-4 py-1.5 border-b border-subtle bg-surface-card/50 text-xs text-text-secondary">
        <span>总 {stats.total}</span>
        <span className="text-status-success">完成 {stats.completed}</span>
        <span className="text-primary">运行 {stats.running}</span>
        <span className="text-text-muted">待定 {stats.pending}</span>
      </div>

      {/* Canvas */}
      <div className="flex-1 flex overflow-hidden relative">
        <TaskFlow
          nodes={nodes}
          edges={edges}
          selectedNodeId={selectedNodeId}
          onNodeClick={id => setSelectedNodeId(prev => prev === id ? null : id)}
          onNodesChange={handleNodesChange}
          onEdgesChange={handleEdgesChange}
          onConnect={handleConnect}
          onNodesDelete={handleNodesDelete}
          onEdgesDelete={handleEdgesDelete}
          onPaneClick={() => setSelectedNodeId(null)}
        />
        {/* Detail panel */}
        {selectedNodeId && (
          <div className="w-64 border-l border-subtle bg-surface-card p-3 overflow-y-auto shrink-0">
            <div className="flex justify-between mb-2">
              <span className="text-sm font-medium">节点详情</span>
              <button onClick={() => setSelectedNodeId(null)} className="text-text-muted text-xs">✕</button>
            </div>
            <div className="text-xs text-text-muted">{selectedNodeId}</div>
          </div>
        )}
      </div>
    </div>
  );
}

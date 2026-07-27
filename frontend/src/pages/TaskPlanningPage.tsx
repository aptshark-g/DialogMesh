/** Task Planning Page — data management + FlowchartCanvas */
import { useState, useEffect, useRef, useCallback } from 'react';
import { FlowchartCanvas } from '@/components/task/FlowchartCanvas';
import type { FNode, FEdge } from '@/components/task/FlowchartCanvas';
import { useChatStore } from '@/stores/chatStore';
import { useTaskStore } from '@/stores/taskStore';
import { getTaskGraph, saveTaskGraph } from '@/api/session';

/* ── Backend JSON → Canvas nodes ── */
function apiNodesToCanvas(apiNodes: any[]): FNode[] {
  return apiNodes.map((n, i) => ({
    id: n.id || `n_${i}`,
    label: n.name || n.type || '',
    x: (i % 4) * 220 + 40,
    y: Math.floor(i / 4) * 150 + 40,
    w: 140, h: 40,
    type: n.type || 'process',
  }));
}

function canvasNodesToApi(nodes: FNode[]): any[] {
  return nodes.map(n => ({
    id: n.id, name: n.label, type: n.type,
    dependencies: [], children: [],
    status: 'pending' as const, parentId: null, progress: 0,
  }));
}

function canvasEdgesToApi(edges: FEdge[]): any[] {
  return edges.map(e => ({ id: e.id, source: e.source, target: e.target, type: 'dependency' }));
}

export function TaskPlanningPage() {
  const sessionId = useChatStore(s => s.sessionId);
  const [nodes, setNodes] = useState<FNode[]>([]);
  const [edges, setEdges] = useState<FEdge[]>([]);
  const [loaded, setLoaded] = useState(false);

  // Load from backend on mount
  useEffect(() => {
    if (!sessionId || loaded) return;
    getTaskGraph(sessionId)
      .then(data => {
        const apiNodes = data.nodes || [];
        if (apiNodes.length > 0) {
          setNodes(apiNodesToCanvas(apiNodes));
          // Edges from dependencies
          const apiEdges: FEdge[] = [];
          apiNodes.forEach((n: any) => {
            (n.dependencies || []).forEach((depId: string) => {
              apiEdges.push({
                id: `e_${depId}_${n.id}`,
                source: depId, target: n.id,
                sourceHandle: 'bottom', targetHandle: 'top',
                mode: 'auto' as const,
              });
            });
          });
          setEdges(apiEdges);
        }
        setLoaded(true);
      })
      .catch(() => setLoaded(true));
  }, [sessionId, loaded]);

  // ── Save to backend ──
  const lastSaveRef = useRef(0);
  useEffect(() => {
    if (!sessionId || !loaded || nodes.length === 0) return;
    const now = Date.now();
    if (now - lastSaveRef.current < 2000) return;
    lastSaveRef.current = now;
    const apiNodes = canvasNodesToApi(nodes);
    const apiEdges = canvasEdgesToApi(edges);
    // Update Zustand store
    useTaskStore.getState().setTaskGraph({
      id: `tg_${sessionId}`, version: '1.0', nodes: apiNodes as any, edges: apiEdges as any,
      rootNodeId: apiNodes[0]?.id || '', createdAt: '', updatedAt: new Date().toISOString(),
      executionStatus: 'idle' as any, overallProgress: 0,
    });
    saveTaskGraph(sessionId, apiNodes, apiEdges).catch(() => {});
  }, [nodes, edges, sessionId, loaded]);

  if (!loaded) return (
    <div className="flex-1 flex items-center justify-center text-text-muted text-sm bg-surface">加载中...</div>
  );

  return (
    <div className="flex flex-col h-full bg-surface">
      {/* Toolbar */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-subtle bg-surface-card/50 shrink-0">
        <h1 className="text-sm font-semibold text-primary">任务规划</h1>
        <div className="flex-1" />
        <span className="text-[11px] text-text-muted">{nodes.length} 节点 · {edges.length} 连线</span>
        <button onClick={() => { setNodes([]); setEdges([]); }}
          className="px-3 py-1 rounded bg-surface-card border border-subtle text-text-secondary text-xs">清空</button>
        <button onClick={() => window.location.reload()}
          className="px-3 py-1 rounded bg-surface-card border border-subtle text-text-secondary text-xs">刷新</button>
      </div>

      {/* Canvas */}
      <FlowchartCanvas nodes={nodes} edges={edges} onNodesChange={setNodes} onEdgesChange={setEdges} />

      {/* Status bar */}
      <div className="px-4 py-1 border-t border-subtle text-[11px] text-text-muted shrink-0">
        双击节点编辑文字 | 选中后连接点拖线 | Delete删除 | 画布区域拖动平移 | 滚轮缩放
      </div>
    </div>
  );
}

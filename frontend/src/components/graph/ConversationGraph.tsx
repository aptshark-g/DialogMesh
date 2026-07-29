/**
 * ConversationGraph — ReactFlow-based interactive graph editor.
 * Replaces react-force-graph-2d (read-only) with full editing capability.
 * Phase B: right-click context menu + double-click edit + delete key.
 */
import { useCallback, useMemo, useState, useEffect, useRef } from 'react';
import {
  ReactFlow,
  useNodesState,
  useEdgesState,
  Handle,
  Position,
  addEdge,
  type Connection,
  type Node,
  type Edge,
  type NodeProps,
  type NodeMouseHandler,
} from '@reactflow/core';
import { Background } from '@reactflow/background';
import { cn } from '@/lib/utils';
import { useTheme } from '@/stores/themeStore';
import dagre from 'dagre';
import '@reactflow/core/dist/style.css';
import type { GraphNode, GraphEdge } from '@/types/graph';
import { Plus, Trash2, GripVertical, Pencil, ArrowUp, ArrowDown } from 'lucide-react';

export interface ConversationGraphProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  searchQuery: string;
  activeFilters: string[];
  selectedNodeId: string | null;
  onNodeClick: (nodeId: string) => void;
  onEdgeClick?: (edgeId: string) => void;
  onNodeAdd?: (type: string) => void;
  onNodeDelete?: (nodeId: string) => void;
  onNodeEdit?: (nodeId: string, newLabel: string) => void;
  zoomLevel?: number;
  onZoomChange?: (zoom: number) => void;
  className?: string;
}

/* ─── Context Menu ────────────────────────────────────────── */

interface ContextMenuState {
  x: number;
  y: number;
  nodeId: string | null;
  edgeId: string | null;
}

function ContextMenu({ state, onClose, onDelete, onEdit, onPromote, onDemote, onAddChild }: {
  state: ContextMenuState;
  onClose: () => void;
  onDelete: (id: string) => void;
  onEdit: (id: string) => void;
  onPromote?: (id: string) => void;
  onDemote?: (id: string) => void;
  onAddChild?: (id: string) => void;
}) {
  const { theme } = useTheme();
  const isDark = theme === 'dark';
  const items: { label: string; icon: React.ReactNode; action: () => void; danger?: boolean }[] = [];

  if (state.nodeId) {
    items.push({ label: '编辑名称', icon: <Pencil className="w-3.5 h-3.5" />, action: () => onEdit(state.nodeId!) });
    if (onAddChild) items.push({ label: '添加子节点', icon: <Plus className="w-3.5 h-3.5" />, action: () => onAddChild(state.nodeId!) });
    if (onPromote) items.push({ label: '提升 (活跃)', icon: <ArrowUp className="w-3.5 h-3.5" />, action: () => onPromote(state.nodeId!) });
    if (onDemote) items.push({ label: '降级 (降温)', icon: <ArrowDown className="w-3.5 h-3.5" />, action: () => onDemote(state.nodeId!) });
    items.push({ label: '删除节点', icon: <Trash2 className="w-3.5 h-3.5" />, action: () => onDelete(state.nodeId!), danger: true });
  } else if (state.edgeId) {
    items.push({ label: '删除连线', icon: <Trash2 className="w-3.5 h-3.5" />, action: () => onDelete(state.edgeId!), danger: true });
  }

  return (
    <div
      className={cn(
        'fixed z-50 min-w-[160px] rounded-lg shadow-xl border py-1 text-sm',
        isDark ? 'bg-surface-card border-subtle text-text-primary' : 'bg-white border-gray-200 text-gray-800'
      )}
      style={{ left: state.x, top: state.y }}
      onClick={(e) => e.stopPropagation()}
    >
      {items.map((item, i) => (
        <button
          key={i}
          className={cn(
            'w-full flex items-center gap-2 px-3 py-1.5 text-left hover:bg-surface-card-hover transition-colors',
            item.danger && (isDark ? 'text-status-error' : 'text-red-600')
          )}
          onClick={() => { item.action(); onClose(); }}
        >
          {item.icon}
          <span>{item.label}</span>
        </button>
      ))}
    </div>
  );
}

/* ─── Node Types ──────────────────────────────────────────── */

const HANDLE_STYLE: React.CSSProperties = {
  width: 8, height: 8, background: '#6366f1', border: 'none', borderRadius: 4,
};

function SessionNode({ data }: NodeProps) {
  const size = (data?.size as number) || 1;
  return (
    <div className={cn(
      'rounded-xl border-2 px-4 py-3 min-w-[120px] max-w-[200px] shadow-lg transition-all cursor-pointer',
      size > 5 ? 'border-primary bg-surface-card-active' : 'border-subtle bg-surface-card',
    )}>
      <Handle type="target" position={Position.Top} style={HANDLE_STYLE} />
      <div className="text-xs font-semibold text-text-primary truncate">
        {data?.label as string || '?'}
      </div>
      <div className="text-[10px] text-text-muted mt-1">{size} 条消息</div>
      <Handle type="source" position={Position.Bottom} style={HANDLE_STYLE} />
    </div>
  );
}

function TaskNode({ data }: NodeProps) {
  const status = (data?.status as string) || 'pending';
  const colorMap: Record<string, string> = {
    pending: 'border-status-pending', running: 'border-primary',
    completed: 'border-status-success', failed: 'border-status-error',
  };
  return (
    <div className={cn(
      'rounded-lg border-2 px-4 py-2.5 min-w-[110px] max-w-[200px] shadow-md transition-all cursor-pointer',
      colorMap[status] || 'border-subtle', 'bg-surface-card',
    )}>
      <Handle type="target" position={Position.Top} style={HANDLE_STYLE} />
      <div className="text-xs font-medium text-text-primary truncate">{data?.label as string || '?'}</div>
      <div className="flex items-center gap-1.5 mt-1">
        <span className={cn('w-2 h-2 rounded-full', colorMap[status]?.replace('border-', 'bg-') || 'bg-text-muted')} />
        <span className="text-[10px] text-text-muted">{status}</span>
      </div>
      <Handle type="source" position={Position.Bottom} style={HANDLE_STYLE} />
    </div>
  );
}

function FallbackNode({ data }: NodeProps) {
  return (
    <div className="rounded-lg border border-subtle px-3 py-2 min-w-[80px] bg-surface-card shadow-sm cursor-pointer">
      <Handle type="target" position={Position.Top} style={HANDLE_STYLE} />
      <div className="text-xs text-text-muted truncate">{data?.label as string || '?'}</div>
      <Handle type="source" position={Position.Bottom} style={HANDLE_STYLE} />
    </div>
  );
}

const CUSTOM_NODE_TYPES = {
  session: SessionNode, task: TaskNode, concept: FallbackNode, default: FallbackNode,
} as const;

/* ─── Main Component ──────────────────────────────────────── */

export function ConversationGraph({
  nodes: graphNodes, edges: graphEdges, searchQuery, activeFilters,
  selectedNodeId, onNodeClick, onEdgeClick, onNodeAdd, onNodeDelete, onNodeEdit,
  className,
}: ConversationGraphProps) {
  const { theme } = useTheme();
  const isDark = theme === 'dark';
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);
  const [editingNode, setEditingNode] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');

  const initialNodes = useMemo(() => {
    // Use dagre for tree layout instead of random positions
    const g = new dagre.graphlib.Graph();
    g.setDefaultEdgeLabel(() => ({}));
    g.setGraph({ rankdir: 'TB', nodesep: 60, ranksep: 80 });
    g.nodes().forEach(n => g.removeNode(n));  // clear

    graphNodes.forEach(n => g.setNode(n.id, { width: 160, height: 50 }));
    graphEdges.forEach(e => g.setEdge(e.source, e.target));

    dagre.layout(g);

    return graphNodes.map((n) => {
      const pos = g.node(n.id);
      return {
        id: n.id, type: (n.type || 'default') as string,
        position: pos ? { x: pos.x - 80, y: pos.y - 25 } : { x: 0, y: 0 },
        data: { label: n.label, type: n.type, size: (n as any).size, status: (n as any).status },
        selected: n.id === selectedNodeId,
        style: searchQuery && !n.label?.toLowerCase().includes(searchQuery.toLowerCase()) ? { opacity: 0.3 } : undefined,
        hidden: activeFilters.length > 0 && !activeFilters.includes(n.type || ''),
      };
    });
  }, [graphNodes, graphEdges, selectedNodeId, searchQuery, activeFilters]);

  const initialEdges = useMemo(() => graphEdges.map((e) => ({
    id: e.id || `${e.source}-${e.target}`, source: e.source, target: e.target,
    type: 'smoothstep', animated: true,
    style: { stroke: isDark ? '#4A4560' : '#D1D5DB', strokeWidth: 2 },
    label: e.type || '', labelStyle: { fill: isDark ? '#6B6680' : '#9CA3AF', fontSize: 10 },
    labelBgStyle: { fill: isDark ? '#1A1724' : '#FFF', fillOpacity: 0.9 },
  })), [graphEdges, isDark]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  const prevNodeCount = useRef(initialNodes.length);
  useEffect(() => {
    if (initialNodes.length !== prevNodeCount.current) {
      setNodes(initialNodes); setEdges(initialEdges);
      prevNodeCount.current = initialNodes.length;
    }
  }, [initialNodes, initialEdges]);

  const onConnect = useCallback(
    (connection: Connection) => setEdges((eds) => addEdge({ ...connection, type: 'smoothstep', animated: true }, eds)),
    [setEdges]
  );

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => onNodeClick(node.id),
    [onNodeClick]
  );

  // ─── Right-click ──────────────────────────────────────────

  const handleNodeContextMenu = useCallback(
    (event: React.MouseEvent, node: Node) => {
      event.preventDefault();
      setContextMenu({ x: event.clientX, y: event.clientY, nodeId: node.id, edgeId: null });
    }, []
  );

  const handleEdgeContextMenu = useCallback(
    (event: React.MouseEvent, edge: Edge) => {
      event.preventDefault();
      setContextMenu({ x: event.clientX, y: event.clientY, nodeId: null, edgeId: edge.id });
    }, []
  );

  const handlePaneClick = useCallback(() => {
    setContextMenu(null);
    setEditingNode(null);
  }, []);

  // ─── Delete key ───────────────────────────────────────────

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Delete' || e.key === 'Backspace') {
        const s = nodes.filter((n) => n.selected);
        if (s.length > 0) {
          const ids = s.map((n) => n.id);
          setNodes((nds) => nds.filter((n) => !ids.includes(n.id)));
          setEdges((eds) => eds.filter((e) => !ids.includes(e.source) && !ids.includes(e.target)));
          ids.forEach((id) => onNodeDelete?.(id));
        }
      }
      if (e.key === 'Escape') { setContextMenu(null); setEditingNode(null); }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [nodes, setNodes, setEdges, onNodeDelete]);

  // ─── Double-click edit ────────────────────────────────────

  const handleNodeDoubleClick = useCallback((_: React.MouseEvent, node: Node) => {
    setEditingNode(node.id);
    setEditValue((node.data?.label as string) || '');
  }, []);

  const handleEditSubmit = useCallback(() => {
    if (editingNode && editValue.trim()) {
      setNodes((nds) => nds.map((n) =>
        n.id === editingNode ? { ...n, data: { ...n.data, label: editValue.trim() } } : n
      ));
      onNodeEdit?.(editingNode, editValue.trim());
    }
    setEditingNode(null);
  }, [editingNode, editValue, setNodes, onNodeEdit]);

  const bgColor = isDark ? '#0C0A0F' : '#FDFCF8';

  return (
    <div className={cn('absolute inset-0 rounded-xl overflow-hidden border border-subtle', className)}>
      {nodes.length === 0 ? (
        <div className="flex items-center justify-center h-full text-text-muted text-sm">
          {graphNodes.length === 0 ? '📭 暂无图数据 — 开始聊天后自动生成' : '⏳ 加载中...'}
        </div>
      ) : (
      <ReactFlow
        nodes={nodes.map((n) =>
          editingNode === n.id
            ? { ...n, data: { ...n.data, label: editValue }, className: 'ring-2 ring-primary' }
            : n
        )}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeClick={handleNodeClick}
        onNodeDoubleClick={handleNodeDoubleClick}
        onNodeContextMenu={handleNodeContextMenu}
        onEdgeContextMenu={handleEdgeContextMenu}
        onPaneClick={handlePaneClick}
        nodeTypes={CUSTOM_NODE_TYPES as any}
        fitView snapToGrid snapGrid={[16, 16]}
        style={{ background: bgColor }}
        deleteKeyCode={null}
        multiSelectionKeyCode="Shift"
      >
        <Background color={isDark ? '#2A2635' : '#E5E7EB'} gap={20} />
      </ReactFlow>
      )}

      {/* Context Menu */}
      {contextMenu && (
        <>
          <div className="fixed inset-0 z-40" onClick={handlePaneClick} />
          <ContextMenu
            state={contextMenu}
            onClose={() => setContextMenu(null)}
            onDelete={(id) => {
              setNodes((nds) => nds.filter((n) => n.id !== id));
              setEdges((eds) => eds.filter((e) => e.source !== id && e.target !== id));
              onNodeDelete?.(id);
            }}
            onEdit={(id) => {
              const node = nodes.find((n) => n.id === id);
              setEditingNode(id);
              setEditValue((node?.data?.label as string) || '');
            }}
            onPromote={(id) => onNodeEdit?.(id, nodes.find((n) => n.id === id)?.data?.label as string || '')}
            onDemote={(id) => onNodeEdit?.(id, nodes.find((n) => n.id === id)?.data?.label as string || '')}
          />
        </>
      )}

      {/* Inline Edit Overlay */}
      {editingNode && (
        <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-50 flex items-center gap-2 bg-surface-card border border-primary rounded-lg px-3 py-2 shadow-xl">
          <input
            autoFocus
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleEditSubmit(); if (e.key === 'Escape') setEditingNode(null); }}
            className="bg-surface-sidebar text-text-primary text-sm rounded px-2 py-1 outline-none border border-subtle focus:border-primary min-w-[200px]"
            placeholder="输入节点名称..."
          />
          <button onClick={handleEditSubmit} className="px-3 py-1 bg-primary text-white rounded text-xs font-medium hover:bg-primary-dark">确认</button>
          <button onClick={() => setEditingNode(null)} className="px-2 py-1 text-text-muted text-xs hover:text-text-primary">取消</button>
        </div>
      )}
    </div>
  );
}

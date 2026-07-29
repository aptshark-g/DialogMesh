/**
 * ConversationGraph — ReactFlow-based interactive graph editor.
 * Replaces react-force-graph-2d (read-only) with full editing capability.
 * Reuses TaskFlow's node/edge patterns for consistency.
 */
import { useCallback, useMemo, useState } from 'react';
import {
  ReactFlow,
  useNodesState,
  useEdgesState,
  Handle,
  Position,
  addEdge,
  Background,
  Controls,
  type Connection,
  type Node,
  type Edge,
  type NodeProps,
} from '@reactflow/core';
import { cn } from '@/lib/utils';
import { useTheme } from '@/stores/themeStore';
import '@reactflow/core/dist/style.css';
import type { GraphNode, GraphEdge } from '@/types/graph';

export interface ConversationGraphProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  searchQuery: string;
  activeFilters: string[];
  selectedNodeId: string | null;
  onNodeClick: (nodeId: string) => void;
  onEdgeClick?: (edgeId: string) => void;
  zoomLevel?: number;
  onZoomChange?: (zoom: number) => void;
  className?: string;
}

/* ─── Node Type Registry ──────────────────────────────────────── */

const HANDLE_STYLE: React.CSSProperties = {
  width: 8, height: 8, background: '#6366f1', border: 'none', borderRadius: 4,
};

function SessionNode({ data }: NodeProps) {
  const size = (data?.size as number) || 1;
  return (
    <div className={cn(
      'rounded-xl border-2 px-4 py-3 min-w-[120px] max-w-[200px] shadow-lg transition-all',
      size > 5 ? 'border-primary bg-surface-card-active' : 'border-subtle bg-surface-card',
    )}>
      <Handle type="target" position={Position.Top} style={HANDLE_STYLE} />
      <div className="text-xs font-semibold text-text-primary truncate">
        {data?.label as string || '?'}
      </div>
      <div className="text-[10px] text-text-muted mt-1">
        {size} 条消息
      </div>
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
      'rounded-lg border-2 px-4 py-2.5 min-w-[110px] max-w-[200px] shadow-md transition-all',
      colorMap[status] || 'border-subtle',
      'bg-surface-card',
    )}>
      <Handle type="target" position={Position.Top} style={HANDLE_STYLE} />
      <div className="text-xs font-medium text-text-primary truncate">
        {data?.label as string || '?'}
      </div>
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
    <div className="rounded-lg border border-subtle px-3 py-2 min-w-[80px] bg-surface-card shadow-sm">
      <Handle type="target" position={Position.Top} style={HANDLE_STYLE} />
      <div className="text-xs text-text-muted truncate">{data?.label as string || '?'}</div>
      <Handle type="source" position={Position.Bottom} style={HANDLE_STYLE} />
    </div>
  );
}

const CUSTOM_NODE_TYPES = {
  session: SessionNode,
  task: TaskNode,
  concept: FallbackNode,
  default: FallbackNode,
} as const;

/* ─── Main Component ──────────────────────────────────────────── */

export function ConversationGraph({
  nodes: graphNodes,
  edges: graphEdges,
  searchQuery,
  activeFilters,
  selectedNodeId,
  onNodeClick,
  onEdgeClick,
  className,
}: ConversationGraphProps) {
  const { theme } = useTheme();
  const isDark = theme === 'dark';

  // Convert external GraphNode/GraphEdge to ReactFlow format
  const initialNodes = useMemo(() => graphNodes.map((n) => ({
    id: n.id,
    type: (n.type || 'default') as string,
    position: { x: Math.random() * 400, y: Math.random() * 300 },
    data: {
      label: n.label,
      type: n.type,
      size: (n as any).size,
      status: (n as any).status,
    },
    selected: n.id === selectedNodeId,
    style: searchQuery && !n.label?.toLowerCase().includes(searchQuery.toLowerCase())
      ? { opacity: 0.3 } : undefined,
    hidden: activeFilters.length > 0 && !activeFilters.includes(n.type || ''),
  })), [graphNodes, selectedNodeId, searchQuery, activeFilters]);

  const initialEdges = useMemo(() => graphEdges.map((e) => ({
    id: e.id || `${e.source}-${e.target}`,
    source: e.source,
    target: e.target,
    type: 'smoothstep',
    animated: true,
    style: { stroke: isDark ? '#4A4560' : '#D1D5DB', strokeWidth: 2 },
    label: e.type || '',
    labelStyle: { fill: isDark ? '#6B6680' : '#9CA3AF', fontSize: 10 },
    labelBgStyle: { fill: isDark ? '#1A1724' : '#FFFFFF', fillOpacity: 0.9 },
  })), [graphEdges, isDark]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  const onConnect = useCallback(
    (connection: Connection) => setEdges((eds) => addEdge({ ...connection, type: 'smoothstep', animated: true }, eds)),
    [setEdges]
  );

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => onNodeClick(node.id),
    [onNodeClick]
  );

  const handleEdgeClick = useCallback(
    (_: React.MouseEvent, edge: Edge) => onEdgeClick?.(edge.id),
    [onEdgeClick]
  );

  const bgColor = isDark ? '#0C0A0F' : '#FDFCF8';

  return (
    <div className={cn('w-full h-full rounded-xl overflow-hidden border border-subtle', className)}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeClick={handleNodeClick}
        onEdgeClick={handleEdgeClick}
        nodeTypes={CUSTOM_NODE_TYPES as any}
        fitView
        snapToGrid
        snapGrid={[16, 16]}
        style={{ background: bgColor }}
        attributionPosition="bottom-left"
      >
        <Background color={isDark ? '#2A2635' : '#E5E7EB'} gap={20} />
        <Controls className="[&>button]:!bg-surface-card [&>button]:!border-subtle [&>button]:!text-text-secondary" />
      </ReactFlow>
    </div>
  );
}

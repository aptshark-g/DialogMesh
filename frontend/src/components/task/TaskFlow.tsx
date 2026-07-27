import { useCallback, useMemo, useRef, useEffect, type FC, type CSSProperties } from 'react';
import type { MouseEvent } from 'react';
import {
  ReactFlow,
  useReactFlow,
  Handle,
  Position,
  getBezierPath,
  BaseEdge,
  EdgeLabelRenderer,
  addEdge,
  applyNodeChanges,
  applyEdgeChanges,
  type Node,
  type Edge,
  type Connection,
  type NodeChange,
  type EdgeChange,
} from '@reactflow/core';
import { Background } from '@reactflow/background';
import { MiniMap } from '@reactflow/minimap';
import { cn } from '@/lib/utils';
import { Plus, Minus, Maximize2 } from 'lucide-react';
import { useTheme } from '@/stores/themeStore';

/* ==================== CSS Animation ==================== */

let dashInjected = false;
function injectDashAnimation(): void {
  if (typeof document === 'undefined' || dashInjected) return;
  dashInjected = true;
  const style = document.createElement('style');
  style.id = 'rf-dashdraw';
  style.textContent = `@keyframes dashdraw { from { stroke-dashoffset: 20; } to { stroke-dashoffset: 0; } }`;
  document.head.appendChild(style);
}

/* ==================== Node Handles ==================== */

const handleStyle: CSSProperties = { width: 8, height: 8, background: '#4A4560', border: 'none' };

/* ==================== Node Types ==================== */

function StartNode({ data }: { data?: Record<string, unknown> }) {
  return (
    <div className="rounded-lg border-2 border-emerald bg-transparent px-4 py-2 min-w-[100px] text-center">
      <Handle type="target" position={Position.Top} style={handleStyle} isConnectable={true} />
      <span className="text-sm font-medium text-primary">{(data?.name as string) || '开始'}</span>
      <Handle type="source" position={Position.Bottom} style={handleStyle} isConnectable={true} />
    </div>
  );
}

function ProcessNode({ data }: { data?: Record<string, unknown> }) {
  const status = (data?.status as string) || 'pending';
  const borderMap: Record<string, string> = {
    pending: 'border-status-pending',
    running: 'border-primary',
    completed: 'border-status-success',
    failed: 'border-status-error',
  };
  const isDangerous = (data?.isDangerous as boolean) ?? false;
  return (
    <div className={cn(
      'relative rounded-lg border-2 bg-transparent px-4 py-3 min-w-[180px]',
      borderMap[status] || 'border-status-pending',
      status === 'running' && 'animate-executing-pulse'
    )}>
      <Handle type="target" position={Position.Top} style={handleStyle} isConnectable={true} />
      {isDangerous && (
        <div className="absolute -top-2 -right-2 w-5 h-5 bg-status-error rounded-full flex items-center justify-center text-white text-[10px] font-bold z-10">⚠</div>
      )}
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-primary">{(data?.name as string) || ''}</span>
      </div>
      {!!data?.description && (
        <div className="text-xs text-secondary mt-1 line-clamp-2">{(data?.description as string)}</div>
      )}
      {status === 'running' && (
        <div className="mt-2 text-xs">{(data?.progress as number ?? 0)}%</div>
      )}
      <Handle type="source" position={Position.Bottom} style={handleStyle} isConnectable={true} />
    </div>
  );
}

function DecisionNode({ data }: { data?: Record<string, unknown> }) {
  const status = (data?.status as string) || 'pending';
  return (
    <div className="relative bg-transparent">
      <Handle type="target" position={Position.Top} style={handleStyle} isConnectable={true} />
      <div
        className={cn(
          'relative px-4 py-6 min-w-[180px] text-center rounded-full border-2',
          status === 'completed' ? 'border-status-success' : 'border-primary'
        )}
        style={{ transform: 'rotate(-2deg)' }}
      >
        <span className="text-sm font-medium text-primary">{(data?.name as string) || ''}</span>
      </div>
      <Handle type="source" position={Position.Bottom} style={handleStyle} isConnectable={true} id="bottom" />
      <Handle type="source" position={Position.Right} style={handleStyle} isConnectable={true} id="right" />
      <Handle type="source" position={Position.Left} style={handleStyle} isConnectable={true} id="left" />
    </div>
  );
}

function EndNode({ data }: { data?: Record<string, unknown> }) {
  return (
    <div className="rounded-full border-2 border-emerald bg-transparent px-6 py-3 min-w-[80px] text-center">
      <Handle type="target" position={Position.Top} style={handleStyle} isConnectable={true} />
      <span className="text-sm font-medium text-primary">{(data?.name as string) || '结束'}</span>
    </div>
  );
}

const nodeTypes = {
  start: StartNode,
  process: ProcessNode,
  decision: DecisionNode,
  end: EndNode,
} as Record<string, ComponentType<{ data?: Record<string, unknown> }>>;

/* ==================== Custom Edge ==================== */

function AnimatedEdge({
  id, sourceX, sourceY, targetX, targetY,
  sourcePosition, targetPosition, data,
}: {
  id: string | undefined;
  sourceX: number;
  sourceY: number;
  targetX: number;
  targetY: number;
  sourcePosition: Position;
  targetPosition: Position;
  data?: { status?: string };
}) {
  const [edgePath] = getBezierPath({ sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition });
  const color = data?.status === 'completed' ? '#10B981' : data?.status === 'running' ? '#D97706' : '#6B6680';
  return (
    <>
      <BaseEdge id={id as string} path={edgePath} style={{ stroke: color, strokeWidth: 2 }} />
      <EdgeLabelRenderer>
        {data?.status === 'running' && (
          <div
            style={{
              position: 'absolute', transform: `translate(-50%, -50%) translate(${(sourceX + targetX) / 2}px, ${(sourceY + targetY) / 2}px)`,
              fontSize: 10, color: '#D97706', pointerEvents: 'all',
            }}
            className="absolute text-xs text-muted bg-surface-card px-2 py-0.5 rounded-sm border border-subtle pointer-events-none"
          >
            执行中
          </div>
        )}
      </EdgeLabelRenderer>
    </>
  );
}

const edgeTypes = { animated: AnimatedEdge };

/* ==================== Controls ==================== */

function FitViewHandler() {
  const { fitView } = useReactFlow();
  const done = useRef(false);
  useEffect(() => {
    if (!done.current) {
      setTimeout(() => { fitView({ padding: 0.2 }); done.current = true; }, 100);
    }
  }, [fitView]);
  return null;
}

function FlowControls() {
  const { zoomIn, zoomOut, fitView } = useReactFlow();
  return (
    <div className="absolute bottom-4 right-4 flex flex-col gap-2 z-10">
      <button onClick={() => zoomIn?.()} className="w-8 h-8 rounded-md bg-surface-card border border-subtle flex items-center justify-center text-secondary hover:text-primary hover:bg-surface-card-hover transition-colors"><Plus size={16} /></button>
      <button onClick={() => zoomOut?.()} className="w-8 h-8 rounded-md bg-surface-card border border-subtle flex items-center justify-center text-secondary hover:text-primary hover:bg-surface-card-hover transition-colors"><Minus size={16} /></button>
      <button onClick={() => fitView?.()} className="w-8 h-8 rounded-md bg-surface-card border border-subtle flex items-center justify-center text-secondary hover:text-primary hover:bg-surface-card-hover transition-colors"><Maximize2 size={14} /></button>
    </div>
  );
}

function getMiniMapNodeColor(node: Node): string {
  const s = (node.data?.status as string) || 'pending';
  const m: Record<string, string> = { pending: '#6B6680', running: '#D97706', completed: '#10B981', failed: '#EF4444' };
  return m[s] || '#6B6680';
}

injectDashAnimation();

/* ==================== Props ==================== */

export interface TaskFlowProps {
  nodes: Node[];
  edges: Edge[];
  selectedNodeId: string | null;
  onNodeClick: (nodeId: string) => void;
  onNodesChange: (changes: NodeChange[]) => void;
  onEdgesChange: (changes: EdgeChange[]) => void;
  onConnect: (connection: Connection) => void;
  onNodesDelete: (nodeIds: string[]) => void;
  onEdgesDelete: (edgeIds: string[]) => void;
  onPaneClick: () => void;
}

/* ==================== TaskFlow — Controlled Component ==================== */

export const TaskFlow: FC<TaskFlowProps> = ({
  nodes,
  edges,
  selectedNodeId,
  onNodeClick,
  onNodesChange,
  onEdgesChange,
  onConnect,
  onNodesDelete,
  onEdgesDelete,
  onPaneClick,
}) => {
  const theme = useTheme();
  const isLight = theme === 'light';

  const highlightedNodes = useMemo(() => {
    if (!selectedNodeId) return nodes;
    return nodes.map((node) => ({
      ...node,
      className: selectedNodeId === node.id ? '' : 'opacity-50',
    }));
  }, [nodes, selectedNodeId]);

  const handleConnect = useCallback((params: Connection) => {
    onConnect(params);
  }, [onConnect]);

  const handleNodesDelete = useCallback((deleted: { id: string }[]) => {
    onNodesDelete(deleted.map(d => d.id));
  }, [onNodesDelete]);

  const handleEdgesDelete = useCallback((deleted: { id: string }[]) => {
    onEdgesDelete(deleted.map(d => d.id));
  }, [onEdgesDelete]);

  return (
    <div className="flex-1 w-full h-full relative">
      <ReactFlow
        nodes={highlightedNodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodeClick={(_e, node) => onNodeClick(node.id)}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={handleConnect}
        onNodesDelete={handleNodesDelete}
        onEdgesDelete={handleEdgesDelete}
        onPaneClick={onPaneClick}
        nodesDraggable={true}
        nodesConnectable={true}
        deleteKeyCode="Backspace"
        elementsSelectable={true}
        panOnDrag={true}
        selectNodesOnDrag={true}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.1}
        maxZoom={2}
        style={{ background: isLight ? '#FDFCF8' : '#0C0A0F' }}
        proOptions={{ hideAttribution: true }}
      >
        <FitViewHandler />
        <FlowControls />
        <Background color={isLight ? '#D1D5DB' : '#3A3548'} gap={20} size={1} variant="dots" />
        <MiniMap
          nodeColor={getMiniMapNodeColor}
          nodeStrokeColor={isLight ? '#D1D5DB' : '#2A2635'}
          maskColor={isLight ? 'rgba(0,0,0,0.04)' : 'rgba(0,0,0,0.6)'}
          nodeStrokeWidth={3}
          pannable
          zoomable
          style={{ background: isLight ? '#F5F0E8' : '#1A1724', border: isLight ? '1px solid #E5E7EB' : '1px solid #2A2635' }}
          position="bottom-right"
        />
      </ReactFlow>
    </div>
  );
};

export default TaskFlow;

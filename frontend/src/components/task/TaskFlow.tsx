import { useEffect, useCallback, useMemo, type FC, type CSSProperties, type ComponentType } from 'react';
import type { MouseEvent } from 'react';
import {
  ReactFlow,
  useNodesState,
  useEdgesState,
  useReactFlow,
  Handle,
  Position,
  getBezierPath,
  BaseEdge,
  EdgeLabelRenderer,
} from '@reactflow/core';
import type { Node, Edge } from '@reactflow/core';
import { Background } from '@reactflow/background';
import { MiniMap } from '@reactflow/minimap';
import { cn } from '@/lib/utils';
import { Plus, Minus, Maximize2 } from 'lucide-react';

/* ==================== CSS Animation ==================== */

function injectDashAnimation(): void {
  if (typeof document === 'undefined') return;
  if (document.getElementById('rf-dashdraw')) return;
  const style = document.createElement('style');
  style.id = 'rf-dashdraw';
  style.textContent = `
    @keyframes dashdraw {
      from { stroke-dashoffset: 20; }
      to { stroke-dashoffset: 0; }
    }
  `;
  document.head.appendChild(style);
}

/* ==================== Node Handles ==================== */

const handleStyle: CSSProperties = { width: 8, height: 8, background: '#4A4560', border: 'none' };

/* ==================== Placeholder Nodes ==================== */

function StartNode({ data }: { data?: Record<string, unknown> }) {
  return (
    <div className="rounded-lg border-2 border-emerald bg-transparent px-4 py-2 min-w-[100px] text-center">
      <Handle type="target" position={Position.Top} style={handleStyle} />
      <span className="text-sm font-medium text-primary">{(data?.name as string) || '开始'}</span>
      <Handle type="source" position={Position.Bottom} style={handleStyle} />
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
    skipped: 'border-status-pending',
    blocked: 'border-status-pending',
  };
  const isDangerous = (data?.isDangerous as boolean) ?? false;

  return (
    <div className={cn(
      'relative rounded-lg border-2 bg-transparent px-4 py-3 min-w-[180px]',
      borderMap[status] || 'border-status-pending',
      status === 'running' && 'animate-executing-pulse'
    )}>
      <Handle type="target" position={Position.Top} style={handleStyle} />
      {isDangerous && (
        <div className="absolute -top-2 -right-2 w-5 h-5 bg-status-error rounded-full flex items-center justify-center text-white text-[10px] font-bold z-10">⚠</div>
      )}
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-primary">{(data?.name as string) || ''}</span>
      </div>
      {!!data?.description && (
        <div className="text-xs text-secondary mt-1 line-clamp-2">{(data?.description as string)}</div>
      )}
      <div className="mt-2 flex items-center justify-end">
        <span className={cn(
          'text-[10px] px-1.5 py-0.5 rounded-sm font-medium',
          status === 'completed' && 'bg-status-success/10 text-status-success',
          status === 'running' && 'bg-primary/10 text-primary',
          status === 'failed' && 'bg-status-error/10 text-status-error',
          status === 'pending' && 'bg-status-pending/10 text-status-pending',
        )}>
          {status === 'completed' ? '已完成' : status === 'running' ? '执行中' : status === 'failed' ? '失败' : '待执行'}
        </span>
      </div>
      <Handle type="source" position={Position.Bottom} style={handleStyle} />
    </div>
  );
}

function DecisionNode({ data }: { data?: Record<string, unknown> }) {
  return (
    <div className="relative">
      <Handle type="target" position={Position.Top} style={handleStyle} />
      <div className="w-20 h-20 border-2 border-border-medium bg-transparent rotate-45 flex items-center justify-center">
        <span className="text-xs text-primary -rotate-45 text-center leading-tight">{(data?.name as string) || '决策'}</span>
      </div>
      <Handle type="source" position={Position.Bottom} style={handleStyle} id="bottom" />
      <Handle type="source" position={Position.Right} style={handleStyle} id="right" />
      <Handle type="source" position={Position.Left} style={handleStyle} id="left" />
      <div className="absolute top-24 left-1/2 -translate-x-1/2 text-xs text-muted whitespace-nowrap">
        {(data?.description as string) || ''}
      </div>
    </div>
  );
}

function EndNode({ data }: { data?: Record<string, unknown> }) {
  return (
    <div className="rounded-lg border-2 border-muted bg-transparent px-4 py-2 min-w-[100px] text-center">
      <Handle type="target" position={Position.Top} style={handleStyle} />
      <span className="text-sm font-medium text-primary">{(data?.name as string) || '结束'}</span>
    </div>
  );
}

const nodeTypes: Record<string, ComponentType> = {
  start: StartNode,
  process: ProcessNode,
  decision: DecisionNode,
  end: EndNode,
};

/* ==================== Placeholder Edges ==================== */

function AnimatedEdge(props: Record<string, unknown>) {
  const { id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data } = props;
  const [edgePath] = getBezierPath({
    sourceX: sourceX as number,
    sourceY: sourceY as number,
    targetX: targetX as number,
    targetY: targetY as number,
    sourcePosition: sourcePosition as string,
    targetPosition: targetPosition as string,
  });
  const status = (data as Record<string, unknown> | undefined)?.status as string || 'pending';
  const color = status === 'running' ? '#D97706' : status === 'completed' ? '#10B981' : status === 'failed' ? '#EF4444' : '#3A3548';

  return (
    <BaseEdge
      id={id as string}
      path={edgePath}
      style={{
        stroke: color,
        strokeWidth: 2,
        strokeDasharray: '5 5',
        animation: 'dashdraw 0.5s linear infinite',
      }}
    />
  );
}

function ConditionEdge(props: Record<string, unknown>) {
  const { id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, label, data } = props;
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX: sourceX as number,
    sourceY: sourceY as number,
    targetX: targetX as number,
    targetY: targetY as number,
    sourcePosition: sourcePosition as string,
    targetPosition: targetPosition as string,
  });
  const status = (data as Record<string, unknown> | undefined)?.status as string || 'pending';
  const color = status === 'running' ? '#D97706' : status === 'completed' ? '#10B981' : status === 'failed' ? '#EF4444' : '#3A3548';
  const conditionLabel = (label as string) || (data as Record<string, unknown> | undefined)?.condition as string || '';

  return (
    <>
      <BaseEdge id={id as string} path={edgePath} style={{ stroke: color, strokeWidth: 2 }} />
      {conditionLabel && (
        <EdgeLabelRenderer>
          <div
            className="absolute text-xs text-muted bg-surface-card px-2 py-0.5 rounded-sm border border-subtle pointer-events-none"
            style={{
              transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            }}
          >
            {conditionLabel}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

const edgeTypes: Record<string, ComponentType> = {
  animated: AnimatedEdge,
  condition: ConditionEdge,
};

/* ==================== Internal Helpers ==================== */

const FitViewHandler: FC = () => {
  const { fitView } = useReactFlow();
  useEffect(() => {
    const timer = setTimeout(() => fitView({ padding: 0.2 }), 50);
    return () => clearTimeout(timer);
  }, [fitView]);
  return null;
};

const FlowControls: FC = () => {
  const { zoomIn, zoomOut, fitView } = useReactFlow();
  return (
    <div className="absolute bottom-4 left-4 z-10 flex flex-col gap-1 bg-surface-card border border-subtle rounded-md p-1 shadow-card">
      <button type="button" onClick={() => zoomIn()} className="p-1.5 rounded hover:bg-surface-card-hover text-secondary hover:text-primary transition-colors" title="Zoom In">
        <Plus className="w-4 h-4" />
      </button>
      <button type="button" onClick={() => zoomOut()} className="p-1.5 rounded hover:bg-surface-card-hover text-secondary hover:text-primary transition-colors" title="Zoom Out">
        <Minus className="w-4 h-4" />
      </button>
      <button type="button" onClick={() => fitView({ padding: 0.2 })} className="p-1.5 rounded hover:bg-surface-card-hover text-secondary hover:text-primary transition-colors" title="Fit View">
        <Maximize2 className="w-4 h-4" />
      </button>
    </div>
  );
};

/* ==================== Props ==================== */

export interface TaskFlowProps {
  nodes: Node[];
  edges: Edge[];
  selectedNodeId: string | null;
  onNodeClick: (nodeId: string) => void;
  onNodesChange?: (changes: unknown[]) => void;
  onEdgesChange?: (changes: unknown[]) => void;
  onPaneClick?: () => void;
}

/* ==================== TaskFlow Component ==================== */

export const TaskFlow: FC<TaskFlowProps> = ({
  nodes: initialNodes,
  edges: initialEdges,
  selectedNodeId,
  onNodeClick,
  onNodesChange: externalNodesChange,
  onEdgesChange: externalEdgesChange,
  onPaneClick,
}) => {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  useEffect(() => {
    injectDashAnimation();
  }, []);

  useEffect(() => {
    setNodes(initialNodes);
  }, [initialNodes, setNodes]);

  useEffect(() => {
    setEdges(initialEdges);
  }, [initialEdges, setEdges]);

  const handleNodeClick = useCallback((_event: MouseEvent, node: Node) => {
    onNodeClick(node.id);
  }, [onNodeClick]);

  const handlePaneClick = useCallback(() => {
    onPaneClick?.();
  }, [onPaneClick]);

  const handleNodesChange = useCallback((changes: unknown[]) => {
    onNodesChange(changes);
    externalNodesChange?.(changes);
  }, [onNodesChange, externalNodesChange]);

  const handleEdgesChange = useCallback((changes: unknown[]) => {
    onEdgesChange(changes);
    externalEdgesChange?.(changes);
  }, [onEdgesChange, externalEdgesChange]);

  const getMiniMapNodeColor = useCallback((node: { data?: Record<string, unknown> }) => {
    const status = node.data?.status as string;
    switch (status) {
      case 'completed': return '#10B981';
      case 'running': return '#D97706';
      case 'failed': return '#EF4444';
      case 'pending': return '#6B6680';
      default: return '#3A3548';
    }
  }, []);

  const highlightedNodes = useMemo(() => {
    if (!selectedNodeId) return nodes;
    return nodes.map((node) => ({
      ...node,
      style: {
        ...node.style,
        opacity: selectedNodeId === node.id ? 1 : 0.5,
      },
    }));
  }, [nodes, selectedNodeId]);

  return (
    <div className="flex-1 w-full h-full relative">
      <ReactFlow
        nodes={highlightedNodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodeClick={handleNodeClick}
        onNodesChange={handleNodesChange}
        onEdgesChange={handleEdgesChange}
        onPaneClick={handlePaneClick}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={true}
        panOnDrag={true}
        selectNodesOnDrag={false}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.1}
        maxZoom={2}
        style={{ background: '#0C0A0F' }}
        proOptions={{ hideAttribution: true }}
      >
        <FitViewHandler />
        <FlowControls />
        <Background color="#3A3548" gap={20} size={1} variant="dots" />
        <MiniMap
          nodeColor={getMiniMapNodeColor}
          nodeStrokeColor="#2A2635"
          maskColor="rgba(0, 0, 0, 0.6)"
          style={{ background: '#1A1724', border: '1px solid #2A2635' }}
          position="bottom-right"
        />
      </ReactFlow>
    </div>
  );
};

export default TaskFlow;

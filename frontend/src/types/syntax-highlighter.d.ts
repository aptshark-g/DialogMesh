declare module 'react-syntax-highlighter' {
  import { FC, CSSProperties } from 'react';
  interface SyntaxHighlighterProps {
    language?: string;
    style?: Record<string, unknown>;
    children: string;
    customStyle?: CSSProperties;
    codeTagProps?: Record<string, unknown>;
    showLineNumbers?: boolean;
    lineNumberStyle?: CSSProperties;
    wrapLines?: boolean;
    wrapLongLines?: boolean;
    PreTag?: keyof JSX.IntrinsicElements | FC;
    CodeTag?: keyof JSX.IntrinsicElements | FC;
    [key: string]: unknown;
  }
  export const Prism: FC<SyntaxHighlighterProps>;
  export const Light: FC<SyntaxHighlighterProps>;
  export const PrismAsync: FC<SyntaxHighlighterProps>;
  export const PrismAsyncLight: FC<SyntaxHighlighterProps>;
  export const LightAsync: FC<SyntaxHighlighterProps>;
}

declare module 'react-syntax-highlighter/dist/esm/styles/prism' {
  export const vscDarkPlus: Record<string, unknown>;
  export const oneDark: Record<string, unknown>;
  export const tomorrow: Record<string, unknown>;
}

declare module 'react-force-graph-2d' {
  import { FC } from 'react';
  interface ForceGraphNode {
    id: string | number;
    [key: string]: unknown;
  }
  interface ForceGraphLink {
    source: string | number | ForceGraphNode;
    target: string | number | ForceGraphNode;
    [key: string]: unknown;
  }
  interface ForceGraphProps {
    graphData?: { nodes?: ForceGraphNode[]; links?: ForceGraphLink[] };
    nodeAutoColorBy?: string;
    nodeLabel?: (node: ForceGraphNode) => string;
    nodeColor?: string | ((node: ForceGraphNode) => string);
    nodeRelSize?: number;
    nodeVal?: number | ((node: ForceGraphNode) => number);
    nodeCanvasObject?: (node: ForceGraphNode, ctx: CanvasRenderingContext2D, globalScale: number) => void;
    nodeCanvasObjectMode?: string | ((node: ForceGraphNode) => string);
    linkLabel?: (link: ForceGraphLink) => string;
    linkColor?: string | ((link: ForceGraphLink) => string);
    linkWidth?: number | ((link: ForceGraphLink) => number);
    linkCurvature?: number | ((link: ForceGraphLink) => number);
    linkDirectionalArrowLength?: number | ((link: ForceGraphLink) => number);
    linkDirectionalArrowRelPos?: number;
    linkDirectionalArrowColor?: string | ((link: ForceGraphLink) => string);
    linkDirectionalArrowVisibility?: boolean | ((link: ForceGraphLink) => boolean);
    dagMode?: string;
    dagLevelDistance?: number;
    dagNodeFilter?: (node: ForceGraphNode) => boolean;
    onNodeClick?: (node: ForceGraphNode) => void;
    onNodeHover?: (node: ForceGraphNode) => void;
    onNodeDrag?: (node: ForceGraphNode, translate: { x: number; y: number }) => void;
    onNodeDragEnd?: (node: ForceGraphNode, translate: { x: number; y: number }) => void;
    onBackgroundClick?: (event: MouseEvent) => void;
    onZoom?: (event: { k: number; x: number; y: number }) => void;
    onZoomEnd?: (event: { k: number; x: number; y: number }) => void;
    onDagError?: (loopNodeIds: (string | number)[]) => void;
    backgroundColor?: string;
    width?: number;
    height?: number;
    warmupTicks?: number;
    cooldownTicks?: number;
    cooldownTime?: number;
    enableNodeDrag?: boolean;
    enableZoomInteraction?: boolean;
    enablePanInteraction?: boolean;
    showNavInfo?: boolean;
    [key: string]: unknown;
  }
  export const ForceGraph2D: FC<ForceGraphProps>;
}

/* ==================== @reactflow/core ==================== */

declare module '@reactflow/core' {
  import { FC, MouseEvent, ComponentType } from 'react';

  export type NodeType = 'default' | 'input' | 'output' | 'group' | string;
  export type EdgeType = 'default' | 'straight' | 'step' | 'smoothstep' | 'bezier' | string;
  export type ConnectionMode = 'strict' | 'loose';

  export interface Node<T = Record<string, unknown>> {
    id: string;
    type?: string;
    position: { x: number; y: number };
    data: T;
    width?: number;
    height?: number;
    selected?: boolean;
    dragging?: boolean;
    targetPosition?: 'left' | 'right' | 'top' | 'bottom';
    sourcePosition?: 'left' | 'right' | 'top' | 'bottom';
    hidden?: boolean;
    parentNode?: string;
    extent?: 'parent' | [[number, number], [number, number]];
    expandParent?: boolean;
    zIndex?: number;
    deletable?: boolean;
    draggable?: boolean;
    selectable?: boolean;
    connectable?: boolean;
    focusable?: boolean;
    style?: React.CSSProperties;
    className?: string;
  }

  export interface Edge {
    id: string;
    type?: string;
    source: string;
    target: string;
    sourceHandle?: string;
    targetHandle?: string;
    label?: string;
    labelStyle?: React.CSSProperties;
    labelShowBg?: boolean;
    labelBgStyle?: React.CSSProperties;
    labelBgPadding?: [number, number];
    labelBgBorderRadius?: number;
    animated?: boolean;
    selected?: boolean;
    hidden?: boolean;
    deletable?: boolean;
    selectable?: boolean;
    focusable?: boolean;
    markerStart?: string | EdgeMarker;
    markerEnd?: string | EdgeMarker;
    zIndex?: number;
    style?: React.CSSProperties;
    className?: string;
    data?: Record<string, unknown>;
  }

  export interface EdgeMarker {
    type: string;
    color?: string;
    width?: number;
    height?: number;
    markerUnits?: string;
    orient?: string;
    strokeWidth?: number;
  }

  export interface Connection {
    source: string | null;
    target: string | null;
    sourceHandle?: string | null;
    targetHandle?: string | null;
  }

  export interface ReactFlowProps {
    nodes: Node[];
    edges: Edge[];
    nodeTypes?: Record<string, ComponentType>;
    edgeTypes?: Record<string, ComponentType>;
    defaultNodes?: Node[];
    defaultEdges?: Edge[];
    fitView?: boolean;
    fitViewOptions?: { padding?: number; includeHiddenNodes?: boolean; minZoom?: number; maxZoom?: number; duration?: number };
    defaultViewport?: { x: number; y: number; zoom: number };
    minZoom?: number;
    maxZoom?: number;
    defaultMarkerColor?: string;
    zoomOnScroll?: boolean;
    zoomOnPinch?: boolean;
    panOnScroll?: boolean;
    panOnDrag?: boolean | number[];
    onPaneClick?: (event: MouseEvent) => void;
    onNodeClick?: (event: MouseEvent, node: Node) => void;
    onEdgeClick?: (event: MouseEvent, edge: Edge) => void;
    onNodeDoubleClick?: (event: MouseEvent, node: Node) => void;
    onNodeMouseEnter?: (event: MouseEvent, node: Node) => void;
    onNodeMouseMove?: (event: MouseEvent, node: Node) => void;
    onNodeMouseLeave?: (event: MouseEvent, node: Node) => void;
    onNodesChange?: (changes: unknown[]) => void;
    onEdgesChange?: (changes: unknown[]) => void;
    onConnect?: (connection: Connection) => void;
    onInit?: (instance: unknown) => void;
    onMove?: (event: MouseEvent | TouchEvent, viewport: { x: number; y: number; zoom: number }) => void;
    onMoveStart?: (event: MouseEvent | TouchEvent, viewport: { x: number; y: number; zoom: number }) => void;
    onMoveEnd?: (event: MouseEvent | TouchEvent, viewport: { x: number; y: number; zoom: number }) => void;
    nodesDraggable?: boolean;
    nodesConnectable?: boolean;
    elementsSelectable?: boolean;
    selectNodesOnDrag?: boolean;
    deleteKeyCode?: string | string[] | null;
    selectionKeyCode?: string | null;
    multiSelectionKeyCode?: string | null;
    zoomActivationKeyCode?: string | null;
    snapToGrid?: boolean;
    snapGrid?: [number, number];
    attributionPosition?: 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right';
    proOptions?: { account?: string; hideAttribution?: boolean };
    style?: React.CSSProperties;
    className?: string;
    children?: React.ReactNode;
  }

  export const ReactFlow: FC<ReactFlowProps>;
  export const Handle: FC<{ type: 'source' | 'target'; position?: 'left' | 'right' | 'top' | 'bottom'; id?: string; style?: React.CSSProperties; isConnectable?: boolean }>;
  export const Position: { Left: 'left'; Top: 'top'; Right: 'right'; Bottom: 'bottom' };

  export function useNodesState(initialNodes?: Node[]): [Node[], (nodes: Node[] | ((prev: Node[]) => Node[])) => void, (changes: unknown[]) => void];
  export function useEdgesState(initialEdges?: Edge[]): [Edge[], (edges: Edge[] | ((prev: Edge[]) => Edge[])) => void, (changes: unknown[]) => void];
  export function useReactFlow(): {
    getNodes: () => Node[];
    getEdges: () => Edge[];
    getNode: (id: string) => Node | undefined;
    getEdge: (id: string) => Edge | undefined;
    setNodes: (nodes: Node[]) => void;
    setEdges: (edges: Edge[]) => void;
    addNodes: (nodes: Node[]) => void;
    addEdges: (edges: Edge[]) => void;
    deleteElements: (payload: { nodes?: Node[]; edges?: Edge[] }) => void;
    fitView: (options?: { padding?: number; includeHiddenNodes?: boolean; minZoom?: number; maxZoom?: number; duration?: number }) => void;
    zoomIn: () => void;
    zoomOut: () => void;
    zoomTo: (level: number) => void;
    project: (position: { x: number; y: number }) => { x: number; y: number };
  };

  export function getIncomers(node: Node, nodes: Node[], edges: Edge[]): Node[];
  export function getOutgoers(node: Node, nodes: Node[], edges: Edge[]): Node[];
  export function isEdge(value: unknown): value is Edge;
  export function isNode(value: unknown): value is Node;

  /* Bezier path helpers */
  export function getBezierPath(params: {
    sourceX: number;
    sourceY: number;
    targetX: number;
    targetY: number;
    sourcePosition?: string;
    targetPosition?: string;
    curvature?: number;
  }): [string, number, number];

  export function getSmoothStepPath(params: {
    sourceX: number;
    sourceY: number;
    targetX: number;
    targetY: number;
    sourcePosition?: string;
    targetPosition?: string;
    borderRadius?: number;
    offset?: number;
  }): [string, number, number];

  export function getSimpleBezierPath(params: {
    sourceX: number;
    sourceY: number;
    targetX: number;
    targetY: number;
    sourcePosition?: string;
    targetPosition?: string;
  }): [string, number, number];

  export function getStraightPath(params: {
    sourceX: number;
    sourceY: number;
    targetX: number;
    targetY: number;
    sourcePosition?: string;
    targetPosition?: string;
  }): [string, number, number];

  /* Edge rendering */
  export const BaseEdge: FC<{
    id?: string;
    path: string;
    markerEnd?: string;
    markerStart?: string;
    style?: React.CSSProperties;
    className?: string;
  }>;

  export const EdgeLabelRenderer: FC<{ children: React.ReactNode }>;
}

declare module '@reactflow/background' {
  import { FC, CSSProperties } from 'react';
  export const Background: FC<{
    color?: string;
    gap?: number;
    size?: number;
    variant?: 'dots' | 'lines' | 'cross';
    style?: CSSProperties;
    className?: string;
  }>;
}

declare module '@reactflow/minimap' {
  import { FC, CSSProperties } from 'react';
  export const MiniMap: FC<{
    nodeStrokeColor?: string | ((node: { id: string; type?: string; data?: Record<string, unknown> }) => string);
    nodeColor?: string | ((node: { id: string; type?: string; data?: Record<string, unknown> }) => string);
    nodeBorderRadius?: number;
    nodeStrokeWidth?: number;
    maskColor?: string;
    maskStrokeColor?: string;
    maskStrokeWidth?: number;
    position?: 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right';
    style?: CSSProperties;
    className?: string;
  }>;
}


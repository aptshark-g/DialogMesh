// Type declarations for react-force-graph-2d
// Minimal types to satisfy TypeScript without the full package types

declare module 'react-force-graph-2d' {
  import type * as React from 'react';

  interface ForceGraphNode {
    id: string;
    [key: string]: unknown;
  }

  interface ForceGraphLink {
    source: string | ForceGraphNode;
    target: string | ForceGraphNode;
    [key: string]: unknown;
  }

  interface ForceGraphProps {
    graphData?: {
      nodes: ForceGraphNode[];
      links: ForceGraphLink[];
    };
    width?: number;
    height?: number;
    backgroundColor?: string;
    nodeLabel?: string | ((node: ForceGraphNode) => string);
    nodeColor?: string | ((node: ForceGraphNode) => string);
    nodeVal?: number | ((node: ForceGraphNode) => number);
    nodeRelSize?: number;
    nodeOpacity?: number;
    nodeResolution?: number;
    nodeVisibility?: boolean | ((node: ForceGraphNode) => boolean);
    nodeCanvasObject?: (
      node: ForceGraphNode,
      ctx: CanvasRenderingContext2D,
      globalScale: number
    ) => void;
    nodeCanvasObjectMode?: string | ((node: ForceGraphNode) => string);
    linkLabel?: string | ((link: ForceGraphLink) => string);
    linkColor?: string | ((link: ForceGraphLink) => string);
    linkWidth?: number | ((link: ForceGraphLink) => number);
    linkOpacity?: number;
    linkDirectionalArrowLength?: number;
    linkDirectionalArrowRelPos?: number;
    linkDirectionalArrowColor?: string | ((link: ForceGraphLink) => string);
    linkDirectionalParticles?: number | ((link: ForceGraphLink) => number);
    linkDirectionalParticleSpeed?: number | ((link: ForceGraphLink) => number);
    linkDirectionalParticleWidth?: number | ((link: ForceGraphLink) => number);
    linkDirectionalParticleColor?: string | ((link: ForceGraphLink) => string);
    linkCurvature?: number | ((link: ForceGraphLink) => number);
    linkVisibility?: boolean | ((link: ForceGraphLink) => boolean);
    linkCanvasObject?: (
      link: ForceGraphLink,
      ctx: CanvasRenderingContext2D,
      globalScale: number
    ) => void;
    warmupTicks?: number;
    cooldownTicks?: number;
    cooldownTime?: number;
    onEngineStop?: () => void;
    onNodeClick?: (node: ForceGraphNode, event: MouseEvent) => void;
    onNodeRightClick?: (node: ForceGraphNode, event: MouseEvent) => void;
    onNodeHover?: (node: ForceGraphNode | null, previousNode: ForceGraphNode | null) => void;
    onNodeDrag?: (node: ForceGraphNode, translate: { x: number; y: number }) => void;
    onNodeDragEnd?: (node: ForceGraphNode, translate: { x: number; y: number }) => void;
    onLinkClick?: (link: ForceGraphLink, event: MouseEvent) => void;
    onLinkRightClick?: (link: ForceGraphLink, event: MouseEvent) => void;
    onLinkHover?: (link: ForceGraphLink | null, previousLink: ForceGraphLink | null) => void;
    onBackgroundClick?: (event: MouseEvent) => void;
    onBackgroundRightClick?: (event: MouseEvent) => void;
    onZoom?: (transform: { k: number; x: number; y: number }) => void;
    onZoomEnd?: (transform: { k: number; x: number; y: number }) => void;
    dagMode?: 'td' | 'bu' | 'lr' | 'rl' | 'radialout' | 'radialin' | null;
    dagLevelDistance?: number;
    d3AlphaMin?: number;
    d3AlphaDecay?: number;
    d3VelocityDecay?: number;
    forceEngine?: 'd3' | 'ngraph';
    ngraphPhysics?: Record<string, unknown>;
    enableZoomPanInteraction?: boolean;
    enableNodeDrag?: boolean;
    enablePointerInteraction?: boolean;
    [key: string]: unknown;
  }

  const ForceGraph2D: React.ComponentType<ForceGraphProps>;
  export default ForceGraph2D;
}

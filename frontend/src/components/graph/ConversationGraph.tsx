import { useCallback, useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import type { GraphNode, GraphEdge } from '@/types/graph';
import { getIntentColor } from '@/types/graph';
import ForceGraph2D from 'react-force-graph-2d';

export interface ConversationGraphProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  searchQuery: string;
  activeFilters: string[];
  selectedNodeId: string | null;
  onNodeClick: (nodeId: string) => void;
  zoomLevel?: number;
  onZoomChange?: (zoom: number) => void;
  className?: string;
}

interface GraphData {
  nodes: Array<{
    id: string;
    label: string;
    type: string;
    intent: string;
    val: number;
    color: string;
    x?: number;
    y?: number;
  }>;
  links: Array<{
    source: string;
    target: string;
    color: string;
  }>;
}

export function ConversationGraph({
  nodes,
  edges,
  searchQuery,
  activeFilters,
  selectedNodeId,
  onNodeClick,
  zoomLevel: _zoomLevel,
  onZoomChange,
  className,
}: ConversationGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });

  // Observe container size
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        setDimensions({ width, height });
      }
    });

    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Build filtered graph data
  const graphData = useCallback((): GraphData => {
    const query = searchQuery.trim().toLowerCase();
    const hasActiveFilters = activeFilters.length > 0;

    const filteredNodes = nodes.filter((node) => {
      const matchesSearch =
        !query ||
        node.label?.toLowerCase().includes(query) ||
        node.id.toLowerCase().includes(query);
      const matchesFilter =
        !hasActiveFilters || activeFilters.includes(node.intent || 'UNKNOWN');
      return matchesSearch && matchesFilter;
    });

    const visibleNodeIds = new Set(filteredNodes.map((n) => n.id));

    const filteredEdges = edges.filter(
      (e) => visibleNodeIds.has(e.source) && visibleNodeIds.has(e.target)
    );

    const graphNodes = filteredNodes.map((node) => {
      const intentColor = getIntentColor(node.intent || 'UNKNOWN');
      const isSelected = node.id === selectedNodeId;
      const isSearchMatch = query && node.label?.toLowerCase().includes(query);

      return {
        id: node.id,
        label: node.label || node.id,
        type: node.type || 'unknown',
        intent: node.intent || 'UNKNOWN',
        val: node.val ?? (node.type === 'cluster' ? 8 : 4),
        color: intentColor.hex,
        x: node.x,
        y: node.y,
        isSelected,
        isSearchMatch,
      };
    });

    const graphLinks = filteredEdges.map((edge) => ({
      source: edge.source,
      target: edge.target,
      color: edge.color || '#3A3548',
    }));

    return { nodes: graphNodes, links: graphLinks };
  }, [nodes, edges, searchQuery, activeFilters, selectedNodeId]);

  const data = graphData();

  // Handle node canvas rendering
  const nodeCanvasObject = useCallback(
    (
      node: {
        id: string;
        label: string;
        type: string;
        intent: string;
        val: number;
        color: string;
        x?: number;
        y?: number;
        isSelected?: boolean;
        isSearchMatch?: boolean;
      },
      ctx: CanvasRenderingContext2D,
      globalScale: number
    ) => {
      const isCluster = node.type === 'cluster';
      const radius = isCluster ? node.val * 4 + 4 : node.val * 3 + 2;

      // Draw selection glow
      if (node.isSelected) {
        ctx.beginPath();
        ctx.arc(node.x ?? 0, node.y ?? 0, radius + 4, 0, 2 * Math.PI);
        ctx.fillStyle = 'rgba(217, 119, 6, 0.2)';
        ctx.fill();
        ctx.strokeStyle = '#D97706';
        ctx.lineWidth = 2;
        ctx.stroke();
      }

      // Draw search highlight
      if (node.isSearchMatch) {
        ctx.beginPath();
        ctx.arc(node.x ?? 0, node.y ?? 0, radius + 6, 0, 2 * Math.PI);
        ctx.strokeStyle = 'rgba(217, 119, 6, 0.6)';
        ctx.lineWidth = 1.5;
        ctx.setLineDash([4, 4]);
        ctx.stroke();
        ctx.setLineDash([]);
      }

      // Draw node body
      if (isCluster) {
        // Cluster: dashed circle
        ctx.beginPath();
        ctx.arc(node.x ?? 0, node.y ?? 0, radius, 0, 2 * Math.PI);
        ctx.strokeStyle = node.color;
        ctx.lineWidth = 1.5;
        ctx.setLineDash([4, 4]);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = `${node.color}10`;
        ctx.fill();
      } else {
        // Regular node: filled circle with border
        ctx.beginPath();
        ctx.arc(node.x ?? 0, node.y ?? 0, radius, 0, 2 * Math.PI);
        ctx.fillStyle = `${node.color}10`;
        ctx.fill();
        ctx.strokeStyle = node.color;
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }

      // Skip label when zoomed out to avoid overlap
      if (globalScale < 0.6) return;

      const fontSize = Math.max(10, 12 / Math.max(0.5, globalScale * 0.5));
      ctx.font = `${isCluster ? '500' : '400'} ${fontSize}px var(--font-sans, sans-serif)`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';

      const maxChars = isCluster ? 10 : 6;
      const displayLabel =
        node.label.length > maxChars
          ? `${node.label.slice(0, maxChars)}…`
          : node.label;

      const textMetrics = ctx.measureText(displayLabel);
      const textWidth = textMetrics.width;
      const paddingX = 6;
      const paddingY = 3;
      const bgWidth = textWidth + paddingX * 2;
      const bgHeight = fontSize + paddingY * 2;
      const labelY = (node.y ?? 0) + radius + fontSize + 2;

      // Draw semi-transparent rounded background
      const bgX = (node.x ?? 0) - bgWidth / 2;
      const bgY = labelY - bgHeight / 2;
      const cornerRadius = 4;

      ctx.beginPath();
      ctx.moveTo(bgX + cornerRadius, bgY);
      ctx.lineTo(bgX + bgWidth - cornerRadius, bgY);
      ctx.arcTo(bgX + bgWidth, bgY, bgX + bgWidth, bgY + cornerRadius, cornerRadius);
      ctx.lineTo(bgX + bgWidth, bgY + bgHeight - cornerRadius);
      ctx.arcTo(bgX + bgWidth, bgY + bgHeight, bgX + bgWidth - cornerRadius, bgY + bgHeight, cornerRadius);
      ctx.lineTo(bgX + cornerRadius, bgY + bgHeight);
      ctx.arcTo(bgX, bgY + bgHeight, bgX, bgY + bgHeight - cornerRadius, cornerRadius);
      ctx.lineTo(bgX, bgY + cornerRadius);
      ctx.arcTo(bgX, bgY, bgX + cornerRadius, bgY, cornerRadius);
      ctx.closePath();
      ctx.fillStyle = 'rgba(255, 255, 255, 0.15)';
      ctx.fill();
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.25)';
      ctx.lineWidth = 1;
      ctx.stroke();

      // Draw label text
      ctx.fillStyle = isCluster ? '#6B6680' : '#E8E6F0';
      ctx.fillText(displayLabel, node.x ?? 0, labelY);
    },
    []
  );

  // Handle node click
  const handleNodeClick = useCallback(
    (node: { id: string }) => {
      onNodeClick(node.id);
    },
    [onNodeClick]
  );

  // Handle zoom
  const handleZoom = useCallback(
    (transform: { k: number }) => {
      onZoomChange?.(transform.k);
    },
    [onZoomChange]
  );

  return (
    <div
      ref={containerRef}
      className={cn('relative w-full h-full overflow-hidden', className)}
    >
      {data.nodes.length > 0 ? (
        <ForceGraph2D
          graphData={data}
          width={dimensions.width}
          height={dimensions.height}
          backgroundColor="transparent"
          nodeRelSize={4}
          nodeCanvasObject={nodeCanvasObject as unknown as (
            node: Record<string, unknown>,
            ctx: CanvasRenderingContext2D,
            globalScale: number
          ) => void}
          nodeCanvasObjectMode={() => 'replace'}
          linkColor={() => '#3A3548'}
          linkWidth={1}
          linkDirectionalArrowLength={4}
          linkDirectionalArrowRelPos={1}
          linkDirectionalArrowColor={() => '#3A3548'}
          onNodeClick={handleNodeClick as unknown as (
            node: Record<string, unknown>,
            event: MouseEvent
          ) => void}
          onZoom={handleZoom}
          enableZoomPanInteraction
          enableNodeDrag
          warmupTicks={30}
          cooldownTicks={100}
          d3VelocityDecay={0.3}
          d3AlphaMin={0.01}
          linkDistance={100}
        />
      ) : (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="text-center">
            <p className="text-text-muted text-sm">暂无节点数据</p>
            <p className="text-text-muted text-xs mt-1">
              尝试调整过滤器或搜索条件
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

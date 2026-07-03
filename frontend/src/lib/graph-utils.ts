// FILE: src/lib/graph-utils.ts

import type {
  GraphNode,
  GraphEdge,
  ClusterNode,
  ViewMode,
} from '../types/graph';

// ==================== 邻接表构建 ====================

export type AdjacencyList = Map<string, Set<string>>;
export type WeightedAdjacencyList = Map<string, Map<string, number>>;

export function buildAdjacencyList(
  nodes: GraphNode[],
  edges: GraphEdge[],
  directed = true
): AdjacencyList {
  const adj = new Map<string, Set<string>>();
  for (const node of nodes) {
    adj.set(node.id, new Set());
  }
  for (const edge of edges) {
    adj.get(edge.source)?.add(edge.target);
    if (!directed) {
      adj.get(edge.target)?.add(edge.source);
    }
  }
  return adj;
}

export function buildWeightedAdjacencyList(
  nodes: GraphNode[],
  edges: GraphEdge[],
  directed = true
): WeightedAdjacencyList {
  const adj = new Map<string, Map<string, number>>();
  for (const node of nodes) {
    adj.set(node.id, new Map());
  }
  for (const edge of edges) {
    const w = edge.weight ?? 1;
    adj.get(edge.source)?.set(edge.target, w);
    if (!directed) {
      adj.get(edge.target)?.set(edge.source, w);
    }
  }
  return adj;
}

export function buildReverseAdjacencyList(
  nodes: GraphNode[],
  edges: GraphEdge[]
): AdjacencyList {
  const adj = new Map<string, Set<string>>();
  for (const node of nodes) {
    adj.set(node.id, new Set());
  }
  for (const edge of edges) {
    adj.get(edge.target)?.add(edge.source);
  }
  return adj;
}

// ==================== 遍历算法 ====================

export type TraversalOrder = 'pre' | 'post';

export function bfs(
  nodes: GraphNode[],
  edges: GraphEdge[],
  startId: string,
  directed = true
): string[] {
  const adj = buildAdjacencyList(nodes, edges, directed);
  const visited = new Set<string>();
  const queue: string[] = [];
  const result: string[] = [];

  if (adj.has(startId)) {
    queue.push(startId);
    visited.add(startId);
  }

  while (queue.length > 0) {
    const curr = queue.shift()!;
    result.push(curr);
    const neighbors = adj.get(curr) ?? new Set();
    for (const n of neighbors) {
      if (!visited.has(n)) {
        visited.add(n);
        queue.push(n);
      }
    }
  }
  return result;
}

export function dfs(
  nodes: GraphNode[],
  edges: GraphEdge[],
  startId: string,
  directed = true
): string[] {
  const adj = buildAdjacencyList(nodes, edges, directed);
  const visited = new Set<string>();
  const result: string[] = [];

  function visit(nodeId: string): void {
    if (visited.has(nodeId)) return;
    visited.add(nodeId);
    result.push(nodeId);
    const neighbors = adj.get(nodeId) ?? new Set();
    for (const n of neighbors) {
      visit(n);
    }
  }

  if (adj.has(startId)) {
    visit(startId);
  }
  return result;
}

export function dfsPostOrder(
  nodes: GraphNode[],
  edges: GraphEdge[],
  startId: string,
  directed = true
): string[] {
  const adj = buildAdjacencyList(nodes, edges, directed);
  const visited = new Set<string>();
  const result: string[] = [];

  function visit(nodeId: string): void {
    if (visited.has(nodeId)) return;
    visited.add(nodeId);
    const neighbors = adj.get(nodeId) ?? new Set();
    for (const n of neighbors) {
      visit(n);
    }
    result.push(nodeId);
  }

  if (adj.has(startId)) {
    visit(startId);
  }
  return result;
}

// ==================== 路径与连通性 ====================

export function shortestPath(
  nodes: GraphNode[],
  edges: GraphEdge[],
  sourceId: string,
  targetId: string,
  directed = true
): string[] | null {
  const adj = buildAdjacencyList(nodes, edges, directed);
  if (!adj.has(sourceId) || !adj.has(targetId)) return null;

  const visited = new Set<string>();
  const parent = new Map<string, string>();
  const queue: string[] = [sourceId];
  visited.add(sourceId);

  while (queue.length > 0) {
    const curr = queue.shift()!;
    if (curr === targetId) break;
    const neighbors = adj.get(curr) ?? new Set();
    for (const n of neighbors) {
      if (!visited.has(n)) {
        visited.add(n);
        parent.set(n, curr);
        queue.push(n);
      }
    }
  }

  if (!visited.has(targetId)) return null;

  const path: string[] = [];
  let curr: string = targetId;
  while (curr !== sourceId) {
    path.unshift(curr);
    const p = parent.get(curr);
    if (p === undefined) return null;
    curr = p;
  }
  path.unshift(sourceId);
  return path;
}

export function allPaths(
  nodes: GraphNode[],
  edges: GraphEdge[],
  sourceId: string,
  targetId: string,
  directed = true,
  maxDepth = 10
): string[][] {
  const adj = buildAdjacencyList(nodes, edges, directed);
  if (!adj.has(sourceId) || !adj.has(targetId)) return [];

  const paths: string[][] = [];
  const path: string[] = [sourceId];
  const visited = new Set<string>([sourceId]);

  function backtrack(nodeId: string, depth: number): void {
    if (nodeId === targetId) {
      paths.push([...path]);
      return;
    }
    if (depth >= maxDepth) return;
    const neighbors = adj.get(nodeId) ?? new Set();
    for (const n of neighbors) {
      if (!visited.has(n)) {
        visited.add(n);
        path.push(n);
        backtrack(n, depth + 1);
        path.pop();
        visited.delete(n);
      }
    }
  }

  backtrack(sourceId, 0);
  return paths;
}

export function findConnectedComponents(
  nodes: GraphNode[],
  edges: GraphEdge[]
): string[][] {
  const adj = buildAdjacencyList(nodes, edges, false);
  const visited = new Set<string>();
  const components: string[][] = [];

  for (const node of nodes) {
    if (!visited.has(node.id)) {
      const comp: string[] = [];
      const stack: string[] = [node.id];
      visited.add(node.id);
      while (stack.length > 0) {
        const curr = stack.pop()!;
        comp.push(curr);
        const neighbors = adj.get(curr) ?? new Set();
        for (const n of neighbors) {
          if (!visited.has(n)) {
            visited.add(n);
            stack.push(n);
          }
        }
      }
      components.push(comp);
    }
  }
  return components;
}

// ==================== 拓扑排序 ====================

export function topologicalSort(
  nodes: GraphNode[],
  edges: GraphEdge[]
): string[] | null {
  const inDegree = new Map<string, number>();
  for (const node of nodes) {
    inDegree.set(node.id, 0);
  }
  for (const edge of edges) {
    inDegree.set(edge.target, (inDegree.get(edge.target) ?? 0) + 1);
  }

  const queue: string[] = [];
  for (const [id, deg] of inDegree) {
    if (deg === 0) queue.push(id);
  }

  const result: string[] = [];
  const adj = buildAdjacencyList(nodes, edges, true);

  while (queue.length > 0) {
    const curr = queue.shift()!;
    result.push(curr);
    const neighbors = adj.get(curr) ?? new Set();
    for (const n of neighbors) {
      const newDeg = (inDegree.get(n) ?? 0) - 1;
      inDegree.set(n, newDeg);
      if (newDeg === 0) {
        queue.push(n);
      }
    }
  }

  if (result.length !== nodes.length) return null;
  return result;
}

// ==================== 节点与边查询 ====================

export function getNeighbors(
  _nodes: GraphNode[],
  edges: GraphEdge[],
  nodeId: string,
  directed = true
): { inbound: string[]; outbound: string[] } {
  const inbound: string[] = [];
  const outbound: string[] = [];
  for (const edge of edges) {
    if (edge.source === nodeId) {
      outbound.push(edge.target);
    }
    if (edge.target === nodeId) {
      inbound.push(edge.source);
    }
  }
  if (!directed) {
    const all = new Set([...inbound, ...outbound]);
    return { inbound: [...all], outbound: [...all] };
  }
  return { inbound, outbound };
}

export function getDegree(
  _nodes: GraphNode[],
  edges: GraphEdge[],
  nodeId: string,
  directed = true
): { inDegree: number; outDegree: number; total: number } {
  let inDegree = 0;
  let outDegree = 0;
  for (const edge of edges) {
    if (edge.source === nodeId) outDegree++;
    if (edge.target === nodeId) inDegree++;
  }
  if (!directed) {
    return { inDegree: outDegree + inDegree, outDegree: outDegree + inDegree, total: outDegree + inDegree };
  }
  return { inDegree, outDegree, total: inDegree + outDegree };
}

export function getEdgesForNode(
  edges: GraphEdge[],
  nodeId: string
): GraphEdge[] {
  return edges.filter((e) => e.source === nodeId || e.target === nodeId);
}

export function getEdgesBetween(
  edges: GraphEdge[],
  sourceId: string,
  targetId: string
): GraphEdge[] {
  return edges.filter(
    (e) => e.source === sourceId && e.target === targetId
  );
}

export function getNodeById(
  nodes: GraphNode[],
  nodeId: string
): GraphNode | undefined {
  return nodes.find((n) => n.id === nodeId);
}

export function getNodesByType(
  nodes: GraphNode[],
  type: string
): GraphNode[] {
  return nodes.filter((n) => n.type === type);
}

export function getNodesByIntent(
  nodes: GraphNode[],
  intent: string
): GraphNode[] {
  return nodes.filter((n) => n.intent === intent);
}

export function getNodesByCluster(
  nodes: GraphNode[],
  cluster: string
): GraphNode[] {
  return nodes.filter((n) => n.cluster === cluster);
}

// ==================== 过滤与搜索 ====================

export interface GraphFilterOptions {
  nodeTypes?: string[];
  edgeTypes?: GraphEdge['type'][];
  intents?: string[];
  clusters?: string[];
  searchQuery?: string;
  minWeight?: number;
  maxWeight?: number;
}

export function filterGraph(
  nodes: GraphNode[],
  edges: GraphEdge[],
  options: GraphFilterOptions
): { nodes: GraphNode[]; edges: GraphEdge[] } {
  let filteredNodes = [...nodes];
  let filteredEdges = [...edges];

  if (options.nodeTypes && options.nodeTypes.length > 0) {
    filteredNodes = filteredNodes.filter((n) =>
      n.type ? options.nodeTypes!.includes(n.type) : false
    );
  }

  if (options.intents && options.intents.length > 0) {
    filteredNodes = filteredNodes.filter((n) =>
      n.intent ? options.intents!.includes(n.intent) : false
    );
  }

  if (options.clusters && options.clusters.length > 0) {
    filteredNodes = filteredNodes.filter((n) =>
      n.cluster ? options.clusters!.includes(n.cluster) : false
    );
  }

  if (options.searchQuery && options.searchQuery.trim().length > 0) {
    const q = options.searchQuery.toLowerCase().trim();
    filteredNodes = filteredNodes.filter(
      (n) =>
        n.label.toLowerCase().includes(q) ||
        (n.description?.toLowerCase().includes(q) ?? false) ||
        (n.id.toLowerCase().includes(q) ?? false)
    );
  }

  if (options.edgeTypes && options.edgeTypes.length > 0) {
    filteredEdges = filteredEdges.filter((e) =>
      e.type ? options.edgeTypes!.includes(e.type) : false
    );
  }

  if (options.minWeight !== undefined) {
    filteredEdges = filteredEdges.filter(
      (e) => (e.weight ?? 1) >= options.minWeight!
    );
  }

  if (options.maxWeight !== undefined) {
    filteredEdges = filteredEdges.filter(
      (e) => (e.weight ?? 1) <= options.maxWeight!
    );
  }

  const nodeIds = new Set(filteredNodes.map((n) => n.id));
  filteredEdges = filteredEdges.filter(
    (e) => nodeIds.has(e.source) && nodeIds.has(e.target)
  );

  return { nodes: filteredNodes, edges: filteredEdges };
}

export function searchNodes(
  nodes: GraphNode[],
  query: string
): GraphNode[] {
  if (!query || query.trim().length === 0) return nodes;
  const q = query.toLowerCase().trim();
  return nodes.filter(
    (n) =>
      n.label.toLowerCase().includes(q) ||
      (n.description?.toLowerCase().includes(q) ?? false) ||
      (n.id.toLowerCase().includes(q) ?? false) ||
      (n.type?.toLowerCase().includes(q) ?? false) ||
      (n.intent?.toLowerCase().includes(q) ?? false)
  );
}

// ==================== 布局计算 ====================

export interface LayoutConfig {
  width: number;
  height: number;
  nodeRadius?: number;
  padding?: number;
}

export function computeTreeLayout(
  nodes: GraphNode[],
  edges: GraphEdge[],
  config: LayoutConfig
): Map<string, { x: number; y: number }> {
  const positions = new Map<string, { x: number; y: number }>();
  const rev = buildReverseAdjacencyList(nodes, edges);

  const padding = config.padding ?? 40;
  const availableWidth = config.width - padding * 2;
  const availableHeight = config.height - padding * 2;

  function getDepth(nodeId: string, visited = new Set<string>()): number {
    if (visited.has(nodeId)) return 0;
    visited.add(nodeId);
    const parents = rev.get(nodeId) ?? new Set();
    if (parents.size === 0) return 0;
    let maxParentDepth = 0;
    for (const p of parents) {
      maxParentDepth = Math.max(maxParentDepth, getDepth(p, new Set(visited)));
    }
    return maxParentDepth + 1;
  }

  const depthMap = new Map<string, number>();
  for (const node of nodes) {
    depthMap.set(node.id, getDepth(node.id));
  }

  const maxDepth = Math.max(0, ...depthMap.values());
  const levelHeight = maxDepth > 0 ? availableHeight / (maxDepth + 1) : availableHeight;

  const nodesByLevel = new Map<number, string[]>();
  for (const [id, d] of depthMap) {
    const arr = nodesByLevel.get(d) ?? [];
    arr.push(id);
    nodesByLevel.set(d, arr);
  }

  for (const [level, nodeIds] of nodesByLevel) {
    const step = nodeIds.length > 1 ? availableWidth / (nodeIds.length - 1) : 0;
    for (let i = 0; i < nodeIds.length; i++) {
      const x = nodeIds.length > 1 ? padding + i * step : config.width / 2;
      const y = padding + level * levelHeight;
      positions.set(nodeIds[i], { x, y });
    }
  }

  return positions;
}

export function computeTimelineLayout(
  nodes: GraphNode[],
  config: LayoutConfig
): Map<string, { x: number; y: number }> {
  const positions = new Map<string, { x: number; y: number }>();
  const padding = config.padding ?? 40;
  const availableWidth = config.width - padding * 2;

  const sorted = [...nodes].filter((n) => n.timestamp).sort((a, b) => {
    const ta = a.timestamp ? new Date(a.timestamp).getTime() : 0;
    const tb = b.timestamp ? new Date(b.timestamp).getTime() : 0;
    return ta - tb;
  });

  if (sorted.length === 0) return positions;

  const minTime = sorted[0].timestamp
    ? new Date(sorted[0].timestamp).getTime()
    : 0;
  const lastTimestamp = sorted[sorted.length - 1].timestamp;
  const maxTime = lastTimestamp
    ? new Date(lastTimestamp).getTime()
    : minTime;
  const timeRange = Math.max(1, maxTime - minTime);

  for (const node of sorted) {
    const t = node.timestamp ? new Date(node.timestamp).getTime() : minTime;
    const x = padding + ((t - minTime) / timeRange) * availableWidth;
    const y = config.height / 2 + (Math.random() - 0.5) * (config.height * 0.3);
    positions.set(node.id, { x, y });
  }

  for (const node of nodes) {
    if (!positions.has(node.id)) {
      positions.set(node.id, { x: config.width / 2, y: config.height / 2 });
    }
  }

  return positions;
}

export function computeForceLayout(
  nodes: GraphNode[],
  edges: GraphEdge[],
  config: LayoutConfig,
  iterations = 100
): Map<string, { x: number; y: number }> {
  const positions = new Map<string, { x: number; y: number }>();
  const width = config.width;
  const height = config.height;
  const padding = config.padding ?? 40;

  for (const node of nodes) {
    if (node.x !== undefined && node.y !== undefined) {
      positions.set(node.id, { x: node.x, y: node.y });
    } else {
      positions.set(node.id, {
        x: padding + Math.random() * (width - padding * 2),
        y: padding + Math.random() * (height - padding * 2),
      });
    }
  }

  const k = Math.sqrt((width * height) / Math.max(1, nodes.length)) * 0.5;
  const temperature = width / 10;
  const cooling = temperature / iterations;

  for (let iter = 0; iter < iterations; iter++) {
    const forces = new Map<string, { fx: number; fy: number }>();
    for (const node of nodes) {
      forces.set(node.id, { fx: 0, fy: 0 });
    }

    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i];
        const b = nodes[j];
        const posA = positions.get(a.id)!;
        const posB = positions.get(b.id)!;
        const dx = posA.x - posB.x;
        const dy = posA.y - posB.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const force = (k * k) / dist;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        const fa = forces.get(a.id)!;
        const fb = forces.get(b.id)!;
        fa.fx += fx;
        fa.fy += fy;
        fb.fx -= fx;
        fb.fy -= fy;
      }
    }

    for (const edge of edges) {
      const posA = positions.get(edge.source);
      const posB = positions.get(edge.target);
      if (!posA || !posB) continue;
      const dx = posB.x - posA.x;
      const dy = posB.y - posA.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const force = (dist * dist) / k;
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;
      const fa = forces.get(edge.source)!;
      const fb = forces.get(edge.target)!;
      fa.fx += fx;
      fa.fy += fy;
      fb.fx -= fx;
      fb.fy -= fy;
    }

    const temp = temperature - iter * cooling;
    for (const node of nodes) {
      const pos = positions.get(node.id)!;
      const f = forces.get(node.id)!;
      const disp = Math.sqrt(f.fx * f.fx + f.fy * f.fy) || 1;
      const dx = (f.fx / disp) * Math.min(disp, temp);
      const dy = (f.fy / disp) * Math.min(disp, temp);
      pos.x = Math.max(padding, Math.min(width - padding, pos.x + dx));
      pos.y = Math.max(padding, Math.min(height - padding, pos.y + dy));
    }
  }

  return positions;
}

export function computeLayout(
  nodes: GraphNode[],
  edges: GraphEdge[],
  viewMode: ViewMode,
  config: LayoutConfig
): Map<string, { x: number; y: number }> {
  switch (viewMode) {
    case 'tree':
      return computeTreeLayout(nodes, edges, config);
    case 'timeline':
      return computeTimelineLayout(nodes, config);
    case 'force':
    default:
      return computeForceLayout(nodes, edges, config);
  }
}

// ==================== 聚类 ====================

export function clusterByField(
  nodes: GraphNode[],
  field: 'type' | 'intent' | 'cluster'
): Map<string, GraphNode[]> {
  const clusters = new Map<string, GraphNode[]>();
  for (const node of nodes) {
    const key = node[field] ?? 'unknown';
    const arr = clusters.get(key) ?? [];
    arr.push(node);
    clusters.set(key, arr);
  }
  return clusters;
}

export function computeClusterNodes(
  nodes: GraphNode[],
  edges: GraphEdge[],
  positions: Map<string, { x: number; y: number }>
): ClusterNode[] {
  const clusters = clusterByField(nodes, 'cluster');
  const clusterList: ClusterNode[] = [];

  for (const [clusterId, clusterNodes] of clusters) {
    if (clusterNodes.length === 0) continue;

    let sumX = 0;
    let sumY = 0;
    for (const node of clusterNodes) {
      const pos = positions.get(node.id);
      sumX += pos?.x ?? 0;
      sumY += pos?.y ?? 0;
    }

    const centerX = sumX / clusterNodes.length;
    const centerY = sumY / clusterNodes.length;

    const topics = [
      ...new Set(clusterNodes.map((n) => n.type).filter(Boolean)),
    ];

    const clusterNodeIds = new Set(clusterNodes.map((n) => n.id));
    let internalEdges = 0;
    for (const edge of edges) {
      if (clusterNodeIds.has(edge.source) && clusterNodeIds.has(edge.target)) {
        internalEdges++;
      }
    }
    const maxEdges = clusterNodes.length * (clusterNodes.length - 1);
    const density = maxEdges > 0 ? internalEdges / maxEdges : 0;

    clusterList.push({
      id: clusterId,
      label: clusterId,
      nodeCount: clusterNodes.length,
      centerX,
      centerY,
      color: clusterNodes[0]?.color ?? '#6B6680',
      density,
      topics: topics as string[],
    });
  }

  return clusterList;
}

// ==================== 图统计 ====================

export interface GraphStats {
  nodeCount: number;
  edgeCount: number;
  density: number;
  averageDegree: number;
  connectedComponents: number;
  diameter: number;
}

export function computeGraphStats(
  nodes: GraphNode[],
  edges: GraphEdge[]
): GraphStats {
  const nodeCount = nodes.length;
  const edgeCount = edges.length;
  const density =
    nodeCount > 1 ? edgeCount / (nodeCount * (nodeCount - 1)) : 0;

  let totalDegree = 0;
  for (const node of nodes) {
    const deg = getDegree(nodes, edges, node.id, false);
    totalDegree += deg.total;
  }
  const averageDegree = nodeCount > 0 ? totalDegree / nodeCount : 0;

  const components = findConnectedComponents(nodes, edges);
  const connectedComponents = components.length;

  let diameter = 0;
  for (const comp of components) {
    for (const source of comp) {
      for (const target of comp) {
        if (source === target) continue;
        const path = shortestPath(nodes, edges, source, target, false);
        if (path) {
          diameter = Math.max(diameter, path.length - 1);
        }
      }
    }
  }

  return {
    nodeCount,
    edgeCount,
    density,
    averageDegree,
    connectedComponents,
    diameter,
  };
}

export function computeBetweennessCentrality(
  nodes: GraphNode[],
  edges: GraphEdge[]
): Map<string, number> {
  const centrality = new Map<string, number>();
  for (const node of nodes) {
    centrality.set(node.id, 0);
  }

  const adj = buildAdjacencyList(nodes, edges, false);

  for (const source of nodes) {
    const dist = new Map<string, number>();
    const paths = new Map<string, number>();
    const pred = new Map<string, string[]>();
    const stack: string[] = [];
    const queue: string[] = [];

    for (const node of nodes) {
      dist.set(node.id, -1);
      paths.set(node.id, 0);
      pred.set(node.id, []);
    }
    dist.set(source.id, 0);
    paths.set(source.id, 1);
    queue.push(source.id);

    while (queue.length > 0) {
      const v = queue.shift()!;
      stack.push(v);
      const neighbors = adj.get(v) ?? new Set();
      for (const w of neighbors) {
        if (dist.get(w) === -1) {
          dist.set(w, (dist.get(v) ?? 0) + 1);
          queue.push(w);
        }
        if ((dist.get(w) ?? 0) === (dist.get(v) ?? 0) + 1) {
          paths.set(w, (paths.get(w) ?? 0) + (paths.get(v) ?? 0));
          const p = pred.get(w) ?? [];
          p.push(v);
          pred.set(w, p);
        }
      }
    }

    const delta = new Map<string, number>();
    for (const node of nodes) {
      delta.set(node.id, 0);
    }
    while (stack.length > 0) {
      const w = stack.pop()!;
      for (const v of pred.get(w) ?? []) {
        delta.set(
          v,
          (delta.get(v) ?? 0) +
            ((paths.get(v) ?? 0) / (paths.get(w) ?? 1)) *
              (1 + (delta.get(w) ?? 0))
        );
      }
      if (w !== source.id) {
        centrality.set(w, (centrality.get(w) ?? 0) + (delta.get(w) ?? 0));
      }
    }
  }

  return centrality;
}

// ==================== 验证 ====================

export interface GraphValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
}

export function validateGraph(
  nodes: GraphNode[],
  edges: GraphEdge[]
): GraphValidationResult {
  const errors: string[] = [];
  const warnings: string[] = [];

  const ids = new Set<string>();
  const duplicates = new Set<string>();
  for (const node of nodes) {
    if (ids.has(node.id)) {
      duplicates.add(node.id);
    } else {
      ids.add(node.id);
    }
  }
  if (duplicates.size > 0) {
    errors.push(`Duplicate node IDs: ${[...duplicates].join(', ')}`);
  }

  const edgeIds = new Set<string>();
  const dupEdgeIds = new Set<string>();
  for (const edge of edges) {
    if (edgeIds.has(edge.id)) {
      dupEdgeIds.add(edge.id);
    } else {
      edgeIds.add(edge.id);
    }
  }
  if (dupEdgeIds.size > 0) {
    errors.push(`Duplicate edge IDs: ${[...dupEdgeIds].join(', ')}`);
  }

  const danglingEdges: string[] = [];
  for (const edge of edges) {
    if (!ids.has(edge.source)) {
      danglingEdges.push(edge.source);
    }
    if (!ids.has(edge.target)) {
      danglingEdges.push(edge.target);
    }
  }
  if (danglingEdges.length > 0) {
    errors.push(
      `Dangling edge references to non-existent nodes: ${[...new Set(danglingEdges)].join(', ')}`
    );
  }

  if (nodes.length === 0) {
    warnings.push('Graph contains no nodes');
  }
  if (edges.length > 0 && nodes.length === 0) {
    errors.push('Edges exist but no nodes are defined');
  }

  return {
    valid: errors.length === 0,
    errors,
    warnings,
  };
}

// ==================== 转换与序列化 ====================

export interface SerializedGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  metadata?: {
    version: string;
    exportedAt: string;
  };
}

export function serializeGraph(
  nodes: GraphNode[],
  edges: GraphEdge[]
): SerializedGraph {
  return {
    nodes: [...nodes],
    edges: [...edges],
    metadata: {
      version: '1.0',
      exportedAt: new Date().toISOString(),
    },
  };
}

export function deserializeGraph(data: SerializedGraph): {
  nodes: GraphNode[];
  edges: GraphEdge[];
} {
  return {
    nodes: data.nodes ?? [],
    edges: data.edges ?? [],
  };
}

export function graphToAdjacencyMatrix(
  nodes: GraphNode[],
  edges: GraphEdge[]
): { nodeIds: string[]; matrix: number[][] } {
  const nodeIds = nodes.map((n) => n.id);
  const indexMap = new Map(nodeIds.map((id, i) => [id, i]));
  const n = nodeIds.length;
  const matrix: number[][] = Array.from({ length: n }, () =>
    Array.from({ length: n }, () => 0)
  );
  for (const edge of edges) {
    const si = indexMap.get(edge.source);
    const ti = indexMap.get(edge.target);
    if (si !== undefined && ti !== undefined) {
      matrix[si][ti] = edge.weight ?? 1;
    }
  }
  return { nodeIds, matrix };
}

export function graphToDot(
  nodes: GraphNode[],
  edges: GraphEdge[],
  directed = true
): string {
  const type = directed ? 'digraph' : 'graph';
  const arrow = directed ? '->' : '--';
  const lines = [`${type} G {`];

  for (const node of nodes) {
    const label = node.label.replace(/"/g, '\\"');
    lines.push(`  "${node.id}" [label="${label}"];`);
  }

  for (const edge of edges) {
    const label = edge.label ? ` [label="${edge.label.replace(/"/g, '\\"')}"]` : '';
    lines.push(`  "${edge.source}" ${arrow} "${edge.target}"${label};`);
  }

  lines.push('}');
  return lines.join('\n');
}

export function graphToCytoscapeElements(
  nodes: GraphNode[],
  edges: GraphEdge[]
): Array<
  | { data: { id: string; label: string; [key: string]: unknown } }
  | { data: { id: string; source: string; target: string; [key: string]: unknown } }
> {
  const elements: Array<
    | { data: { id: string; label: string; [key: string]: unknown } }
    | { data: { id: string; source: string; target: string; [key: string]: unknown } }
  > = [];

  for (const node of nodes) {
    elements.push({
      data: {
        id: node.id,
        label: node.label,
        ...node.metadata,
      },
    });
  }

  for (const edge of edges) {
    elements.push({
      data: {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        label: edge.label,
      },
    });
  }

  return elements;
}

// ==================== 辅助函数 ====================

export function getSubgraph(
  nodes: GraphNode[],
  edges: GraphEdge[],
  nodeIds: string[]
): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const idSet = new Set(nodeIds);
  const filteredNodes = nodes.filter((n) => idSet.has(n.id));
  const filteredEdges = edges.filter(
    (e) => idSet.has(e.source) && idSet.has(e.target)
  );
  return { nodes: filteredNodes, edges: filteredEdges };
}

export function mergeGraphs(
  ...graphs: { nodes: GraphNode[]; edges: GraphEdge[] }[]
): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const nodeMap = new Map<string, GraphNode>();
  const edgeMap = new Map<string, GraphEdge>();

  for (const graph of graphs) {
    for (const node of graph.nodes) {
      nodeMap.set(node.id, node);
    }
    for (const edge of graph.edges) {
      edgeMap.set(edge.id, edge);
    }
  }

  return {
    nodes: [...nodeMap.values()],
    edges: [...edgeMap.values()],
  };
}

export function invertEdgeDirections(edges: GraphEdge[]): GraphEdge[] {
  return edges.map((e) => ({
    ...e,
    source: e.target,
    target: e.source,
  }));
}

export function deduplicateEdges(edges: GraphEdge[]): GraphEdge[] {
  const seen = new Set<string>();
  return edges.filter((e) => {
    const key = `${e.source}|${e.target}|${e.type ?? 'default'}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function createEdgeId(source: string, target: string): string {
  return `edge_${source}_${target}_${Math.random().toString(36).slice(2, 8)}`;
}

export function estimateGraphComplexity(
  nodes: GraphNode[],
  edges: GraphEdge[]
): 'trivial' | 'simple' | 'moderate' | 'complex' {
  const n = nodes.length;
  const e = edges.length;
  if (n <= 5 && e <= 5) return 'trivial';
  if (n <= 20 && e <= 30) return 'simple';
  if (n <= 100 && e <= 200) return 'moderate';
  return 'complex';
}

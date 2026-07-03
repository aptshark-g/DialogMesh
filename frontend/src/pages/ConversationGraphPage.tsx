import { useState, useCallback, useMemo, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { GraphToolbar, GraphLegend, ConversationGraph } from '@/components/graph';
import { useGraphStore } from '@/stores/graphStore';
import type { GraphNode, GraphEdge, ViewMode } from '@/types/graph';
import { getIntentColor } from '@/types/graph';
import { formatTimestamp } from '@/lib/utils';
import { RefreshCw, Info } from 'lucide-react';
import { Tooltip } from '@/components/ui/Tooltip';

// ==================== Mock Data ====================

const MOCK_NODES: GraphNode[] = [
  { id: 'turn_1', label: '如何设计记忆存储', type: 'ai', intent: 'EXPLAIN', x: 0, y: 0 },
  { id: 'turn_2', label: '存储设计需要考虑', type: 'ai', intent: 'SCAN_MEMORY', x: 50, y: -30 },
  { id: 'turn_3', label: '记忆冲突如何解决', type: 'ai', intent: 'READ_MEMORY', x: 100, y: 0 },
  { id: 'turn_4', label: '短期记忆用于当前', type: 'ai', intent: 'WRITE_MEMORY', x: 150, y: -30 },
  { id: 'turn_5', label: '能否修改某个值', type: 'ai', intent: 'HACK_VALUE', x: 80, y: 50 },
  { id: 'turn_6', label: '提供代码示例', type: 'ai', intent: 'PROVIDE_CODE', x: 120, y: 60 },
  { id: 'turn_7', label: '冲突解决相关', type: 'cluster', intent: 'UNKNOWN', x: 60, y: -60 },
  { id: 'turn_8', label: '记忆类型对比', type: 'cluster', intent: 'UNKNOWN', x: 140, y: -60 },
  { id: 'turn_9', label: '检索增强方案', type: 'ai', intent: 'EXPLAIN', x: 20, y: 40 },
  { id: 'turn_10', label: '向量数据库选型', type: 'ai', intent: 'SCAN_MEMORY', x: 60, y: 30 },
];

const MOCK_EDGES: GraphEdge[] = [
  { id: 'e1', source: 'turn_1', target: 'turn_2', type: 'dependency' },
  { id: 'e2', source: 'turn_2', target: 'turn_3', type: 'causal' },
  { id: 'e3', source: 'turn_3', target: 'turn_4', type: 'dependency' },
  { id: 'e4', source: 'turn_1', target: 'turn_5', type: 'similarity' },
  { id: 'e5', source: 'turn_5', target: 'turn_6', type: 'causal' },
  { id: 'e6', source: 'turn_2', target: 'turn_7', type: 'hierarchical' },
  { id: 'e7', source: 'turn_4', target: 'turn_8', type: 'hierarchical' },
  { id: 'e8', source: 'turn_1', target: 'turn_9', type: 'reference' },
  { id: 'e9', source: 'turn_9', target: 'turn_10', type: 'dependency' },
];

// ==================== Component ====================

export function ConversationGraphPage() {
  const navigate = useNavigate();

  // Local state for graph page
  const [searchQuery, setSearchQuery] = useState('');
  const [activeFilters, setActiveFilters] = useState<string[]>([]);
  const [viewMode, setViewMode] = useState<ViewMode>('force');
  const [zoomLevel, setZoomLevel] = useState(1);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [legendVisible, setLegendVisible] = useState(true);
  const [lastUpdated, setLastUpdated] = useState(new Date());

  // Use graph store for nodes/edges (initialize with mock data)
  const graphStore = useGraphStore();

  useEffect(() => {
    graphStore.setNodes(MOCK_NODES);
    graphStore.setEdges(MOCK_EDGES);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const nodes = graphStore.nodes;
  const edges = graphStore.edges;

  // Derived: node counts by intent
  const nodeCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const node of nodes) {
      const intent = node.intent || 'UNKNOWN';
      counts[intent] = (counts[intent] || 0) + 1;
    }
    return counts;
  }, [nodes]);

  // Derived: filtered node count
  const filteredNodeCount = useMemo(() => {
    const hasQuery = searchQuery.trim().length > 0;
    const hasFilters = activeFilters.length > 0;
    if (!hasQuery && !hasFilters) return nodes.length;

    const query = searchQuery.trim().toLowerCase();
    return nodes.filter((n) => {
      const matchesQuery = !hasQuery || (n.label?.toLowerCase().includes(query) ?? false);
      const matchesFilter = !hasFilters || activeFilters.includes(n.intent || 'UNKNOWN');
      return matchesQuery && matchesFilter;
    }).length;
  }, [nodes, searchQuery, activeFilters]);

  // Handlers
  const handleSearchChange = useCallback((query: string) => {
    setSearchQuery(query);
    graphStore.setSearchQuery(query);
  }, [graphStore]);

  const handleFilterToggle = useCallback((intent: string) => {
    setActiveFilters((prev) => {
      const next = prev.includes(intent)
        ? prev.filter((i) => i !== intent)
        : [...prev, intent];
      graphStore.setFilters(next);
      return next;
    });
  }, [graphStore]);

  const handleViewModeChange = useCallback((mode: ViewMode) => {
    setViewMode(mode);
    graphStore.setViewMode(mode);
  }, [graphStore]);

  const handleZoomIn = useCallback(() => {
    setZoomLevel((prev) => Math.min(prev + 0.2, 3));
  }, []);

  const handleZoomOut = useCallback(() => {
    setZoomLevel((prev) => Math.max(prev - 0.2, 0.1));
  }, []);

  const handleResetZoom = useCallback(() => {
    setZoomLevel(1);
  }, []);

  const handleNodeClick = useCallback(
    (nodeId: string) => {
      const nextId = selectedNodeId === nodeId ? null : nodeId;
      setSelectedNodeId(nextId);
      graphStore.setSelectedNode(nextId);
    },
    [graphStore, selectedNodeId]
  );

  const handleRefresh = useCallback(() => {
    setLastUpdated(new Date());
  }, []);

  const handleNavigateToChat = useCallback(() => {
    if (selectedNodeId) {
      navigate(`/chat/${selectedNodeId}`);
    }
  }, [navigate, selectedNodeId]);

  // Selected node details
  const selectedNode = useMemo(
    () => nodes.find((n) => n.id === selectedNodeId) ?? null,
    [nodes, selectedNodeId]
  );

  return (
    <div className="flex flex-col h-full bg-surface">
      {/* Page Header */}
      <header className="px-4 md:px-6 pt-4 md:pt-6 pb-4 shrink-0">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 sm:gap-0">
          <div>
            <h1 className="text-xl md:text-2xl font-semibold text-text-primary">对话树图谱</h1>
            <p className="text-sm text-text-muted mt-1">
              以力导向图形式展示所有对话 session 的关系
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Tooltip content="刷新数据" position="bottom">
              <button
                type="button"
                onClick={handleRefresh}
                className="p-2 rounded-lg bg-surface-card border border-subtle text-text-secondary hover:text-text-primary hover:bg-surface-card-hover transition-colors"
                aria-label="刷新"
              >
                <RefreshCw className="w-4 h-4" />
              </button>
            </Tooltip>
            <div className="text-xs text-text-muted">
              更新于 {formatTimestamp(lastUpdated.toISOString())}
            </div>
          </div>
        </div>
        <div className="mt-3 border-b border-subtle" />
      </header>

      {/* Graph Toolbar */}
      <GraphToolbar
        searchQuery={searchQuery}
        onSearchChange={handleSearchChange}
        activeFilters={activeFilters}
        onFilterToggle={handleFilterToggle}
        viewMode={viewMode}
        onViewModeChange={handleViewModeChange}
        zoomLevel={zoomLevel}
        onZoomIn={handleZoomIn}
        onZoomOut={handleZoomOut}
        onResetZoom={handleResetZoom}
        nodeCounts={nodeCounts}
      />

      {/* Graph Canvas */}
      <div className="flex-1 relative overflow-hidden">
        <ConversationGraph
          nodes={nodes}
          edges={edges}
          searchQuery={searchQuery}
          activeFilters={activeFilters}
          selectedNodeId={selectedNodeId}
          onNodeClick={handleNodeClick}
          zoomLevel={zoomLevel}
          onZoomChange={setZoomLevel}
        />

        {/* Graph Legend */}
        <GraphLegend
          visible={legendVisible}
          onToggle={() => setLegendVisible((prev) => !prev)}
          nodeCounts={nodeCounts}
          activeFilters={activeFilters}
          onFilterToggle={handleFilterToggle}
          totalNodes={nodes.length}
          filteredNodes={filteredNodeCount}
        />

        {/* Selected Node Info Panel (bottom-left overlay) */}
        <AnimatePresence>
          {selectedNode && (
            <motion.div
              initial={{ opacity: 0, y: 20, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 20, scale: 0.98 }}
              transition={{ duration: 0.25 }}
              className="absolute bottom-4 left-4 right-4 sm:right-auto sm:w-64 z-10 rounded-xl bg-surface-card border border-subtle shadow-card overflow-hidden"
            >
              <div className="px-3 py-2.5 border-b border-subtle flex items-center justify-between">
                <span className="text-xs font-semibold text-text-primary">节点详情</span>
                <button
                  type="button"
                  onClick={() => setSelectedNodeId(null)}
                  className="text-text-muted hover:text-text-primary transition-colors"
                  aria-label="关闭"
                >
                  <span className="text-xs">×</span>
                </button>
              </div>
              <div className="px-3 py-3 space-y-2">
                <div className="flex items-center gap-2">
                  <span
                    className="w-3 h-3 rounded-full"
                    style={{
                      backgroundColor: getIntentColor(selectedNode.intent || 'UNKNOWN').hex,
                    }}
                  />
                  <span className="text-xs font-medium text-text-primary">
                    {selectedNode.label || selectedNode.id}
                  </span>
                </div>
                <div className="text-[10px] text-text-muted space-y-1">
                  <div className="flex justify-between">
                    <span>ID</span>
                    <span className="text-text-secondary font-mono">{selectedNode.id}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>类型</span>
                    <span className="text-text-secondary">{selectedNode.type}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>意图</span>
                    <span className="text-text-secondary">
                      {getIntentColor(selectedNode.intent || 'UNKNOWN').label}
                    </span>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={handleNavigateToChat}
                  className="w-full mt-2 px-3 py-1.5 rounded-md bg-primary text-white text-xs font-medium hover:bg-primary-dark transition-colors"
                >
                  跳转至对话
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Empty state hint when no filters match */}
        <AnimatePresence>
          {filteredNodeCount === 0 && nodes.length > 0 && (
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.2 }}
              className="absolute inset-0 flex items-center justify-center pointer-events-none"
            >
              <div className="bg-surface-card border border-subtle rounded-xl px-6 py-4 shadow-card text-center">
                <Info className="w-6 h-6 text-text-muted mx-auto mb-2" />
                <p className="text-sm text-text-secondary">没有匹配的节点</p>
                <p className="text-xs text-text-muted mt-1">
                  尝试清除搜索或调整过滤器
                </p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Status Bar */}
      <div className="shrink-0 px-4 py-2 border-t border-subtle bg-surface-card flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 sm:gap-0 text-xs text-text-muted">
        <div className="flex items-center gap-2 sm:gap-4 flex-wrap">
          <span>
            节点总数: <span className="text-text-secondary font-medium">{nodes.length}</span>
          </span>
          <span>
            显示节点: <span className="text-text-secondary font-medium">{filteredNodeCount}</span>
          </span>
          <span>
            选中节点: <span className="text-text-secondary font-medium">{selectedNodeId ? 1 : 0}</span>
          </span>
          <span>
            边数: <span className="text-text-secondary font-medium">{edges.length}</span>
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span>缩放: {Math.round(zoomLevel * 100)}%</span>
          <span>·</span>
          <span>视图: {viewMode === 'force' ? '力导向' : viewMode === 'timeline' ? '时间线' : '树形'}</span>
        </div>
      </div>
    </div>
  );
}

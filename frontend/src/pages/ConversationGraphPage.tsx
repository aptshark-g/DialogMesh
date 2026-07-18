import { useState, useCallback, useMemo, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { GraphToolbar, GraphLegend, ConversationGraph } from '../components/graph';
import { useGraphStore } from '../stores/graphStore';
import type { GraphNode, GraphEdge, ViewMode } from '../types/graph';
import { getIntentColor } from '../types/graph';
import { formatTimestamp } from '../lib/utils';
import { RefreshCw, Info } from 'lucide-react';
import { Tooltip } from '../components/ui/Tooltip';
import { useV6Graph } from '../hooks/useV6Graph';

export function ConversationGraphPage() {
  const navigate = useNavigate();
  const { graph, loading, error, refresh } = useV6Graph();

  // Local state for graph page
  const [searchQuery, setSearchQuery] = useState('');
  const [activeFilters, setActiveFilters] = useState<string[]>([]);
  const [viewMode, setViewMode] = useState<ViewMode>('force');
  const [zoomLevel, setZoomLevel] = useState(1);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [legendVisible, setLegendVisible] = useState(true);
  const [lastUpdated, setLastUpdated] = useState(new Date());

  // Use graph store for nodes/edges (initialize from API)
  const graphStore = useGraphStore();

  useEffect(() => {
    if (!graph) return;
    const apiNodes: GraphNode[] = graph.nodes.map((node) => ({
      id: node.id,
      label: node.id,
      type: 'ai',
      intent: (node.state?.intent as string) || 'UNKNOWN',
    }));
    const apiEdges: GraphEdge[] = graph.edges.map((edge) => ({
      id: `${edge.source}-${edge.target}`,
      source: edge.source,
      target: edge.target,
      type: edge.type,
    }));
    graphStore.setNodes(apiNodes);
    graphStore.setEdges(apiEdges);
  }, [graph]); // eslint-disable-line react-hooks/exhaustive-deps

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

  // Look up original node state from API graph
  const selectedNodeState = useMemo(() => {
    if (!selectedNodeId || !graph) return null;
    const originalNode = graph.nodes.find((n) => n.id === selectedNodeId);
    return originalNode?.state ?? null;
  }, [selectedNodeId, graph]);

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
    refresh();
    setLastUpdated(new Date());
  }, [refresh]);

  const handleNavigateToChat = useCallback(() => {
    navigate('/chat');
  }, [navigate]);

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
                disabled={loading}
                className="p-2 rounded-lg bg-surface-card border border-subtle text-text-secondary hover:text-text-primary hover:bg-surface-card-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                aria-label="刷新"
              >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
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

        {/* Loading overlay */}
        <AnimatePresence>
          {loading && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="absolute inset-0 flex items-center justify-center bg-surface/60 z-20"
            >
              <div className="bg-surface-card border border-subtle rounded-xl px-6 py-4 shadow-card text-center">
                <RefreshCw className="w-6 h-6 text-primary mx-auto mb-2 animate-spin" />
                <p className="text-sm text-text-secondary">加载中…</p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Error overlay */}
        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="absolute inset-0 flex items-center justify-center bg-surface/60 z-20"
            >
              <div className="bg-surface-card border border-red-200 dark:border-red-900 rounded-xl px-6 py-4 shadow-card text-center max-w-sm mx-4">
                <Info className="w-6 h-6 text-red-500 mx-auto mb-2" />
                <p className="text-sm text-text-secondary">加载失败</p>
                <p className="text-xs text-text-muted mt-1">{error.message}</p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Selected Node Info Panel (bottom-left overlay) */}
        <AnimatePresence>
          {selectedNode && (
            <motion.div
              initial={{ opacity: 0, y: 20, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 20, scale: 0.98 }}
              transition={{ duration: 0.25 }}
              className="absolute bottom-4 left-4 right-4 sm:right-auto sm:w-80 z-10 rounded-xl bg-surface-card border border-subtle shadow-card overflow-hidden"
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
                {/* Node state from API */}
                {selectedNodeState && Object.keys(selectedNodeState).length > 0 && (
                  <div className="border-t border-subtle pt-2 mt-2">
                    <span className="text-[10px] font-semibold text-text-primary">State</span>
                    <div className="mt-1 space-y-1 max-h-32 overflow-y-auto">
                      {Object.entries(selectedNodeState).map(([key, value]) => (
                        <div key={key} className="flex justify-between text-[10px]">
                          <span className="text-text-muted">{key}</span>
                          <span className="text-text-secondary font-mono truncate max-w-[140px]">
                            {typeof value === 'string' ? value : JSON.stringify(value)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
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

        {/* Empty state hint when no data or no filters match */}
        <AnimatePresence>
          {!loading && !error && filteredNodeCount === 0 && (
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.2 }}
              className="absolute inset-0 flex items-center justify-center pointer-events-none"
            >
              <div className="bg-surface-card border border-subtle rounded-xl px-6 py-4 shadow-card text-center">
                <Info className="w-6 h-6 text-text-muted mx-auto mb-2" />
                <p className="text-sm text-text-secondary">
                  {nodes.length === 0 ? '暂无数据' : '没有匹配的节点'}
                </p>
                <p className="text-xs text-text-muted mt-1">
                  {nodes.length === 0 ? '对话图谱为空，请尝试刷新' : '尝试清除搜索或调整过滤器'}
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

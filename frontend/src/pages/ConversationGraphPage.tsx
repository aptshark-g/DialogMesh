import { useState, useCallback, useMemo, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  GraphToolbar,
  GraphLegend,
  ConversationGraph,
  GraphEditPanel,
  DiscourseTreeView,
  ObjectsView,
  AnnotationsView,
} from '../components/graph';
import type { GraphEditTarget } from '../components/graph';
import { useGraphStore } from '../stores/graphStore';
import type { GraphNode, GraphEdge, ViewMode } from '../types/graph';
import { getIntentColor } from '../types/graph';
import { cn, formatTimestamp } from '../lib/utils';
import { RefreshCw, Info, GitBranch, ListTree, Boxes, MessageSquare, Pencil } from 'lucide-react';
import { Tooltip } from '../components/ui/Tooltip';
import { Toast } from '../components/ui/Toast';
import { useV6Graph } from '../hooks/useV6Graph';
import { editGraph, editDiscourseTree, editObjects } from '../api/v6';
import type {
  V6GraphEditRequest,
  V6DiscourseTreeEditRequest,
  V6ObjectEditRequest,
} from '../types/api';

type PageTab = 'graph' | 'tree' | 'objects' | 'annotations';

const PAGE_TABS: { value: PageTab; label: string; icon: typeof GitBranch }[] = [
  { value: 'graph', label: '交互图', icon: GitBranch },
  { value: 'tree', label: '对话树', icon: ListTree },
  { value: 'objects', label: '语义对象', icon: Boxes },
  { value: 'annotations', label: '注释', icon: MessageSquare },
];

// V6 edge.type 是自由字符串,映射到前端 GraphEdge 的有限联合类型
const GRAPH_EDGE_TYPES = ['dependency', 'causal', 'similarity', 'hierarchical', 'reference'] as const;

function toGraphEdgeType(value: string): GraphEdge['type'] {
  return (GRAPH_EDGE_TYPES as readonly string[]).includes(value)
    ? (value as NonNullable<GraphEdge['type']>)
    : undefined;
}

interface ToastState {
  key: number;
  type: 'success' | 'error';
  message: string;
}

export function ConversationGraphPage() {
  const navigate = useNavigate();
  const { graph, discourseTree, objects, loading, error, refresh } = useV6Graph();

  // Local state for graph page
  const [activeTab, setActiveTab] = useState<PageTab>('graph');
  const [searchQuery, setSearchQuery] = useState('');
  const [activeFilters, setActiveFilters] = useState<string[]>([]);
  const [viewMode, setViewMode] = useState<ViewMode>('force');
  const [zoomLevel, setZoomLevel] = useState(1);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [legendVisible, setLegendVisible] = useState(true);
  const [lastUpdated, setLastUpdated] = useState(new Date());

  // Edit mode state
  const [editMode, setEditMode] = useState(false);
  const [editTarget, setEditTarget] = useState<GraphEditTarget | null>(null);
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [toast, setToast] = useState<ToastState | null>(null);

  // Use graph store for nodes/edges (initialize from API)
  const graphStore = useGraphStore();

  const showToast = useCallback((type: ToastState['type'], message: string) => {
    setToast({ key: Date.now(), type, message });
  }, []);

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
      type: toGraphEdgeType(edge.type),
      weight: edge.weight,
    }));
    graphStore.setNodes(apiNodes);
    graphStore.setEdges(apiEdges);
  }, [graph]); // eslint-disable-line react-hooks/exhaustive-deps

  const nodes = graphStore.nodes;
  const edges = graphStore.edges;

  const nodeIds = useMemo(() => nodes.map((n) => n.id), [nodes]);

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
      // 编辑模式: 点击节点打开编辑面板
      if (editMode) {
        const originalNode = graph?.nodes.find((n) => n.id === nodeId);
        setEditTarget({ kind: 'node', id: nodeId, state: originalNode?.state ?? {} });
        return;
      }
      const nextId = selectedNodeId === nodeId ? null : nodeId;
      setSelectedNodeId(nextId);
      graphStore.setSelectedNode(nextId);
    },
    [graphStore, selectedNodeId, editMode, graph]
  );

  const handleEdgeClick = useCallback(
    (edgeId: string) => {
      if (!editMode || !graph) return;
      const apiEdge = graph.edges.find((e) => `${e.source}-${e.target}` === edgeId);
      if (!apiEdge) return;
      setEditTarget({
        kind: 'edge',
        source: apiEdge.source,
        target: apiEdge.target,
        edgeType: apiEdge.type,
        weight: apiEdge.weight,
      });
    },
    [editMode, graph]
  );

  const handleAddEdge = useCallback(() => {
    setEditTarget({ kind: 'add_edge' });
  }, []);

  const handleRefresh = useCallback(() => {
    refresh();
    setLastUpdated(new Date());
  }, [refresh]);

  const handleNavigateToChat = useCallback(() => {
    navigate('/chat');
  }, [navigate]);

  // 图谱编辑提交 (后端业务失败返回 200 + { error })
  const handleGraphEditSubmit = useCallback(
    async (req: V6GraphEditRequest) => {
      setEditSubmitting(true);
      try {
        const resp = await editGraph(req);
        if (resp.error) {
          showToast('error', `编辑失败: ${resp.error}`);
          return;
        }
        showToast('success', '图谱已更新');
        setEditTarget(null);
        refresh();
        setLastUpdated(new Date());
      } catch (err) {
        showToast('error', err instanceof Error ? err.message : '编辑请求失败');
      } finally {
        setEditSubmitting(false);
      }
    },
    [refresh, showToast]
  );

  // 对话树编辑提交
  const handleTreeEdit = useCallback(
    async (req: V6DiscourseTreeEditRequest): Promise<boolean> => {
      setEditSubmitting(true);
      try {
        const resp = await editDiscourseTree(req);
        if (resp.error) {
          showToast('error', `编辑失败: ${resp.error}`);
          return false;
        }
        showToast('success', '对话树已更新');
        refresh();
        setLastUpdated(new Date());
        return true;
      } catch (err) {
        showToast('error', err instanceof Error ? err.message : '编辑请求失败');
        return false;
      } finally {
        setEditSubmitting(false);
      }
    },
    [refresh, showToast]
  );

  // 语义对象编辑提交
  const handleObjectEdit = useCallback(
    async (req: V6ObjectEditRequest): Promise<boolean> => {
      setEditSubmitting(true);
      try {
        const resp = await editObjects(req);
        if (resp.error) {
          showToast('error', `编辑失败: ${resp.error}`);
          return false;
        }
        showToast('success', '语义对象已更新');
        refresh();
        setLastUpdated(new Date());
        return true;
      } catch (err) {
        showToast('error', err instanceof Error ? err.message : '编辑请求失败');
        return false;
      } finally {
        setEditSubmitting(false);
      }
    },
    [refresh, showToast]
  );

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
              查看并编辑对话图谱、discourse tree、语义对象与注释
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

      {/* Tab Bar */}
      <div className="px-4 md:px-6 pt-3 shrink-0">
        <div className="inline-flex items-center bg-surface-card rounded-md border border-subtle p-0.5">
          {PAGE_TABS.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.value;
            return (
              <button
                key={tab.value}
                type="button"
                onClick={() => setActiveTab(tab.value)}
                className={cn(
                  'flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-sm transition-colors',
                  isActive
                    ? 'bg-primary text-white'
                    : 'text-text-secondary hover:text-text-primary hover:bg-surface-card-hover'
                )}
                aria-pressed={isActive}
              >
                <Icon className="w-3.5 h-3.5" />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      {activeTab === 'graph' && (
        <>
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
            editMode={editMode}
            onEditModeChange={setEditMode}
            onAddEdge={handleAddEdge}
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
              onEdgeClick={handleEdgeClick}
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

            {/* Edit mode hint */}
            <AnimatePresence>
              {editMode && (
                <motion.div
                  initial={{ opacity: 0, y: -8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  transition={{ duration: 0.2 }}
                  className="absolute top-3 left-1/2 -translate-x-1/2 z-10 flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-primary text-white text-xs font-medium shadow-card"
                >
                  <Pencil className="w-3 h-3" />
                  <span>编辑模式: 点击节点或边进行编辑</span>
                </motion.div>
              )}
            </AnimatePresence>

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
                    <p className="text-xs text-text-muted mt-1">{error}</p>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Selected Node Info Panel (bottom-left overlay) */}
            <AnimatePresence>
              {selectedNode && !editMode && (
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
                          {Object.entries(selectedNodeState ?? {}).map(([key, value]) => (
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
                      {nodes.length === 0 ? '对话图谱为空,请尝试刷新' : '尝试清除搜索或调整过滤器'}
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
              {editMode && <span className="text-primary font-medium">编辑模式</span>}
              {editMode && <span>·</span>}
              <span>缩放: {Math.round(zoomLevel * 100)}%</span>
              <span>·</span>
              <span>视图: {viewMode === 'force' ? '力导向' : viewMode === 'timeline' ? '时间线' : '树形'}</span>
            </div>
          </div>
        </>
      )}

      {activeTab === 'tree' && (
        <div className="flex-1 overflow-y-auto px-4 md:px-6 py-4">
          <DiscourseTreeView
            data={discourseTree}
            loading={loading}
            submitting={editSubmitting}
            onEdit={handleTreeEdit}
          />
        </div>
      )}

      {activeTab === 'objects' && (
        <div className="flex-1 overflow-y-auto px-4 md:px-6 py-4">
          <ObjectsView
            data={objects}
            loading={loading}
            submitting={editSubmitting}
            onEdit={handleObjectEdit}
          />
        </div>
      )}

      {activeTab === 'annotations' && (
        <div className="flex-1 overflow-y-auto px-4 md:px-6 py-4">
          <AnnotationsView />
        </div>
      )}

      {/* Graph Edit Panel */}
      <GraphEditPanel
        target={editTarget}
        nodeIds={nodeIds}
        submitting={editSubmitting}
        onClose={() => setEditTarget(null)}
        onSubmit={handleGraphEditSubmit}
      />

      {/* Toast */}
      {toast && (
        <Toast
          key={toast.key}
          type={toast.type}
          message={toast.message}
          onClose={() => setToast(null)}
        />
      )}
    </div>
  );
}

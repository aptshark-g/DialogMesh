// FILE: src/stores/graphStore.ts

import { create } from 'zustand';
import type { GraphNode, GraphEdge, ViewMode } from '../types/graph';

interface GraphState {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selectedNodeId: string | null;
  viewMode: ViewMode;
  filters: string[];
  searchQuery: string;
}

interface GraphActions {
  setNodes: (nodes: GraphNode[]) => void;
  setEdges: (edges: GraphEdge[]) => void;
  setSelectedNode: (id: string | null) => void;
  setViewMode: (mode: ViewMode) => void;
  setFilters: (filters: string[]) => void;
  setSearchQuery: (query: string) => void;
  clearFilters: () => void;
}

export interface GraphStore extends GraphState, GraphActions {}

const initialState: GraphState = {
  nodes: [],
  edges: [],
  selectedNodeId: null,
  viewMode: 'force',
  filters: [],
  searchQuery: '',
};

export const useGraphStore = create<GraphStore>((set) => ({
  ...initialState,

  setNodes: (nodes: GraphNode[]) => set({ nodes }),

  setEdges: (edges: GraphEdge[]) => set({ edges }),

  setSelectedNode: (id: string | null) => set({ selectedNodeId: id }),

  setViewMode: (mode: ViewMode) => set({ viewMode: mode }),

  setFilters: (filters: string[]) => set({ filters }),

  setSearchQuery: (query: string) => set({ searchQuery: query }),

  clearFilters: () => set({ filters: [], searchQuery: '' }),
}));

// ==================== Selector hooks ====================

export function useGraphNodes(): GraphNode[] {
  return useGraphStore((s) => s.nodes);
}

export function useGraphEdges(): GraphEdge[] {
  return useGraphStore((s) => s.edges);
}

export function useGraphSelectedNodeId(): string | null {
  return useGraphStore((s) => s.selectedNodeId);
}

export function useGraphViewMode(): ViewMode {
  return useGraphStore((s) => s.viewMode);
}

export function useGraphFilters(): string[] {
  return useGraphStore((s) => s.filters);
}

export function useGraphSearchQuery(): string {
  return useGraphStore((s) => s.searchQuery);
}

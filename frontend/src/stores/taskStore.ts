// FILE: src/stores/taskStore.ts

import { create } from 'zustand';
import type {
  TaskGraph,
  TaskExecutionStatus,
  TaskNodeStatus,
  TaskNode,
  TaskNodeType,
  TaskEdge,
} from '../types/task';

interface TaskState {
  taskGraph: TaskGraph | null;
  executionStatus: TaskExecutionStatus;
  selectedNodeId: string | null;
}

interface TaskActions {
  setTaskGraph: (graph: TaskGraph | null) => void;
  setExecutionStatus: (status: TaskExecutionStatus) => void;
  setSelectedNode: (id: string | null) => void;
  executeNode: (nodeId: string) => void;
  resetExecution: () => void;
  // ═══ v6 WS live updates ═══
  onStepStart: (index: number, tool: string, action: string) => void;
  onStepComplete: (index: number, status: string, duration_ms: number) => void;
  onExecutionDone: (summary: string) => void;
}

export interface TaskStore extends TaskState, TaskActions {}

const initialState: TaskState = {
  taskGraph: null,
  executionStatus: 'idle',
  selectedNodeId: null,
};

export const useTaskStore = create<TaskStore>((set, get) => ({
  ...initialState,

  setTaskGraph: (graph: TaskGraph | null) => set({ taskGraph: graph }),

  setExecutionStatus: (status: TaskExecutionStatus) =>
    set({ executionStatus: status }),

  setSelectedNode: (id: string | null) => set({ selectedNodeId: id }),

  executeNode: (nodeId: string) => {
    const { taskGraph } = get();
    if (!taskGraph) return;

    const updatedNodes = taskGraph.nodes.map((node) => {
      if (node.id === nodeId) {
        return { ...node, status: 'running' as TaskNodeStatus };
      }
      return node;
    });

    set({
      taskGraph: { ...taskGraph, nodes: updatedNodes },
      executionStatus: 'running',
    });
  },

  resetExecution: () => {
    const { taskGraph } = get();
    if (!taskGraph) { set({ executionStatus: 'idle' }); return; }
    const resetNodes = taskGraph.nodes.map((node) =>
      node.status === 'running' || node.status === 'completed' || node.status === 'failed'
        ? { ...node, status: 'pending' as TaskNodeStatus } : node);
    set({ taskGraph: { ...taskGraph, nodes: resetNodes }, executionStatus: 'idle', selectedNodeId: null });
  },

  // ═══ v6 WS live updates ═══
  onStepStart: (index, tool, action) => {
    const { taskGraph } = get();
    if (!taskGraph) return;
    const updated = taskGraph.nodes.map((n, i) =>
      i === index ? { ...n, status: 'running' as TaskNodeStatus, meta: { ...n.meta, tool, action } } : n);
    set({ taskGraph: { ...taskGraph, nodes: updated }, executionStatus: 'running' });
  },

  onStepComplete: (index, status, duration_ms) => {
    const { taskGraph } = get();
    if (!taskGraph) return;
    const nodeStatus: TaskNodeStatus = status === 'success' ? 'completed' : 'failed';
    const updated = taskGraph.nodes.map((n, i) =>
      i === index ? { ...n, status: nodeStatus, meta: { ...n.meta, duration_ms } } : n);
    set({ taskGraph: { ...taskGraph, nodes: updated } });
  },

  onExecutionDone: (_summary) => {
    set({ executionStatus: 'completed' });
  },
}));

// ==================== Selector hooks ====================

export function useTaskGraphStore(): TaskGraph | null {
  return useTaskStore((s) => s.taskGraph);
}

export function useTaskExecutionStatus(): TaskExecutionStatus {
  return useTaskStore((s) => s.executionStatus);
}

export function useTaskSelectedNodeId(): string | null {
  return useTaskStore((s) => s.selectedNodeId);
}

// ═══ Conversion: TaskGraphNode[] (API) → TaskGraph (store) ═══

import type { TaskGraphNode as ApiTaskNode } from '../types/api';

export function convertToTaskGraph(apiNodes: ApiTaskNode[] | null | undefined): TaskGraph | null {
  if (!apiNodes || apiNodes.length === 0) return null;
  const now = new Date().toISOString();
  const nodes: TaskNode[] = apiNodes.map((n, i) => ({
    id: n.id,
    name: n.name || n.type || `node_${i}`,
    description: n.params?.description as string || '',
    type: (mapNodeType(n.type) as TaskNodeType),
    status: mapStatus(n.status),
    parentId: null,
    dependencies: n.dependencies || [],
    children: [],
    progress: n.progress,
    result: n.result,
    checkpoint: n.checkpoint || false,
  }));
  // Build edges from dependencies
  const edges: TaskEdge[] = [];
  nodes.forEach(node => {
    node.dependencies.forEach(depId => {
      edges.push({ id: `e_${depId}_${node.id}`, source: depId, target: node.id, type: 'dependency' });
    });
  });
  // Set children
  edges.forEach(e => {
    const parent = nodes.find(n => n.id === e.source);
    if (parent) parent.children.push(e.target);
  });
  const roots = nodes.filter(n => n.dependencies.length === 0);
  return {
    id: `dag_${Date.now()}`,
    version: '1.0',
    nodes,
    edges,
    rootNodeId: roots[0]?.id || '',
    createdAt: now,
    updatedAt: now,
    executionStatus: 'idle',
    overallProgress: 0,
  };
}

function mapNodeType(t: string): string {
  const m: Record<string, string> = { pcr:'intent', intent:'intent', context:'execution', subgraph:'execution', profile:'intent', llm_reply:'execution', scan:'execution', read:'execution', write:'execution', analyze:'validation', ask_user:'clarification', explain:'execution', fallback:'execution', behavior:'decision', meta:'intent', discourse:'intent', association:'execution', engineering:'validation', metap:'execution' };
  return m[t] || 'execution';
}

function mapStatus(s: string): TaskNodeStatus {
  const m: Record<string, TaskNodeStatus> = { pending:'pending', running:'running', completed:'completed', failed:'failed' };
  return m[s] || 'pending';
}

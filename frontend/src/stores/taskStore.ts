// FILE: src/stores/taskStore.ts

import { create } from 'zustand';
import type {
  TaskGraph,
  TaskExecutionStatus,
  TaskNodeStatus,
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
      i === index ? { ...n, status: 'running' as TaskNodeStatus, data: { ...n.data, tool, action } } : n);
    set({ taskGraph: { ...taskGraph, nodes: updated }, executionStatus: 'running' });
  },

  onStepComplete: (index, status, duration_ms) => {
    const { taskGraph } = get();
    if (!taskGraph) return;
    const nodeStatus: TaskNodeStatus = status === 'success' ? 'completed' : 'failed';
    const updated = taskGraph.nodes.map((n, i) =>
      i === index ? { ...n, status: nodeStatus, data: { ...n.data, duration_ms } } : n);
    set({ taskGraph: { ...taskGraph, nodes: updated } });
  },

  onExecutionDone: (summary) => {
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

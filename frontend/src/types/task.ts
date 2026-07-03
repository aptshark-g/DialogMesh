// FILE: src/types/task.ts

// ==================== 节点类型与状态 ====================

export type TaskNodeType =
  | 'intent'
  | 'clarification'
  | 'execution'
  | 'validation'
  | 'decision'
  | 'parallel'
  | 'merge';

export type TaskNodeStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'skipped'
  | 'blocked';

export type TaskExecutionStatus =
  | 'idle'
  | 'running'
  | 'paused'
  | 'completed'
  | 'failed'
  | 'cancelled';

// ==================== 任务节点 ====================

export interface TaskNode {
  id: string;
  name: string;
  description: string;
  type: TaskNodeType;
  status: TaskNodeStatus;
  parentId: string | null;
  dependencies: string[];
  children: string[];
  progress?: number;
  result?: string;
  error?: string;
  latencyMs?: number;
  startedAt?: string;
  completedAt?: string;
  metadata?: Record<string, unknown>;
}

// ==================== 任务边 ====================

export interface TaskEdge {
  id: string;
  source: string;
  target: string;
  type: 'dependency' | 'conditional' | 'parallel';
  label?: string;
  condition?: TaskCondition;
}

// ==================== 任务条件 ====================

export interface TaskCondition {
  type: 'always' | 'on_success' | 'on_failure' | 'custom';
  expression?: string;
  description?: string;
}

// ==================== 任务图 ====================

export interface TaskGraph {
  id: string;
  version: string;
  nodes: TaskNode[];
  edges: TaskEdge[];
  rootNodeId: string;
  createdAt: string;
  updatedAt: string;
  executionStatus: TaskExecutionStatus;
  overallProgress: number;
  metadata?: Record<string, unknown>;
}

// ==================== 执行历史 ====================

export interface TaskExecutionRecord {
  nodeId: string;
  status: TaskNodeStatus;
  startedAt: string;
  completedAt?: string;
  latencyMs?: number;
  result?: string;
  error?: string;
}

// ==================== 执行计划 ====================

export interface ExecutionPlan {
  graphId: string;
  parallelGroups: string[][];
  criticalPath: string[];
  estimatedDurationMs: number;
  riskNodes: string[];
}

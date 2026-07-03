// FILE: src/types/graph.ts

// ==================== 节点与边 ====================

export interface GraphNode {
  id: string;
  label: string;
  type?: string;
  intent?: string;
  cluster?: string;
  x?: number;
  y?: number;
  z?: number;
  val?: number;
  color?: string;
  description?: string;
  timestamp?: string;
  metadata?: Record<string, unknown>;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  label?: string;
  type?: 'dependency' | 'causal' | 'similarity' | 'hierarchical' | 'reference';
  weight?: number;
  color?: string;
  dashed?: boolean;
}

// ==================== 视图与过滤 ====================

export type ViewMode = 'force' | 'timeline' | 'tree';

export interface GraphFilter {
  id: string;
  label: string;
  field: string;
  value: string;
  active: boolean;
}

// ==================== 聚类 ====================

export interface ClusterNode {
  id: string;
  label: string;
  nodeCount: number;
  centerX: number;
  centerY: number;
  color: string;
  density: number;
  topics: string[];
}

// ==================== 意图颜色映射 ====================

export type IntentColorKey =
  | 'scan-memory'
  | 'read-memory'
  | 'write-memory'
  | 'hack-value'
  | 'explain'
  | 'provide-code'
  | 'unknown';

export interface IntentColor {
  key: IntentColorKey;
  label: string;
  hex: string;
  bgClass: string;
  textClass: string;
}

export const INTENT_COLOR_MAP: Record<string, IntentColor> = {
  'SCAN_MEMORY': {
    key: 'scan-memory',
    label: '扫描记忆',
    hex: '#D97706',
    bgClass: 'bg-intent-scan-memory/10',
    textClass: 'text-intent-scan-memory',
  },
  'READ_MEMORY': {
    key: 'read-memory',
    label: '读取记忆',
    hex: '#0D9488',
    bgClass: 'bg-intent-read-memory/10',
    textClass: 'text-intent-read-memory',
  },
  'WRITE_MEMORY': {
    key: 'write-memory',
    label: '写入记忆',
    hex: '#8B5CF6',
    bgClass: 'bg-intent-write-memory/10',
    textClass: 'text-intent-write-memory',
  },
  'HACK_VALUE': {
    key: 'hack-value',
    label: '修改值',
    hex: '#E11D48',
    bgClass: 'bg-intent-hack-value/10',
    textClass: 'text-intent-hack-value',
  },
  'EXPLAIN': {
    key: 'explain',
    label: '解释',
    hex: '#3B82F6',
    bgClass: 'bg-intent-explain/10',
    textClass: 'text-intent-explain',
  },
  'PROVIDE_CODE': {
    key: 'provide-code',
    label: '提供代码',
    hex: '#10B981',
    bgClass: 'bg-intent-provide-code/10',
    textClass: 'text-intent-provide-code',
  },
  'UNKNOWN': {
    key: 'unknown',
    label: '未知',
    hex: '#6B6680',
    bgClass: 'bg-intent-unknown/10',
    textClass: 'text-intent-unknown',
  },
};

export function getIntentColor(intent: string): IntentColor {
  return INTENT_COLOR_MAP[intent] ?? INTENT_COLOR_MAP['UNKNOWN'];
}

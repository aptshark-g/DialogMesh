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
  | 'task'
  | 'query'
  | 'correction'
  | 'discussion'
  | 'casual'
  | 'topic_switch'
  | 'unknown';

export interface IntentColor {
  key: IntentColorKey;
  label: string;
  hex: string;
  bgClass: string;
  textClass: string;
}

// 2026-08-18: 图谱意图过滤换用现行分类（cross_domain_ir.IntentCategory）,
// 移除 v3 遗留意图（scan/read/write memory 等）。旧值由后端归一化。
export const INTENT_COLOR_MAP: Record<string, IntentColor> = {
  'task': {
    key: 'task',
    label: '任务',
    hex: '#D97706',
    bgClass: 'bg-[#D97706]/10',
    textClass: 'text-[#D97706]',
  },
  'query': {
    key: 'query',
    label: '查询',
    hex: '#0D9488',
    bgClass: 'bg-[#0D9488]/10',
    textClass: 'text-[#0D9488]',
  },
  'correction': {
    key: 'correction',
    label: '修正',
    hex: '#E11D48',
    bgClass: 'bg-[#E11D48]/10',
    textClass: 'text-[#E11D48]',
  },
  'discussion': {
    key: 'discussion',
    label: '讨论',
    hex: '#3B82F6',
    bgClass: 'bg-[#3B82F6]/10',
    textClass: 'text-[#3B82F6]',
  },
  'casual': {
    key: 'casual',
    label: '闲聊',
    hex: '#8B5CF6',
    bgClass: 'bg-[#8B5CF6]/10',
    textClass: 'text-[#8B5CF6]',
  },
  'topic_switch': {
    key: 'topic_switch',
    label: '话题切换',
    hex: '#10B981',
    bgClass: 'bg-[#10B981]/10',
    textClass: 'text-[#10B981]',
  },
  'unknown': {
    key: 'unknown',
    label: '未知',
    hex: '#6B6680',
    bgClass: 'bg-[#6B6680]/10',
    textClass: 'text-[#6B6680]',
  },
};

export function getIntentColor(intent: string): IntentColor {
  return INTENT_COLOR_MAP[intent] ?? INTENT_COLOR_MAP['UNKNOWN'];
}

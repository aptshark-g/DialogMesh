// FILE: src/types/profile.ts

// ==================== 认知维度 ====================

export interface CognitiveDimension {
  key: string;
  label: string;
  value: number; // 0-100
  max: number;
  description?: string;
}

// ==================== 认知画像 ====================

export interface CognitiveProfile {
  id: string;
  sessionId: string;
  timestamp: string;
  dimensions: CognitiveDimension[];
  overallScore: number;
  confidenceLevel: 'low' | 'medium' | 'high';
  summary?: string;
}

// ==================== 统计指标 ====================

export interface ProfileStats {
  reasoningDepth: number;
  metacognition: number;
  expressionClarity: number;
  contextWindowUsage: number;
  entityCount: number;
  topicTreeDepth: number;
  coherenceScore: number;
  responseLatencyMs: number;
}

// ==================== 意图分布 ====================

export interface IntentDistribution {
  intent: string;
  count: number;
  percentage: number;
  color: string;
  trend: 'up' | 'down' | 'stable';
  trendValue: number;
}

// ==================== 实体云 ====================

export interface EntityCloudItem {
  id: string;
  text: string;
  weight: number;
  category: string;
  color: string;
  frequency: number;
  relatedEntities: string[];
}

// ==================== 雷达图数据 ====================

export interface RadarDataPoint {
  dimension: string;
  fullMark: number;
  value: number;
}

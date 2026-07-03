// FILE: src/types/analytics.ts

// ==================== 趋势分析类型 ====================

export interface TrendDataPoint {
  date: string;
  label: string;
  turns: number;
  messages: number;
  avgLatency: number;
}

export interface TrendSeries {
  data: TrendDataPoint[];
  domain: [number, number];
}

// ==================== 意图分布类型 ====================

export interface IntentDistributionItem {
  intent: string;
  label: string;
  count: number;
  color: string;
  percentage: number;
}

export interface IntentDistributionData {
  items: IntentDistributionItem[];
  total: number;
}

// ==================== 词云类型 ====================

export interface WordCloudItem {
  text: string;
  weight: number;
  color: string;
}

export interface WordCloudData {
  words: WordCloudItem[];
  maxWeight: number;
  minWeight: number;
}

// ==================== 综合指标类型 ====================

export interface SessionAnalytics {
  sessionId: string;
  createdAt: string;
  totalTurns: number;
  intents: Record<string, number>;
  keywords: string[];
  avgLatencyMs: number;
}

export interface GlobalAnalytics {
  sessionCount: number;
  totalTurns: number;
  totalMessages: number;
  avgLatencyMs: number;
  trendData: TrendDataPoint[];
  intentDistribution: IntentDistributionItem[];
  wordCloud: WordCloudData;
  activeSessionIds: string[];
}

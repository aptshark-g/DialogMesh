// FILE: src/stores/analyticsStore.ts

import { create } from 'zustand';
import type {
  TrendDataPoint,
  IntentDistributionItem,
  WordCloudData,
  WordCloudItem,
  GlobalAnalytics,
} from '../types/analytics';
import { getIntentColor } from '../types/graph';

// ==================== 状态类型 ====================

interface AnalyticsState {
  trendData: TrendDataPoint[];
  intentDistribution: IntentDistributionItem[];
  wordCloud: WordCloudData;
  lastUpdated: number;
  isComputing: boolean;
}

interface AnalyticsActions {
  computeAnalytics: () => void;
  setTrendData: (data: TrendDataPoint[]) => void;
  setIntentDistribution: (data: IntentDistributionItem[]) => void;
  setWordCloud: (data: WordCloudData) => void;
}

type AnalyticsStore = AnalyticsState & AnalyticsActions;

// ==================== 常量 ====================

const STOP_WORDS = new Set([
  '的', '了', '是', '在', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也',
  '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这', '那',
  'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
  'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'shall',
  'can', 'need', 'dare', 'ought', 'used', 'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by',
  'from', 'as', 'into', 'through', 'during', 'before', 'after', 'above', 'below', 'between',
  'and', 'but', 'or', 'yet', 'so', 'if', 'because', 'although', 'though', 'while', 'where',
  'when', 'that', 'which', 'who', 'whom', 'whose', 'what', 'this', 'these', 'those', 'i',
  'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them', 'my', 'your',
  'his', 'its', 'our', 'their', 'mine', 'yours', 'hers', 'ours', 'theirs', 'myself', 'yourself',
  'itself', 'ourselves', 'themselves', 'what', 'which', 'who', 'whom', 'whose', 'this', 'that',
  'these', 'those', 'am', 'it', 'was', 'been', 'being', 'have', 'has', 'had', 'do', 'does',
  'did', 'doing', 'will', 'would', 'shall', 'should', 'may', 'might', 'can', 'could',
  'must', 'ought', 'need', 'dare', 'used', 'here', 'there', 'where', 'when', 'why', 'how',
  'all', 'each', 'every', 'both', 'few', 'more', 'most', 'other', 'some', 'such', 'no',
  'nor', 'not', 'only', 'own', 'same', 'than', 'too', 'very', 'just', 'now', 'then',
  'once', 'again', 'also', 'any', 'however', 'thus', 'hence', 'still', 'already',
]);

const TECH_KEYWORDS = new Set([
  'memory', 'scan', 'read', 'write', 'hack', 'value', 'address', 'pointer', 'offset',
  'process', 'module', 'breakpoint', 'trace', 'debug', 'inject', 'hook', 'dump', 'patch',
  'memorygraph', 'dialogmesh', 'llm', 'ai', 'agent', 'model', 'prompt', 'context',
  'embedding', 'vector', 'cluster', 'graph', 'node', 'edge', 'intent', 'slot', 'entity',
  'api', 'websocket', 'rest', 'http', 'json', 'yaml', 'config', 'docker', 'k8s',
  'python', 'javascript', 'typescript', 'react', 'vue', 'node', 'fastapi', 'flask',
  'sqlite', 'redis', 'postgres', 'mysql', 'database', 'query', 'orm', 'sql',
  'thread', 'async', 'await', 'coroutine', 'event', 'loop', 'queue', 'buffer',
  'cache', 'store', 'persist', 'serialize', 'deserialize', 'encode', 'decode',
  'encrypt', 'decrypt', 'hash', 'uuid', 'token', 'auth', 'session', 'cookie',
  'jwt', 'oauth', 'login', 'register', 'user', 'role', 'permission', 'admin',
  'fxlms', 'fpga', 'thd', 'cnn', 'lstm', 'rnn', 'dsp', 'filter', 'noise',
  'vibration', 'control', 'pid', 'adaptive', 'kalman', 'fft', 'spectral',
]);

// ==================== 工具函数 ====================

function getSessionIdsFromStorage(): string[] {
  try {
    const raw = localStorage.getItem('dialogmesh_sessions');
    if (raw) return JSON.parse(raw) as string[];
  } catch {
    // ignore
  }
  return [];
}

function getSessionCreatedAt(sessionId: string): string {
  try {
    const raw = localStorage.getItem(`dialogmesh_session_${sessionId}_created`);
    return raw || '';
  } catch {
    return '';
  }
}

function getSessionMessages(sessionId: string): Array<{
  role: string;
  content: string;
  intent?: string;
  latencyMs?: number;
  timestamp?: number;
}> {
  try {
    const raw = localStorage.getItem(`dialogmesh_session_${sessionId}_messages`);
    if (raw) return JSON.parse(raw) as Array<{
      role: string;
      content: string;
      intent?: string;
      latencyMs?: number;
      timestamp?: number;
    }>;
  } catch {
    // ignore
  }
  return [];
}

function formatDateLabel(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

function extractKeywords(text: string): Map<string, number> {
  const counts = new Map<string, number>();
  const cleaned = text
    .toLowerCase()
    .replace(/[^\u4e00-\u9fa5a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

  // Chinese characters (2+ chars)
  const chineseWords = cleaned.match(/[\u4e00-\u9fa5]{2,}/g) || [];
  for (const word of chineseWords) {
    if (word.length >= 2 && !STOP_WORDS.has(word)) {
      counts.set(word, (counts.get(word) || 0) + 1);
    }
  }

  // English words
  const englishWords = cleaned.match(/[a-z][a-z0-9]*/g) || [];
  for (const word of englishWords) {
    if (word.length >= 3 && !STOP_WORDS.has(word)) {
      counts.set(word, (counts.get(word) || 0) + 1);
    }
  }

  return counts;
}

function computeTrendData(): TrendDataPoint[] {
  const sessionIds = getSessionIdsFromStorage();
  const dailyMap = new Map<string, TrendDataPoint>();

  for (const sessionId of sessionIds) {
    const createdAt = getSessionCreatedAt(sessionId);
    if (!createdAt) continue;

    const date = createdAt.slice(0, 10);
    const label = formatDateLabel(createdAt);
    const messages = getSessionMessages(sessionId);
    const turns = messages.filter((m) => m.role === 'user').length;
    const totalLatency = messages.reduce((sum, m) => sum + (m.latencyMs || 0), 0);
    const avgLatency = messages.length > 0 ? Math.round(totalLatency / messages.length) : 0;

    const existing = dailyMap.get(date);
    if (existing) {
      existing.turns += turns;
      existing.messages += messages.length;
      existing.avgLatency = Math.round(
        (existing.avgLatency * (existing.turns - turns) + totalLatency) /
          Math.max(existing.turns, 1)
      );
    } else {
      dailyMap.set(date, {
        date,
        label,
        turns,
        messages: messages.length,
        avgLatency,
      });
    }
  }

  const sorted = Array.from(dailyMap.values()).sort(
    (a, b) => a.date.localeCompare(b.date)
  );

  // Fill in missing dates for smoother chart
  if (sorted.length >= 2) {
    const filled: TrendDataPoint[] = [];
    const first = new Date(sorted[0].date);
    const last = new Date(sorted[sorted.length - 1].date);
    const dateMap = new Map(sorted.map((d) => [d.date, d]));

    for (let d = new Date(first); d <= last; d.setDate(d.getDate() + 1)) {
      const iso = d.toISOString().slice(0, 10);
      const point = dateMap.get(iso);
      if (point) {
        filled.push(point);
      } else {
        filled.push({
          date: iso,
          label: formatDateLabel(iso),
          turns: 0,
          messages: 0,
          avgLatency: 0,
        });
      }
    }
    return filled;
  }

  return sorted;
}

function computeIntentDistribution(): IntentDistributionItem[] {
  const sessionIds = getSessionIdsFromStorage();
  const intentCounts = new Map<string, number>();

  for (const sessionId of sessionIds) {
    const messages = getSessionMessages(sessionId);
    for (const msg of messages) {
      const intent = msg.intent || 'UNKNOWN';
      intentCounts.set(intent, (intentCounts.get(intent) || 0) + 1);
    }
  }

  const total = Array.from(intentCounts.values()).reduce((a, b) => a + b, 0);
  if (total === 0) {
    return [];
  }

  const items: IntentDistributionItem[] = Array.from(intentCounts.entries())
    .map(([intent, count]) => {
      const colorInfo = getIntentColor(intent);
      return {
        intent,
        label: colorInfo.label,
        count,
        color: colorInfo.hex,
        percentage: Math.round((count / total) * 1000) / 10,
      };
    })
    .sort((a, b) => b.count - a.count);

  return items;
}

function computeWordCloud(): WordCloudData {
  const sessionIds = getSessionIdsFromStorage();
  const globalCounts = new Map<string, number>();

  for (const sessionId of sessionIds) {
    const messages = getSessionMessages(sessionId);
    for (const msg of messages) {
      const keywords = extractKeywords(msg.content || '');
      for (const [word, count] of keywords) {
        globalCounts.set(word, (globalCounts.get(word) || 0) + count);
      }
    }
  }

  if (globalCounts.size === 0) {
    return { words: [], maxWeight: 0, minWeight: 0 };
  }

  const sorted = Array.from(globalCounts.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 60);

  const maxWeight = sorted[0][1];
  const minWeight = sorted[sorted.length - 1][1];

  const colorPalette = [
    '#D97706', '#F59E0B', '#0D9488', '#8B5CF6', '#E11D48',
    '#3B82F6', '#10B981', '#6B6680', '#F472B6', '#06B6D4',
  ];

  const words: WordCloudItem[] = sorted.map(([text, weight], index) => {
    const isTech = TECH_KEYWORDS.has(text.toLowerCase());
    const color = isTech
      ? '#F59E0B'
      : colorPalette[index % colorPalette.length];
    return { text, weight, color };
  });

  return { words, maxWeight, minWeight };
}

// ==================== Store ====================

const initialState: AnalyticsState = {
  trendData: [],
  intentDistribution: [],
  wordCloud: { words: [], maxWeight: 0, minWeight: 0 },
  lastUpdated: 0,
  isComputing: false,
};

export const useAnalyticsStore = create<AnalyticsStore>((set) => ({
  ...initialState,

  computeAnalytics: () => {
    set({ isComputing: true });
    const trendData = computeTrendData();
    const intentDistribution = computeIntentDistribution();
    const wordCloud = computeWordCloud();
    set({
      trendData,
      intentDistribution,
      wordCloud,
      lastUpdated: Date.now(),
      isComputing: false,
    });
  },

  setTrendData: (data) => set({ trendData: data }),
  setIntentDistribution: (data) => set({ intentDistribution: data }),
  setWordCloud: (data) => set({ wordCloud: data }),
}));

// ==================== 选择器 Hook ====================

export function useTrendData(): TrendDataPoint[] {
  return useAnalyticsStore((s) => s.trendData);
}

export function useAnalyticsIntentDistribution(): IntentDistributionItem[] {
  return useAnalyticsStore((s) => s.intentDistribution);
}

export function useAnalyticsWordCloud(): WordCloudData {
  return useAnalyticsStore((s) => s.wordCloud);
}

export function useAnalyticsLastUpdated(): number {
  return useAnalyticsStore((s) => s.lastUpdated);
}

export function useAnalyticsComputing(): boolean {
  return useAnalyticsStore((s) => s.isComputing);
}

export function useGlobalAnalytics(): GlobalAnalytics {
  return useAnalyticsStore((s) => ({
    sessionCount: getSessionIdsFromStorage().length,
    totalTurns: s.trendData.reduce((sum, d) => sum + d.turns, 0),
    totalMessages: s.trendData.reduce((sum, d) => sum + d.messages, 0),
    avgLatencyMs:
      s.trendData.length > 0
        ? Math.round(
            s.trendData.reduce((sum, d) => sum + d.avgLatency, 0) /
              s.trendData.length
          )
        : 0,
    trendData: s.trendData,
    intentDistribution: s.intentDistribution,
    wordCloud: s.wordCloud,
    activeSessionIds: getSessionIdsFromStorage(),
  }));
}

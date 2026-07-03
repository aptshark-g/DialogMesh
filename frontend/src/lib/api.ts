// FILE: src/lib/api.ts

import type {
  CreateSessionResponse,
  SendMessageResponse,
  ClarifyResponse,
  HistoryResponse,
  SessionStatusResponse,
  HealthResponse,
  SessionSummary,
} from '../types/api';
import type { CognitiveProfile, ProfileStats, IntentDistribution } from '../types/profile';
import { getApiConfig } from './config';

function getBaseUrl(): string {
  return getApiConfig().restBaseUrl;
}

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    ...options,
  });

  if (!response.ok) {
    const text = await response.text().catch(() => 'Unknown error');
    throw new Error(`HTTP ${response.status}: ${text}`);
  }

  return response.json() as Promise<T>;
}

// ─── Session API ──────────────────────────────────────────────────────────────

export async function createSession(): Promise<CreateSessionResponse> {
  return fetchJson<CreateSessionResponse>(`${getBaseUrl()}/v3/session`, {
    method: 'POST',
  });
}

export async function sendMessage(
  sessionId: string,
  content: string
): Promise<SendMessageResponse> {
  return fetchJson<SendMessageResponse>(`${getBaseUrl()}/v3/session/${sessionId}/message`, {
    method: 'POST',
    body: JSON.stringify({ content }),
  });
}

export async function sendClarification(
  sessionId: string,
  clarificationId: string,
  answers: Record<string, unknown>
): Promise<ClarifyResponse> {
  return fetchJson<ClarifyResponse>(`${getBaseUrl()}/v3/session/${sessionId}/clarify`, {
    method: 'POST',
    body: JSON.stringify({ clarification_id: clarificationId, answers }),
  });
}

export async function getHistory(
  sessionId: string,
  limit?: number,
  offset?: number
): Promise<HistoryResponse> {
  const params = new URLSearchParams();
  if (limit !== undefined) params.append('limit', String(limit));
  if (offset !== undefined) params.append('offset', String(offset));
  const query = params.toString();
  return fetchJson<HistoryResponse>(
    `${getBaseUrl()}/v3/session/${sessionId}/history${query ? `?${query}` : ''}`
  );
}

export async function getSessionStatus(sessionId: string): Promise<SessionStatusResponse> {
  return fetchJson<SessionStatusResponse>(`${getBaseUrl()}/v3/session/${sessionId}/status`);
}

export async function getHealth(): Promise<HealthResponse> {
  return fetchJson<HealthResponse>(`${getBaseUrl()}/v3/health`);
}

// ─── Profile API ──────────────────────────────────────────────────────────────

export async function getCognitiveProfile(sessionId: string): Promise<CognitiveProfile> {
  return fetchJson<CognitiveProfile>(`${getBaseUrl()}/v3/session/${sessionId}/profile`);
}

export async function getProfileStats(sessionId: string): Promise<ProfileStats> {
  return fetchJson<ProfileStats>(`${getBaseUrl()}/v3/session/${sessionId}/profile/stats`);
}

export async function getIntentDistribution(sessionId: string): Promise<IntentDistribution[]> {
  return fetchJson<IntentDistribution[]>(`${getBaseUrl()}/v3/session/${sessionId}/profile/intents`);
}

// ─── Dashboard Helpers ──────────────────────────────────────────────────────

export function buildSessionSummaries(
  sessionIds: string[]
): Promise<SessionSummary[]> {
  // 并行获取所有会话状态
  return Promise.all(
    sessionIds.map(async (id) => {
      try {
        const status = await getSessionStatus(id);
        const history = await getHistory(id, 1);
        return {
          session_id: id,
          created_at: status.last_activity_at,
          last_activity_at: status.last_activity_at,
          state: status.state,
          current_turn: status.current_turn,
          message_preview: history.messages[0]?.content,
        };
      } catch {
        return {
          session_id: id,
          created_at: '',
          last_activity_at: '',
          state: 'closed' as const,
          current_turn: 0,
          message_preview: undefined,
        };
      }
    })
  );
}

export function getWsUrl(sessionId: string): string {
  const wsBase = getApiConfig().wsBaseUrl;
  return `${wsBase}/v3/ws/${sessionId}`;
}

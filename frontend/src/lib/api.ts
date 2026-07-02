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

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

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
  return fetchJson<CreateSessionResponse>(`${BASE_URL}/v3/session`, {
    method: 'POST',
  });
}

export async function sendMessage(
  sessionId: string,
  content: string
): Promise<SendMessageResponse> {
  return fetchJson<SendMessageResponse>(`${BASE_URL}/v3/session/${sessionId}/message`, {
    method: 'POST',
    body: JSON.stringify({ content }),
  });
}

export async function sendClarification(
  sessionId: string,
  clarificationId: string,
  answers: Record<string, unknown>
): Promise<ClarifyResponse> {
  return fetchJson<ClarifyResponse>(`${BASE_URL}/v3/session/${sessionId}/clarify`, {
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
    `${BASE_URL}/v3/session/${sessionId}/history${query ? `?${query}` : ''}`
  );
}

export async function getSessionStatus(sessionId: string): Promise<SessionStatusResponse> {
  return fetchJson<SessionStatusResponse>(`${BASE_URL}/v3/session/${sessionId}/status`);
}

export async function getHealth(): Promise<HealthResponse> {
  return fetchJson<HealthResponse>(`${BASE_URL}/v3/health`);
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
  const wsBase = BASE_URL.replace(/^http/, 'ws');
  return `${wsBase}/v3/ws/${sessionId}`;
}

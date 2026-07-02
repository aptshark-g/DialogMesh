import type {
  CreateSessionResponse,
  SendMessageResponse,
  ClarifyResponse,
  HistoryResponse,
  SessionStatusResponse,
  HealthResponse,
} from '../types/api.ts';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

async function apiFetch<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${url}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!response.ok) {
    const err = await response.text();
    throw new Error(`HTTP ${response.status}: ${err}`);
  }
  return response.json() as Promise<T>;
}

export function createSession(): Promise<CreateSessionResponse> {
  return apiFetch<CreateSessionResponse>('/v3/session', { method: 'POST' });
}

export function sendMessage(sessionId: string, content: string): Promise<SendMessageResponse> {
  return apiFetch<SendMessageResponse>(`/v3/session/${sessionId}/message`, {
    method: 'POST',
    body: JSON.stringify({ content }),
  });
}

export function submitClarification(
  sessionId: string,
  clarificationId: string,
  answers: Record<string, unknown>
): Promise<ClarifyResponse> {
  return apiFetch<ClarifyResponse>(`/v3/session/${sessionId}/clarify`, {
    method: 'POST',
    body: JSON.stringify({ clarification_id: clarificationId, answers }),
  });
}

export function getHistory(sessionId: string, limit?: number, offset?: number): Promise<HistoryResponse> {
  const params = new URLSearchParams();
  if (limit !== undefined) params.append('limit', String(limit));
  if (offset !== undefined) params.append('offset', String(offset));
  const qs = params.toString();
  return apiFetch<HistoryResponse>(`/v3/session/${sessionId}/history${qs ? `?${qs}` : ''}`);
}

export function getSessionStatus(sessionId: string): Promise<SessionStatusResponse> {
  return apiFetch<SessionStatusResponse>(`/v3/session/${sessionId}/status`);
}

export function getHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>('/v3/health');
}

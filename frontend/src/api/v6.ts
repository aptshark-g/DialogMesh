// FILE: src/api/v6.ts
// DialogMesh v6 GUI API — Profile, Graph, Rules, Feedback, Sessions

import type {
  V6ProfileResponse,
  V6ProfileEditRequest,
  V6ProfileEditResponse,
  V6TraceResponse,
  V6AbcResponse,
  V6MindResponse,
  V6GraphResponse,
  V6DiscourseTreeResponse,
  V6ObjectsResponse,
  V6RulesResponse,
  V6RuleEditRequest,
  V6RuleEditResponse,
  V6FeedbackRequest,
  V6FeedbackResponse,
  V6PersistenceResponse,
  V6SessionListItem,
  V6SessionData,
} from '../types/api';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

async function apiFetch<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${url}`, {
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    ...options,
  });
  if (!response.ok) {
    const err = await response.text().catch(() => 'Unknown error');
    throw new Error(`HTTP ${response.status}: ${err}`);
  }
  return response.json() as Promise<T>;
}

// ─── Profile ─────────────────────────────────────────────────────────────────

export function getProfile(): Promise<V6ProfileResponse> {
  return apiFetch<V6ProfileResponse>('/v6/profile');
}

export function editProfile(req: V6ProfileEditRequest): Promise<V6ProfileEditResponse> {
  return apiFetch<V6ProfileEditResponse>('/v6/profile', {
    method: 'PUT',
    body: JSON.stringify(req),
  });
}

// ─── Trace / ABC / Mind ──────────────────────────────────────────────────────

export function getTrace(): Promise<V6TraceResponse> {
  return apiFetch<V6TraceResponse>('/v6/trace');
}

export function getAbc(): Promise<V6AbcResponse> {
  return apiFetch<V6AbcResponse>('/v6/abc');
}

export function getMind(): Promise<V6MindResponse> {
  return apiFetch<V6MindResponse>('/v6/mind');
}

// ─── Visualization ────────────────────────────────────────────────────────────

export function getGraph(): Promise<V6GraphResponse> {
  return apiFetch<V6GraphResponse>('/v6/graph');
}

export function getDiscourseTree(): Promise<V6DiscourseTreeResponse> {
  return apiFetch<V6DiscourseTreeResponse>('/v6/discourse-tree');
}

export function getObjects(): Promise<V6ObjectsResponse> {
  return apiFetch<V6ObjectsResponse>('/v6/objects');
}

// ─── Rules ─────────────────────────────────────────────────────────────────

export function getRules(): Promise<V6RulesResponse> {
  return apiFetch<V6RulesResponse>('/v6/rules');
}

export function editRule(req: V6RuleEditRequest): Promise<V6RuleEditResponse> {
  return apiFetch<V6RuleEditResponse>('/v6/rules', {
    method: 'PUT',
    body: JSON.stringify(req),
  });
}

// ─── Feedback ────────────────────────────────────────────────────────────────

export function submitFeedback(req: V6FeedbackRequest): Promise<V6FeedbackResponse> {
  return apiFetch<V6FeedbackResponse>('/v6/feedback', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

// ─── Persistence & Sessions ────────────────────────────────────────────────

export function getPersistence(): Promise<V6PersistenceResponse> {
  return apiFetch<V6PersistenceResponse>('/v6/persistence');
}

export function getSessions(): Promise<V6SessionListItem[]> {
  return apiFetch<V6SessionListItem[]>('/v6/sessions');
}

export function getSessionData(filename: string): Promise<V6SessionData> {
  return apiFetch<V6SessionData>(`/v6/session/${encodeURIComponent(filename)}`);
}

// FILE: src/api/v4.ts
// DialogMesh v4 Event API — 前端客户端

import type {
  EventRequest,
  EventResponse,
  IngestResponse,
  StatusResponse,
  InspectResponse,
  HealthResponse,
  CheckpointResponse,
} from '../types/api';
import { sessionHeaders } from './sessionHeaders';

// B5（2026-08-07）: 默认相对路径 → 同源代理
const BASE_URL = import.meta.env.VITE_API_BASE_URL || '';
// v4 API 的 P0 Bearer 鉴权 (core/agent/v4/api.py auth_middleware)
const AUTH_TOKEN = import.meta.env.VITE_API_TOKEN || 'dev-token';

async function apiFetch<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${url}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      Authorization: `Bearer ${AUTH_TOKEN}`,
      ...sessionHeaders(),
      ...(options?.headers || {}),
    },
  });
  if (!response.ok) {
    const err = await response.text().catch(() => 'Unknown error');
    throw new Error(`HTTP ${response.status}: ${err}`);
  }
  return response.json() as Promise<T>;
}

// ─── Core Event API ──────────────────────────────────────────────────────────

/**
 * Send a dialog message to the v4 cognitive runtime.
 * Returns the LLM response directly in the `response` field.
 */
export function sendEvent(
  text: string,
  eventId?: string,
  traceId?: string
): Promise<EventResponse> {
  const req: EventRequest = {
    event_id: eventId || `evt_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    kind: 'dialog.message',
    payload: { text },
    trace_id: traceId || '',
  };
  return apiFetch<EventResponse>('/v4/event', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

/**
 * Ingest external document into the cognitive chain.
 */
export function ingestDocument(
  sourcePath: string,
  content?: string,
  fileType: string = 'markdown'
): Promise<IngestResponse> {
  return apiFetch<IngestResponse>('/v4/ingest', {
    method: 'POST',
    body: JSON.stringify({ source_path: sourcePath, content, file_type: fileType }),
  });
}

/**
 * Get runtime engine stats.
 */
export function getStatus(): Promise<StatusResponse> {
  return apiFetch<StatusResponse>('/v4/status');
}

/**
 * Inspect system state (observations, hypotheses, knowledge, skills, world, context).
 */
export function inspectSystem(module: string, limit: number = 10, detail?: boolean): Promise<InspectResponse> {
  const params = new URLSearchParams();
  params.append('limit', String(limit));
  if (detail) params.append('detail', 'true');
  return apiFetch<InspectResponse>(`/v4/inspect/${module}?${params.toString()}`);
}

/**
 * Manually trigger Slow Path checkpoint.
 */
export function triggerCheckpoint(): Promise<CheckpointResponse> {
  return apiFetch<CheckpointResponse>('/v4/checkpoint', { method: 'POST' });
}

/**
 * Health check.
 */
export function getHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>('/v4/health');
}

// ─── WebSocket helpers ─────────────────────────────────────────────────────

export function getV4WsUrl(): string {
  const wsBase = import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:8000';
  return `${wsBase}/v4/ws`;
}

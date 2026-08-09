import type {
  CreateSessionResponse,
  SendMessageResponse,
  ClarifyResponse,
  HistoryResponse,
  SessionStatusResponse,
  HealthResponse,
} from '../types/api.ts';
import { sessionHeaders } from './sessionHeaders';

// B5（2026-08-07）: 默认相对路径 → 同源代理
const BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

async function apiFetch<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${url}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...sessionHeaders(),
      ...(options?.headers || {}),
    },
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

export function sendMessage(sessionId: string, content: string, provider?: string, model?: string): Promise<SendMessageResponse> {
  const body: any = { content };
  if (provider) body.provider = provider;
  if (model) body.model = model;
  return apiFetch<SendMessageResponse>(`/v3/session/${sessionId}/message`, {
    method: 'POST',
    body: JSON.stringify(body),
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

export function editDAG(sessionId: string, instruction: string, currentNodes: any[]): Promise<{status: string; nodes: any[]; error?: string}> {
  return fetch(`${BASE_URL}/v3/session/${sessionId}/dag-edit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ instruction, current_nodes: currentNodes }),
  }).then(res => res.json());
}

export interface TaskGraphData {
  nodes: any[];
  edges: any[];
  version?: number;
}

/** 版本冲突（409）——服务端已有更新版本, 本地编辑被拒绝覆盖。 */
export class TaskGraphConflictError extends Error {
  currentVersion: number;
  serverNodes: any[];
  serverEdges: any[];

  constructor(detail: any) {
    super('任务规划已被更新, 本地编辑与服务器版本冲突');
    this.name = 'TaskGraphConflictError';
    this.currentVersion = detail?.current_version ?? 0;
    this.serverNodes = detail?.nodes ?? [];
    this.serverEdges = detail?.edges ?? [];
  }
}

/**
 * 保存任务图（乐观更新 + 版本冲突检测）。
 * 带 version = 冲突检测（409 → TaskGraphConflictError）;
 * 不带 version = 强制覆盖（向后兼容旧调用）。
 */
export function saveTaskGraph(
  sessionId: string,
  nodes: any[],
  edges: any[],
  version?: number,
): Promise<TaskGraphData> {
  const body: any = { nodes, edges };
  if (version !== undefined) body.version = version;
  return fetch(`${BASE_URL}/v3/session/${sessionId}/task-graph`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then(async (res) => {
    if (res.status === 409) {
      const data = await res.json().catch(() => null);
      throw new TaskGraphConflictError(data?.detail);
    }
    if (!res.ok) {
      const err = await res.text();
      throw new Error(`HTTP ${res.status}: ${err}`);
    }
    return res.json() as Promise<TaskGraphData>;
  });
}

export function getTaskGraph(sessionId: string): Promise<TaskGraphData> {
  return apiFetch<TaskGraphData>(`/v3/session/${sessionId}/task-graph`);
}

export function getHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>('/v3/health');
}

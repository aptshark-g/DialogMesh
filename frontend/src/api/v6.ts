// FILE: src/api/v6.ts
// DialogMesh v6 GUI API — 42 endpoints covering Profile, Graph, Rules,
// Providers, Router, DeepChain, Pipeline, Metrics, Sessions

import type {
  V6ProfileResponse, V6ProfileEditRequest, V6ProfileEditResponse,
  V6TraceResponse, V6AbcResponse, V6MindResponse, V6MindFullResponse,
  V6GraphResponse, V6DiscourseTreeResponse, V6ObjectsResponse,
  V6RulesResponse, V6RuleEditRequest, V6RuleEditResponse,
  V6FeedbackRequest, V6FeedbackResponse,
  V6ProvidersResponse, V6ProviderSwitchRequest, V6ProviderSwitchResponse,
  V6TokensResponse,
  V6RouterModesResponse, V6RouterModesRequest,
  V6RelationsResponse, V6CausalResponse, V6BehaviorResponse, V6EngineeringResponse,
  V6PipelineResponse, V6ExtractionResponse, V6PerspectivesResponse,
  V6ParametersResponse, V6ParameterEditRequest,
  V6ContextResponse, V6ContextConfigRequest,
  V6MetricsResponse,
  V6PersistenceResponse, V6PersistenceGraphsResponse,
  V6SessionListItem, V6SessionData,
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

// ═══════════════════════════════════════════════════════════════════════════
// 画像 & 信号 (Profile & Signals)
// ═══════════════════════════════════════════════════════════════════════════

export function getProfile(): Promise<V6ProfileResponse> {
  return apiFetch<V6ProfileResponse>('/v6/profile');
}

export function editProfile(req: V6ProfileEditRequest): Promise<V6ProfileEditResponse> {
  return apiFetch<V6ProfileEditResponse>('/v6/profile', {
    method: 'PUT',
    body: JSON.stringify(req),
  });
}

export function getTrace(): Promise<V6TraceResponse> {
  return apiFetch<V6TraceResponse>('/v6/trace');
}

export function getAbc(): Promise<V6AbcResponse> {
  return apiFetch<V6AbcResponse>('/v6/abc');
}

export function getMind(): Promise<V6MindResponse> {
  return apiFetch<V6MindResponse>('/v6/mind');
}

export function getMindFull(): Promise<V6MindFullResponse> {
  return apiFetch<V6MindFullResponse>('/v6/mind/full');
}

// ═══════════════════════════════════════════════════════════════════════════
// 图/树/对象 (Visualization)
// ═══════════════════════════════════════════════════════════════════════════

export function getGraph(): Promise<V6GraphResponse> {
  return apiFetch<V6GraphResponse>('/v6/graph');
}

export function getDiscourseTree(): Promise<V6DiscourseTreeResponse> {
  return apiFetch<V6DiscourseTreeResponse>('/v6/discourse-tree');
}

export function getObjects(): Promise<V6ObjectsResponse> {
  return apiFetch<V6ObjectsResponse>('/v6/objects');
}

// ═══════════════════════════════════════════════════════════════════════════
// 深层链 (Deep Chain)
// ═══════════════════════════════════════════════════════════════════════════

export function getRelations(): Promise<V6RelationsResponse> {
  return apiFetch<V6RelationsResponse>('/v6/relations');
}

export function getCausal(): Promise<V6CausalResponse> {
  return apiFetch<V6CausalResponse>('/v6/causal');
}

export function getBehavior(): Promise<V6BehaviorResponse> {
  return apiFetch<V6BehaviorResponse>('/v6/behavior');
}

export function getEngineering(): Promise<V6EngineeringResponse> {
  return apiFetch<V6EngineeringResponse>('/v6/engineering');
}

// ═══════════════════════════════════════════════════════════════════════════
// 规则 & 反馈 (Rules & Feedback)
// ═══════════════════════════════════════════════════════════════════════════

export function getRules(): Promise<V6RulesResponse> {
  return apiFetch<V6RulesResponse>('/v6/rules');
}

export function editRule(req: V6RuleEditRequest): Promise<V6RuleEditResponse> {
  return apiFetch<V6RuleEditResponse>('/v6/rules', {
    method: 'PUT',
    body: JSON.stringify(req),
  });
}

export function submitFeedback(req: V6FeedbackRequest): Promise<V6FeedbackResponse> {
  return apiFetch<V6FeedbackResponse>('/v6/feedback', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// 提供商 & 运维 (Providers & Ops)
// ═══════════════════════════════════════════════════════════════════════════

export function getProviders(): Promise<V6ProvidersResponse> {
  return apiFetch<V6ProvidersResponse>('/v6/providers');
}

export function switchProvider(req: V6ProviderSwitchRequest): Promise<V6ProviderSwitchResponse> {
  return apiFetch<V6ProviderSwitchResponse>('/v6/providers', {
    method: 'PUT',
    body: JSON.stringify(req),
  });
}

export function getTokens(): Promise<V6TokensResponse> {
  return apiFetch<V6TokensResponse>('/v6/providers/tokens');
}

export function testProviderConnection(): Promise<{ healthy: boolean; latency_ms: number }> {
  return apiFetch<{ healthy: boolean; latency_ms: number }>('/v6/providers/test', { method: 'POST' });
}

export function getMetrics(): Promise<V6MetricsResponse> {
  return apiFetch<V6MetricsResponse>('/v6/metrics');
}

export function updateContextConfig(req: V6ContextConfigRequest): Promise<{ updated: string[]; count: number }> {
  return apiFetch<{ updated: string[]; count: number }>('/v6/context/config', {
    method: 'PUT',
    body: JSON.stringify(req),
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// 路由/Switch (Gateway)
// ═══════════════════════════════════════════════════════════════════════════

export function getRouterModes(): Promise<V6RouterModesResponse> {
  return apiFetch<V6RouterModesResponse>('/v6/router/modes');
}

export function setRouterModes(req: V6RouterModesRequest): Promise<{ updated: string[]; count: number }> {
  return apiFetch<{ updated: string[]; count: number }>('/v6/router/modes', {
    method: 'PUT',
    body: JSON.stringify(req),
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// 业务管道 (Pipeline)
// ═══════════════════════════════════════════════════════════════════════════

export function getPipeline(): Promise<V6PipelineResponse> {
  return apiFetch<V6PipelineResponse>('/v6/pipeline');
}

export function getExtraction(): Promise<V6ExtractionResponse> {
  return apiFetch<V6ExtractionResponse>('/v6/extraction');
}

export function getPerspectives(): Promise<V6PerspectivesResponse> {
  return apiFetch<V6PerspectivesResponse>('/v6/perspectives');
}

export function getParameters(): Promise<V6ParametersResponse> {
  return apiFetch<V6ParametersResponse>('/v6/parameters');
}

export function editParameters(req: V6ParameterEditRequest): Promise<{ updated: string[]; count: number }> {
  return apiFetch<{ updated: string[]; count: number }>('/v6/parameters', {
    method: 'PUT',
    body: JSON.stringify(req),
  });
}

export function getContext(): Promise<V6ContextResponse> {
  return apiFetch<V6ContextResponse>('/v6/context');
}

// ═══════════════════════════════════════════════════════════════════════════
// 持久化 & 会话 (Persistence & Sessions)
// ═══════════════════════════════════════════════════════════════════════════

export function getPersistence(): Promise<V6PersistenceResponse> {
  return apiFetch<V6PersistenceResponse>('/v6/persistence');
}

export function getPersistenceGraphs(): Promise<V6PersistenceGraphsResponse> {
  return apiFetch<V6PersistenceGraphsResponse>('/v6/persistence/graphs');
}

export function getSessions(): Promise<V6SessionListItem[]> {
  return apiFetch<V6SessionListItem[]>('/v6/sessions');
}

export function getSessionData(filename: string): Promise<V6SessionData> {
  return apiFetch<V6SessionData>(`/v6/session/${encodeURIComponent(filename)}`);
}

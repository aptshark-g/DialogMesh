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
  // v8 Gateway
  V6GatewayProvidersResponse, V6GatewayProviderConfigRequest, V6GatewayProviderConfigResponse,
  V6GatewayTestResponse, V6GatewayModelsResponse,
  V6GatewayActiveRequest, V6GatewayActiveResponse,
  V6GatewayConfig, V6GatewayConfigRequest, V6GatewayUsage, V6GatewayStats, V6GatewayHealth,
  V6ServiceStatus,
  // v8 Meta
  V6MetaStatsResponse, V6MetaQueueResponse,
  // v8 Versions
  V6VersionsResponse,
  // v8 Inertia
  V6InertiaResponse,
  // v8 Behavior
  V6BehaviorPatternsResponse, V6BehaviorFeedbackRequest,
  // v8 Annotations
  V6AnnotationsResponse, V6AnnotationStatsResponse,
  // v8 Corrections
  V6ProfileCorrectionsResponse, V6ProfileCorrection,
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

// ═══════════════════════════════════════════════════════════════════════════
// 网关 (Gateway) — switch 代理
// ═══════════════════════════════════════════════════════════════════════════

export function getGatewayProviders(): Promise<V6GatewayProvidersResponse> {
  return apiFetch<V6GatewayProvidersResponse>('/v6/gateway/providers');
}

export function configGatewayProvider(
  name: string,
  req: V6GatewayProviderConfigRequest
): Promise<V6GatewayProviderConfigResponse> {
  return apiFetch<V6GatewayProviderConfigResponse>(`/v6/gateway/providers/${encodeURIComponent(name)}`, {
    method: 'PUT',
    body: JSON.stringify(req),
  });
}

export function testGatewayProvider(name: string): Promise<V6GatewayTestResponse> {
  return apiFetch<V6GatewayTestResponse>(`/v6/gateway/providers/${encodeURIComponent(name)}/test`, {
    method: 'POST',
  });
}

export function fetchGatewayProviderModels(name: string): Promise<V6GatewayModelsResponse> {
  return apiFetch<V6GatewayModelsResponse>(`/v6/gateway/providers/${encodeURIComponent(name)}/models`, {
    method: 'POST',
  });
}

export function setGatewayActive(req: V6GatewayActiveRequest): Promise<V6GatewayActiveResponse> {
  return apiFetch<V6GatewayActiveResponse>('/v6/gateway/active', {
    method: 'PUT',
    body: JSON.stringify(req),
  });
}

export function getGatewayConfig(): Promise<V6GatewayConfig> {
  return apiFetch<V6GatewayConfig>('/v6/gateway/config');
}

export function updateGatewayConfig(req: V6GatewayConfigRequest): Promise<V6GatewayConfig> {
  return apiFetch<V6GatewayConfig>('/v6/gateway/config', {
    method: 'PUT',
    body: JSON.stringify(req),
  });
}

export function getGatewayUsage(): Promise<V6GatewayUsage> {
  return apiFetch<V6GatewayUsage>('/v6/gateway/usage');
}

export function getGatewayStats(): Promise<V6GatewayStats> {
  return apiFetch<V6GatewayStats>('/v6/gateway/stats');
}

export function getGatewayHealth(): Promise<V6GatewayHealth> {
  return apiFetch<V6GatewayHealth>('/v6/gateway/health');
}

export function reloadGateway(): Promise<{ reloaded: boolean }> {
  return apiFetch<{ reloaded: boolean }>('/v6/gateway/reload', { method: 'POST' });
}

// ═══════════════════════════════════════════════════════════════════════════
// 服务检测 (Service Status)
// ═══════════════════════════════════════════════════════════════════════════

export async function checkServiceStatus(url: string, name: string, path: string = '/v4/health'): Promise<V6ServiceStatus> {
  const start = performance.now();
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);
    const response = await fetch(`${url}${path}`, {
      signal: controller.signal,
      headers: { Accept: 'application/json' },
    });
    clearTimeout(timeout);
    const latency = Math.round(performance.now() - start);
    if (response.ok) {
      const data = await response.json().catch(() => ({ status: 'ok' }));
      return { name, url, healthy: true, latency_ms: latency, version: data.version || null, error: null };
    }
    return { name, url, healthy: false, latency_ms: latency, version: null, error: `HTTP ${response.status}` };
  } catch (err) {
    return {
      name, url, healthy: false, latency_ms: null, version: null,
      error: err instanceof Error ? err.message : '连接失败',
    };
  }
}

export function checkDialogMeshStatus(): Promise<V6ServiceStatus> {
  return checkServiceStatus(BASE_URL, 'DialogMesh API', '/v4/health');
}

export function checkSwitchGatewayStatus(): Promise<V6ServiceStatus> {
  const switchUrl = import.meta.env.VITE_SWITCH_URL || 'http://localhost:8080';
  return checkServiceStatus(switchUrl, 'Switch Gateway', '/v1/health');
}
// ═══════════════════════════════════════════════════════════════════════════
// 元认知 (Meta Cognition)
// ═══════════════════════════════════════════════════════════════════════════

export function getMetaStats(): Promise<V6MetaStatsResponse> {
  return apiFetch<V6MetaStatsResponse>('/v6/meta/stats');
}

export function getMetaQueue(): Promise<V6MetaQueueResponse> {
  return apiFetch<V6MetaQueueResponse>('/v6/meta/queue');
}

export function triggerMetaScan(): Promise<{ triggered: boolean }> {
  return apiFetch<{ triggered: boolean }>('/v6/meta/scan', { method: 'POST' });
}

// ═══════════════════════════════════════════════════════════════════════════
// 版本 (Versions)
// ═══════════════════════════════════════════════════════════════════════════

export function getVersions(category: string): Promise<V6VersionsResponse> {
  return apiFetch<V6VersionsResponse>(`/v6/versions/${encodeURIComponent(category)}`);
}

export function rollbackVersion(category: string, commitId: string): Promise<{ rolled_back: boolean }> {
  return apiFetch<{ rolled_back: boolean }>(`/v6/versions/${encodeURIComponent(category)}/rollback`, {
    method: 'POST',
    body: JSON.stringify({ commit_id: commitId }),
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// 惯性 (Inertia)
// ═══════════════════════════════════════════════════════════════════════════

export function getInertia(): Promise<V6InertiaResponse> {
  return apiFetch<V6InertiaResponse>('/v6/inertia');
}

// ═══════════════════════════════════════════════════════════════════════════
// 行为模式 (Behavior Patterns)
// ═══════════════════════════════════════════════════════════════════════════

export function getBehaviorPatterns(): Promise<V6BehaviorPatternsResponse> {
  return apiFetch<V6BehaviorPatternsResponse>('/v6/behavior/patterns');
}

export function submitBehaviorFeedback(req: V6BehaviorFeedbackRequest): Promise<{ updated: boolean }> {
  return apiFetch<{ updated: boolean }>('/v6/behavior/feedback', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// 注释 (Annotations)
// ═══════════════════════════════════════════════════════════════════════════

export function getAnnotations(): Promise<V6AnnotationsResponse> {
  return apiFetch<V6AnnotationsResponse>('/v6/annotate');
}

export function addAnnotation(text: string): Promise<{ id: string }> {
  return apiFetch<{ id: string }>('/v6/annotate', {
    method: 'POST',
    body: JSON.stringify({ text }),
  });
}

export function getAnnotationStats(): Promise<V6AnnotationStatsResponse> {
  return apiFetch<V6AnnotationStatsResponse>('/v6/annotate/stats');
}

// ═══════════════════════════════════════════════════════════════════════════
// 画像修正 (Profile Corrections)
// ═══════════════════════════════════════════════════════════════════════════

export function getProfileCorrections(): Promise<V6ProfileCorrectionsResponse> {
  return apiFetch<V6ProfileCorrectionsResponse>('/v6/profile/corrections');
}

export function reviewProfileCorrections(): Promise<{ reviewed: boolean }> {
  return apiFetch<{ reviewed: boolean }>('/v6/profile/corrections/review', { method: 'POST' });
}

// ═══════════════════════════════════════════════════════════════════════════
// 本地 Provider 模板兜底 (当后端不可用时使用)
// ═══════════════════════════════════════════════════════════════════════════

export const DEFAULT_PROVIDERS: V6GatewayProvidersResponse = {
  providers: [
    {
      name: 'deepseek',
      display_name: 'DeepSeek',
      configured: false,
      healthy: null,
      base_url: 'https://api.deepseek.com',
      models: [
        { id: 'deepseek-v4-flash', display: 'DeepSeek V4 Flash', context: 128000, cost_in: 0.27, cost_out: 1.10 },
        { id: 'deepseek-v4-pro', display: 'DeepSeek V4 Pro', context: 64000, cost_in: 0.55, cost_out: 2.19 },
      ],
    },
    {
      name: 'openai',
      display_name: 'OpenAI',
      configured: false,
      healthy: null,
      base_url: 'https://api.openai.com',
      models: [
        { id: 'gpt-4o', display: 'GPT-4o', context: 128000, cost_in: 2.50, cost_out: 10.00 },
        { id: 'gpt-4o-mini', display: 'GPT-4o Mini', context: 128000, cost_in: 0.15, cost_out: 0.60 },
      ],
    },
    {
      name: 'lmstudio',
      display_name: 'LM Studio',
      configured: false,
      healthy: null,
      base_url: 'http://127.0.0.1:1234/v1',
      models: [
        { id: 'nvidia/nemotron-3-nano-4b', display: 'Nemotron Nano 4B', context: 4096, cost_in: 0, cost_out: 0 },
      ],
    },
    {
      name: 'ollama',
      display_name: 'Ollama',
      configured: false,
      healthy: null,
      base_url: 'http://localhost:11434',
      models: [
        { id: 'qwen2.5:7b', display: 'Qwen 2.5 7B', context: 32768, cost_in: 0, cost_out: 0 },
        { id: 'llama3.1:8b', display: 'Llama 3.1 8B', context: 128000, cost_in: 0, cost_out: 0 },
      ],
    },
  ],
  active_provider: '',
  active_model: '',
};

export function submitProfileCorrections(corrections: V6ProfileCorrection[]): Promise<{ reviewed: boolean }> {
  return apiFetch<{ reviewed: boolean }>('/v6/profile/corrections/review', {
    method: 'POST',
    body: JSON.stringify(corrections),
  });
}

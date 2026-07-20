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
  // v8 Meta Retrospect
  V6MetaRetrospectResponse,
  // v8 Behavior Predict / Belief / OCEAN Params
  V6BehaviorPredictResponse, V6BeliefResponse, V6OceanParamsResponse,
  // v8 Engineering Chain
  V6SubgraphResponse,
  V6RecursiveMapResponse, V6RecursiveMapControlRequest, V6RecursiveMapControlResponse,
  V6EngineeringModulesResponse, V6EngineeringConstraintEditRequest, V6EngineeringConstraintEditResponse,
  // v8 Visualization Edit
  V6GraphEditRequest, V6GraphEditResponse,
  V6DiscourseTreeEditRequest, V6DiscourseTreeEditResponse,
  V6ObjectEditRequest, V6ObjectEditResponse,
  V6RelationEditRequest, V6RelationEditResponse,
  V6IrEditRequest, V6IrEditResponse,
  // v8 Gateway Provider Add/Remove
  V6GatewayProviderAddRequest, V6GatewayProviderMutationResponse,
  // v10 Scheduler & Degradation
  V6SyncResponse, V6CausalChainResponse, V6DegradationResponse,
  V6TtlResponse, V6TtlTickResponse, V6SubgraphCacheResponse,
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

export function addGatewayProvider(req: V6GatewayProviderAddRequest): Promise<V6GatewayProviderMutationResponse> {
  return apiFetch<V6GatewayProviderMutationResponse>('/v6/gateway/providers', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export function removeGatewayProvider(name: string): Promise<V6GatewayProviderMutationResponse> {
  return apiFetch<V6GatewayProviderMutationResponse>(`/v6/gateway/providers/${encodeURIComponent(name)}`, {
    method: 'DELETE',
  });
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

export function triggerMetaRetrospect(target?: string, category?: string): Promise<V6MetaRetrospectResponse> {
  const params = new URLSearchParams();
  if (target) params.set('target', target);
  if (category) params.set('category', category);
  const qs = params.toString();
  return apiFetch<V6MetaRetrospectResponse>(`/v6/meta/retrospect${qs ? `?${qs}` : ''}`, { method: 'POST' });
}

// ═══════════════════════════════════════════════════════════════════════════
// 版本 (Versions)
// ═══════════════════════════════════════════════════════════════════════════

export function getVersions(category: string, target?: string): Promise<V6VersionsResponse> {
  const qs = target ? `?target=${encodeURIComponent(target)}` : '';
  return apiFetch<V6VersionsResponse>(`/v6/versions/${encodeURIComponent(category)}${qs}`);
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

export function getBehaviorPredictions(): Promise<V6BehaviorPredictResponse> {
  return apiFetch<V6BehaviorPredictResponse>('/v6/behavior/predict');
}

export function getBelief(sessionId: string = 'default'): Promise<V6BeliefResponse> {
  return apiFetch<V6BeliefResponse>(`/v6/belief?session_id=${encodeURIComponent(sessionId)}`);
}

export function applyOceanParams(): Promise<V6OceanParamsResponse> {
  return apiFetch<V6OceanParamsResponse>('/v6/ocean/params', { method: 'POST' });
}

// ═══════════════════════════════════════════════════════════════════════════
// 工程链 (Engineering Chain)
// ═══════════════════════════════════════════════════════════════════════════

export function getSubgraph(perspective: 'dialogue' | 'meta' = 'dialogue'): Promise<V6SubgraphResponse> {
  return apiFetch<V6SubgraphResponse>(`/v6/subgraph/${encodeURIComponent(perspective)}`);
}

export function getRecursiveMap(): Promise<V6RecursiveMapResponse> {
  return apiFetch<V6RecursiveMapResponse>('/v6/recursive-map');
}

export function controlRecursiveMap(req: V6RecursiveMapControlRequest): Promise<V6RecursiveMapControlResponse> {
  return apiFetch<V6RecursiveMapControlResponse>('/v6/recursive-map', {
    method: 'PUT',
    body: JSON.stringify(req),
  });
}

export function getEngineeringModules(): Promise<V6EngineeringModulesResponse> {
  return apiFetch<V6EngineeringModulesResponse>('/v6/engineering/modules');
}

export function editEngineeringConstraints(req: V6EngineeringConstraintEditRequest): Promise<V6EngineeringConstraintEditResponse> {
  return apiFetch<V6EngineeringConstraintEditResponse>('/v6/engineering/constraints', {
    method: 'PUT',
    body: JSON.stringify(req),
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// 可视化编辑 (Visualization Edit) — 白盒化
// ═══════════════════════════════════════════════════════════════════════════

export function editGraph(req: V6GraphEditRequest): Promise<V6GraphEditResponse> {
  return apiFetch<V6GraphEditResponse>('/v6/edit/graph', {
    method: 'PUT',
    body: JSON.stringify(req),
  });
}

export function editDiscourseTree(req: V6DiscourseTreeEditRequest): Promise<V6DiscourseTreeEditResponse> {
  return apiFetch<V6DiscourseTreeEditResponse>('/v6/edit/discourse-tree', {
    method: 'PUT',
    body: JSON.stringify(req),
  });
}

export function editObjects(req: V6ObjectEditRequest): Promise<V6ObjectEditResponse> {
  return apiFetch<V6ObjectEditResponse>('/v6/edit/objects', {
    method: 'PUT',
    body: JSON.stringify(req),
  });
}

export function editRelations(req: V6RelationEditRequest): Promise<V6RelationEditResponse> {
  return apiFetch<V6RelationEditResponse>('/v6/edit/relations', {
    method: 'PUT',
    body: JSON.stringify(req),
  });
}

export function editIr(req: V6IrEditRequest): Promise<V6IrEditResponse> {
  return apiFetch<V6IrEditResponse>('/v6/edit/ir', {
    method: 'PUT',
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

// ═══════════════════════════════════════════════════════════════════════════
// 调度 & 降级 (Scheduler & Degradation) — v10 NEW
// ═══════════════════════════════════════════════════════════════════════════

/** 强一致读: 阻塞至事件处理完; 可选 block_id 读取指定块最新状态 */
export function getSync(blockId?: string): Promise<V6SyncResponse> {
  const qs = blockId ? `?block_id=${encodeURIComponent(blockId)}` : '';
  return apiFetch<V6SyncResponse>(`/v6/sync${qs}`);
}

/** 因果链追踪 (前端乐观更新); 可选 event 追踪指定事件链,缺省返回全局统计 */
export function getCausalChain(event?: string): Promise<V6CausalChainResponse> {
  const qs = event ? `?event=${encodeURIComponent(event)}` : '';
  return apiFetch<V6CausalChainResponse>(`/v6/causal-chain${qs}`);
}

/** 当前系统降级级别 */
export function getDegradation(): Promise<V6DegradationResponse> {
  return apiFetch<V6DegradationResponse>('/v6/degradation');
}

/** HCWA 温度迁移统计 */
export function getTtl(): Promise<V6TtlResponse> {
  return apiFetch<V6TtlResponse>('/v6/ttl');
}

/** 触发温度迁移 tick */
export function tickTtl(): Promise<V6TtlTickResponse> {
  return apiFetch<V6TtlTickResponse>('/v6/ttl/tick', { method: 'POST' });
}

/** 子图缓存命中率统计 */
export function getSubgraphCache(): Promise<V6SubgraphCacheResponse> {
  return apiFetch<V6SubgraphCacheResponse>('/v6/subgraph/cache');
}

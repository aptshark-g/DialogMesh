// FILE: src/api/v6.ts
// DialogMesh v6 GUI API — 42 endpoints covering Profile, Graph, Rules,
// Providers, Router, DeepChain, Pipeline, Metrics, Sessions

import { sessionHeaders } from './sessionHeaders';
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
  V6GatewayConfig, V6GatewayConfigRequest, V6GatewayUsage, V6GatewayStats,
  V6GatewayHealth, V6GatewayCost,
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
    // v8 Seven Trees
    V6AgentTreesResponse,
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
  V6HeuristicsResponse,
  V6ChangelogResponse, V6InterveneRequest,
  V6GovernorStats, V6DiagnosisStats, V6SystemProfile,
  V6RepairsResponse, V6ProbeStats, V6WarmupStats,
  V6BlueprintSuggestions, V6LlmCallsResponse,
} from '../types/api';

// B5（2026-08-07）: 默认相对路径 → 同源代理（dev server / nginx），
// 避免跨域 CORS 被系统 Chrome 剥离（B5_UI_TEST_PLAN_20260807.md）
const BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

/** 可视化编辑版本冲突（409）——服务端已有更新版本, 本地编辑被拒绝。 */
export class VizConflictError extends Error {
  currentVersion: number;

  constructor(detail: any) {
    super('图谱已被更新, 本地编辑与服务器版本冲突');
    this.name = 'VizConflictError';
    this.currentVersion = detail?.current_version ?? 0;
  }
}

async function apiFetch<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${url}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      ...sessionHeaders(),
      ...(options?.headers || {}),
    },
  });
  if (!response.ok) {
    if (response.status === 409) {
      const data = await response.json().catch(() => null);
      throw new VizConflictError(data?.detail);
    }
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

// B5（2026-08-07）: 支持 ?sid= — 图谱按当前会话取对话树（OS 式三级取数）
export function getGraph(sid?: string): Promise<V6GraphResponse> {
  const qs = sid ? `?sid=${encodeURIComponent(sid)}` : '';
  return apiFetch<V6GraphResponse>(`/v6/graph${qs}`);
}

export function getDiscourseTree(sid?: string): Promise<V6DiscourseTreeResponse> {
  const qs = sid ? `?sid=${encodeURIComponent(sid)}` : '';
  return apiFetch<V6DiscourseTreeResponse>(`/v6/discourse-tree${qs}`);
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

/** 二阶抽象（A24）: 启发库存白盒视图（A19）。 */
export function getHeuristics(): Promise<V6HeuristicsResponse> {
  return apiFetch<V6HeuristicsResponse>('/v6/heuristics');
}

/** GAP-F1: 决策变更事件流（git log 语义, 回看/审计）。 */
export function getChangelog(limit = 50, kind = ''): Promise<V6ChangelogResponse> {
  const qs = kind ? `?limit=${limit}&kind=${encodeURIComponent(kind)}` : `?limit=${limit}`;
  return apiFetch<V6ChangelogResponse>(`/v6/changelog${qs}`);
}

/** GAP-F1: PR review 介入回写（approve→applied / reject→rejected）。 */
export function interveneChangelog(req: V6InterveneRequest): Promise<{ intervened: boolean; event?: unknown }> {
  return apiFetch<{ intervened: boolean; event?: unknown }>('/v6/changelog/intervene', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export interface CompressionFeedbackResult {
  recorded: boolean;
  id?: string;
  stats?: { total: number; good: number; bad: number; good_rate: number };
}

/** GAP-4: 压缩质量反馈（Hermes manual_compression_feedback 对齐）。 */
export function submitCompressionFeedback(req: {
  quality: 'good' | 'bad';
  comment?: string;
  compression_id?: string;
}): Promise<CompressionFeedbackResult> {
  return apiFetch<CompressionFeedbackResult>('/v6/context/compression-feedback', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// 持久化 & 会话 (Persistence & Sessions)
// ═══════════════════════════════════════════════════════════════════════════

export function getPersistence(): Promise<V6PersistenceResponse> {
  return apiFetch<V6PersistenceResponse>('/v6/persistence');
}

export function getHealth(): Promise<{ status: string; version: string }> {
  return apiFetch<{ status: string; version: string }>('/v3/health');
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

// ═══ B15/B16（2026-08-17）: 项目 CRUD + 会话归属（服务端持久化）═══ #

export interface V6Project {
  id: string;
  name: string;
  color: string;
  created_at: number;
  path?: string | null;
}

export interface V6ProjectsResponse {
  projects: V6Project[];
  session_project: Record<string, string>;
}

export function getProjects(): Promise<V6ProjectsResponse> {
  return apiFetch<V6ProjectsResponse>('/v6/projects');
}

export function createProjectApi(
  name: string,
  color?: string,
  path?: string,
  createDir = false
): Promise<V6Project> {
  return apiFetch<V6Project>('/v6/projects', {
    method: 'POST',
    body: JSON.stringify({ name, color, path, create_dir: createDir }),
  });
}

export function patchProjectApi(id: string, patch: { name?: string; color?: string; path?: string | null; create_dir?: boolean }): Promise<V6Project> {
  return apiFetch<V6Project>(`/v6/projects/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  });
}

/** 只读目录浏览（2026-08-17, 项目文件夹选择）: path 为空 → data/projects 根 */
export interface V6ProjectBrowseEntry {
  name: string;
  path: string;
}

export async function browseProjectDirs(path?: string): Promise<{ path: string; entries: V6ProjectBrowseEntry[] }> {
  const q = path ? `?path=${encodeURIComponent(path)}` : '';
  return apiFetch<{ path: string; entries: V6ProjectBrowseEntry[] }>(`/v6/projects/browse${q}`);
}

// ═══ 项目设计元信息（二阶抽象, 2026-08-17）═══ #

export interface V6ProjectDesign {
  philosophy: string;
  axioms: string[];
  goals: string[];
  updated_at: number;
  source: string;
}

export function getProjectDesign(projectId: string): Promise<V6ProjectDesign> {
  return apiFetch<V6ProjectDesign>(`/v6/projects/${encodeURIComponent(projectId)}/design`);
}

export function saveProjectDesign(
  projectId: string,
  req: { philosophy?: string; axioms?: string[]; goals?: string[]; source?: string }
): Promise<V6ProjectDesign> {
  return apiFetch<V6ProjectDesign>(`/v6/projects/${encodeURIComponent(projectId)}/design`, {
    method: 'PUT',
    body: JSON.stringify(req),
  });
}

export function digestProjectDesign(projectId: string, useLlm = true): Promise<V6ProjectDesign> {
  return apiFetch<V6ProjectDesign>(
    `/v6/projects/${encodeURIComponent(projectId)}/design/digest?use_llm=${useLlm}`,
    { method: 'POST' }
  );
}

// ═══ Git 只读状态（环境信息面板, 2026-08-17）═══ #

export interface V6GitStatus {
  repo_root: string;
  branch: string;
  remote: string;
  ahead: number;
  behind: number;
  branches: { name: string; current: boolean }[];
  additions: number;
  deletions: number;
  staged: number;
  unstaged: number;
  untracked: number;
  last_commit: { hash: string; message: string; date: string; author: string };
  changed_files: { path: string; status: string }[];
  dirty: boolean;
}

export function getGitStatus(): Promise<V6GitStatus> {
  return apiFetch<V6GitStatus>('/v6/git/status');
}

export function switchGitBranch(name: string, create = false): Promise<{ ok: boolean; branch: string }> {
  return apiFetch<{ ok: boolean; branch: string }>('/v6/git/branch', {
    method: 'POST',
    body: JSON.stringify({ name, create }),
  });
}

export function gitCommit(message: string): Promise<{ ok: boolean; detail: string }> {
  return apiFetch<{ ok: boolean; detail: string }>('/v6/git/commit', {
    method: 'POST',
    body: JSON.stringify({ message }),
  });
}

export function gitPush(): Promise<{ ok: boolean; detail: string }> {
  return apiFetch<{ ok: boolean; detail: string }>('/v6/git/push', { method: 'POST' });
}

// ═══ 系统后台进程（工程链副屏, 2026-08-18）═══ #

export interface V6SystemProcesses {
  threads: {
    name: string;
    label: string;
    daemon: boolean;
    alive: boolean;
    ident: number | null;
  }[];
  count: number;
  memory: Record<string, unknown>;
}

export function getSystemProcesses(): Promise<V6SystemProcesses> {
  return apiFetch<V6SystemProcesses>('/v6/system/processes');
}

export function deleteProjectApi(id: string): Promise<{ deleted: boolean }> {
  return apiFetch<{ deleted: boolean }>(`/v6/projects/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  });
}

export function assignSessionProjectApi(sessionId: string, projectId: string | null): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>(`/v6/sessions/${encodeURIComponent(sessionId)}/project`, {
    method: 'PUT',
    body: JSON.stringify({ project_id: projectId }),
  });
}

// ═══ 工具 / 技能白盒视图（2026-08-17, 工程页）═══ #

export interface V6ToolItem {
  name: string;
  description: string;
  category: string;
}

export interface V6ChannelInfo {
  name: string;
  source: string;
  status: 'ok' | 'planned';
  count: number;
  note?: string;
}

export interface V6ToolsResponse {
  tools: V6ToolItem[];
  total: number;
  channels: V6ChannelInfo[];
  error?: string;
}

export interface V6SkillItem {
  name: string;
  strategies: string[];
  source: string;
}

export interface V6SkillsResponse {
  skills: V6SkillItem[];
  total: number;
  channels: V6ChannelInfo[];
  error?: string;
}

export function getTools(): Promise<V6ToolsResponse> {
  return apiFetch<V6ToolsResponse>('/v6/tools');
}

export function getSkills(): Promise<V6SkillsResponse> {
  return apiFetch<V6SkillsResponse>('/v6/skills');
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

export function getGatewayCost(): Promise<V6GatewayCost> {
  return apiFetch<V6GatewayCost>('/v6/gateway/cost');
}

// ═══ 价格目录同步（2026-08-17: LiteLLM 源）═══ #

export interface V6GatewayPrices {
  synced: boolean;
  fetched_at: string | null;
  source: string | null;
  model_count: number;
  stale: boolean;
}

export interface V6GatewaySyncPricesResult extends V6GatewayPrices {
  enriched_models: number;
  added_models: number;
  note?: string;
}

export function getGatewayPrices(): Promise<V6GatewayPrices> {
  return apiFetch<V6GatewayPrices>('/v6/gateway/prices');
}

export function syncGatewayPrices(force = true): Promise<V6GatewaySyncPricesResult> {
  return apiFetch<V6GatewaySyncPricesResult>(`/v6/gateway/sync-prices?force=${force}`, { method: 'POST' });
}

export function getGatewayErrorCatalog(): Promise<string> {
  return apiFetch<string>('/v6/gateway/error-catalog');
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
// 七树白盒 (Seven Trees, 2026-08-16)
// ═══════════════════════════════════════════════════════════════════════════

export function getAgentTrees(
  sid?: string,
  q?: string,
): Promise<V6AgentTreesResponse> {
  const params = new URLSearchParams();
  if (sid) params.set('sid', sid);
  if (q) params.set('q', q);
  const qs = params.toString();
  return apiFetch<V6AgentTreesResponse>(`/v6/agent-trees${qs ? `?${qs}` : ''}`);
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

// ═══ v6 Chat Pipeline ═══

export interface ChatRequest {
  message: string;
  session_id?: string;
  provider?: string;
  model?: string;
}

export interface ChatResponse {
  session_id: string;
  status: 'completed' | 'pending_review' | 'error';
  answer?: string;
  checkpoint?: {
    checkpoint_id: string;
    requires_review: boolean;
    reasons: string[];
    steps: Array<{
      idx: number; action: string; tool: string;
      risk: string; violated: string[];
      approved: boolean | null; modified: boolean;
      params_preview: string; notes: string;
    }>;
    decision: string;
    general_note: string;
  };
  latency_ms: number;
  trace_id?: string;
  execution?: { status: string; summary: string; results?: unknown[] };
}

export interface CheckpointRespondRequest {
  session_id: string;
  checkpoint_id: string;
  decision: 'approved' | 'adjusted' | 'rejected';
  note?: string;
  steps?: Record<string, { approved: boolean; params?: Record<string, unknown> }>;
}

export interface CheckpointRespondResponse {
  session_id: string;
  status: string;
  answer?: string;
  execution?: { status: string; summary: string };
  latency_ms: number;
}

export function sendChatMessage(req: ChatRequest): Promise<ChatResponse> {
  return apiFetch<ChatResponse>('/v6/chat', {
    method: 'POST',
    body: JSON.stringify(req),
    headers: { 'Content-Type': 'application/json' },
  });
}

export function respondCheckpoint(req: CheckpointRespondRequest): Promise<CheckpointRespondResponse> {
  return apiFetch<CheckpointRespondResponse>('/v6/checkpoint/respond', {
    method: 'POST',
    body: JSON.stringify(req),
    headers: { 'Content-Type': 'application/json' },
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// 运行治理白盒 (Governance, 2026-08-17 前端绑定)
// ═══════════════════════════════════════════════════════════════════════════

/** ExecutionGovernor 熔断/幂等/治理动作（A10 小环白盒）。 */
export function getGovernorStats(): Promise<V6GovernorStats> {
  return apiFetch<V6GovernorStats>('/v6/governor');
}

/** 元认知异步诊断队列 + 报告（A10 大环白盒）。 */
export function getDiagnosisStats(): Promise<V6DiagnosisStats> {
  return apiFetch<V6DiagnosisStats>('/v6/diagnosis');
}

/** 系统自画像（元认知读自己的模块地图/覆盖/薄弱点）。 */
export function getSystemProfile(force = false): Promise<V6SystemProfile> {
  return apiFetch<V6SystemProfile>(`/v6/system-profile${force ? '?force=true' : ''}`);
}

/** 自修复待审队列。 */
export function getRepairs(): Promise<V6RepairsResponse> {
  return apiFetch<V6RepairsResponse>('/v6/repairs');
}

/** 审批 gate: 确认修复包 → 真实应用（git apply + 验证 + 失败回滚）。 */
export function applyRepair(repairId: string): Promise<Record<string, unknown>> {
  return apiFetch<Record<string, unknown>>(`/v6/repairs/${encodeURIComponent(repairId)}/apply`, {
    method: 'POST',
  });
}

/** 验证结果回写（passed → applied / failed → 建议回滚）。 */
export function confirmRepair(repairId: string, passed: boolean): Promise<Record<string, unknown>> {
  return apiFetch<Record<string, unknown>>(`/v6/repairs/${encodeURIComponent(repairId)}/confirm`, {
    method: 'POST',
    body: JSON.stringify({ passed }),
  });
}

/** 主动体检状态 + 历史（无触发也定期自检）。 */
export function getProbeStats(): Promise<V6ProbeStats> {
  return apiFetch<V6ProbeStats>('/v6/probe');
}

/** 立即执行一轮主动体检（异步入诊断器队列）。 */
export function runProbe(): Promise<{ ok: boolean; run?: unknown; error?: string }> {
  return apiFetch<{ ok: boolean; run?: unknown; error?: string }>('/v6/probe/run', {
    method: 'POST',
  });
}

/** 启动期预热状态 + 历史。 */
export function getWarmupStats(): Promise<V6WarmupStats> {
  return apiFetch<V6WarmupStats>('/v6/warmup');
}

/** 手动触发一轮预热（同步, 预算截断）。 */
export function runWarmup(): Promise<{ ok: boolean; run?: unknown; error?: string }> {
  return apiFetch<{ ok: boolean; run?: unknown; error?: string }>('/v6/warmup/run', {
    method: 'POST',
  });
}

/** 蓝图自增长建议（高频意图 → 建议模板）。 */
export function getBlueprintSuggestions(): Promise<V6BlueprintSuggestions> {
  return apiFetch<V6BlueprintSuggestions>('/v6/blueprint/suggestions');
}

/** LLM 调用观测（各阶段延迟/空返回/错误 + 明细, trace_id 可展）。 */
export function getLlmCalls(recent = 20): Promise<V6LlmCallsResponse> {
  return apiFetch<V6LlmCallsResponse>(`/v6/llm-calls?recent=${recent}`);
}

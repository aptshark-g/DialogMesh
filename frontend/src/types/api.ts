// FILE: src/types/api.ts

// ==================== REST API 类型 ====================

export interface CreateSessionResponse {
  session_id: string;
  created_at: string;
  ws_url: string;
  status: 'active' | 'initializing' | 'error';
  capabilities: string[];
  session_ttl_seconds: number;
}

export interface SendMessageResponse {
  message_id: string;
  session_id: string;
  status: 'accepted' | 'rejected' | 'error';
  content: string;
  response_format: string;
  intent: string;
  task_graph: TaskGraphNode[] | null;
  clarifications: ClarificationItem[];
  suggestions: string[];
  latency_ms: number;
  error: string | null;
}

export interface ClarifyResponse {
  status: 'accepted' | 'rejected' | 'error';
  clarification_id: string;
  intent: string;
  clarifications: ClarificationItem[];
  suggestions: string[];
  error: string | null;
}

export interface HistoryRecord {
  message_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  metadata?: Record<string, unknown>;
  intent?: string;
  latency_ms?: number;
}

export interface HistoryResponse {
  session_id: string;
  messages: HistoryRecord[];
  has_more: boolean;
  total_turns: number;
}

export interface SessionStatusResponse {
  session_id: string;
  state: 'idle' | 'processing' | 'clarifying' | 'error' | 'closed' | 'active' | 'waiting_clarification' | 'responding';
  current_turn: number;
  pending_clarification: boolean;
  last_activity_at: string;
  expires_at: string;
  resolved_entities: Record<string, unknown>;
  cognitive_profile: Record<string, unknown>;
  fsm: string | Record<string, unknown>;
}

export interface HealthResponse {
  status: string;
  [key: string]: unknown;
}

// ==================== 组件专用类型 ====================

export interface ClarificationItem {
  id: string;
  field: string;
  question: string;
  type: 'choice' | 'text' | 'confirm';
  options?: string[];
  required: boolean;
  context?: string;
}

export interface TaskGraphNode {
  id: string;
  name: string;
  type: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  dependencies: string[];
  progress?: number;
  result?: string;
  // Blueprint 层节点专属 (§十五统一DAG)
  params?: Record<string, any>;
  checkpoint?: boolean;
}

export interface ConnectionStatus {
  connected: boolean;
  connecting: boolean;
  error: string | null;
  lastPingAt: string | null;
}

export type SessionState = 'idle' | 'active' | 'waiting_clarification' | 'processing' | 'error' | 'closed' | 'clarifying' | 'responding' | 'thinking' | 'initializing';

export interface ThinkingStepPayload {
  step: number;
  description: string;
  detail?: string;
}

export interface SessionSummary {
  session_id: string;
  created_at: string;
  last_activity_at: string;
  state: string;
  current_turn: number;
  message_preview?: string;
}

// ==================== WebSocket 类型 ====================

export type ClientMessageType = 'ping' | 'message' | 'clarify' | 'get_status' | 'heartbeat';

export type ServerEventType =
  | 'HEARTBEAT'
  | 'MESSAGE'
  | 'CLARIFICATION'
  | 'SYSTEM_STATUS'
  | 'ERROR'
  | 'TASK_GRAPH_UPDATE'
  | 'COGNITIVE_TREE_UPDATE'
  | 'THINKING_START'
  | 'THINKING_STEP'
  | 'THINKING_END';

export interface WebSocketClientMessage {
  type: ClientMessageType;
  payload: Record<string, unknown>;
  client_timestamp?: number;
  request_id?: string;
}

export interface WebSocketServerEvent {
  event_type: ServerEventType;
  payload: Record<string, unknown>;
  server_timestamp: number;
  request_id?: string;
  session_id?: string;
}

// ==================== WsClient 类型 (兼容 ws.ts) ====================

export type WsClientMessageType = ClientMessageType;

export interface WsClientMessage {
  type: WsClientMessageType;
  payload: Record<string, unknown>;
  client_timestamp?: number;
  request_id?: string;
}

export type WsServerEventType = ServerEventType;

export interface WsServerEvent {
  event_type: WsServerEventType;
  payload: Record<string, unknown>;
  server_timestamp: number;
  request_id?: string;
}

export interface WsPingPayload {
  echo?: string;
}

export interface WsMessagePayload {
  content: string;
  context?: Record<string, unknown>;
}

export interface WsClarifyPayload {
  clarification_id: string;
  answers: Record<string, unknown>;
}

export interface WsHeartbeatPayload {
  interval_ms?: number;
  timestamp?: number;
}

export interface ConnectionState {
  connected: boolean;
  connecting: boolean;
  reconnecting: boolean;
  lastPingAt: string | null;
  error: string | null;
}

// ==================== Store 状态类型 ====================

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: number;
  status?: 'sending' | 'sent' | 'error' | 'streaming';
  intent?: string;
  taskGraph?: TaskGraphNode[];
  clarifications?: ClarificationItem[];
  suggestions?: string[];
  latencyMs?: number;
  thinkingSteps?: ThinkingStepPayload[];
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: number;
  status?: 'sending' | 'sent' | 'error' | 'streaming';
  intent?: string;
  metadata?: {
    intent?: string;
    taskGraph?: TaskGraphNode[];
    clarifications?: ClarificationItem[];
    suggestions?: string[];
    latencyMs?: number;
    thinkingSteps?: ThinkingStepPayload[];
  };
  taskGraph?: TaskGraphNode[];
  clarifications?: ClarificationItem[];
  suggestions?: string[];
  latencyMs?: number;
  thinkingSteps?: ThinkingStepPayload[];
  clarificationId?: string;
}

export interface ThinkingStep {
  step: number;
  description: string;
  timestamp: number;
}

export interface CognitiveProfile {
  reasoning_depth: number;
  context_window_usage: number;
  entity_count: number;
  topic_tree_depth: number;
  coherence_score: number;
}

export interface FSMState {
  current_state: string;
  previous_state: string;
  transitions: number;
  state_history: string[];
}

export interface TaskNode {
  node_id: string;
  parent_id: string | null;
  type: 'intent' | 'clarification' | 'execution' | 'validation';
  status: 'pending' | 'active' | 'completed' | 'failed';
  description: string;
  dependencies: string[];
  result?: unknown;
  latency_ms?: number;
}

export interface SessionBaseState {
  sessionId: string | null;
  wsConnected: boolean;
  wsConnecting: boolean;
  wsUrl: string | null;
  restBaseUrl: string;
  sessionState: SessionState | null;
  pendingClarification: boolean;
  currentTurn: number;
  cognitiveProfile: CognitiveProfile | null;
  fsm: FSMState | null;
  messages: Message[];
  isLoading: boolean;
  error: string | null;
  capabilities: string[];
  sessionTtl: number;
  expiresAt: string | null;
  lastActivityAt: string | null;
}

export interface SessionActions {
  setRestBaseUrl: (url: string) => void;
  setSessionId: (id: string | null) => void;
  setWsUrl: (url: string | null) => void;
  setWsConnected: (connected: boolean) => void;
  setWsConnecting: (connecting: boolean) => void;
  setSessionState: (state: SessionState | null) => void;
  setPendingClarification: (pending: boolean) => void;
  setCurrentTurn: (turn: number) => void;
  setCognitiveProfile: (profile: CognitiveProfile | null) => void;
  setFsm: (fsm: FSMState | null) => void;
  setCapabilities: (caps: string[]) => void;
  setSessionTtl: (ttl: number) => void;
  setExpiresAt: (expires: string | null) => void;
  setLastActivityAt: (activity: string | null) => void;
  addMessage: (message: Message) => void;
  updateMessage: (id: string, updates: Partial<Message>) => void;
  removeMessage: (id: string) => void;
  clearMessages: () => void;
  appendMessageContent: (id: string, content: string) => void;
  updateTaskGraph: (taskGraph: TaskNode[]) => void;
  setIsLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  clearError: () => void;
  resetSession: () => void;
  initializeSession: (response: CreateSessionResponse) => void;
  syncFromStatus: (status: SessionStatusResponse) => void;
}

export type SessionStore = SessionBaseState & SessionActions;

export interface CognitiveTreeNode {
  id: string;
  label: string;
  depth: number;
  confidence: number;
  children: CognitiveTreeNode[];
}

export interface ServerWebSocketEvent {
  type: ServerEventType;
  payload: Record<string, unknown>;
  server_timestamp: number;
  request_id?: string;
}

export interface ClientWebSocketMessage {
  type: ClientMessageType;
  payload: Record<string, unknown>;
  client_timestamp?: number;
  request_id?: string;
}

// ==================== 兼容旧版类型名 ====================

export type WebSocketClientType = ClientMessageType;
export type WebSocketEventType = ServerEventType;

// ==================== v4 API 类型 ====================

export interface EventRequest {
  event_id: string;
  kind: string;
  payload: Record<string, unknown>;
  trace_id: string;
}

export interface EventResponse {
  status: string;
  event_id: string;
  response: string;
  llm_metrics?: Record<string, unknown>;
}

export interface IngestResponse {
  status: string;
  source_path: string;
  observation_count: number;
  type_distribution: Record<string, unknown>;
}

export interface StatusResponse {
  async: Record<string, unknown>;
  slow: Record<string, unknown>;
  deep: Record<string, unknown>;
}

export interface InspectResponse {
  module: string;
  count?: number;
  items?: unknown[];
  [key: string]: unknown;
}

export interface CheckpointResponse {
  status: string;
  results: { adapter: string; ok: boolean }[];
}

// ==================== v6 API 类型 ====================

// Profile
export interface V6ProfileResponse {
  oceAN_dims: Record<string, number>;
  mbti: string;
  turn_count: number;
  top_dimensions: string[];
  bfi_history: number;
  bfi_latest: Record<string, number>;
}

export interface V6ProfileEditRequest {
  dim?: string;
  value?: number;
  mbti?: string;
}

export interface V6ProfileEditResponse {
  updated: string[];
  feedback: string[];
}

// Trace
export interface V6TraceResponse {
  reason_distribution: Record<string, number>;
  avg_confidence: number;
  total: number;
}

// ABC
export interface V6AbcResponse {
  [key: string]: unknown;
}

// Mind
export interface V6MindResponse {
  [key: string]: unknown;
}

// Graph
export interface V6GraphNode {
  id: string;
  label?: string;
  type?: string;
  size?: number;
  temperature?: string;
  entities?: string[];
  state?: Record<string, unknown>;
  // B5（2026-08-07）: 对话树块扩展字段（TREE_TIERING）
  intent?: string;
  depth?: number;
  raw_text?: string;
  summary?: string;
}

export interface V6GraphEdge {
  source: string;
  target: string;
  type: string;
  weight: number;
}

export interface V6GraphResponse {
  nodes: V6GraphNode[];
  edges: V6GraphEdge[];
  subgraph_nodes: string[];
  version?: number;
}

// Discourse Tree
export interface V6DiscourseBlock {
  id: string;
  tree_id: string;
  topic: string;
  temperature: string;
  edus: number;
  children: string[];
  parent: string | null;
}

export interface V6DiscourseTreeResponse {
  blocks: V6DiscourseBlock[];
  total: number;
  version?: number;
}

// Objects
export interface V6ObjectNode {
  id: string;
  lifespan: string;
  relations: string[];
}

export interface V6ObjectEdge {
  source: string;
  target: string;
  type: string;
}

export interface V6ObjectsResponse {
  nodes: V6ObjectNode[];
  edges: V6ObjectEdge[];
  total_objects: number;
  version?: number;
}

// Rules
export interface V6Rule {
  name: string;
  premise: Record<string, unknown>;
  conclusion: Record<string, unknown>;
  confidence: number;
  hits: number;
  misses: number;
  source: string;
}

export interface V6RulesResponse {
  rules: V6Rule[];
  total: number;
}

export interface V6RuleEditRequest {
  name: string;
  conclusion?: Record<string, unknown>;
  confidence?: number;
}

export interface V6RuleEditResponse {
  updated: string;
  conclusion: Record<string, unknown>;
  confidence: number;
}

// Feedback
export interface V6FeedbackRequest {
  turn: number;
  correct: boolean;
  rule_name: string;
}

export interface V6FeedbackResponse {
  updated: boolean;
  rule?: string;
  hit?: boolean;
  mind_updated?: boolean;
  error?: string;
}

// Persistence
export interface V6PersistenceResponse {
  annotation_store: unknown;
  unified_store: unknown;
  oceAN_saved: boolean;
  rules_saved: boolean;
}

// Sessions
export interface V6SessionListItem {
  name: string;
  size: number;
}

export type V6SessionData = unknown[];

// ==================== v4 WebSocket 类型 ====================

export type V4ServerEventType =
  | 'MESSAGE'
  | 'THINKING_START'
  | 'THINKING_STEP'
  | 'THINKING_END'
  | 'ERROR'
  | 'HEARTBEAT'
  | 'STATUS_UPDATE';

export interface V4WebSocketEvent {
  event_type: V4ServerEventType;
  payload: Record<string, unknown>;
  server_timestamp: number;
  request_id?: string;
}

export interface V4WebSocketMessage {
  type: 'message' | 'ping' | 'heartbeat';
  payload: Record<string, unknown>;
  client_timestamp?: number;
}

// ═══════════════════════════════════════════════════════════════════════════
// v6 NEW — Providers & Ops
// ═══════════════════════════════════════════════════════════════════════════

export interface V6ProviderInfo {
  name: string;
  model: string;
  healthy: boolean;
  stats?: Record<string, unknown>;
}

export interface V6ProvidersResponse {
  active: V6ProviderInfo;
  failover: {
    primary: string;
    fallback: string;
    active_idx: number;
    failures: number;
  };
  active_provider?: string;
  active_model?: string;
}

export interface V6ProviderSwitchRequest {
  provider?: string;
  base_url?: string;
  model?: string;
  api_key?: string;
}

export interface V6ProviderSwitchResponse {
  switched: string;
  model: string;
  healthy: boolean;
}

export interface V6TokensResponse {
  current: { turns: number; est_tokens: number };
  all_sessions: { count: number; est_tokens: number };
  rate: Record<string, string>;
}

export interface V6MetricsResponse {
  engine_uptime?: number;
  subsystems_loaded?: number;
  subsystems_total?: number;
  total_turn_count?: number;
  [key: string]: unknown;
}

export interface V6ContextConfigRequest {
  token_budget?: number;
  domain_P?: number;
  domain_C?: number;
  domain_K?: number;
  domain_E?: number;
  domain_B?: number;
}

// ═══════════════════════════════════════════════════════════════════════════
// v6 NEW — Router / Switch (Gateway)
// ═══════════════════════════════════════════════════════════════════════════

export interface V6RouterMode {
  name: string;
  complexity: string;
  cost: string;
  latency: string;
}

export interface V6RouterModesResponse {
  available: boolean;
  modes: V6RouterMode[];
  active: string;
  force_mode: string | null;
  disabled: { remote: boolean; small_model: boolean };
  cost_budget: string;
  route_stats: Record<string, number>;
  complexity: { evaluator_available: boolean; last_score: number | null };
  degradation_chain: string[];
}

export interface V6RouterModesRequest {
  mode?: string;
  disable_remote?: boolean;
  disable_small_model?: boolean;
  cost_budget?: string;
}

// ═══════════════════════════════════════════════════════════════════════════
// v6 NEW — Deep Chain
// ═══════════════════════════════════════════════════════════════════════════

export interface V6RelationsResponse {
  version?: number;
  [key: string]: unknown;
}

export interface V6CausalResponse {
  [key: string]: unknown;
}

export interface V6BehaviorResponse {
  [key: string]: unknown;
}

export interface V6EngineeringResponse {
  [key: string]: unknown;
}

// ═══════════════════════════════════════════════════════════════════════════
// v6 NEW — Pipeline
// ═══════════════════════════════════════════════════════════════════════════

export interface V6PipelineResponse {
  [key: string]: unknown;
}

export interface V6ExtractionResponse {
  [key: string]: unknown;
}

export interface V6PerspectivesResponse {
  [key: string]: unknown;
}

export interface V6ParameterItem {
  name: string;
  value: number | string | boolean;
  description?: string;
  range?: [number, number];
  editable: boolean;
}

export interface V6ParametersResponse {
  parameters: V6ParameterItem[];
  total: number;
}

export interface V6ParameterEditRequest {
  parameters: Record<string, number | string | boolean>;
}

export interface V6ContextResponse {
  intent_category?: string;
  entries?: { domain: string; type: string; content: string; confidence: number; estimated_tokens: number }[];
  total_tokens?: number;
  [key: string]: unknown;
}

// ═══════════════════════════════════════════════════════════════════════════
// v6 NEW — Mind Full / Persistence Graphs
// ═══════════════════════════════════════════════════════════════════════════

export interface V6MindFullResponse {
  [key: string]: unknown;
}

export interface V6PersistenceGraphsResponse {
  graphs: { name: string; node_count: number; edge_count: number; updated_at: string }[];
}

// ═══════════════════════════════════════════════════════════════════════════
// v8 NEW — Gateway (switch 代理)
// ═══════════════════════════════════════════════════════════════════════════

export interface V6GatewayModel {
  id: string;
  display: string;
  context: number;
  cost_in: number;
  cost_out: number;
  max_output?: number;
  capabilities?: string[];
}

export interface V6GatewayProvider {
  name: string;
  display_name: string;
  configured: boolean;
  healthy: boolean | null;
  base_url: string;
  models: V6GatewayModel[] | null;
  api_key?: string;
}

export interface V6GatewayProvidersResponse {
  providers: V6GatewayProvider[];
  active_provider: string;
  active_model: string;
}

export interface V6GatewayProviderConfigRequest {
  api_key?: string;
  base_url?: string;
}

export interface V6GatewayProviderConfigResponse {
  name: string;
  configured: boolean;
  healthy: boolean;
  models_fetched: number;
}

export interface V6GatewayTestResponse {
  name: string;
  healthy: boolean;
  latency_ms: number;
  models_available: number;
  error: string | null;
}

export interface V6GatewayModelsResponse {
  name: string;
  models: V6GatewayModel[];
}

export interface V6GatewayActiveRequest {
  provider: string;
  model: string;
}

export interface V6GatewayActiveResponse {
  active_provider: string;
  active_model: string;
  healthy: boolean;
  switched_at: string;
}

export interface V6GatewayConfig {
  active_provider: string;
  active_model: string;
  failover_chain: string[];
  auto_failover: boolean;
  max_retries: number;
  timeout_ms: number;
  stats: Record<string, {
    calls: number;
    errors: number;
    avg_latency_ms: number;
    total_tokens: number;
  }>;
}

export interface V6GatewayConfigRequest {
  failover_chain?: string[];
  auto_failover?: boolean;
  max_retries?: number;
  timeout_ms?: number;
}

export interface V6GatewayUsageSession {
  provider: string;
  model: string;
  turns: number;
  prompt_tokens: number;
  completion_tokens: number;
  cost_estimate: string;
  latency_avg_ms: number;
}

export interface V6GatewayUsage {
  current_session: V6GatewayUsageSession;
  all_sessions: {
    total_tokens: number;
    total_cost: string;
    by_provider: Record<string, { tokens: number; cost: string }>;
  };
}

// 网关计费（2026-08-13, switch /v1/usage 透传）: 真实 token/请求/费用
export interface V6GatewayCost {
  total_requests?: number;
  total_tokens?: number;
  by_provider?: Record<string, number>;
  cost?: {
    total?: { prompt_tokens: number; completion_tokens: number;
              requests: number; cost_usd: number };
    by_key?: Record<string, {
      key: string; prompt_tokens: number; completion_tokens: number;
      requests: number; cost_usd: number }>;
    by_model?: Record<string, {
      model: string; prompt_tokens: number; completion_tokens: number;
      requests: number; cost_usd: number }>;
    tenant_count?: number;
  };
}

export interface V6GatewayStats {
  // 2026-08-13: 对齐 switch /v1/stats 真实字段
  uptime_seconds?: number;
  requests?: number;
  tokens_prompt?: number;
  tokens_completion?: number;
  cache_hits?: number;
  cache_misses?: number;
  rate_limit_hits?: number;
  circuit_opens?: number;
  stream_requests?: number;
  active_connections?: number;
  requests_by_provider?: Record<string, number>;
  requests_by_model?: Record<string, number>;
  requests_by_status?: Record<string, number>;
  errors_by_provider?: Record<string, number>;
  latency_by_provider?: Record<string, number>;
  latency_p50?: number;
  latency_p95?: number;
  latency_p99?: number;
  cache_hit_rate?: number;
}

export interface V6GatewayHealth {
  status: string;
  providers_total: number;
  providers_healthy: number;
  circuits: Record<string, string>;
}

// ═══════════════════════════════════════════════════════════════════════════
// v8 NEW — Service Status (前端检测)
// ═══════════════════════════════════════════════════════════════════════════

export interface V6ServiceStatus {
  name: string;
  url: string;
  healthy: boolean;
  latency_ms: number | null;
  version: string | null;
  error: string | null;
}

// ═══════════════════════════════════════════════════════════════════════════
// v8 NEW — Meta Cognition
// ═══════════════════════════════════════════════════════════════════════════

export interface V6MetaStatsResponse {
  queue_size: number;
  pending: number;
  reviewed: number;
  decisions_total: number;
  self_audit: {
    accuracy: number;
    by_verdict: Record<string, number>;
  };
}

export interface V6MetaQueueResponse {
  [key: string]: unknown;
}

// ═══════════════════════════════════════════════════════════════════════════
// v8 NEW — Versions
// ═══════════════════════════════════════════════════════════════════════════

export interface V6VersionCommit {
  id: string;
  ts: number;
  author: string;
  before: string;
  after: string;
  reason: string;
  verify: string;
}

export interface V6VersionsResponse {
  target: string;
  commits: V6VersionCommit[];
}

// ═══════════════════════════════════════════════════════════════════════════
// v8 NEW — Seven Trees (七树白盒, 2026-08-16)
// ═══════════════════════════════════════════════════════════════════════════

export interface V6TreeStats {
  tree_name: string;
  total_nodes: number;
  active: number;
  completed: number;
  archived: number;
  failed: number;
}

export interface V6AgentTreeSession {
  session_id: string;
  loaded: boolean;
  stats: V6TreeStats[];
}

export interface V6AgentTreesResponse {
  sessions?: V6AgentTreeSession[];
  session_count?: number;
  total_nodes?: number;
  stats?: V6TreeStats[];
  hits?: Array<{
    session_id?: string;
    tree: string;
    node_id: string;
    content: string;
  }>;
  query?: string;
  error?: string;
}

// ═══════════════════════════════════════════════════════════════════════════
// v8 NEW — Inertia
// ═══════════════════════════════════════════════════════════════════════════

export interface V6InertiaResponse {
  total_patterns: number;
  stable: number;
  confirmed: number;
  breaking: number;
  by_weight: Record<string, number>;
  constraints: string[];
}

// ═══════════════════════════════════════════════════════════════════════════
// v8 NEW — Behavior Patterns
// ═══════════════════════════════════════════════════════════════════════════

export interface V6BehaviorPattern {
  trigger: string;
  predicted: string;
  confidence: number;
  support: number;
  verdict: string;
}

export interface V6BehaviorPatternsResponse {
  patterns: V6BehaviorPattern[];
  stats: {
    total_patterns: number;
    user_approved: number;
  };
}

export interface V6BehaviorFeedbackRequest {
  pattern_id: string;
  correct: boolean;
}

// ═══════════════════════════════════════════════════════════════════════════
// v8 NEW — Annotations
// ═══════════════════════════════════════════════════════════════════════════

export interface V6Annotation {
  id: string;
  text: string;
  timestamp: string;
  author: string;
}

export interface V6AnnotationsResponse {
  annotations: V6Annotation[];
  total: number;
}

export interface V6AnnotationStatsResponse {
  total: number;
  by_author: Record<string, number>;
  by_date: Record<string, number>;
}

// ═══════════════════════════════════════════════════════════════════════════
// v8 NEW — Profile Corrections
// ═══════════════════════════════════════════════════════════════════════════

export interface V6ProfileCorrection {
  id: string;
  ts: number;
  author: string;
  before: string;
  after: string;
  reason: string;
  verify: string;
}

export interface V6ProfileCorrectionsResponse {
  corrections: V6ProfileCorrection[];
  total: number;
}

// ═══════════════════════════════════════════════════════════════════════════
// v8 NEW — Meta Retrospect (回溯报告)
// ═══════════════════════════════════════════════════════════════════════════

export interface V6MetaRetrospectDelta {
  value_change: number;
  direction?: 'increase' | 'decrease';
}

export interface V6MetaRetrospectResponse {
  target: string;
  delta: V6MetaRetrospectDelta;
  verdict: string;
}

// ═══════════════════════════════════════════════════════════════════════════
// v8 NEW — Behavior Predict / Belief / OCEAN Params
// ═══════════════════════════════════════════════════════════════════════════

export interface V6BehaviorPrediction {
  trigger: string;
  predicted: string;
  conf: number;
}

export interface V6BehaviorPredictResponse {
  recent_actions: string[];
  predictions: Record<string, V6BehaviorPrediction>;
}

export interface V6BeliefEntry {
  posterior: number;
  locked: boolean;
}

export interface V6BeliefResponse {
  total_hypotheses: number;
  locked: number;
  avg_evidence: number;
  by_hypothesis: Record<string, V6BeliefEntry>;
}

export interface V6OceanParamsResponse {
  applied: Record<string, string>;
  ocean: Record<string, number>;
}

// ═══════════════════════════════════════════════════════════════════════════
// v8 NEW — Engineering Chain (Subgraph / Recursive Map / Modules)
// ═══════════════════════════════════════════════════════════════════════════

export interface V6SubgraphEntry {
  domain: string;
  content: string;
}

export interface V6SubgraphResponse {
  perspective: string;
  domains: Record<string, number>;
  entries: V6SubgraphEntry[];
  total_tokens: number;
  budget: number;
}

export interface V6RecursiveMapResponse {
  total_nodes: number;
  by_level: Record<string, number>;
  high_coupling: number;
  expanded: number;
}

export interface V6RecursiveMapControlRequest {
  node: string;
  action: 'expand' | 'collapse';
}

export interface V6RecursiveMapControlResponse {
  node: string;
  action: string;
  expanded: boolean;
}

export interface V6EngineeringModule {
  name: string;
  type: string;
}

export interface V6EngineeringModulesResponse {
  modules: V6EngineeringModule[];
}

export interface V6EngineeringConstraintEditRequest {
  name: string;
  action: 'add_constraint' | 'remove_constraint';
  constraint: string;
}

export interface V6EngineeringConstraintEditResponse {
  updated: string;
  constraint: string;
}

// ═══════════════════════════════════════════════════════════════════════════
// v8 NEW — Visualization Edit (白盒化编辑)
// ═══════════════════════════════════════════════════════════════════════════

export interface V6GraphEditRequest {
  action: 'update_weight' | 'add_edge' | 'remove_edge' | 'set_node';
  source?: string;
  target?: string;
  weight?: number;
  edge_type?: string;
  node_id?: string;
  node_state?: Record<string, unknown>;
  version?: number;
}

export interface V6GraphEditResponse {
  edited?: 'edge' | 'node';
  source?: string;
  target?: string;
  weight?: number;
  node?: string;
  state?: Record<string, unknown>;
  error?: string;
}

export interface V6DiscourseTreeEditRequest {
  action: 'reclassify' | 'merge' | 'split' | 'rename';
  block_id: string;
  temperature?: string;
  topic?: string;
  parent_id?: string;
  version?: number;
}

export interface V6DiscourseTreeEditResponse {
  edited?: 'temperature' | 'topic' | 'parent';
  block?: string;
  before?: string;
  after?: string;
  error?: string;
}

export interface V6ObjectEditRequest {
  action: 'relate' | 'unrelate' | 'rename' | 'set_lifespan';
  source?: string;
  target?: string;
  relation_type?: string;
  lifespan?: string;
  new_name?: string;
  version?: number;
}

export interface V6ObjectEditResponse {
  edited?: 'relation_added' | 'relation_removed' | false;
  source?: string;
  target?: string;
  type?: string;
  reason?: string;
  error?: string;
}

export interface V6RelationEditRequest {
  action: 'update' | 'add' | 'remove';
  source?: string;
  target?: string;
  kind?: string;
  strength?: number;
  version?: number;
}

export interface V6RelationEditResponse {
  edited?: 'relation' | 'added';
  source?: string;
  target?: string;
  error?: string;
}

export interface V6IrEditRequest {
  domain: string;
  entry_type?: string;
  content: string;
  confidence?: number;
  version?: number;
}

export interface V6IrEditResponse {
  edited?: 'ir_entry_added';
  domain?: string;
  type?: string;
  error?: string;
}

// 二阶抽象（A24）— 启发库存白盒视图（A19）
export interface V6HeuristicItem {
  heuristic_id: string;
  pattern_desc: string;
  conditions: string;
  counterexample: string;
  reasoning_path: string;
  coverage: number;
  support: number;
  insight_score: number;
  source: 'seed' | 'axiom' | 'distilled' | 'rule';
  active: boolean;
  ts: number;
}

export interface V6HeuristicsResponse {
  heuristics: V6HeuristicItem[];
  stats: {
    total: number;
    active: number;
    by_source: Record<string, number>;
    avg_coverage: number;
    avg_insight: number;
  };
}

// GAP-F1 — 变更日志（决策事件流, git log + PR review 语义）
export interface V6ChangelogEvent {
  kind: 'strategy_switch' | 'plan_gate' | 'meta_advice' | 'user_correction' | string;
  dimension: string;
  attribution?: string;
  before?: unknown;
  after?: unknown;
  reason?: string;
  actor?: string;
  turn?: number;
  ts: number;
  comment?: string;
  status?: 'applied' | 'proposed' | 'rejected' | 'reverted' | string;
  request_id?: string;
  trace_id?: string;
}

export interface V6ChangelogResponse {
  events: V6ChangelogEvent[];
  stats: {
    total: number;
    proposed: number;
    applied: number;
    rejected: number;
    reverted: number;
  };
}

export interface V6InterveneRequest {
  status: 'applied' | 'rejected';
  comment?: string;
  dimension?: string;
  kind?: string;
}

// ═══════════════════════════════════════════════════════════════════════════
// v8 NEW — Gateway Provider Add/Remove
// ═══════════════════════════════════════════════════════════════════════════

export interface V6GatewayProviderAddRequest {
  name: string;
  base_url: string;
  api_key?: string;
  kind?: string;
  models?: V6GatewayModel[];
}

export interface V6GatewayProviderMutationResponse {
  error?: string;
  fallback?: string;
  [key: string]: unknown;
}




// ═══════════════════════════════════════════════════════════════════════════
// v10 NEW — 调度 & 降级 (Sync / Causal Chain / Degradation / TTL / Subgraph Cache)
// ═══════════════════════════════════════════════════════════════════════════

/** GET /v6/sync — 强一致读; 不传 block_id 时返回 { status, pending } */
export interface V6SyncResponse {
  status?: string;
  pending?: number;
  block_id?: string;
  text?: string;
}

export interface V6CausalChainEvent {
  event: string;
  depth: number;
}

/** GET /v6/causal-chain — 传 event 返回 { chain, remaining }; 不传返回全局统计 */
export interface V6CausalChainResponse {
  chain?: V6CausalChainEvent[];
  remaining?: number;
  tracked_chains?: number;
  avg_chain_length?: number;
  p90_chain_length?: number;
}

export type V6DegradationLevel = 'NORMAL' | 'WARNING' | 'DEGRADED' | 'EMERGENCY';

/** GET /v6/degradation — 当前系统降级级别 */
export interface V6DegradationResponse {
  level: V6DegradationLevel;
  queue_depth: number;
}

/** GET /v6/ttl — HCWA 温度迁移统计; 引擎未就绪时返回 { error } */
export interface V6TtlResponse {
  by_state?: Record<string, number>;
  total?: number;
  error?: string;
}

/** POST /v6/ttl/tick — 触发温度迁移; 引擎未就绪时返回 { error } */
export interface V6TtlTickResponse {
  promoted?: string[];
  demoted?: string[];
  error?: string;
}

/** GET /v6/subgraph/cache — 子图缓存统计; 引擎未就绪时返回 { error } */
export interface V6SubgraphCacheResponse {
  size?: number;
  hits?: number;
  stale?: number;
  error?: string;
}

// ═══════════════════════════════════════════════════════════════════════════
// 运行治理白盒（2026-08-17 前端绑定, 后端 stubs_api /v6/*）
// ═══════════════════════════════════════════════════════════════════════════

/** GET /v6/governor — ExecutionGovernor 各 scope 熔断状态 + 最近治理动作 */
export interface V6GovernorBreaker {
  scope: string;
  state: string;                 // closed | open | half_open
  consecutive_failures: number;
  total_calls: number;
  total_failures: number;
  window_seconds: number;
}

export interface V6GovernorAction {
  ts?: number;
  action?: string;
  scope?: string;
  reason?: string;
  [key: string]: unknown;
}

export interface V6GovernorStats {
  breakers: V6GovernorBreaker[];
  in_flight: number;
  recent_actions: V6GovernorAction[];
  error?: string;
}

/** GET /v6/diagnosis — 元认知异步诊断队列 + 报告 */
export interface V6DiagnosisReport {
  id?: string;
  ts?: number;
  trigger?: string;
  root_cause?: string;
  confidence?: number;
  suggestions?: string[];
  self_adjusted?: boolean;
  [key: string]: unknown;
}

export interface V6DiagnosisStats {
  pending: number;
  repairs: V6RepairItem[];
  last_trigger: Record<string, number>;
  reports: V6DiagnosisReport[];
  error?: string;
}

/** 自修复包（repairs 列表 / apply / confirm） */
export interface V6RepairItem {
  id: string;
  status: 'pending' | 'verifying' | 'applied' | 'failed' | string;
  source?: string;
  summary?: string;
  reason?: string;
  patch?: string;
  apply_result?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface V6RepairsResponse {
  repairs: V6RepairItem[];
  error?: string;
}

/** GET /v6/system-profile — 系统自画像（元认知读自己） */
export interface V6SystemProfile {
  [key: string]: unknown;
  modules?: unknown[];
  weak_points?: unknown[];
  error?: string;
}

/** GET /v6/probe — 主动体检状态 + 历史 */
export interface V6ProbeHistoryEntry {
  ts?: number;
  triggered?: boolean;
  skipped?: boolean;
  findings?: unknown[];
  [key: string]: unknown;
}

export interface V6ProbeStats {
  running: boolean;
  interval_s: number;
  startup_delay_s: number;
  last_run?: number | null;
  next_due_ts?: number | null;
  next_due_in_s?: number;
  runs: number;
  history: V6ProbeHistoryEntry[];
  error?: string;
}

/** GET /v6/warmup — 启动期预热状态 + 历史 */
export interface V6WarmupStats {
  running: boolean;
  budget_s: number;
  last?: Record<string, unknown> | null;
  runs: number;
  history: Array<Record<string, unknown>>;
  error?: string;
}

/** GET /v6/blueprint/suggestions — 蓝图自增长建议 */
export interface V6BlueprintSuggestions {
  suggestions: Array<Record<string, unknown>>;
  note?: string;
  ok?: boolean;
  error?: string;
}

/** GET /v6/llm-calls — LLM 调用观测（延迟/空返回/错误 + 明细） */
export interface V6LlmCallEntry {
  ts?: number;
  stage?: string;
  latency_ms?: number;
  ok?: boolean;
  empty?: boolean;
  error?: string;
  trace_id?: string;
  [key: string]: unknown;
}

export interface V6LlmCallsResponse {
  stats: Record<string, unknown>;
  recent: V6LlmCallEntry[];
  error?: string;
}

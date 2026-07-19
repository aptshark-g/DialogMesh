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
  state: Record<string, unknown>;
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

export interface V6GatewayStats {
  requests: number;
  tokens: number;
  latency_p50: number;
  latency_p95: number;
  latency_p99: number;
  cache_hit_rate: number;
  errors_by_provider: Record<string, number>;
  requests_by_model: Record<string, number>;
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




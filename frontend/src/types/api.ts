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

export interface Session {
  session_id: string;
  created_at: string;
  state: string;
  current_turn: number;
  pending_clarification: boolean;
  last_activity_at: string;
  expires_at: string;
}


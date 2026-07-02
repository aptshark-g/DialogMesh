// FILE: src/lib/websocketClient.ts

import type {
  WebSocketClientMessage,
  WebSocketServerEvent,
  ClientMessageType,
  CreateSessionResponse,
  SendMessageResponse,
  ClarifyResponse,
  HistoryResponse,
  SessionStatusResponse,
  HealthResponse,
} from '../types/api';

const DEFAULT_REST_BASE_URL = 'http://localhost:8000';
const WS_RECONNECT_INTERVAL = 3000;
const WS_MAX_RECONNECT_ATTEMPTS = 5;
const WS_PING_INTERVAL = 15000;

export class RestApiClient {
  private baseUrl: string;
  constructor(baseUrl: string = DEFAULT_REST_BASE_URL) {
    this.baseUrl = baseUrl.replace(/\/$/, '');
  }
  setBaseUrl(url: string): void { this.baseUrl = url.replace(/\/$/, ''); }
  getBaseUrl(): string { return this.baseUrl; }
  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    const response = await fetch(url, { headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, ...options });
    if (!response.ok) { const text = await response.text().catch(() => 'Unknown error'); throw new Error(`HTTP ${response.status}: ${text}`); }
    return response.json() as Promise<T>;
  }
  async createSession(): Promise<CreateSessionResponse> { return this.request<CreateSessionResponse>('/v3/session', { method: 'POST' }); }
  async sendMessage(sessionId: string, content: string, options: { responseFormat?: string; context?: Record<string, unknown> } = {}): Promise<SendMessageResponse> { return this.request<SendMessageResponse>(`/v3/session/${sessionId}/message`, { method: 'POST', body: JSON.stringify({ content, response_format: options.responseFormat ?? 'text', context: options.context ?? {} }) }); }
  async sendClarification(sessionId: string, clarificationId: string, answers: Record<string, unknown>): Promise<ClarifyResponse> { return this.request<ClarifyResponse>(`/v3/session/${sessionId}/clarify`, { method: 'POST', body: JSON.stringify({ clarification_id: clarificationId, answers }) }); }
  async getHistory(sessionId: string, options: { limit?: number; before?: string } = {}): Promise<HistoryResponse> { const params = new URLSearchParams(); if (options.limit) params.append('limit', String(options.limit)); if (options.before) params.append('before', options.before); const query = params.toString() ? `?${params.toString()}` : ''; return this.request<HistoryResponse>(`/v3/session/${sessionId}/history${query}`); }
  async getSessionStatus(sessionId: string): Promise<SessionStatusResponse> { return this.request<SessionStatusResponse>(`/v3/session/${sessionId}/status`); }
  async getHealth(): Promise<HealthResponse> { return this.request<HealthResponse>('/v3/health'); }
}

type EventHandler = (event: WebSocketServerEvent) => void;
type StatusHandler = (connected: boolean) => void;
type ErrorHandler = (error: Error) => void;
export interface WebSocketOptions {
  autoReconnect?: boolean; reconnectInterval?: number; maxReconnectAttempts?: number; pingInterval?: number; onEvent?: EventHandler; onStatusChange?: StatusHandler; onError?: ErrorHandler;
}
export class WebSocketClient {
  private ws: WebSocket | null = null; private _sessionId: string | null = null; private wsUrl: string | null = null; private reconnectAttempts = 0; private pingTimer: ReturnType<typeof setInterval> | null = null; private reconnectTimer: ReturnType<typeof setTimeout> | null = null; private options: Required<WebSocketOptions>; private messageQueue: WebSocketClientMessage[] = []; private requestIdCounter = 0;
  constructor(options: WebSocketOptions = {}) { this.options = { autoReconnect: true, reconnectInterval: WS_RECONNECT_INTERVAL, maxReconnectAttempts: WS_MAX_RECONNECT_ATTEMPTS, pingInterval: WS_PING_INTERVAL, onEvent: () => {}, onStatusChange: () => {}, onError: () => {}, ...options }; }
  connect(sessionId: string, wsUrl?: string): void { if (this.ws?.readyState === WebSocket.OPEN) { console.warn('[WebSocket] 已连接，跳过重复连接'); return; } this._sessionId = sessionId; this.wsUrl = wsUrl ?? `ws://localhost:8000/v3/ws/${sessionId}`; this.reconnectAttempts = 0; this.doConnect(); }
  private doConnect(): void { if (!this.wsUrl) { this.options.onError(new Error('WebSocket URL 未设置')); return; } try { this.ws = new WebSocket(this.wsUrl); this.ws.onopen = () => { console.log('[WebSocket] 连接已建立'); this.reconnectAttempts = 0; this.options.onStatusChange(true); this.flushMessageQueue(); this.startPing(); }; this.ws.onmessage = (event) => { this.handleMessage(event.data); }; this.ws.onclose = (event) => { console.log(`[WebSocket] 连接关闭: code=${event.code}, reason=${event.reason}`); this.stopPing(); this.options.onStatusChange(false); this.ws = null; if (this.options.autoReconnect && this.reconnectAttempts < this.options.maxReconnectAttempts) { this.scheduleReconnect(); } else if (this.reconnectAttempts >= this.options.maxReconnectAttempts) { this.options.onError(new Error('WebSocket 重连次数超限')); } }; this.ws.onerror = () => { console.error('[WebSocket] 连接错误'); this.options.onError(new Error('WebSocket 连接失败')); }; } catch (err) { this.options.onError(err instanceof Error ? err : new Error(String(err))); } }
  disconnect(): void { this.options.autoReconnect = false; this.clearTimers(); if (this.ws) { this.ws.onclose = null; this.ws.onmessage = null; this.ws.onerror = null; if (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING) { this.ws.close(1000, '客户端主动断开'); } this.ws = null; } this._sessionId = null; this.wsUrl = null; this.reconnectAttempts = 0; this.messageQueue = []; this.options.onStatusChange(false); }
  isConnected(): boolean { return this.ws?.readyState === WebSocket.OPEN; }
  isConnecting(): boolean { return this.ws?.readyState === WebSocket.CONNECTING; }
  getSessionId(): string | null { return this._sessionId; }
  send(type: ClientMessageType, payload: Record<string, unknown>): void { const message: WebSocketClientMessage = { type, payload, client_timestamp: Date.now(), request_id: this.generateRequestId() }; if (this.isConnected()) { this.ws!.send(JSON.stringify(message)); } else { this.messageQueue.push(message); } }
  sendMessage(content: string, context?: Record<string, unknown>): void { this.send('message', { content, context: context ?? {} }); }
  sendClarify(clarificationId: string, answers: Record<string, unknown>): void { this.send('clarify', { clarification_id: clarificationId, answers }); }
  sendGetStatus(): void { this.send('get_status', {}); }
  sendPing(): void { this.send('ping', {}); }
  sendHeartbeat(): void { this.send('heartbeat', { timestamp: Date.now() }); }
  private handleMessage(data: string): void { try { const event = JSON.parse(data) as WebSocketServerEvent; this.options.onEvent(event); } catch (err) { console.error('[WebSocket] 消息解析失败:', err, data); } }
  private flushMessageQueue(): void { while (this.messageQueue.length > 0 && this.isConnected()) { const message = this.messageQueue.shift(); if (message) { this.ws!.send(JSON.stringify(message)); } } }
  private scheduleReconnect(): void { this.reconnectAttempts++; const delay = this.options.reconnectInterval * this.reconnectAttempts; console.log(`[WebSocket] ${delay}ms 后尝试第 ${this.reconnectAttempts} 次重连...`); this.reconnectTimer = setTimeout(() => { this.doConnect(); }, delay); }
  private startPing(): void { this.pingTimer = setInterval(() => { if (this.isConnected()) { this.sendPing(); } }, this.options.pingInterval); }
  private stopPing(): void { if (this.pingTimer) { clearInterval(this.pingTimer); this.pingTimer = null; } }
  private clearTimers(): void { this.stopPing(); if (this.reconnectTimer) { clearTimeout(this.reconnectTimer); this.reconnectTimer = null; } }
  private generateRequestId(): string { return `req-${++this.requestIdCounter}-${Date.now()}`; }
}

export function createRestClient(baseUrl?: string): RestApiClient { return new RestApiClient(baseUrl); }
export function createWebSocketClient(options?: WebSocketOptions): WebSocketClient { return new WebSocketClient(options); }
export { DEFAULT_REST_BASE_URL, WS_RECONNECT_INTERVAL, WS_MAX_RECONNECT_ATTEMPTS, WS_PING_INTERVAL };
export type { TaskNode, ClarificationItem, WebSocketClientMessage, WebSocketServerEvent, ServerEventType, ClientMessageType } from '../types/api';

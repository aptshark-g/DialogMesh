// FILE: src/lib/websocket.ts

import type {
  WebSocketServerEvent as ServerWebSocketEvent,
  WebSocketClientMessage as ClientWebSocketMessage,
  ServerEventType,
  ConnectionStatus,
} from '../types/api';

export type EventHandler = (event: ServerWebSocketEvent) => void;
export type StatusHandler = (status: ConnectionStatus) => void;

const HEARTBEAT_INTERVAL_MS = 30000;
const RECONNECT_DELAY_MS = 3000;
const MAX_RECONNECT_ATTEMPTS = 5;

export class DialogMeshWebSocket {
  private ws: WebSocket | null = null;
  private url: string;
  private sessionId: string;

  private eventHandlers: Map<ServerEventType, Set<EventHandler>> = new Map();
  private statusHandlers: Set<StatusHandler> = new Set();

  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private reconnectAttempts = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private intentionallyClosed = false;

  private status: ConnectionStatus = {
    connected: false,
    connecting: false,
    error: null,
    lastPingAt: null,
  };

  constructor(sessionId: string, url: string) {
    this.sessionId = sessionId;
    this.url = url;
  }

  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN || this.ws?.readyState === WebSocket.CONNECTING) {
      return;
    }
    this.intentionallyClosed = false;
    this.updateStatus({ connecting: true, error: null });

    try {
      this.ws = new WebSocket(this.url);
      this.ws.onopen = () => this.onOpen();
      this.ws.onmessage = (msg) => this.onMessage(msg);
      this.ws.onclose = () => this.onClose();
      this.ws.onerror = (err) => this.onError(err);
    } catch (err) {
      this.updateStatus({
        connecting: false,
        error: err instanceof Error ? err.message : 'WebSocket 连接失败',
      });
      this.scheduleReconnect();
    }
  }

  disconnect(): void {
    this.intentionallyClosed = true;
    this.clearTimers();
    this.reconnectAttempts = 0;
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.updateStatus({ connected: false, connecting: false, error: null });
  }

  send(type: ClientWebSocketMessage['type'], payload: Record<string, unknown>): boolean {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      return false;
    }
    const msg: ClientWebSocketMessage = {
      type,
      payload,
      client_timestamp: Date.now(),
      request_id: `${this.sessionId}_${Date.now()}`,
    };
    this.ws.send(JSON.stringify(msg));
    return true;
  }

  sendMessage(content: string): boolean {
    return this.send('message', { content });
  }

  sendClarify(clarificationId: string, answers: Record<string, string>): boolean {
    return this.send('clarify', { clarification_id: clarificationId, answers });
  }

  sendHeartbeat(): boolean {
    return this.send('heartbeat', {});
  }

  sendGetStatus(): boolean {
    return this.send('get_status', {});
  }

  onEvent(type: ServerEventType, handler: EventHandler): () => void {
    if (!this.eventHandlers.has(type)) {
      this.eventHandlers.set(type, new Set());
    }
    this.eventHandlers.get(type)!.add(handler);
    return () => this.eventHandlers.get(type)?.delete(handler);
  }

  onAnyEvent(handler: EventHandler): () => void {
    const allTypes: ServerEventType[] = [
      'HEARTBEAT', 'MESSAGE', 'CLARIFICATION', 'SYSTEM_STATUS',
      'ERROR', 'TASK_GRAPH_UPDATE', 'COGNITIVE_TREE_UPDATE',
      'THINKING_START', 'THINKING_STEP', 'THINKING_END',
    ];
    const unsubscribers = allTypes.map((t) => this.onEvent(t, handler));
    return () => unsubscribers.forEach((fn) => fn());
  }

  onStatusChange(handler: StatusHandler): () => void {
    this.statusHandlers.add(handler);
    handler(this.status);
    return () => this.statusHandlers.delete(handler);
  }

  getStatus(): ConnectionStatus {
    return { ...this.status };
  }

  isConnected(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }

  private onOpen(): void {
    this.reconnectAttempts = 0;
    this.updateStatus({ connected: true, connecting: false, error: null });
    this.startHeartbeat();
  }

  private onMessage(msg: MessageEvent): void {
    try {
      const event = JSON.parse(msg.data as string) as ServerWebSocketEvent;
      this.dispatchEvent(event);
    } catch {
      // 忽略非 JSON 消息
    }
  }

  private onClose(): void {
    this.ws = null;
    this.clearTimers();
    this.updateStatus({ connected: false, connecting: false });
    if (!this.intentionallyClosed) {
      this.scheduleReconnect();
    }
  }

  private onError(_err: Event): void {
    this.updateStatus({ error: 'WebSocket 连接异常' });
  }

  private dispatchEvent(event: ServerWebSocketEvent): void {
    const handlers = this.eventHandlers.get(event.event_type);
    handlers?.forEach((h) => {
      try {
        h(event);
      } catch {
        // 忽略 handler 异常
      }
    });
  }

  private startHeartbeat(): void {
    this.clearHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      this.sendHeartbeat();
      this.updateStatus({ lastPingAt: new Date().toISOString() });
    }, HEARTBEAT_INTERVAL_MS);
  }

  private clearHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  private clearTimers(): void {
    this.clearHeartbeat();
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      this.updateStatus({ error: 'WebSocket 重连次数已达上限' });
      return;
    }
    this.reconnectAttempts += 1;
    this.reconnectTimer = setTimeout(() => {
      this.connect();
    }, RECONNECT_DELAY_MS * this.reconnectAttempts);
  }

  private updateStatus(partial: Partial<ConnectionStatus>): void {
    this.status = { ...this.status, ...partial };
    this.statusHandlers.forEach((h) => {
      try {
        h(this.status);
      } catch {
        // 忽略 handler 异常
      }
    });
  }
}

export function createWebSocket(sessionId: string, url?: string): DialogMeshWebSocket {
  const baseUrl = url || `ws://localhost:8000/v3/ws/${sessionId}`;
  return new DialogMeshWebSocket(sessionId, baseUrl);
}

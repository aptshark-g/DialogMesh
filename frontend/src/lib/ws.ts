// FILE: src/lib/ws.ts

import type {
  WsClientMessage as WsClientMessageType,
  WsClientMessageType as WsClientMessageTypeEnum,
  WsServerEvent as WsServerEventType,
  WsServerEventType as WsServerEventTypeEnum,
  ConnectionState,
  WsPingPayload,
  WsMessagePayload,
  WsClarifyPayload,
  WsHeartbeatPayload,
} from '../types/api';

type EventHandler<T = unknown> = (payload: T, event: WsServerEventType) => void;

interface WsClientOptions {
  sessionId: string;
  baseUrl?: string;
  reconnect?: boolean;
  reconnectIntervalMs?: number;
  maxReconnectAttempts?: number;
  heartbeatIntervalMs?: number;
}

class WsClient {
  private ws: WebSocket | null = null;
  private readonly sessionId: string;
  private readonly baseUrl: string;
  private readonly reconnect: boolean;
  private readonly reconnectIntervalMs: number;
  private readonly maxReconnectAttempts: number;
  private readonly heartbeatIntervalMs: number;

  private reconnectAttempts = 0;
  private heartbeatTimer: number | null = null;
  private reconnectTimer: number | null = null;
  private closed = false;

  private readonly handlers: Map<WsServerEventTypeEnum, Set<EventHandler>> = new Map();
  private readonly stateListeners: Set<(state: ConnectionState) => void> = new Set();

  private state: ConnectionState = {
    connected: false,
    connecting: false,
    reconnecting: false,
    lastPingAt: null,
    error: null,
  };

  constructor(options: WsClientOptions) {
    this.sessionId = options.sessionId;
    this.baseUrl = (options.baseUrl ?? 'ws://localhost:8000').replace(/\/$/, '');
    this.reconnect = options.reconnect ?? true;
    this.reconnectIntervalMs = options.reconnectIntervalMs ?? 3000;
    this.maxReconnectAttempts = options.maxReconnectAttempts ?? 10;
    this.heartbeatIntervalMs = options.heartbeatIntervalMs ?? 15000;
  }

  // ─── 连接管理 ───

  connect(): void {
    if (this.ws || this.state.connecting) return;
    this.closed = false;
    this.updateState({ connecting: true, error: null });

    const url = `${this.baseUrl}/v3/ws/${this.sessionId}`;
    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
      this.updateState({ connected: true, connecting: false, reconnecting: false, error: null });
      this.startHeartbeat();
    };

    this.ws.onmessage = (event) => {
      this.handleMessage(event.data);
    };

    this.ws.onclose = () => {
      this.ws = null;
      this.stopHeartbeat();
      this.updateState({ connected: false, connecting: false });
      if (this.reconnect && !this.closed) {
        this.scheduleReconnect();
      }
    };

    this.ws.onerror = () => {
      this.updateState({ error: 'WebSocket 连接发生错误' });
    };
  }

  disconnect(): void {
    this.closed = true;
    this.stopHeartbeat();
    this.clearReconnectTimer();
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.updateState({ connected: false, connecting: false, reconnecting: false });
  }

  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      this.updateState({ error: 'WebSocket 重连次数已达上限' });
      return;
    }
    this.reconnectAttempts += 1;
    this.updateState({ reconnecting: true });
    this.reconnectTimer = window.setTimeout(() => {
      this.connect();
    }, this.reconnectIntervalMs);
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  // ─── 心跳 ───

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatTimer = window.setInterval(() => {
      this.send('heartbeat', { interval_ms: this.heartbeatIntervalMs } as WsHeartbeatPayload);
    }, this.heartbeatIntervalMs);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer !== null) {
      window.clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  // ─── 发送 ───

  send(type: WsClientMessageTypeEnum, payload: unknown, requestId?: string): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      throw new Error('WebSocket 未连接');
    }
    const message: WsClientMessageType = {
      type,
      payload: payload as Record<string, unknown>,
      client_timestamp: Date.now(),
      request_id: requestId ?? crypto.randomUUID(),
    };
    this.ws.send(JSON.stringify(message));
  }

  sendPing(payload?: WsPingPayload): void {
    this.send('ping', payload ?? { echo: 'ping' });
  }

  sendMessage(payload: WsMessagePayload, requestId?: string): void {
    this.send('message', payload, requestId);
  }

  sendClarify(payload: WsClarifyPayload, requestId?: string): void {
    this.send('clarify', payload, requestId);
  }

  requestStatus(requestId?: string): void {
    this.send('get_status', {}, requestId);
  }

  // ─── 接收 ───

  private handleMessage(data: string): void {
    try {
      const event = JSON.parse(data) as WsServerEventType;
      this.emit(event.event_type, event.payload, event);
      if (event.event_type === 'HEARTBEAT') {
        this.updateState({ lastPingAt: new Date().toISOString() });
      }
    } catch {
      // 忽略非 JSON 消息
    }
  }

  // ─── 事件订阅 ───

  on<T = unknown>(eventType: WsServerEventTypeEnum, handler: EventHandler<T>): () => void {
    if (!this.handlers.has(eventType)) {
      this.handlers.set(eventType, new Set());
    }
    const set = this.handlers.get(eventType)!;
    const wrapped = handler as EventHandler;
    set.add(wrapped);
    return () => {
      set.delete(wrapped);
    };
  }

  off<T = unknown>(eventType: WsServerEventTypeEnum, handler: EventHandler<T>): void {
    const set = this.handlers.get(eventType);
    if (set) {
      set.delete(handler as EventHandler);
    }
  }

  private emit(eventType: WsServerEventTypeEnum, payload: unknown, event: WsServerEventType): void {
    const set = this.handlers.get(eventType);
    if (set) {
      for (const handler of set) {
        handler(payload, event);
      }
    }
  }

  // ─── 状态 ───

  private updateState(partial: Partial<ConnectionState>): void {
    this.state = { ...this.state, ...partial };
    for (const listener of this.stateListeners) {
      listener(this.state);
    }
  }

  getState(): ConnectionState {
    return { ...this.state };
  }

  subscribeState(listener: (state: ConnectionState) => void): () => void {
    this.stateListeners.add(listener);
    listener(this.state);
    return () => {
      this.stateListeners.delete(listener);
    };
  }

  isConnected(): boolean {
    return this.state.connected;
  }
}

export { WsClient };
export type { EventHandler, WsClientOptions };

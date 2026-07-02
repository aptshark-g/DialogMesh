// FILE: src/hooks/useWebSocket.ts

import { useEffect, useRef, useCallback } from 'react';
import { useSessionStore } from '../stores/sessionStore';
import {
  WebSocketClient,
  RestApiClient,
  createWebSocketClient,
  createRestClient,
} from '../lib/websocketClient';
import {
  type WebSocketServerEvent,
  type ServerEventType,
  type CreateSessionResponse,
  type SendMessageResponse,
  type ClarifyResponse,
  type HistoryResponse,
  type SessionStatusResponse,
  type HealthResponse,
  type Message,
} from '../types/api';

// ==================== useWebSocket Hook ====================

export interface UseWebSocketReturn {
  // 状态
  connected: boolean;
  connecting: boolean;
  sessionId: string | null;
  sessionState: string | null;

  // 连接操作
  connect: (sessionId: string, wsUrl?: string) => void;
  disconnect: () => void;
  createAndConnect: () => Promise<void>;

  // 消息操作
  sendMessage: (content: string, context?: Record<string, unknown>) => void;
  sendClarification: (clarificationId: string, answers: Record<string, unknown>) => void;
  sendPing: () => void;
  sendGetStatus: () => void;

  // 工具
  restClient: RestApiClient;
  wsClient: WebSocketClient | null;
}

export function useWebSocket(): UseWebSocketReturn {
  const wsRef = useRef<WebSocketClient | null>(null);
  const restRef = useRef<RestApiClient | null>(null);

  const store = useSessionStore();

  // 初始化 REST client
  useEffect(() => {
    restRef.current = createRestClient(store.restBaseUrl);
    return () => {
      restRef.current = null;
    };
  }, [store.restBaseUrl]);

  // 更新 REST base URL 当 store 变化时
  useEffect(() => {
    if (restRef.current) {
      restRef.current.setBaseUrl(store.restBaseUrl);
    }
  }, [store.restBaseUrl]);

  // 创建 WebSocket 客户端
  const getOrCreateWsClient = useCallback((): WebSocketClient => {
    if (wsRef.current) return wsRef.current;

    const client = createWebSocketClient({
      autoReconnect: true,
      reconnectInterval: 3000,
      maxReconnectAttempts: 5,
      pingInterval: 15000,
      onEvent: (event: WebSocketServerEvent) => {
        handleServerEvent(event);
      },
      onStatusChange: (connected: boolean) => {
        store.setWsConnected(connected);
        store.setWsConnecting(false);
      },
      onError: (error: Error) => {
        console.error('[useWebSocket] WebSocket 错误:', error);
        store.setError(error.message);
        store.setWsConnecting(false);
      },
    });

    wsRef.current = client;
    return client;
  }, [store]);

  // 处理服务端事件
  const handleServerEvent = useCallback((event: WebSocketServerEvent) => {
    const { event_type, payload } = event;

    switch (event_type) {
      case 'HEARTBEAT': {
        // 心跳响应，无需处理
        break;
      }

      case 'MESSAGE': {
        const msgPayload = payload as {
          message_id?: string;
          content?: string;
          role?: 'assistant' | 'system';
          intent?: string;
          latency_ms?: number;
          complete?: boolean;
        };

        if (msgPayload.complete) {
          // 流式消息结束标记
          const streamingId = `streaming-${msgPayload.message_id ?? Date.now()}`;
          store.updateMessage(streamingId, {
            status: 'sent',
            id: msgPayload.message_id ?? streamingId,
          });
        } else if (msgPayload.content) {
          const messageId = msgPayload.message_id ?? `msg-${Date.now()}`;
          const existingMsg = store.messages.find(
            (m) => m.id === messageId || m.id === `streaming-${messageId}`
          );

          if (existingMsg) {
            store.appendMessageContent(existingMsg.id, msgPayload.content);
          } else {
            const newMessage: Message = {
              id: `streaming-${messageId}`,
              role: msgPayload.role ?? 'assistant',
              content: msgPayload.content,
              timestamp: Date.now(),
              status: 'streaming',
              intent: msgPayload.intent,
              latencyMs: msgPayload.latency_ms,
            };
            store.addMessage(newMessage);
          }
        }

        store.setIsLoading(false);
        break;
      }

      case 'CLARIFICATION': {
        const clPayload = payload as {
          clarification_id?: string;
          clarifications?: unknown[];
          suggestions?: string[];
        };

        store.setPendingClarification(true);

        if (clPayload.clarifications) {
          const lastMsg = [...store.messages].reverse().find(
            (m) => m.role === 'assistant'
          );
          if (lastMsg) {
            store.updateMessage(lastMsg.id, {
              clarifications: clPayload.clarifications as never[],
              suggestions: clPayload.suggestions,
            });
          }
        }
        store.setIsLoading(false);
        break;
      }

      case 'SYSTEM_STATUS': {
        const statusPayload = payload as {
          state?: string;
          current_turn?: number;
          pending_clarification?: boolean;
          last_activity_at?: string;
          expires_at?: string;
        };

        if (statusPayload.state) {
          store.setSessionState(statusPayload.state as never);
        }
        if (typeof statusPayload.current_turn === 'number') {
          store.setCurrentTurn(statusPayload.current_turn);
        }
        if (typeof statusPayload.pending_clarification === 'boolean') {
          store.setPendingClarification(statusPayload.pending_clarification);
        }
        if (statusPayload.last_activity_at) {
          store.setLastActivityAt(statusPayload.last_activity_at);
        }
        if (statusPayload.expires_at) {
          store.setExpiresAt(statusPayload.expires_at);
        }
        break;
      }

      case 'ERROR': {
        const errPayload = payload as { error?: string; message?: string };
        store.setError(errPayload.error ?? errPayload.message ?? '未知服务端错误');
        store.setIsLoading(false);
        break;
      }

      case 'TASK_GRAPH_UPDATE': {
        const tgPayload = payload as { task_graph?: unknown[] };
        if (tgPayload.task_graph) {
          store.updateTaskGraph(tgPayload.task_graph as never[]);
        }
        break;
      }

      case 'COGNITIVE_TREE_UPDATE': {
        const ctPayload = payload as { cognitive_profile?: unknown; fsm?: unknown };
        if (ctPayload.cognitive_profile) {
          store.setCognitiveProfile(ctPayload.cognitive_profile as never);
        }
        if (ctPayload.fsm) {
          store.setFsm(ctPayload.fsm as never);
        }
        break;
      }

      case 'THINKING_START': {
        store.setSessionState('thinking');
        store.setIsLoading(true);
        break;
      }

      case 'THINKING_STEP': {
        const stepPayload = payload as { step?: string; description?: string };
        console.log('[Thinking]', stepPayload.step, stepPayload.description);
        break;
      }

      case 'THINKING_END': {
        store.setSessionState('idle');
        store.setIsLoading(false);
        break;
      }

      default: {
        console.log('[useWebSocket] 未处理事件:', event_type, payload);
      }
    }
  }, [store]);

  // 连接操作
  const connect = useCallback((sessionId: string, wsUrl?: string) => {
    store.setWsConnecting(true);
    store.setError(null);
    const client = getOrCreateWsClient();
    client.connect(sessionId, wsUrl);
  }, [getOrCreateWsClient, store]);

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.disconnect();
      wsRef.current = null;
    }
    store.setWsConnected(false);
    store.setWsConnecting(false);
  }, [store]);

  // 创建会话并连接
  const createAndConnect = useCallback(async () => {
    if (!restRef.current) {
      throw new Error('REST client 未初始化');
    }

    store.setIsLoading(true);
    store.setError(null);

    try {
      const response: CreateSessionResponse = await restRef.current.createSession();
      store.initializeSession(response);
      connect(response.session_id, response.ws_url);
    } catch (err) {
      const message = err instanceof Error ? err.message : '创建会话失败';
      store.setError(message);
      throw err;
    } finally {
      store.setIsLoading(false);
    }
  }, [connect, store]);

  // 发送消息（带 loading 状态）
  const sendMessage = useCallback(
    (content: string, context?: Record<string, unknown>) => {
      const client = wsRef.current;
      if (!client || !client.isConnected()) {
        store.setError('WebSocket 未连接');
        return;
      }

      // 先添加用户消息到 store
      const userMessage: Message = {
        id: `user-${Date.now()}`,
        role: 'user',
        content,
        timestamp: Date.now(),
        status: 'sent',
      };
      store.addMessage(userMessage);
      store.setIsLoading(true);
      store.setError(null);

      client.sendMessage(content, context);
    },
    [store]
  );

  // 发送澄清响应
  const sendClarification = useCallback(
    (clarificationId: string, answers: Record<string, unknown>) => {
      const client = wsRef.current;
      if (!client || !client.isConnected()) {
        store.setError('WebSocket 未连接');
        return;
      }

      store.setPendingClarification(false);
      store.setIsLoading(true);
      store.setError(null);

      client.sendClarify(clarificationId, answers);
    },
    [store]
  );

  // 发送 ping
  const sendPing = useCallback(() => {
    wsRef.current?.sendPing();
  }, []);

  // 发送状态请求
  const sendGetStatus = useCallback(() => {
    wsRef.current?.sendGetStatus();
  }, []);

  // 清理
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.disconnect();
        wsRef.current = null;
      }
    };
  }, []);

  return {
    connected: store.wsConnected,
    connecting: store.wsConnecting,
    sessionId: store.sessionId,
    sessionState: store.sessionState,
    connect,
    disconnect,
    createAndConnect,
    sendMessage,
    sendClarification,
    sendPing,
    sendGetStatus,
    restClient: restRef.current ?? createRestClient(store.restBaseUrl),
    wsClient: wsRef.current,
  };
}

// ==================== useRestApi Hook ====================

export interface UseRestApiReturn {
  client: RestApiClient;
  createSession: () => Promise<CreateSessionResponse>;
  sendMessage: (sessionId: string, content: string) => Promise<SendMessageResponse>;
  sendClarification: (
    sessionId: string,
    clarificationId: string,
    answers: Record<string, unknown>
  ) => Promise<ClarifyResponse>;
  getHistory: (sessionId: string, limit?: number) => Promise<HistoryResponse>;
  getSessionStatus: (sessionId: string) => Promise<SessionStatusResponse>;
  getHealth: () => Promise<HealthResponse>;
  isLoading: boolean;
  error: string | null;
  clearError: () => void;
}

export function useRestApi(): UseRestApiReturn {
  const store = useSessionStore();
  const restRef = useRef<RestApiClient>(createRestClient(store.restBaseUrl));

  useEffect(() => {
    restRef.current.setBaseUrl(store.restBaseUrl);
  }, [store.restBaseUrl]);

  const wrapRequest = useCallback(
    async <T,>(fn: () => Promise<T>): Promise<T> => {
      store.setIsLoading(true);
      store.setError(null);
      try {
        const result = await fn();
        return result;
      } catch (err) {
        const message = err instanceof Error ? err.message : '请求失败';
        store.setError(message);
        throw err;
      } finally {
        store.setIsLoading(false);
      }
    },
    [store]
  );

  const createSession = useCallback(async (): Promise<CreateSessionResponse> => {
    return wrapRequest(() => restRef.current!.createSession());
  }, [wrapRequest]);

  const sendMessage = useCallback(
    async (sessionId: string, content: string): Promise<SendMessageResponse> => {
      return wrapRequest(() => restRef.current!.sendMessage(sessionId, content));
    },
    [wrapRequest]
  );

  const sendClarification = useCallback(
    async (sessionId: string, clarificationId: string, answers: Record<string, unknown>): Promise<ClarifyResponse> => {
      return wrapRequest(() =>
        restRef.current!.sendClarification(sessionId, clarificationId, answers)
      );
    },
    [wrapRequest]
  );

  const getHistory = useCallback(
    async (sessionId: string, limit?: number): Promise<HistoryResponse> => {
      return wrapRequest(() => restRef.current!.getHistory(sessionId, { limit }));
    },
    [wrapRequest]
  );

  const getSessionStatus = useCallback(
    async (sessionId: string): Promise<SessionStatusResponse> => {
      return wrapRequest(() => restRef.current!.getSessionStatus(sessionId));
    },
    [wrapRequest]
  );

  const getHealth = useCallback(async (): Promise<HealthResponse> => {
    return wrapRequest(() => restRef.current!.getHealth());
  }, [wrapRequest]);

  return {
    client: restRef.current,
    createSession,
    sendMessage,
    sendClarification,
    getHistory,
    getSessionStatus,
    getHealth,
    isLoading: store.isLoading,
    error: store.error,
    clearError: store.clearError,
  };
}

export { type ServerEventType, type WebSocketServerEvent };

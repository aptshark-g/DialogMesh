import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import ChatPanel from '../components/ChatPanel';
import { useSession } from '../hooks/useSession';
import { useChat } from '../hooks/useChat';
import type { ConnectionState } from '../types/ui';
import type { WebSocketServerEvent } from '../types/api';

const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:8000';

export function ChatPage() {
  const { sessionId: urlSessionId } = useParams<{ sessionId: string }>();
  const { session, initSession } = useSession();
  const [reconnectCounter, setReconnectCounter] = useState(0);

  const effectiveSessionId = urlSessionId ?? session?.session_id ?? null;

  const {
    messages,
    isThinking,
    thinkingSteps,
    pendingClarification,
    error,
    handleUserMessage,
    handleClarificationSubmit,
    handleWebSocketEvent,
    clearError,
  } = useChat(effectiveSessionId);

  const [connectionState, setConnectionState] = useState<ConnectionState>({
    status: 'closed',
    latencyMs: null,
    lastError: null,
  });

  const connectWs = useCallback(() => {
    if (!effectiveSessionId) return;
    const wsUrl = `${WS_BASE_URL}/v3/ws/${effectiveSessionId}`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      setConnectionState({ status: 'open', latencyMs: null, lastError: null });
    };

    ws.onclose = () => {
      setConnectionState((prev) => ({ ...prev, status: 'closed' }));
    };

    ws.onerror = () => {
      setConnectionState((prev) => ({
        ...prev,
        status: 'error',
        lastError: 'WebSocket 连接错误',
      }));
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as WebSocketServerEvent;
        if (data.event_type !== 'HEARTBEAT') {
          handleWebSocketEvent(data);
        }
      } catch {
        // 忽略非 JSON 消息
      }
    };

    return () => {
      ws.close();
    };
  }, [effectiveSessionId, handleWebSocketEvent, reconnectCounter]);

  useEffect(() => {
    const cleanup = connectWs();
    return cleanup;
  }, [connectWs]);

  useEffect(() => {
    if (!urlSessionId && !session) {
      initSession().catch(() => {});
    }
  }, [urlSessionId, session, initSession]);

  const handleReconnect = useCallback(() => {
    setConnectionState({ status: 'connecting', latencyMs: null, lastError: null });
    setReconnectCounter((c) => c + 1);
  }, []);

  return (
    <div className="h-full flex flex-col">
      <ChatPanel
        messages={messages}
        isThinking={isThinking}
        thinkingSteps={thinkingSteps}
        pendingClarification={pendingClarification}
        error={error}
        connectionState={connectionState}
        onSendMessage={handleUserMessage}
        onClarificationSubmit={handleClarificationSubmit}
        onClearError={clearError}
        onReconnect={handleReconnect}
      />
    </div>
  );
}

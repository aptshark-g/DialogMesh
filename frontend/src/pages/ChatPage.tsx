import { useEffect, useState, useCallback } from 'react';
import ChatPanel from '../components/ChatPanel';
import { useChat } from '../hooks/useChat';
import type { ConnectionState } from '../types/ui';
import type { V4WebSocketEvent } from '../types/api';
import { getV4WsUrl } from '../api/v4';

const WS_URL = getV4WsUrl();

export function ChatPage() {
  const {
    messages,
    isThinking,
    thinkingSteps,
    error,
    handleUserMessage,
    handleWebSocketEvent,
    clearError,
    clearMessages,
  } = useChat();

  const [connectionState, setConnectionState] = useState<ConnectionState>({
    status: 'closed',
    latencyMs: null,
    lastError: null,
  });

  const [reconnectCounter, setReconnectCounter] = useState(0);

  const connectWs = useCallback(() => {
    const ws = new WebSocket(WS_URL);

    ws.onopen = () => {
      setConnectionState({ status: 'open', latencyMs: null, lastError: null });
    };

    ws.onclose = () => {
      setConnectionState(prev => ({ ...prev, status: 'closed' }));
    };

    ws.onerror = () => {
      setConnectionState(prev => ({
        ...prev,
        status: 'error',
        lastError: 'WebSocket 连接错误',
      }));
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as V4WebSocketEvent;
        if (data.event_type !== 'HEARTBEAT') {
          handleWebSocketEvent(data);
        }
      } catch {
        // ignore non-JSON
      }
    };

    return () => {
      ws.close();
    };
  }, [handleWebSocketEvent]);

  useEffect(() => {
    const cleanup = connectWs();
    return cleanup;
  }, [connectWs, reconnectCounter]);

  const handleReconnect = useCallback(() => {
    setConnectionState({ status: 'connecting', latencyMs: null, lastError: null });
    setReconnectCounter(c => c + 1);
  }, []);

  return (
    <div className="h-full flex flex-col">
      <ChatPanel
        messages={messages}
        isThinking={isThinking}
        thinkingSteps={thinkingSteps}
        error={error}
        connectionState={connectionState}
        onSendMessage={handleUserMessage}
        onClearError={clearError}
        onReconnect={handleReconnect}
        onClearMessages={clearMessages}
      />
    </div>
  );
}

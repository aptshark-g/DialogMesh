import { useState, useCallback, useEffect } from 'react';
import ChatPanel from '../components/ChatPanel';
import type { ChatMessage } from '../types/api';
import type { ConnectionState } from '../types/ui';
import { createSession, sendMessage } from '../api/session';
import type { ProviderInfo } from '../components/ProviderSelector';

export function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>(() => {
    try { return JSON.parse(sessionStorage.getItem('dm_chat_msgs') || '[]'); } catch { return []; }
  });
  const [isThinking, setIsThinking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(() =>
    sessionStorage.getItem('dm_chat_sid')
  );

  // Persist chat state across page navigation
  useEffect(() => {
    sessionStorage.setItem('dm_chat_msgs', JSON.stringify(messages.slice(-50)));
    if (sessionId) sessionStorage.setItem('dm_chat_sid', sessionId);
  }, [messages, sessionId]);
  const [activeProvider, setActiveProvider] = useState<ProviderInfo | null>(null);
  const [connectionState, setConnectionState] = useState<ConnectionState>({
    status: 'connecting', latencyMs: null, lastError: null,
  });

  useEffect(() => {
    createSession()
      .then(resp => {
        setSessionId(resp.session_id);
        setConnectionState({ status: 'open', latencyMs: null, lastError: null });
      })
      .catch(err => {
        setConnectionState({ status: 'error', latencyMs: null, lastError: err.message });
      });
  }, []);

  const handleUserMessage = useCallback(async (content: string) => {
    if (!sessionId || !content.trim()) return;

    const userMsg: ChatMessage = { id: Date.now().toString(), role: 'user', content, timestamp: Date.now() };
    setMessages(prev => [...prev, userMsg]);
    setIsThinking(true);

    try {
      const resp = await sendMessage(sessionId, content,
        activeProvider?.name, activeProvider?.model);
      const reply = resp.content || '(no reply)';
      const aiMsg: ChatMessage = { id: (Date.now() + 1).toString(), role: 'assistant', content: reply, timestamp: Date.now() };
      setMessages(prev => [...prev, aiMsg]);
    } catch (err: any) {
      setError(err.message || '发送失败');
    } finally {
      setIsThinking(false);
    }
  }, [sessionId]);

  const clearError = useCallback(() => setError(null), []);
  const clearMessages = useCallback(() => setMessages([]), []);

  return (
    <div className="h-full flex flex-col">
      <ChatPanel
        messages={messages}
        isThinking={isThinking}
        thinkingSteps={[]}
        error={error}
        connectionState={connectionState}
        onSendMessage={handleUserMessage}
        onClearError={clearError}
        onReconnect={() => window.location.reload()}
        onClearMessages={clearMessages}
        onSelectProvider={setActiveProvider}
        activeProvider={activeProvider}
      />
    </div>
  );
}

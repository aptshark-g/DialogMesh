import { useState, useCallback } from 'react';
import type { ChatMessage, V4WebSocketEvent, ThinkingStep } from '../types/api';
import { sendEvent } from '../api/v4';

export function useChat(_sessionId?: string | null) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isThinking, setIsThinking] = useState(false);
  const [thinkingSteps, setThinkingSteps] = useState<ThinkingStep[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [pendingClarification, setPendingClarification] = useState<{
    clarificationId: string;
    questions: { id: string; question: string; type: string; options?: string[]; required: boolean }[];
  } | null>(null);

  const addMessage = useCallback((msg: ChatMessage) => {
    setMessages(prev => [...prev, msg]);
  }, []);

  const handleUserMessage = useCallback(async (content: string) => {
    if (!content.trim()) return;

    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: content.trim(),
      timestamp: Date.now(),
      status: 'sent',
    };
    addMessage(userMsg);
    setError(null);
    setIsThinking(true);
    setThinkingSteps([]);
    setPendingClarification(null);

    try {
      const res = await sendEvent(content.trim());

      const assistantMsg: ChatMessage = {
        id: res.event_id,
        role: 'assistant',
        content: res.response ?? '(无回复)',
        timestamp: Date.now(),
        status: 'sent',
      };
      addMessage(assistantMsg);
    } catch (err) {
      const msg = err instanceof Error ? err.message : '发送失败';
      setError(msg);
    } finally {
      setIsThinking(false);
    }
  }, [addMessage]);

  const handleClarificationSubmit = useCallback(async (_answers: Record<string, unknown>) => {
    // v4 does not have clarification flow; just clear the state
    setPendingClarification(null);
  }, []);

  const handleWebSocketEvent = useCallback((event: V4WebSocketEvent) => {
    switch (event.event_type) {
      case 'THINKING_START': {
        setIsThinking(true);
        setThinkingSteps([]);
        break;
      }
      case 'THINKING_STEP': {
        const payload = event.payload as { step?: number; description?: string };
        if (payload.step !== undefined && payload.description) {
          setThinkingSteps(prev => [
            ...prev,
            { step: payload.step!, description: payload.description, timestamp: Date.now() },
          ]);
        }
        break;
      }
      case 'THINKING_END': {
        setIsThinking(false);
        break;
      }
      case 'MESSAGE': {
        const payload = event.payload as { content?: string; event_id?: string };
        if (payload.content) {
          setMessages(prev => {
            const id = payload.event_id || `ws_${Date.now()}`;
            if (prev.find(m => m.id === id)) return prev;
            const msg: ChatMessage = {
              id,
              role: 'assistant',
              content: payload.content!,
              timestamp: Date.now(),
              status: 'sent',
            };
            return [...prev, msg];
          });
        }
        break;
      }
      case 'ERROR': {
        const payload = event.payload as { message?: string };
        setError(payload.message || '未知错误');
        break;
      }
      default:
        break;
    }
  }, []);

  const clearMessages = useCallback(() => {
    setMessages([]);
  }, []);

  return {
    messages,
    isThinking,
    thinkingSteps,
    pendingClarification,
    error,
    handleUserMessage,
    handleClarificationSubmit,
    handleWebSocketEvent,
    clearError: () => setError(null),
    clearMessages,
  };
}

import { useState, useCallback } from 'react';
import type { ChatMessage, SendMessageResponse, ClarifyResponse, ThinkingStep, WebSocketServerEvent } from '../types/api';
import { sendMessage, submitClarification } from '../api/session';

export function useChat(sessionId: string | null) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isThinking, setIsThinking] = useState(false);
  const [thinkingSteps, setThinkingSteps] = useState<ThinkingStep[]>([]);
  const [pendingClarification, setPendingClarification] = useState<{
    clarificationId: string;
    questions: { id: string; question: string; type: string; options?: string[]; required: boolean }[];
  } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const addMessage = useCallback((msg: ChatMessage) => {
    setMessages(prev => [...prev, msg]);
  }, []);

  const handleUserMessage = useCallback(async (content: string) => {
    if (!sessionId || !content.trim()) return;

    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: content.trim(),
      timestamp: Date.now(),
      status: 'sending',
    };
    addMessage(userMsg);
    setError(null);
    setIsThinking(true);
    setThinkingSteps([]);

    try {
      const res: SendMessageResponse = await sendMessage(sessionId, content.trim());

      setMessages(prev =>
        prev.map(m => (m.id === userMsg.id ? { ...m, status: 'sent' } : m))
      );

      if (res.error) {
        setError(res.error);
        setIsThinking(false);
        return;
      }

      const assistantMsg: ChatMessage = {
        id: res.message_id,
        role: 'assistant',
        content: res.content ?? '',
        timestamp: Date.now(),
        status: 'sent',
        metadata: {
          intent: res.intent ?? undefined,
          taskGraph: res.task_graph ?? undefined,
          clarifications: res.clarifications ?? undefined,
          suggestions: res.suggestions ?? undefined,
          latencyMs: res.latency_ms,
        },
      };
      addMessage(assistantMsg);

      if (res.clarifications && res.clarifications.length > 0) {
        setPendingClarification({
          clarificationId: res.message_id,
          questions: res.clarifications.map(c => ({
            id: c.id,
            question: c.question,
            type: c.type,
            options: c.options,
            required: c.required,
          })),
        });
      } else {
        setPendingClarification(null);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : '发送失败';
      setError(msg);
      setMessages(prev =>
        prev.map(m => (m.id === userMsg.id ? { ...m, status: 'error' } : m))
      );
    } finally {
      setIsThinking(false);
    }
  }, [sessionId, addMessage]);

  const handleClarificationSubmit = useCallback(async (answers: Record<string, unknown>) => {
    if (!sessionId || !pendingClarification) return;

    setError(null);
    setIsThinking(true);

    try {
      const res: ClarifyResponse = await submitClarification(
        sessionId,
        pendingClarification.clarificationId,
        answers
      );

      if (res.error) {
        setError(res.error);
        setIsThinking(false);
        return;
      }

      setPendingClarification(null);

      const assistantMsg: ChatMessage = {
        id: res.clarification_id ?? `clarify-${Date.now()}`,
        role: 'assistant',
        content: res.clarifications?.map(c => c.question).join('\n') ?? '',
        timestamp: Date.now(),
        status: 'sent',
        metadata: {
          intent: res.intent ?? undefined,
          clarifications: res.clarifications ?? undefined,
          suggestions: res.suggestions ?? undefined,
        },
      };
      addMessage(assistantMsg);
    } catch (err) {
      const msg = err instanceof Error ? err.message : '提交失败';
      setError(msg);
    } finally {
      setIsThinking(false);
    }
  }, [sessionId, pendingClarification, addMessage]);

  const handleWebSocketEvent = useCallback((event: WebSocketServerEvent) => {
    switch (event.event_type) {
      case 'THINKING_START': {
        setIsThinking(true);
        setThinkingSteps([]);
        break;
      }
      case 'THINKING_STEP': {
        const payload = event.payload as unknown as { step: number; description: string };
        setThinkingSteps(prev => [
          ...prev,
          { step: payload.step, description: payload.description, timestamp: Date.now() },
        ]);
        break;
      }
      case 'THINKING_END': {
        setIsThinking(false);
        break;
      }
      case 'MESSAGE': {
        const payload = event.payload as unknown as { message_id: string; content: string; role: 'user' | 'assistant' | 'system' };
        setMessages(prev => {
          if (prev.find(m => m.id === payload.message_id)) return prev;
          const msg: ChatMessage = {
            id: payload.message_id,
            role: payload.role,
            content: payload.content,
            timestamp: Date.now(),
            status: 'sent',
          };
          return [...prev, msg];
        });
        break;
      }
      case 'ERROR': {
        const payload = event.payload as unknown as { message: string };
        setError(payload.message || '未知错误');
        break;
      }
      default:
        break;
    }
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
  };
}

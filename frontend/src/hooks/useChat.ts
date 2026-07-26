import { useState, useCallback } from 'react';
import type { ChatMessage, V4WebSocketEvent, ThinkingStep } from '../types/api';
import { sendEvent } from '../api/v4';
import { sendChatMessage, respondCheckpoint } from '../api/v6';
import type { ChatResponse, CheckpointRespondRequest } from '../api/v6';
import { logAction } from '../lib/debug';

interface CheckpointState {
  session_id: string;
  checkpoint: NonNullable<ChatResponse['checkpoint']>;
}

export function useChat(_sessionId?: string | null) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isThinking, setIsThinking] = useState(false);
  const [thinkingSteps, setThinkingSteps] = useState<ThinkingStep[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [pendingClarification, setPendingClarification] = useState<{
    clarificationId: string;
    questions: { id: string; question: string; type: string; options?: string[]; required: boolean }[];
  } | null>(null);
  // ═══ PlanGate checkpoint state ═══
  const [checkpoint, setCheckpoint] = useState<CheckpointState | null>(null);

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
    setCheckpoint(null);

    // Debug: log user action
    logAction('chat_send', { message: content.trim().slice(0, 50), session_id: _sessionId });

    try {
      // v6 pipeline entry
      const resp = await sendChatMessage({
        message: content.trim(),
        session_id: _sessionId || undefined,
      });

      if (resp.status === 'pending_review' && resp.checkpoint) {
        // PlanGate checkpoint — user must approve
        setCheckpoint({
          session_id: resp.session_id,
          checkpoint: resp.checkpoint,
        });
      } else if (resp.status === 'completed' && resp.answer) {
        const assistantMsg: ChatMessage = {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: resp.answer,
          timestamp: Date.now(),
          status: 'sent',
          metadata: {
            execution: resp.execution,
            trace_id: resp.trace_id,
            latency_ms: resp.latency_ms,
          },
        };
        addMessage(assistantMsg);
      } else {
        setError(resp.status === 'error' ? 'Pipeline error' : 'Unknown response');
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : '发送失败';
      setError(msg);
    } finally {
      setIsThinking(false);
    }
  }, [addMessage, _sessionId]);

  // ═══ PlanGate checkpoint response ═══
  const handleCheckpointResponse = useCallback(async (
    decision: 'approved' | 'adjusted' | 'rejected',
    note?: string,
    stepOverrides?: Record<string, { approved: boolean; params?: Record<string, unknown> }>
  ) => {
    if (!checkpoint) return;

    // Debug: log checkpoint response
    logAction('checkpoint_respond', { decision, note });

    setIsThinking(true);
    try {
      const resp = await respondCheckpoint({
        session_id: checkpoint.session_id,
        checkpoint_id: checkpoint.checkpoint.checkpoint_id,
        decision,
        note,
        steps: stepOverrides,
      });

      if (resp.answer) {
        const assistantMsg: ChatMessage = {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: resp.answer,
          timestamp: Date.now(),
          status: 'sent',
          metadata: { execution: resp.execution, latency_ms: resp.latency_ms },
        };
        addMessage(assistantMsg);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '审批提交失败');
    } finally {
      setIsThinking(false);
      setCheckpoint(null);
    }
  }, [checkpoint, addMessage]);

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
        const step = payload.step;
        const description = payload.description;
        if (step !== undefined && description) {
          setThinkingSteps(prev => [
            ...prev,
            { step, description, timestamp: Date.now() },
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
    checkpoint,
    error,
    handleUserMessage,
    handleCheckpointResponse,
    handleClarificationSubmit,
    handleWebSocketEvent,
    clearError: () => setError(null),
    clearCheckpoint: () => setCheckpoint(null),
    clearMessages,
  };
}

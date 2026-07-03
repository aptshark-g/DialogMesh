import { useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Minimize2, Maximize2, Send, Loader2, AlertCircle, MessageSquare } from 'lucide-react';
import { useSession } from '@/hooks/useSession';
import { useChat } from '@/hooks/useChat';
import { useOverlayStore } from '@/stores/overlayStore';
import { cn, formatRelativeTime } from '@/lib/utils';
import type { ChatMessage, WebSocketServerEvent } from '@/types/api';

const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:8000';

export function ChatOverlay() {
  const { isOpen, isMinimized, close, minimize, maximize } = useOverlayStore();
  const { session, initSession } = useSession();
  const [inputValue, setInputValue] = useState('');
  const [clarificationAnswers, setClarificationAnswers] = useState<Record<string, unknown>>({});
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const sessionId = session?.session_id ?? null;

  const {
    messages,
    isThinking,
    pendingClarification,
    error,
    handleUserMessage,
    handleClarificationSubmit,
    handleWebSocketEvent,
    clearError,
  } = useChat(sessionId);

  useEffect(() => {
    if (!sessionId) {
      initSession().catch(() => {});
    }
  }, [sessionId, initSession]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isThinking]);

  useEffect(() => {
    if (!sessionId || !isOpen) return;
    const wsUrl = `${WS_BASE_URL}/v3/ws/${sessionId}`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log('[ChatOverlay] WebSocket connected');
    };

    ws.onclose = () => {
      console.log('[ChatOverlay] WebSocket closed');
    };

    ws.onerror = () => {
      console.error('[ChatOverlay] WebSocket error');
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
  }, [sessionId, isOpen, handleWebSocketEvent]);

  const handleSubmit = useCallback(() => {
    const text = inputValue.trim();
    if (!text || !sessionId) return;
    handleUserMessage(text);
    setInputValue('');
  }, [inputValue, sessionId, handleUserMessage]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }, [handleSubmit]);

  const handleClarificationChange = useCallback((questionId: string, value: unknown) => {
    setClarificationAnswers((prev) => ({ ...prev, [questionId]: value }));
  }, []);

  const handleClarificationSubmitLocal = useCallback(() => {
    if (!pendingClarification) return;
    handleClarificationSubmit(clarificationAnswers);
    setClarificationAnswers({});
  }, [pendingClarification, clarificationAnswers, handleClarificationSubmit]);

  if (!isOpen) return null;

  if (isMinimized) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 20 }}
        className="bg-surface-card border border-subtle rounded-lg shadow-modal p-3 w-[320px] cursor-pointer"
        onClick={maximize}
      >
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-text-primary">DialogMesh</span>
          <Maximize2 className="w-4 h-4 text-text-secondary" />
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 20, scale: 0.95 }}
      transition={{ type: 'spring', damping: 25, stiffness: 300 }}
      className="bg-surface-card border border-subtle rounded-xl shadow-modal overflow-hidden flex flex-col"
      style={{ width: 380, maxHeight: 520 }}
    >
      {/* Header */}
      <div className="h-12 flex items-center justify-between px-4 border-b border-subtle shrink-0 bg-surface-sidebar">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-emerald-500" />
          <span className="text-sm font-semibold text-text-primary">对话助手</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={minimize}
            className="p-1.5 rounded-md hover:bg-surface-card-hover text-text-secondary transition-colors"
            aria-label="最小化"
          >
            <Minimize2 className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={close}
            className="p-1.5 rounded-md hover:bg-surface-card-hover text-text-secondary transition-colors"
            aria-label="关闭"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3 min-h-0">
        {messages.length === 0 && !isThinking && (
          <div className="flex flex-col items-center justify-center py-16 text-text-muted">
            <MessageSquare className="w-10 h-10 mb-2 opacity-50" />
            <p className="text-sm">发送消息开始对话</p>
          </div>
        )}

        {messages.map((msg) => (
          <ChatOverlayMessage key={msg.id} message={msg} />
        ))}

        {isThinking && <ThinkingIndicator />}

        {error && (
          <div className="flex items-center gap-2 p-2 rounded-lg bg-status-error/10 border border-status-error/20 text-status-error text-sm">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span className="flex-1">{error}</span>
            <button
              type="button"
              onClick={clearError}
              className="ml-auto text-xs hover:underline px-1"
            >
              清除
            </button>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Clarification */}
      <AnimatePresence>
        {pendingClarification && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="border-t border-subtle overflow-hidden shrink-0"
          >
            <div className="p-3 space-y-2">
              <p className="text-xs font-medium text-text-primary mb-1">需要澄清</p>
              {pendingClarification.questions.map((q) => (
                <div key={q.id} className="text-sm">
                  <p className="text-text-secondary mb-1">
                    {q.question}
                    {q.required && <span className="text-rose ml-0.5">*</span>}
                  </p>
                  {q.type === 'choice' && q.options ? (
                    <div className="flex flex-wrap gap-2">
                      {q.options.map((opt) => (
                        <button
                          key={opt}
                          type="button"
                          onClick={() => handleClarificationChange(q.id, opt)}
                          className={cn(
                            'px-2 py-1 rounded-md text-xs transition-colors',
                            clarificationAnswers[q.id] === opt
                              ? 'bg-primary text-white'
                              : 'bg-surface-card-hover text-text-primary hover:bg-primary/20'
                          )}
                        >
                          {opt}
                        </button>
                      ))}
                    </div>
                  ) : q.type === 'confirm' ? (
                    <div className="flex flex-wrap gap-2">
                      {['是', '否'].map((opt) => (
                        <button
                          key={opt}
                          type="button"
                          onClick={() => handleClarificationChange(q.id, opt === '是')}
                          className={cn(
                            'px-2 py-1 rounded-md text-xs transition-colors',
                            clarificationAnswers[q.id] === (opt === '是')
                              ? 'bg-primary text-white'
                              : 'bg-surface-card-hover text-text-primary hover:bg-primary/20'
                          )}
                        >
                          {opt}
                        </button>
                      ))}
                    </div>
                  ) : (
                    <input
                      type="text"
                      value={String(clarificationAnswers[q.id] || '')}
                      onChange={(e) => handleClarificationChange(q.id, e.target.value)}
                      className="w-full bg-surface-input border border-subtle rounded-md px-2 py-1 text-sm text-text-primary focus:outline-none focus:border-primary"
                      placeholder="输入回答..."
                    />
                  )}
                </div>
              ))}
              <button
                type="button"
                onClick={handleClarificationSubmitLocal}
                disabled={pendingClarification.questions.some(
                  (q) => q.required && clarificationAnswers[q.id] === undefined
                )}
                className="mt-1 w-full py-1.5 rounded-md bg-primary text-white text-xs font-medium hover:bg-primary-dark transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                提交澄清
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Input */}
      <div className="p-3 border-t border-subtle shrink-0">
        <div className="flex items-center gap-2">
          <input
            ref={inputRef}
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={pendingClarification ? '请先完成上方澄清' : '输入消息...'}
            disabled={isThinking || !!pendingClarification}
            className="flex-1 bg-surface-input border border-subtle rounded-lg px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-primary transition-colors disabled:opacity-50"
          />
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!inputValue.trim() || !sessionId || isThinking || !!pendingClarification}
            className="p-2 rounded-lg bg-primary text-white hover:bg-primary-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            aria-label="发送"
          >
            {isThinking ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
          </button>
        </div>
      </div>
    </motion.div>
  );
}

function ChatOverlayMessage({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user';

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn('flex flex-col gap-1', isUser ? 'items-end' : 'items-start')}
    >
      <div
        className={cn(
          'max-w-[85%] rounded-lg px-3 py-2 text-sm leading-relaxed',
          isUser
            ? 'bg-primary text-white rounded-br-none'
            : 'bg-surface-card-hover text-text-primary rounded-bl-none border border-subtle'
        )}
      >
        <p className="whitespace-pre-wrap break-words">{message.content}</p>
      </div>
      <span className="text-[10px] text-text-muted">
        {formatRelativeTime(message.timestamp)}
      </span>
    </motion.div>
  );
}

function ThinkingIndicator() {
  return (
    <div className="flex items-center gap-2 px-3 py-2">
      <div className="flex gap-1">
        <div className="w-2 h-2 rounded-full bg-primary thinking-dot" />
        <div className="w-2 h-2 rounded-full bg-primary thinking-dot" />
        <div className="w-2 h-2 rounded-full bg-primary thinking-dot" />
      </div>
      <span className="text-xs text-text-muted">思考中...</span>
    </div>
  );
}

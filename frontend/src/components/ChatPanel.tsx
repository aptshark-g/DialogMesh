import { useRef, useEffect, useCallback, useState } from 'react';
import { X } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import MessageBubble from './MessageBubble';
import ChatInput from './ChatInput';
import ThinkingIndicator from './ThinkingIndicator';
import ConnectionStatus from './ConnectionStatus';
import type { ChatMessage, ThinkingStep } from '../types/api';
import type { ConnectionState } from '../types/ui';

interface ChatPanelProps {
  messages: ChatMessage[];
  isThinking: boolean;
  thinkingSteps: ThinkingStep[];
  pendingClarification: {
    clarificationId: string;
    questions: { id: string; question: string; type: string; options?: string[]; required: boolean }[];
  } | null;
  error: string | null;
  connectionState: ConnectionState;
  onSendMessage: (content: string) => void;
  onClarificationSubmit: (answers: Record<string, unknown>) => void;
  onClearError: () => void;
  onReconnect: () => void;
}

export default function ChatPanel({
  messages,
  isThinking,
  thinkingSteps,
  pendingClarification,
  error,
  connectionState,
  onSendMessage,
  onClarificationSubmit,
  onClearError,
  onReconnect,
}: ChatPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [clarificationAnswers, setClarificationAnswers] = useState<Record<string, unknown>>({});

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isThinking, thinkingSteps]);

  const handleClarificationChange = useCallback((questionId: string, value: unknown) => {
    setClarificationAnswers(prev => ({ ...prev, [questionId]: value }));
  }, []);

  const handleClarificationSubmitLocal = useCallback(() => {
    if (!pendingClarification) return;
    const missing = pendingClarification.questions.filter(q => q.required && !clarificationAnswers[q.id]);
    if (missing.length > 0) return;
    onClarificationSubmit(clarificationAnswers);
    setClarificationAnswers({});
  }, [pendingClarification, clarificationAnswers, onClarificationSubmit]);

  const isInputDisabled = isThinking || !!pendingClarification || connectionState.status !== 'open';

  return (
    <div className="flex flex-col h-full">
      {/* Connection Status Bar */}
      <AnimatePresence>
        {(connectionState.status === 'closed' || connectionState.status === 'error' || connectionState.status === 'connecting') && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="flex items-center justify-between px-3 py-2 md:px-4 bg-surface-card border-b border-subtle gap-2">
              <ConnectionStatus state={connectionState} />
              {(connectionState.status === 'closed' || connectionState.status === 'error') && (
                <button
                  onClick={onReconnect}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-primary text-white text-xs font-medium hover:bg-primary-dark transition-colors"
                >
                  重连
                </button>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-3 py-3 md:px-4 md:py-4 space-y-1 scrollbar-hide">
        {messages.length === 0 && !isThinking && (
          <motion.div
            initial={{ opacity: 0, scale: 0.96 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.4, ease: 'easeOut' }}
            className="flex flex-col items-center justify-center h-full text-center px-2"
          >
            <div className="w-14 h-14 md:w-16 md:h-16 rounded-2xl bg-surface-card border border-subtle flex items-center justify-center mb-4 shadow-card">
              <span className="text-2xl md:text-3xl">🔶</span>
            </div>
            <h2 className="text-base md:text-lg font-medium text-text-primary mb-2">开始对话</h2>
            <p className="text-sm text-text-secondary max-w-xs leading-relaxed">
              发送消息与 DialogMesh 认知架构交互。系统将通过 WebSocket 实时推送思考过程与状态更新。
            </p>
          </motion.div>
        )}

        {messages.map((msg, idx) => (
          <div
            key={msg.id}
            className="animate-message-enter"
            style={{ animationDelay: `${idx * 50}ms` }}
          >
            <MessageBubble message={msg} />
          </div>
        ))}

        {isThinking && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
          >
            <ThinkingIndicator steps={thinkingSteps} />
          </motion.div>
        )}

        {/* Error Banner */}
        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ opacity: 0, y: -10, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -10, scale: 0.98 }}
              transition={{ duration: 0.2 }}
              className="flex items-center justify-center my-3"
            >
              <div className="flex items-center gap-2 px-3 py-2 md:px-4 md:py-2.5 rounded-lg bg-status-error/5 border border-status-error/20 text-status-error text-sm max-w-[95%] md:max-w-[90%]">
                <span className="flex-1">{error}</span>
                <button
                  onClick={onClearError}
                  className="flex-shrink-0 p-1 hover:bg-status-error/10 rounded-md transition-colors"
                  aria-label="关闭错误"
                >
                  <X size={14} />
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Clarification Panel */}
      <AnimatePresence>
        {pendingClarification && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            transition={{ duration: 0.3, ease: 'easeOut' }}
            className="px-3 py-3 md:px-4 md:py-3 bg-surface-card border-t border-subtle"
          >
            <p className="text-sm font-medium text-text-primary mb-3 flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-primary flex-shrink-0" />
              需要澄清
            </p>
            <div className="space-y-3">
              {pendingClarification.questions.map(q => (
                <div key={q.id} className="space-y-1">
                  <label className="text-sm text-text-secondary">
                    {q.question}
                    {q.required && <span className="text-status-error ml-1">*</span>}
                  </label>
                  {q.type === 'choice' && q.options ? (
                    <div className="flex flex-wrap gap-2">
                      {q.options.map(opt => (
                        <button
                          key={opt}
                          onClick={() => handleClarificationChange(q.id, opt)}
                          className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${
                            clarificationAnswers[q.id] === opt
                              ? 'bg-primary text-white border-primary'
                              : 'bg-surface-sidebar text-text-primary border-subtle hover:border-primary'
                          }`}
                        >
                          {opt}
                        </button>
                      ))}
                    </div>
                  ) : q.type === 'confirm' ? (
                    <div className="flex gap-2">
                      {['是', '否'].map(opt => (
                        <button
                          key={opt}
                          onClick={() => handleClarificationChange(q.id, opt === '是')}
                          className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${
                            clarificationAnswers[q.id] === (opt === '是')
                              ? 'bg-primary text-white border-primary'
                              : 'bg-surface-sidebar text-text-primary border-subtle hover:border-primary'
                          }`}
                        >
                          {opt}
                        </button>
                      ))}
                    </div>
                  ) : (
                    <input
                      type="text"
                      value={String(clarificationAnswers[q.id] || '')}
                      onChange={e => handleClarificationChange(q.id, e.target.value)}
                      className="w-full px-3 py-2 rounded-lg border border-subtle bg-surface-input text-sm text-text-primary focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary placeholder:text-text-muted"
                      placeholder="请输入..."
                    />
                  )}
                </div>
              ))}
            </div>
            <button
              onClick={handleClarificationSubmitLocal}
              disabled={pendingClarification.questions.some(q => q.required && !clarificationAnswers[q.id])}
              className="mt-3 flex items-center justify-center gap-2 w-full py-2.5 rounded-lg bg-primary text-white text-sm font-medium hover:bg-primary-dark transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              提交澄清
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Input */}
      <ChatInput
        onSend={onSendMessage}
        disabled={isInputDisabled}
        placeholder={pendingClarification ? '请先完成上方澄清' : '输入消息...'}
      />
    </div>
  );
}

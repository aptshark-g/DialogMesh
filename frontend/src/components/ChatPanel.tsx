import { useRef, useEffect, useCallback, useState } from 'react';
import { Wifi, X, ChevronRight } from 'lucide-react';
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
    <div className="flex flex-col h-full bg-surface-main">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-3 bg-surface-card border-b border-gray-200 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center text-white">
            <Wifi size={18} />
          </div>
          <div>
            <h1 className="text-sm font-semibold text-text-primary">DialogMesh v3.0</h1>
            <p className="text-xs text-text-muted">多层 LLM 认知架构</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <ConnectionStatus state={connectionState} />
          {connectionState.status === 'closed' || connectionState.status === 'error' ? (
            <button
              onClick={onReconnect}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-primary text-white text-xs font-medium hover:bg-primary-dark transition-colors"
            >
              <Wifi size={14} />
              重连
            </button>
          ) : null}
        </div>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-1">
        {messages.length === 0 && !isThinking && (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="w-16 h-16 rounded-2xl bg-surface-thinking flex items-center justify-center mb-4">
              <Wifi size={32} className="text-primary" />
            </div>
            <h2 className="text-lg font-medium text-text-primary mb-1">开始对话</h2>
            <p className="text-sm text-text-secondary max-w-xs">
              发送消息与 DialogMesh 认知架构交互。系统将通过 WebSocket 实时推送思考过程与状态更新。
            </p>
          </div>
        )}

        {messages.map(msg => (
          <MessageBubble key={msg.id} message={msg} />
        ))}

        {isThinking && <ThinkingIndicator steps={thinkingSteps} />}

        {/* Error Banner */}
        {error && (
          <div className="flex items-center justify-center my-3">
            <div className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-red-50 border border-status-error/20 text-status-error text-sm max-w-[90%]">
              <span className="flex-1">{error}</span>
              <button
                onClick={onClearError}
                className="flex-shrink-0 p-1 hover:bg-red-100 rounded-md transition-colors"
                aria-label="关闭错误"
              >
                <X size={14} />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Clarification Panel */}
      {pendingClarification && (
        <div className="px-4 py-3 bg-surface-thinking border-t border-primary-light/30">
          <p className="text-sm font-medium text-text-primary mb-3 flex items-center gap-2">
            <ChevronRight size={16} className="text-primary" />
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
                            : 'bg-surface-card text-text-primary border-gray-200 hover:border-primary'
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
                            : 'bg-surface-card text-text-primary border-gray-200 hover:border-primary'
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
                    className="w-full px-3 py-2 rounded-lg border border-gray-200 bg-surface-card text-sm text-text-primary focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
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
        </div>
      )}

      {/* Input */}
      <ChatInput
        onSend={onSendMessage}
        disabled={isInputDisabled}
        placeholder={pendingClarification ? '请先完成上方澄清' : '输入消息...'}
      />
    </div>
  );
}

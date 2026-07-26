import { memo, useCallback, useState } from 'react';
import { User, Bot, AlertCircle, Clock, ChevronDown, ChevronRight, Loader2, Check, X, MessageSquare } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import type { ChatMessage, TaskGraphNode, ThinkingStepPayload } from '../types/api';
import { cn } from '../lib/utils';
import { submitFeedback } from '../api/v6';
import { TaskGraphView } from './TaskGraphView';
import { Toast } from './ui/Toast';

function renderMarkdown(text: string): string {
  // Simple inline markdown → HTML (bold, italic, code, tables, headers, lists, links)
  return text
    .replace(/### (.+)/g, '<h3 class="text-base font-bold mt-3 mb-1">$1</h3>')
    .replace(/## (.+)/g, '<h2 class="text-lg font-bold mt-4 mb-2">$1</h2>')
    .replace(/^# (.+)/gm, '<h1 class="text-xl font-bold mt-4 mb-2">$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`([^`]+)`/g, '<code class="bg-surface-sidebar px-1 rounded text-xs">$1</code>')
    .replace(/^- (.+)/gm, '<li class="ml-4 list-disc">$1</li>')
    .replace(/^(\d+)\. (.+)/gm, '<li class="ml-4 list-decimal">$1</li>')
    .replace(/\|(.+)\|/g, (m) => {
      const cells = m.split('|').filter(c => c.trim());
      if (m.includes('---')) return '';
      const tag = m.includes('---') ? 'th' : 'td';
      return '<tr>' + cells.map(c => `<${tag} class="border px-2 py-1 text-sm">${c.trim()}</${tag}>`).join('') + '</tr>';
    })
    .replace(/(<tr>.*<\/tr>\n?)+/g, (m) => `<table class="border-collapse my-2">${m}</table>`)
    .replace(/\n\n/g, '<br/><br/>')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" class="text-primary underline">$1</a>');
}

export interface MessageBubbleProps {
  message: ChatMessage;
  className?: string;
}

/** Extract a field from either the metadata object or the top-level ChatMessage, preferring metadata. */
function getMessageField<T>(
  message: ChatMessage,
  metadataKey: string,
  topLevelKey: keyof ChatMessage
): T | undefined {
  const meta = message.metadata as Record<string, unknown> | undefined;
  if (meta && metadataKey in meta && meta[metadataKey] !== undefined) {
    return meta[metadataKey] as T;
  }
  const topValue = message[topLevelKey];
  return topValue !== undefined ? (topValue as T) : undefined;
}

const MessageBubble = memo(function MessageBubble({ message, className }: MessageBubbleProps) {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';
  const isError = message.status === 'error';

  // Extract fields from both metadata and top-level with fallback
  const intent = getMessageField<string>(message, 'intent', 'intent');
  const taskGraph = getMessageField<TaskGraphNode[]>(message, 'taskGraph', 'taskGraph');
  const suggestions = getMessageField<string[]>(message, 'suggestions', 'suggestions');
  const latencyMs = getMessageField<number>(message, 'latencyMs', 'latencyMs');
  const thinkingSteps = getMessageField<ThinkingStepPayload[]>(
    message,
    'thinkingSteps',
    'thinkingSteps'
  );
  const clarificationId = message.clarificationId;

  const formatTime = useCallback((ts: number): string => {
    const d = new Date(ts);
    return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
  }, []);

  const [showThinking, setShowThinking] = useState(false);

  // ─── 消息反馈 (✓/✗) ───
  const [feedback, setFeedback] = useState<'up' | 'down' | 'comment' | null>(null);
  const [feedbackSending, setFeedbackSending] = useState<'up' | 'down' | 'comment' | null>(null);
  const [feedbackError, setFeedbackError] = useState<string | null>(null);

  const handleFeedback = useCallback(
    async (rating: 'up' | 'down' | 'comment') => {
      if (feedback || feedbackSending) return;
      setFeedbackSending(rating);
      setFeedbackError(null);
      try {
        if (rating === 'comment') {
          // Send to meta-cognition annotation
          const { addAnnotation } = await import('../api/v6');
          const text = `[用户注释] 消息ID=${message.id}: ${window.prompt('注释内容 (送元认知审核):', '请审查此回复') || '需要审查'}`;
          await addAnnotation(text);
          setFeedback(rating);
        } else {
          const meta = message.metadata as Record<string, unknown> | undefined;
          const turn = typeof meta?.turn === 'number' ? meta.turn : 0;
          const ruleName = typeof meta?.rule_name === 'string' ? meta.rule_name : '';
          const resp = await submitFeedback({ turn, correct: rating === 'up', rule_name: ruleName });
          if (resp.error) {
            setFeedbackError(resp.error);
          } else {
            setFeedback(rating);
          }
        }
      } catch (err) {
        setFeedbackError(err instanceof Error ? err.message : '反馈提交失败');
      } finally {
        setFeedbackSending(null);
      }
    },
    [feedback, feedbackSending, message]
  );

  if (isSystem) {
    return (
      <div className={cn('flex justify-center my-3', className)}>
        <div className="flex items-center gap-2 px-4 py-2 rounded-full bg-surface-sidebar border border-gray-200 text-text-muted text-xs">
          <AlertCircle size={14} />
          <span>{message.content}</span>
        </div>
      </div>
    );
  }

  return (
    <>
      {feedbackError && (
        <Toast type="error" message={feedbackError} onClose={() => setFeedbackError(null)} />
      )}
      <div
        className={cn('flex w-full mb-4', isUser ? 'justify-end' : 'justify-start', className)}
      >
      <div
        className={cn(
          'flex max-w-[92%] sm:max-w-[85%] md:max-w-[75%] gap-2 md:gap-3',
          isUser ? 'flex-row-reverse' : 'flex-row'
        )}
      >
        {/* Avatar */}
        <motion.div
          className={cn(
            'flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center',
            isUser ? 'bg-primary text-white' : 'bg-surface-thinking text-primary'
          )}
          whileHover={{ scale: 1.1 }}
          transition={{ type: 'spring', stiffness: 300 }}
        >
          {isUser ? <User size={16} /> : <Bot size={16} />}
        </motion.div>

        {/* Content */}
        <div className={cn('group flex flex-col', isUser ? 'items-end' : 'items-start')}>
          <motion.div
            className={cn(
              'relative px-4 py-3 rounded-2xl text-sm leading-relaxed shadow-sm',
              isUser
                ? 'bg-primary text-white rounded-br-md'
                : 'bg-surface-card text-text-primary border border-gray-200 rounded-bl-md',
              isError && 'border-status-error bg-red-50'
            )}
            whileHover={{ scale: 1.01 }}
            transition={{ duration: 0.15 }}
          >
            <div className={message.status === 'streaming' ? 'stream-cursor prose prose-sm max-w-none' : 'prose prose-sm max-w-none'}
              dangerouslySetInnerHTML={{ __html: renderMarkdown(message.content) }} />

            {/* Metadata badges */}
            {intent && (
              <div className="mt-2 flex flex-wrap gap-1">
                <span className="inline-flex items-center px-2 py-0.5 rounded-md bg-surface-thinking text-primary text-xs font-medium">
                  Intent: {intent}
                </span>
              </div>
            )}

            {clarificationId && (
              <div className="mt-2 flex flex-wrap gap-1">
                <span className="inline-flex items-center px-2 py-0.5 rounded-md bg-status-warning/10 text-status-warning text-xs font-medium">
                  Clarification: {clarificationId}
                </span>
              </div>
            )}

            {suggestions && suggestions.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {suggestions.map((s, idx) => (
                  <span
                    key={idx}
                    className="inline-flex items-center px-2 py-0.5 rounded-md bg-surface-sidebar text-text-secondary text-xs border border-gray-200"
                  >
                    {s}
                  </span>
                ))}
              </div>
            )}

            {latencyMs !== undefined && (
              <div className="mt-2 flex items-center gap-1 text-xs text-text-muted">
                <Clock size={12} />
                <span>{latencyMs}ms</span>
              </div>
            )}
          </motion.div>

          {/* 消息反馈按钮 (助手消息,hover 显示) */}
          {!isUser && message.status !== 'streaming' && (
            <div
              className={cn(
                'mt-1 flex items-center gap-1 transition-opacity',
                feedback ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
              )}
            >
              <button
                type="button"
                onClick={() => handleFeedback('up')}
                disabled={feedbackSending !== null}
                title="回答正确"
                className={cn(
                  'p-1 rounded-md border transition-colors disabled:opacity-50',
                  feedback === 'up'
                    ? 'bg-primary text-white border-primary'
                    : 'border-gray-200 text-text-muted hover:text-primary hover:border-primary/40'
                )}
              >
                {feedbackSending === 'up' ? (
                  <Loader2 size={12} className="animate-spin" />
                ) : (
                  <Check size={12} />
                )}
              </button>
              <button
                type="button"
                onClick={() => handleFeedback('down')}
                disabled={feedbackSending !== null}
                title="回答有误"
                className={cn(
                  'p-1 rounded-md border transition-colors disabled:opacity-50',
                  feedback === 'down'
                    ? 'bg-status-error text-white border-status-error'
                    : 'border-gray-200 text-text-muted hover:text-status-error hover:border-status-error/40'
                )}
              >
                {feedbackSending === 'down' ? (
                  <Loader2 size={12} className="animate-spin" />
                ) : (
                  <X size={12} />
                )}
              </button>
              <button
                type="button"
                onClick={() => handleFeedback('comment')}
                disabled={feedbackSending !== null}
                title="注释 (送元认知审核)"
                className={cn(
                  'p-1 rounded-md border transition-colors disabled:opacity-50',
                  feedback === 'comment'
                    ? 'bg-amber-500 text-white border-amber-500'
                    : 'border-gray-200 text-text-muted hover:text-amber-500 hover:border-amber-500/40'
                )}
              >
                <MessageSquare size={12} />
              </button>
              {feedback && (
                <span className="text-xs text-text-muted ml-1">感谢反馈</span>
              )}
            </div>
          )}

          {/* Thinking Steps */}
          {thinkingSteps && thinkingSteps.length > 0 && (
            <div className="mt-2 w-full">
              <button
                type="button"
                onClick={() => setShowThinking(!showThinking)}
                className="flex items-center gap-1 text-xs text-text-muted hover:text-primary transition-colors"
              >
                {showThinking ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                <span>Thinking Steps ({thinkingSteps.length})</span>
              </button>
              <AnimatePresence>
                {showThinking && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.2, ease: 'easeInOut' }}
                    className="overflow-hidden"
                  >
                    <div className="mt-1 bg-surface-thinking border border-amber-200/50 rounded-lg p-2 space-y-1">
                      {thinkingSteps.map((step, idx) => (
                        <motion.div
                          key={idx}
                          initial={{ opacity: 0, x: -4 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ delay: idx * 0.05 }}
                          className="flex items-start gap-2 text-xs text-text-secondary"
                        >
                          <span className="text-primary font-medium min-w-[1.5rem]">{step.step}.</span>
                          <div className="flex-1">
                            <p>{step.description}</p>
                            {step.detail && <p className="text-text-muted mt-0.5">{step.detail}</p>}
                          </div>
                        </motion.div>
                      ))}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )}

          {/* Task Graph */}
          {taskGraph && taskGraph.length > 0 && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3 }}
              className="mt-2 w-full"
            >
              <TaskGraphView nodes={taskGraph} />
            </motion.div>
          )}

          {/* Timestamp & Status */}
          <span className="mt-1 text-xs text-text-muted flex items-center gap-1">
            {message.status === 'sending' && (
              <span className="text-status-info">发送中...</span>
            )}
            {message.status === 'streaming' && (
              <span className="text-status-info flex items-center gap-1">
                <Loader2 size={12} className="animate-spin" />
                接收中...
              </span>
            )}
            {message.status === 'error' && (
              <span className="text-status-error">发送失败</span>
            )}
            {formatTime(message.timestamp)}
          </span>
        </div>
      </div>
      </div>
    </>
  );
});

export default MessageBubble;

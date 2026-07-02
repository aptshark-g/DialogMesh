import { memo } from 'react';
import { User, Bot, AlertCircle, Clock } from 'lucide-react';
import type { ChatMessage } from '../types/api';

interface MessageBubbleProps {
  message: ChatMessage;
}

const MessageBubble = memo(function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';
  const isError = message.status === 'error';

  const formatTime = (ts: number): string => {
    const d = new Date(ts);
    return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
  };

  if (isSystem) {
    return (
      <div className="flex justify-center my-3">
        <div className="flex items-center gap-2 px-4 py-2 rounded-full bg-surface-sidebar border border-gray-200 text-text-muted text-xs">
          <AlertCircle size={14} />
          <span>{message.content}</span>
        </div>
      </div>
    );
  }

  return (
    <div className={`flex w-full mb-4 ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`flex max-w-[85%] md:max-w-[75%] gap-3 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
        {/* Avatar */}
        <div
          className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
            isUser ? 'bg-primary text-white' : 'bg-surface-thinking text-primary'
          }`}
        >
          {isUser ? <User size={16} /> : <Bot size={16} />}
        </div>

        {/* Content */}
        <div className={`flex flex-col ${isUser ? 'items-end' : 'items-start'}`}>
          <div
            className={`relative px-4 py-3 rounded-2xl text-sm leading-relaxed shadow-sm ${
              isUser
                ? 'bg-primary text-white rounded-br-md'
                : 'bg-surface-card text-text-primary border border-gray-200 rounded-bl-md'
            } ${isError ? 'border-status-error bg-red-50' : ''}`}
          >
            {message.content}

            {/* Metadata badges */}
            {message.metadata?.intent && (
              <div className="mt-2 flex flex-wrap gap-1">
                <span className="inline-flex items-center px-2 py-0.5 rounded-md bg-surface-thinking text-primary text-xs font-medium">
                  Intent: {message.metadata.intent}
                </span>
              </div>
            )}

            {message.metadata?.suggestions && message.metadata.suggestions.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {message.metadata.suggestions.map((s, idx) => (
                  <span
                    key={idx}
                    className="inline-flex items-center px-2 py-0.5 rounded-md bg-surface-sidebar text-text-secondary text-xs border border-gray-200"
                  >
                    {s}
                  </span>
                ))}
              </div>
            )}

            {message.metadata?.latencyMs && (
              <div className="mt-2 flex items-center gap-1 text-xs text-text-muted">
                <Clock size={12} />
                <span>{message.metadata.latencyMs}ms</span>
              </div>
            )}
          </div>

          {/* Task Graph */}
          {message.metadata?.taskGraph && message.metadata.taskGraph.length > 0 && (
            <div className="mt-2 w-full bg-surface-card border border-gray-200 rounded-lg p-3 shadow-sm">
              <p className="text-xs font-medium text-text-secondary mb-2">Task Graph</p>
              <div className="space-y-1.5">
                {message.metadata.taskGraph.map(node => (
                  <div key={node.id} className="flex items-center gap-2 text-xs">
                    <div
                      className={`w-2 h-2 rounded-full ${
                        node.status === 'completed'
                          ? 'bg-status-success'
                          : node.status === 'running'
                          ? 'bg-status-info'
                          : node.status === 'failed'
                          ? 'bg-status-error'
                          : 'bg-gray-300'
                      }`}
                    />
                    <span className="text-text-primary flex-1">{node.name}</span>
                    {node.progress !== undefined && (
                      <div className="w-16 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-primary rounded-full transition-all"
                          style={{ width: `${node.progress}%` }}
                        />
                      </div>
                    )}
                    <span className="text-text-muted w-12 text-right">{node.status}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Timestamp */}
          <span className="mt-1 text-xs text-text-muted flex items-center gap-1">
            {message.status === 'sending' && <span className="text-status-info">发送中...</span>}
            {message.status === 'error' && <span className="text-status-error">发送失败</span>}
            {formatTime(message.timestamp)}
          </span>
        </div>
      </div>
    </div>
  );
});

export default MessageBubble;

import { useRef, useEffect } from 'react';
import { X } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import MessageBubble from './MessageBubble';
import ChatInput from './ChatInput';
import ThinkingIndicator from './ThinkingIndicator';
import ConnectionStatus from './ConnectionStatus';
import { ProviderSelector } from './ProviderSelector';
import type { ProviderInfo } from './ProviderSelector';
import type { ChatMessage, ThinkingStep } from '../types/api';
import type { ConnectionState } from '../types/ui';

interface ChatPanelProps {
  messages: ChatMessage[];
  isThinking: boolean;
  thinkingSteps: ThinkingStep[];
  error: string | null;
  connectionState: ConnectionState;
  onSendMessage: (content: string) => void;
  onClearError: () => void;
  onClearMessages?: () => void;
  onSelectProvider?: (info: ProviderInfo) => void;
  activeProvider?: ProviderInfo | null;
  onReconnect: () => void;
}

export default function ChatPanel({
  messages, isThinking, thinkingSteps, error, connectionState,
  onSendMessage, onSelectProvider, activeProvider,
  onClearError, onReconnect,
}: ChatPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isThinking]);

  const isInputDisabled = isThinking || connectionState.status !== 'open';

  return (
    <div className="flex flex-col h-full">
      <AnimatePresence>
        {(connectionState.status === 'closed' || connectionState.status === 'error' || connectionState.status === 'connecting') && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
            <div className="flex items-center justify-between px-3 py-2 bg-surface-card border-b border-subtle gap-2">
              <ConnectionStatus state={connectionState} />
              {(connectionState.status === 'closed' || connectionState.status === 'error') && (
                <button onClick={onReconnect} className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-primary text-white text-xs font-medium hover:bg-primary-dark transition-colors">重连</button>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {onSelectProvider && (
        <div className="px-3 pt-2">
          <div className="w-full max-w-3xl mx-auto flex items-center">
            <ProviderSelector onSelect={onSelectProvider} active={activeProvider ?? null} />
          </div>
        </div>
      )}

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-3 py-3">
        {/* 消息列:与输入条同宽居中(max-w-3xl), 空态在列内垂直居中 */}
        <div className="w-full max-w-3xl mx-auto min-h-full flex flex-col space-y-1">
        {messages.length === 0 && !isThinking && (
          <div className="flex-1 flex flex-col items-center justify-center text-center">
            <div className="w-14 h-14 rounded-2xl bg-surface-card border border-subtle flex items-center justify-center mb-4 shadow-card">
              <span className="text-2xl">🔶</span>
            </div>
            <h2 className="text-lg font-medium text-text-primary mb-2">开始对话</h2>
            <p className="text-sm text-text-secondary max-w-xs">发送消息与 DialogMesh 认知架构交互。</p>
          </div>
        )}

        {messages.map((msg, idx) => (
          <div key={msg.id} className="animate-message-enter" style={{ animationDelay: `${idx * 50}ms` }}>
            <MessageBubble message={msg} />
          </div>
        ))}

        {isThinking && (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
            <ThinkingIndicator steps={thinkingSteps} />
          </motion.div>
        )}

        <AnimatePresence>
          {error && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex items-center justify-center my-3">
              <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-status-error/5 border border-status-error/20 text-status-error text-sm">
                <span className="flex-1">{error}</span>
                <button onClick={onClearError} className="p-1 hover:bg-status-error/10 rounded-md"><X size={14} /></button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
        </div>
      </div>

      <ChatInput onSend={onSendMessage} disabled={isInputDisabled} placeholder="输入消息..." />
    </div>
  );
}

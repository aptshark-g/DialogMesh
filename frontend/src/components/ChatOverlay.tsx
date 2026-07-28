import { useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Minimize2, Maximize2, Send, Loader2, AlertCircle, MessageSquare } from 'lucide-react';
import { useOverlayStore } from '@/stores/overlayStore';
import { useChatStore } from '@/stores/chatStore';
import { sendMessage, createSession } from '@/api/session';
import { cn } from '@/lib/utils';

export function ChatOverlay() {
  const { isOpen, isMinimized, close, minimize, maximize } = useOverlayStore();
  const messages = useChatStore(s => s.messages);
  const sessionId = useChatStore(s => s.sessionId);
  const isThinking = useChatStore(s => s.isThinking);
  const addUser = useChatStore(s => s.addUserMessage);
  const addAI = useChatStore(s => s.addAIMessage);
  const setSessionId = useChatStore(s => s.setSessionId);
  const setThinking = useChatStore(s => s.setThinking);
  const [inputValue, setInputValue] = useState('');
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isThinking]);

  const handleSubmit = useCallback(async () => {
    const text = inputValue.trim();
    if (!text || isThinking) return;
    let sid = sessionId;
    if (!sid) {
      try { const r = await createSession(); sid = r.session_id; setSessionId(sid); } catch { return; }
    }
    addUser(text);
    setInputValue('');
    setThinking(true);
    setError(null);
    try {
      const resp = await sendMessage(sid, text);
      const reply = resp.content || '';
      if (reply && reply !== '(no reply)' && reply !== '(empty)') {
        addAI(reply, { taskGraph: resp.task_graph, metadata: { taskGraph: resp.task_graph, latencyMs: resp.latency_ms } } as any);
      }
    } catch (e: any) {
      const msg = e?.message || String(e);
      setError(msg);
      addAI(`[错误] ${msg}`, {} as any);
    } finally { setThinking(false); }
  }, [inputValue, sessionId, isThinking, addUser, addAI, setSessionId, setThinking]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }, [handleSubmit]);

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
          {messages.length > 0 && <span className="text-[10px] text-text-muted">{messages.length}</span>}
        </div>
        <div className="flex items-center gap-1">
          <button type="button" onClick={minimize} className="p-1.5 rounded-md hover:bg-surface-card-hover text-text-secondary transition-colors">
            <Minimize2 className="w-4 h-4" />
          </button>
          <button type="button" onClick={close} className="p-1.5 rounded-md hover:bg-surface-card-hover text-text-secondary transition-colors">
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

        {messages.map((msg, i) => {
          const isUser = msg.role === 'user';
          return (
            <div key={i} className={`flex flex-col gap-1 ${isUser ? 'items-end' : 'items-start'}`}>
              <div className={cn(
                'max-w-[85%] rounded-lg px-3 py-2 text-sm leading-relaxed whitespace-pre-wrap break-words',
                isUser
                  ? 'bg-primary/10 text-text-primary'
                  : 'bg-surface-card text-text-primary border border-subtle'
              )}>
                {msg.content}
              </div>
              {(msg as any).metadata?.taskGraph && (
                <span className="text-[10px] text-primary">📋 已生成任务规划</span>
              )}
            </div>
          );
        })}

        {isThinking && (
          <div className="flex items-center gap-2 px-3 py-2">
            <Loader2 className="w-4 h-4 animate-spin text-text-muted" />
            <span className="text-xs text-text-muted">思考中...</span>
          </div>
        )}

        {error && (
          <div className="flex items-center gap-2 p-2 rounded-lg bg-status-error/10 border border-status-error/20 text-status-error text-sm">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span className="flex-1 text-xs">{error}</span>
            <button type="button" onClick={() => setError(null)} className="ml-auto text-xs hover:underline px-1">清除</button>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-3 border-t border-subtle shrink-0">
        <div className="flex items-center gap-2">
          <input ref={inputRef} type="text" value={inputValue}
            onChange={(e) => setInputValue(e.target.value)} onKeyDown={handleKeyDown}
            placeholder="输入消息..." disabled={isThinking}
            className="flex-1 bg-surface-input border border-subtle rounded-lg px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-primary transition-colors disabled:opacity-50" />
          <button type="button" onClick={handleSubmit}
            disabled={!inputValue.trim() || isThinking}
            className="p-2 rounded-lg bg-primary text-white hover:bg-primary-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
            {isThinking ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
          </button>
        </div>
      </div>
    </motion.div>
  );
}

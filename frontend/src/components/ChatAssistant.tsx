/** Floating Chat Assistant — accessible from any page */
import { useState, useRef, useEffect } from 'react';
import { useChatStore } from '@/stores/chatStore';
import { sendMessage, createSession } from '@/api/session';
import { MessageSquare, Send, X, Loader2 } from 'lucide-react';

export function ChatAssistant() {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const messages = useChatStore(s => s.messages);
  const sessionId = useChatStore(s => s.sessionId);
  const addUser = useChatStore(s => s.addUserMessage);
  const addAI = useChatStore(s => s.addAIMessage);
  const setSessionId = useChatStore(s => s.setSessionId);
  const listRef = useRef<HTMLDivElement>(null);

  // Scroll to bottom on new messages
  useEffect(() => {
    if (open && listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [messages.length, open]);

  const handleSend = async () => {
    if (!input.trim() || sending) return;
    let sid = sessionId;
    if (!sid) {
      const resp = await createSession();
      sid = resp.session_id;
      setSessionId(sid);
    }
    addUser(input);
    setInput('');
    setSending(true);
    try {
      const resp = await sendMessage(sid, input);
      const reply = resp.content || '';
      if (reply && reply !== '(no reply)' && reply !== '(empty)')
        addAI(reply, { taskGraph: resp.task_graph, metadata: { taskGraph: resp.task_graph, latencyMs: resp.latency_ms } });
    } catch (e: any) {
      addAI(`[错误] ${e.message || '请求失败'}`, { metadata: {} });
    } finally { setSending(false); }
  };

  const lastMessages = messages.slice(-8); // only show recent

  return (
    <>
      {/* Floating button */}
      {!open && (
        <button
          onClick={() => setOpen(true)}
          className="fixed bottom-4 right-4 z-50 w-12 h-12 rounded-full bg-primary text-white shadow-lg hover:bg-primary/90 flex items-center justify-center transition-all"
          title="对话助手"
        >
          <MessageSquare size={20} />
          {messages.length > 0 && (
            <span className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-red-500 text-white text-[10px] flex items-center justify-center">
              {messages.length > 99 ? '99' : messages.length}
            </span>
          )}
        </button>
      )}

      {/* Expanded panel */}
      {open && (
        <div className="fixed bottom-4 right-4 z-50 w-[360px] max-w-[calc(100vw-2rem)] h-[480px] max-h-[calc(100vh-2rem)] bg-white dark:bg-[#1a1a1a] border border-subtle rounded-xl shadow-2xl flex flex-col overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-subtle bg-surface-card/80 shrink-0">
            <div className="flex items-center gap-2">
              <MessageSquare size={16} className="text-primary" />
              <span className="text-sm font-medium text-primary">对话助手</span>
              <span className="text-[10px] text-text-muted">{messages.length} 条</span>
            </div>
            <button onClick={() => setOpen(false)} className="text-text-muted hover:text-primary p-1">
              <X size={16} />
            </button>
          </div>

          {/* Messages */}
          <div ref={listRef} className="flex-1 overflow-y-auto px-3 py-2 space-y-2 text-sm">
            {lastMessages.length === 0 ? (
              <div className="text-center text-text-muted text-xs mt-8">开始对话，我可以在任何页面辅助你</div>
            ) : (
              lastMessages.map((m, i) => (
                <div key={i} className={`${m.role === 'user' ? 'text-right' : 'text-left'}`}>
                  <div className={`inline-block max-w-[85%] px-3 py-1.5 rounded-lg text-xs whitespace-pre-wrap ${
                    m.role === 'user'
                      ? 'bg-primary/10 text-text-primary'
                      : 'bg-surface-card border border-subtle text-text-secondary'
                  }`}>
                    {m.content?.slice(0, 300)}{(m.content?.length || 0) > 300 ? '...' : ''}
                  </div>
                  {m.role === 'assistant' && (m as any).metadata?.taskGraph && (
                    <div className="text-[10px] text-primary mt-0.5">📋 已生成任务规划</div>
                  )}
                </div>
              ))
            )}
            {sending && (
              <div className="flex items-center gap-2 text-text-muted text-xs">
                <Loader2 size={12} className="animate-spin" /> 思考中...
              </div>
            )}
          </div>

          {/* Input */}
          <div className="px-3 py-2 border-t border-subtle bg-surface-card/50 shrink-0 flex gap-2">
            <input
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
              placeholder="输入消息..."
              disabled={sending}
              className="flex-1 px-3 py-1.5 rounded-lg border border-subtle bg-surface text-sm text-text-primary placeholder:text-text-muted outline-none focus:border-primary/50 disabled:opacity-50"
            />
            <button onClick={handleSend} disabled={sending || !input.trim()}
              className="px-3 py-1.5 rounded-lg bg-primary text-white text-sm disabled:opacity-40 shrink-0">
              {sending ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
            </button>
          </div>
        </div>
      )}
    </>
  );
}

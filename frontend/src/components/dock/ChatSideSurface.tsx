/** ChatSideSurface — 副槽迷你对话(P1-A 双槽位)。
 *
 *  与主槽 /chat 共享 chatStore 与 useChatSend, 消息互通。
 *  典型工作态: 中间任务图/图谱, 右边对话讨论(点交换⇄ 即反转)。
 *  未来 UI 自动化时: 主槽 = 执行视口, 副槽 = 本对话(见 UI_REFACTOR_PLAN B9)。
 */
import { useEffect, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';
import { Send, Sparkles } from 'lucide-react';
import MessageBubble from '../MessageBubble';
import ThinkingIndicator from '../ThinkingIndicator';
import { useChatStore } from '@/stores/chatStore';
import { useChatSend } from '@/hooks/useChatSend';

export function ChatSideSurface() {
  const messages = useChatStore((s) => s.messages);
  const { send, isThinking } = useChatSend();
  const [text, setText] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);

  // 2026-08-17: 消费「选中文字 → 侧边提问」预填（拓扑对话）
  useEffect(() => {
    const ask = useChatStore.getState().consumeAsk();
    if (ask) {
      setText(ask);
      // 稍后让输入框挂载后自动发送（不打断用户手动编辑——仅当有预填时）
      // 这里只预填, 由用户确认发送; 若需自动发送可在此调 send(ask)。
    }
  }, []);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isThinking]);

  const submit = () => {
    const t = text.trim();
    if (!t || isThinking) return;
    setText('');
    send(t);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* 消息流 */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-3 py-3 space-y-2">
        {messages.length === 0 && !isThinking && (
          <div className="h-full flex flex-col items-center justify-center text-center py-10">
            <p className="text-xs text-text-muted">还没有消息</p>
            <p className="text-[11px] text-text-muted mt-1 leading-relaxed">
              在下方输入即可开始对话
            </p>
          </div>
        )}
        {messages.map((m) => (
          <MessageBubble key={m.id} message={m} />
        ))}
        {isThinking && <ThinkingIndicator steps={[]} />}
      </div>

      {/* 迷你输入条 */}
      <div className="shrink-0 px-3 pb-3 pt-1">
        <div className="flex items-end gap-1.5 rounded-xl border border-border-subtle bg-surface-card p-1.5 focus-within:border-border-strong transition-colors">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={onKeyDown}
            rows={1}
            placeholder="输入消息..."
            aria-label="副槽对话输入"
            className="flex-1 resize-none bg-transparent border-none px-2 py-1.5 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-0"
          />
          <button
            type="button"
            onClick={submit}
            disabled={isThinking || !text.trim()}
            className="shrink-0 w-7 h-7 flex items-center justify-center rounded-full bg-primary text-white hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
            aria-label="发送"
          >
            {isThinking ? <Sparkles size={13} /> : <Send size={13} />}
          </button>
        </div>
      </div>
    </div>
  );
}

export default ChatSideSurface;

import { useState, useCallback, useRef } from 'react';
import { Send, Loader2, Sparkles } from 'lucide-react';

interface ChatInputProps {
  onSend: (content: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

export default function ChatInput({ onSend, disabled = false, placeholder = '输入消息...' }: ChatInputProps) {
  const [text, setText] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }, [text, disabled, onSend]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit]
  );

  const handleChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setText(e.target.value);
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, []);

  return (
    <div className="flex items-end gap-2 px-4 py-3 bg-surface-card border-t border-gray-200">
      <div className="flex-1 relative">
        <textarea
          ref={textareaRef}
          value={text}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          rows={1}
          className="w-full resize-none rounded-xl border border-gray-200 bg-surface-main px-4 py-3 pr-10 text-sm text-text-primary placeholder:text-text-muted focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-50 disabled:cursor-not-allowed"
          placeholder={disabled ? 'AI 思考中...' : placeholder}
        />
        {disabled && (
          <div className="absolute right-3 top-3">
            <Loader2 size={16} className="animate-spin text-primary" />
          </div>
        )}
      </div>
      <button
        type="button"
        onClick={handleSubmit}
        disabled={disabled || !text.trim()}
        className="flex-shrink-0 flex items-center justify-center w-10 h-10 rounded-xl bg-primary text-white shadow-sm hover:bg-primary-dark transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        aria-label="发送"
      >
        {disabled ? <Sparkles size={18} /> : <Send size={18} />}
      </button>
    </div>
  );
}

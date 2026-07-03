import type { KeyboardEvent, ChangeEvent } from 'react';
import { useState, useCallback, useRef } from 'react';
import { motion } from 'framer-motion';
import { Send, Sparkles, Paperclip, Code, AtSign, Image, Grid } from 'lucide-react';

export interface ChatInputProps {
  onSend: (content: string) => void;
  disabled?: boolean;
  placeholder?: string;
  maxLength?: number;
  onAttach?: () => void;
  onCodeBlock?: () => void;
  onMention?: () => void;
  onImage?: () => void;
  onGrid?: () => void;
}

export default function ChatInput({
  onSend,
  disabled = false,
  placeholder = '输入消息... (Shift + Enter 换行, Enter 发送)',
  maxLength,
  onAttach,
  onCodeBlock,
  onMention,
  onImage,
  onGrid,
}: ChatInputProps) {
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
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit]
  );

  const handleChange = useCallback((e: ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    if (maxLength !== undefined && value.length > maxLength) {
      return;
    }
    setText(value);
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [maxLength]);

  const charCount = text.length;
  const showCharCount = maxLength !== undefined;
  const isOverLimit = maxLength !== undefined && charCount > maxLength;

  return (
    <div className="px-3 py-2 md:px-4 md:py-3 bg-surface-card border-t border-border-subtle">
      {/* 主输入容器 */}
      <div className="flex items-end gap-2 rounded-lg border border-border-subtle bg-surface-card p-2 md:p-3 focus-within:border-border-strong transition-colors">
        <div className="flex-1 relative flex flex-col">
          <textarea
            ref={textareaRef}
            value={text}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            disabled={disabled}
            rows={1}
            className="w-full resize-none bg-transparent border-none px-0 py-0 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-0 disabled:opacity-50 disabled:cursor-not-allowed"
            placeholder={disabled ? 'AI 思考中...' : placeholder}
          />
          {showCharCount && (
            <div className={`text-right text-xs mt-1 ${isOverLimit ? 'text-status-error' : 'text-text-muted'}`}>
              {charCount}/{maxLength}
            </div>
          )}
        </div>
        <motion.button
          type="button"
          onClick={handleSubmit}
          disabled={disabled || !text.trim()}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          transition={{ type: 'spring', stiffness: 400, damping: 17 }}
          className="flex-shrink-0 flex items-center justify-center w-10 h-10 md:w-12 md:h-12 rounded-full bg-primary text-white hover:shadow-amber transition-shadow disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:scale-100"
          aria-label="发送"
        >
          {disabled ? <Sparkles size={16} className="md:w-[18px] md:h-[18px]" /> : <Send size={16} className="md:w-[18px] md:h-[18px]" />}
        </motion.button>
      </div>

      {/* 底部工具栏 */}
      <div className="flex items-center justify-between mt-2 px-1">
        <div className="flex items-center gap-2 md:gap-3 overflow-x-auto scrollbar-hide">
          {onAttach && (
            <button
              type="button"
              onClick={onAttach}
              className="text-text-muted hover:text-text-secondary transition-colors p-1"
              aria-label="附件"
            >
              <Paperclip size={18} className="md:w-5 md:h-5" />
            </button>
          )}
          {onCodeBlock && (
            <button
              type="button"
              onClick={onCodeBlock}
              className="text-text-muted hover:text-text-secondary transition-colors p-1"
              aria-label="代码块"
            >
              <Code size={18} className="md:w-5 md:h-5" />
            </button>
          )}
          {onMention && (
            <button
              type="button"
              onClick={onMention}
              className="text-text-muted hover:text-text-secondary transition-colors p-1"
              aria-label="提及"
            >
              <AtSign size={18} className="md:w-5 md:h-5" />
            </button>
          )}
          {onImage && (
            <button
              type="button"
              onClick={onImage}
              className="text-text-muted hover:text-text-secondary transition-colors p-1"
              aria-label="图片"
            >
              <Image size={18} className="md:w-5 md:h-5" />
            </button>
          )}
          {onGrid && (
            <button
              type="button"
              onClick={onGrid}
              className="text-text-muted hover:text-text-secondary transition-colors p-1"
              aria-label="网格"
            >
              <Grid size={18} className="md:w-5 md:h-5" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

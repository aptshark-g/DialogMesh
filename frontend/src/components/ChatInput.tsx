import type { KeyboardEvent, ChangeEvent } from 'react';
import { useState, useCallback, useRef } from 'react';
import { motion } from 'framer-motion';
import { Send, Sparkles, Paperclip, Code, AtSign, Image, Grid, Brain, Globe } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface SendOptions {
  thinking: boolean;
  web: boolean;
}

export interface ChatInputProps {
  onSend: (content: string, opts?: SendOptions) => void;
  disabled?: boolean;
  placeholder?: string;
  maxLength?: number;
  defaultThinking?: boolean;
  defaultWeb?: boolean;
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
  defaultThinking = true,
  defaultWeb = false,
  onAttach,
  onCodeBlock,
  onMention,
  onImage,
  onGrid,
}: ChatInputProps) {
  const [text, setText] = useState('');
  const [thinking, setThinking] = useState(defaultThinking);
  const [web, setWeb] = useState(defaultWeb);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed, { thinking, web });
    setText('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }, [text, disabled, onSend, thinking, web]);

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
    <div className="px-3 pt-1 pb-4 md:px-4">
      {/* 主输入容器 — 浮动药丸条, 与消息列同宽居中(720px 对齐 mockup v2) */}
      <div className="w-full max-w-[720px] mx-auto">
      <div className="flex items-end gap-2 rounded-full border border-border-subtle bg-surface-card shadow-card py-1.5 pl-4 pr-1.5 focus-within:border-border-strong transition-colors">
        <div className="flex-1 relative flex flex-col">
          <textarea
            ref={textareaRef}
            value={text}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            disabled={disabled}
            rows={1}
            className="w-full resize-none bg-transparent border-none px-0 py-0 text-[13.5px] text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-0 disabled:opacity-50 disabled:cursor-not-allowed"
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
          className="flex-shrink-0 flex items-center justify-center w-8 h-8 rounded-full bg-primary text-white hover:shadow-amber transition-shadow disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:scale-100"
          aria-label="发送"
        >
          {disabled ? <Sparkles size={14} /> : <Send size={14} />}
        </motion.button>
      </div>

      {/* 底部工具栏 */}
      <div className="flex items-center justify-between mt-2 px-1">
        <div className="flex items-center gap-2 md:gap-3 overflow-x-auto scrollbar-hide">
          {/* 2026-08-17: 深度思考 / 联网开关（B 类前端接线） */}
          <button
            type="button"
            onClick={() => setThinking(v => !v)}
            title={thinking ? '深度思考：已开启（显示推理过程）' : '深度思考：已关闭（快速回答）'}
            aria-pressed={thinking}
            className={cn(
              'flex items-center gap-1 px-2 py-1 rounded-full text-[11px] transition-colors border',
              thinking
                ? 'bg-primary/10 text-primary border-primary/25'
                : 'text-text-muted border-transparent hover:text-text-secondary'
            )}
          >
            <Brain size={13} />
            深度思考
          </button>
          <button
            type="button"
            onClick={() => setWeb(v => !v)}
            title={web ? '联网搜索：已开启（先搜索再回答）' : '联网搜索：已关闭'}
            aria-pressed={web}
            className={cn(
              'flex items-center gap-1 px-2 py-1 rounded-full text-[11px] transition-colors border',
              web
                ? 'bg-status-info/10 text-status-info border-status-info/25'
                : 'text-text-muted border-transparent hover:text-text-secondary'
            )}
          >
            <Globe size={13} />
            联网
          </button>
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
    </div>
  );
}

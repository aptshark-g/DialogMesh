// FILE: src/components/SelectionAsk.tsx
// 选中文字 → 「在侧边聊天提问」浮层（2026-08-17, 拓扑对话）。
// 全局监听鼠标松开, 若页内有非空文本选区, 在选区末尾附近弹出玻璃浮层;
// 点击「在侧边提问」→ 预填副槽聊天（chatStore.pendingAsk）并打开副槽。

import { useCallback, useEffect, useRef, useState } from 'react';
import { MessageSquarePlus } from 'lucide-react';
import { useChatStore } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';
import { specMove } from '@/lib/spec';

interface PopupPos {
  x: number;
  y: number;
}

export function SelectionAsk() {
  const [pos, setPos] = useState<PopupPos | null>(null);
  const [text, setText] = useState('');
  const timerRef = useRef<number | null>(null);

  const hide = useCallback(() => {
    if (timerRef.current) window.clearTimeout(timerRef.current);
    setPos(null);
    setText('');
  }, []);

  const onMouseUp = useCallback(() => {
    if (timerRef.current) window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(() => {
      const sel = window.getSelection();
      const t = sel?.toString()?.trim() ?? '';
      if (!t || t.length < 4) {
        setPos(null);
        setText('');
        return;
      }
      setText(t.slice(0, 600));
      // 浮层定位在选区末尾（endContainer 位置）
      const range = sel?.getRangeAt(0);
      if (range) {
        const rect = range.getBoundingClientRect();
        setPos({
          x: Math.min(rect.right + 4, window.innerWidth - 180),
          y: Math.max(rect.bottom + 4, rect.top),
        });
      } else {
        setPos({ x: window.innerWidth / 2, y: 80 });
      }
    }, 120);
  }, []);

  const ask = useCallback(() => {
    if (!text) return;
    // 预填副槽提问 + 打开副槽（chat 表面）
    useChatStore.getState().setPendingAsk(text);
    useUIStore.getState().setDockContent('chat');
    useUIStore.getState().openSidePanel();
    hide();
  }, [text, hide]);

  useEffect(() => {
    document.addEventListener('mouseup', onMouseUp);
    document.addEventListener('scroll', hide, true);
    return () => {
      document.removeEventListener('mouseup', onMouseUp);
      document.removeEventListener('scroll', hide, true);
    };
  }, [onMouseUp, hide]);

  if (!pos || !text) return null;
  return (
    <div
      className="fixed z-50"
      style={{ left: pos.x, top: pos.y }}
      onPointerMove={specMove}
    >
      <div className="spec-panel glass-panel rounded-full px-2 py-1 shadow-float">
        <button
          type="button"
          onClick={ask}
          onPointerMove={specMove}
          className="spec-item flex items-center gap-1.5 px-2 py-1 rounded-full text-[11px] text-text-primary hover:text-primary transition-colors"
          title="将选中内容发送到侧边聊天提问"
        >
          <MessageSquarePlus className="h-3.5 w-3.5" />
          在侧边提问
        </button>
      </div>
    </div>
  );
}

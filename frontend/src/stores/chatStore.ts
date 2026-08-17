import { create } from 'zustand';
import type { ChatMessage } from '../types/api';
import type { ProviderInfo } from '../components/ProviderSelector';

interface ChatStore {
  messages: ChatMessage[];
  sessionId: string | null;
  isThinking: boolean;
  /** 当前流式回复的思考过程（实时累积） */
  thinkingText: string;
  /** 选中文字 → 侧边提问的预填内容（SelectionAsk 写入, 副槽消费） */
  pendingAsk: string;
  activeProvider: ProviderInfo | null;
  addUserMessage: (content: string) => void;
  addAIMessage: (content: string, extra?: Partial<ChatMessage>) => void;
  /** 流式：创建/追加 AI 消息内容（边收边填充） */
  streamStart: (id: string) => void;
  streamAppend: (id: string, delta: string) => void;
  streamFinish: (id: string, extra?: Partial<ChatMessage>) => void;
  setThinkingText: (t: string) => void;
  setPendingAsk: (t: string) => void;
  consumeAsk: () => string;
  setThinking: (v: boolean) => void;
  setSessionId: (id: string) => void;
  loadSession: (id: string, msgs: ChatMessage[]) => void;
  setActiveProvider: (p: ProviderInfo | null) => void;
  clear: () => void;
}

// Persist to sessionStorage for tab survival
const KEY = 'dm_chat_store';

function load(): Partial<ChatStore> {
  try { return JSON.parse(sessionStorage.getItem(KEY) || '{}'); } catch { return {}; }
}

export const useChatStore = create<ChatStore>((set, _get) => {
  const saved = load();
  return {
    messages: saved.messages || [],
    sessionId: saved.sessionId || null,
    isThinking: false,
    thinkingText: '',
    pendingAsk: '',
    activeProvider: null,
    addUserMessage: (content) => set(s => {
      const msg: ChatMessage = { id: Date.now().toString(), role: 'user', content, timestamp: Date.now() };
      return { messages: [...s.messages, msg] };
    }),
    addAIMessage: (content, extra) => set(s => {
      const msg: ChatMessage = {
        id: (Date.now()+1).toString(), role: 'assistant', content, timestamp: Date.now(),
        ...(extra || {}),
      };
      return { messages: [...s.messages, msg] };
    }),
    streamStart: (id) => set(s => ({
      isThinking: true,
      thinkingText: '',
      messages: [...s.messages, {
        id, role: 'assistant', content: '', timestamp: Date.now(),
        status: 'streaming',
      }],
    })),
    streamAppend: (id, delta) => set(s => ({
      messages: s.messages.map(m =>
        m.id === id ? { ...m, content: m.content + delta } : m),
    })),
    streamFinish: (id, extra) => set(s => ({
      isThinking: false,
      messages: s.messages.map(m =>
        m.id === id ? { ...m, status: 'sent', ...(extra || {}) } : m),
    })),
    setThinkingText: (t) => set({ thinkingText: t }),
    setPendingAsk: (t) => set({ pendingAsk: t }),
    consumeAsk: () => {
      const t: string = useChatStore.getState().pendingAsk;
      if (t) set({ pendingAsk: '' });
      return t;
    },
    setThinking: (v) => set({ isThinking: v }),
    setSessionId: (id) => set({ sessionId: id }),
    loadSession: (id, msgs) => set({ sessionId: id, messages: msgs, isThinking: false, thinkingText: '' }),
    setActiveProvider: (p) => set({ activeProvider: p }),
    clear: () => set({ messages: [], sessionId: null, thinkingText: '' }),
  };
});

// Auto-persist to sessionStorage
useChatStore.subscribe((state) => {
  sessionStorage.setItem(KEY, JSON.stringify({
    messages: state.messages.slice(-100),
    sessionId: state.sessionId,
  }));
});

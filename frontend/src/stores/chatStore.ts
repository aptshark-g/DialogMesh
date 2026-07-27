import { create } from 'zustand';
import type { ChatMessage } from '../types/api';
import type { ProviderInfo } from '../components/ProviderSelector';

interface ChatStore {
  messages: ChatMessage[];
  sessionId: string | null;
  isThinking: boolean;
  activeProvider: ProviderInfo | null;
  addUserMessage: (content: string) => void;
  addAIMessage: (content: string) => void;
  setThinking: (v: boolean) => void;
  setSessionId: (id: string) => void;
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
    activeProvider: null,
    addUserMessage: (content) => set(s => {
      const msg: ChatMessage = { id: Date.now().toString(), role: 'user', content, timestamp: Date.now() };
      return { messages: [...s.messages, msg] };
    }),
    addAIMessage: (content) => set(s => {
      const msg: ChatMessage = { id: (Date.now()+1).toString(), role: 'assistant', content, timestamp: Date.now() };
      return { messages: [...s.messages, msg] };
    }),
    setThinking: (v) => set({ isThinking: v }),
    setSessionId: (id) => set({ sessionId: id }),
    setActiveProvider: (p) => set({ activeProvider: p }),
    clear: () => set({ messages: [], sessionId: null }),
  };
});

// Auto-persist to sessionStorage
useChatStore.subscribe((state) => {
  sessionStorage.setItem(KEY, JSON.stringify({
    messages: state.messages.slice(-100),
    sessionId: state.sessionId,
  }));
});

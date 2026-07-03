// FILE: src/stores/sessionStore.ts
import { create } from 'zustand';

import { getApiConfig } from '../lib/config';
import type {
  SessionBaseState,
  SessionActions,
  CreateSessionResponse,
  SessionStatusResponse,
  CognitiveProfile,
  FSMState,
  Message,
  TaskNode,
  TaskGraphNode,
  SessionState,
} from '../types/api';

const initialState: Omit<SessionBaseState, keyof SessionActions> = {
  sessionId: null,
  wsConnected: false,
  wsConnecting: false,
  wsUrl: null,
  restBaseUrl: getApiConfig().restBaseUrl,
  sessionState: null,
  pendingClarification: false,
  currentTurn: 0,
  cognitiveProfile: null,
  fsm: null,
  messages: [],
  isLoading: false,
  error: null,
  capabilities: [],
  sessionTtl: 3600,
  expiresAt: null,
  lastActivityAt: null,
};

export const useSessionStore = create<SessionBaseState & SessionActions>((set, get) => ({
  ...initialState,

  // -------------------- 连接管理 --------------------

  setRestBaseUrl: (url: string) => set({ restBaseUrl: url }),

  setSessionId: (id: string | null) => set({ sessionId: id }),

  setWsUrl: (url: string | null) => set({ wsUrl: url }),

  setWsConnected: (connected: boolean) => set({ wsConnected: connected }),

  setWsConnecting: (connecting: boolean) => set({ wsConnecting: connecting }),

  // -------------------- 会话状态 --------------------

  setSessionState: (state: SessionState | null) => set({ sessionState: state }),

  setPendingClarification: (pending: boolean) => set({ pendingClarification: pending }),

  setCurrentTurn: (turn: number) => set({ currentTurn: turn }),

  setCognitiveProfile: (profile: CognitiveProfile | null) => set({ cognitiveProfile: profile }),

  setFsm: (fsm: FSMState | null) => set({ fsm }),

  setCapabilities: (caps: string[]) => set({ capabilities: caps }),

  setSessionTtl: (ttl: number) => set({ sessionTtl: ttl }),

  setExpiresAt: (expires: string | null) => set({ expiresAt: expires }),

  setLastActivityAt: (activity: string | null) => set({ lastActivityAt: activity }),

  // -------------------- 消息管理 --------------------

  addMessage: (message: Message) =>
    set((state) => ({
      messages: [...state.messages, message],
    })),

  updateMessage: (id: string, updates: Partial<Message>) =>
    set((state) => ({
      messages: state.messages.map((msg) =>
        msg.id === id ? { ...msg, ...updates } : msg
      ),
    })),

  removeMessage: (id: string) =>
    set((state) => ({
      messages: state.messages.filter((msg) => msg.id !== id),
    })),

  clearMessages: () => set({ messages: [] }),

  appendMessageContent: (id: string, content: string) =>
    set((state) => ({
      messages: state.messages.map((msg) =>
        msg.id === id ? { ...msg, content: msg.content + content } : msg
      ),
    })),

  // -------------------- 任务图 --------------------

  updateTaskGraph: (taskGraph: TaskNode[]) =>
    set((state) => {
      const lastAssistantMessage = [...state.messages]
        .reverse()
        .find((m) => m.role === 'assistant');
      if (!lastAssistantMessage) return {};

      return {
        messages: state.messages.map((msg) =>
          msg.id === lastAssistantMessage.id
            ? { ...msg, taskGraph: taskGraph as unknown as TaskGraphNode[] }
            : msg
        ),
      };
    }),

  // -------------------- 加载与错误 --------------------

  setIsLoading: (loading: boolean) => set({ isLoading: loading }),

  setError: (error: string | null) => set({ error }),

  clearError: () => set({ error: null }),

  // -------------------- 复合操作 --------------------

  resetSession: () =>
    set({
      ...initialState,
      restBaseUrl: get().restBaseUrl,
    }),

  initializeSession: (response: CreateSessionResponse) =>
    set({
      sessionId: response.session_id,
      wsUrl: response.ws_url,
      sessionState: response.status === 'active' ? 'idle' : 'initializing',
      capabilities: response.capabilities,
      sessionTtl: response.session_ttl_seconds,
      pendingClarification: false,
      currentTurn: 0,
      error: null,
      messages: [],
      isLoading: false,
      wsConnected: false,
      wsConnecting: false,
      cognitiveProfile: null,
      fsm: null,
      expiresAt: null,
      lastActivityAt: response.created_at,
    }),

  syncFromStatus: (status: SessionStatusResponse) =>
    set({
      sessionId: status.session_id,
      sessionState: status.state as SessionState,
      pendingClarification: status.pending_clarification,
      currentTurn: status.current_turn,
      cognitiveProfile: status.cognitive_profile as unknown as CognitiveProfile,
      fsm: status.fsm as unknown as FSMState,
      lastActivityAt: status.last_activity_at,
      expiresAt: status.expires_at,
    }),
}));

// ==================== 选择器 hook ====================

export function useSessionId(): string | null {
  return useSessionStore((s) => s.sessionId);
}

export function useWsConnected(): boolean {
  return useSessionStore((s) => s.wsConnected);
}

export function useSessionState(): SessionState | null {
  return useSessionStore((s) => s.sessionState);
}

export function useMessages(): Message[] {
  return useSessionStore((s) => s.messages);
}

export function useIsLoading(): boolean {
  return useSessionStore((s) => s.isLoading);
}

export function useStoreError(): string | null {
  return useSessionStore((s) => s.error);
}

export function usePendingClarification(): boolean {
  return useSessionStore((s) => s.pendingClarification);
}

export function useCognitiveProfile(): CognitiveProfile | null {
  return useSessionStore((s) => s.cognitiveProfile);
}

export function useFsm(): FSMState | null {
  return useSessionStore((s) => s.fsm);
}

export function useCapabilities(): string[] {
  return useSessionStore((s) => s.capabilities);
}

export function useRestBaseUrl(): string {
  return useSessionStore((s) => s.restBaseUrl);
}

export function useTaskGraph(): TaskNode[] | undefined {
  return useSessionStore((s) => {
    const lastAssistant = [...s.messages]
      .reverse()
      .find((m) => m.role === 'assistant');
    return lastAssistant?.taskGraph as unknown as TaskNode[] | undefined;
  });
}

// ==================== 派生状态选择器 ====================

export function useLatestMessage(): Message | null {
  return useSessionStore((s) => {
    const msgs = s.messages;
    return msgs.length > 0 ? msgs[msgs.length - 1] : null;
  });
}

export function useUserMessages(): Message[] {
  return useSessionStore((s) => s.messages.filter((m) => m.role === 'user'));
}

export function useAssistantMessages(): Message[] {
  return useSessionStore((s) =>
    s.messages.filter((m) => m.role === 'assistant')
  );
}

export function useMessageCount(): number {
  return useSessionStore((s) => s.messages.length);
}

export function useHasActiveSession(): boolean {
  return useSessionStore((s) => s.sessionId !== null && s.sessionState !== 'closed');
}

export function useSessionExpiresIn(): number | null {
  return useSessionStore((s) => {
    if (!s.expiresAt) return null;
    const expires = new Date(s.expiresAt).getTime();
    const now = Date.now();
    return Math.max(0, Math.floor((expires - now) / 1000));
  });
}

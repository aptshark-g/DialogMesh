export const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:8000';

export const API_ENDPOINTS = {
  createSession: `${BASE_URL}/v3/session`,
  sendMessage: (sessionId: string) => `${BASE_URL}/v3/session/${sessionId}/message`,
  clarify: (sessionId: string) => `${BASE_URL}/v3/session/${sessionId}/clarify`,
  history: (sessionId: string) => `${BASE_URL}/v3/session/${sessionId}/history`,
  status: (sessionId: string) => `${BASE_URL}/v3/session/${sessionId}/status`,
  health: `${BASE_URL}/v3/health`,
  ws: (sessionId: string) => `${WS_BASE_URL}/v3/ws/${sessionId}`,
} as const;

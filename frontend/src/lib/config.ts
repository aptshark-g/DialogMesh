const STORAGE_KEY = 'dialogmesh_api_config';

export interface ApiConfig {
  restBaseUrl: string;
  wsBaseUrl: string;
}

const DEFAULT_CONFIG: ApiConfig = {
  // B5（2026-08-07）: 默认相对路径 → 同源请求走 dev/prod 代理，
  // 绕开系统 Chrome 剥离 CORS 响应头的环境问题（B5_UI_TEST_PLAN）。
  // 显式 VITE_API_BASE_URL 或 localStorage 配置仍可覆盖（远程/独立部署）。
  restBaseUrl: import.meta.env.VITE_API_BASE_URL || '',
  wsBaseUrl: import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:8000',
};

function loadConfig(): ApiConfig {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<ApiConfig>;
      return {
        restBaseUrl: parsed.restBaseUrl || DEFAULT_CONFIG.restBaseUrl,
        wsBaseUrl: parsed.wsBaseUrl || DEFAULT_CONFIG.wsBaseUrl,
      };
    }
  } catch {
    // ignore parse errors
  }
  return { ...DEFAULT_CONFIG };
}

let _config: ApiConfig = loadConfig();

export function getApiConfig(): ApiConfig {
  return { ..._config };
}

export function setApiConfig(updates: Partial<ApiConfig>): void {
  _config = { ..._config, ...updates };
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(_config));
  } catch {
    // ignore storage errors
  }
}

export function resetApiConfig(): void {
  _config = { ...DEFAULT_CONFIG };
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(_config));
  } catch {
    // ignore storage errors
  }
}

export const BASE_URL = _config.restBaseUrl;
export const WS_BASE_URL = _config.wsBaseUrl;

export function buildApiEndpoints(config: ApiConfig) {
  const base = config.restBaseUrl;
  const ws = config.wsBaseUrl;
  return {
    createSession: `${base}/v3/session`,
    sendMessage: (sessionId: string) => `${base}/v3/session/${sessionId}/message`,
    clarify: (sessionId: string) => `${base}/v3/session/${sessionId}/clarify`,
    history: (sessionId: string) => `${base}/v3/session/${sessionId}/history`,
    status: (sessionId: string) => `${base}/v3/session/${sessionId}/status`,
    health: `${base}/v3/health`,
    ws: (sessionId: string) => `${ws}/v3/ws/${sessionId}`,
  } as const;
}

export const API_ENDPOINTS = buildApiEndpoints(_config);

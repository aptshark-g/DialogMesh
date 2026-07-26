// FILE: src/lib/debug.ts
// Frontend signal monitor — logs all user actions + API calls.
// Drop this import into any page to enable tracing.
//
// Usage:
//   import { initDebug } from '../lib/debug';
//   initDebug();  // call once in App.tsx
//
// Output (browser console + stored in sessionStorage):
//   [DM:API] POST /v6/chat → 200 (1124ms)
//   [DM:ACT] User clicked "Send" with message "hello"
//   [DM:ERR] POST /v6/chat → 500: "Internal error"

type DebugEntry = {
  ts: number;
  type: 'api_request' | 'api_response' | 'api_error' | 'user_action' | 'ws_event' | 'state_change';
  detail: string;
  data?: unknown;
};

const MAX_LOGS = 500;
const logs: DebugEntry[] = [];

function _log(type: DebugEntry['type'], detail: string, data?: unknown) {
  const entry: DebugEntry = { ts: Date.now(), type, detail, data };
  logs.push(entry);
  if (logs.length > MAX_LOGS) logs.shift();

  const prefix = `[DM:${type.toUpperCase().replace('_',':')}]`;
  const color = type.includes('error') ? 'color:red' : type.includes('response') ? 'color:green' : 'color:gray';
  console.log(`%c${prefix}%c ${detail}`, color, '', data || '');

  // Persist to sessionStorage
  try { sessionStorage.setItem('dm_debug_logs', JSON.stringify(logs.slice(-50))); } catch {}
}

// ═══ API Interceptor ═══
export function interceptFetch() {
  const orig = window.fetch;
  window.fetch = async function(input: RequestInfo | URL, init?: RequestInit) {
    const url = typeof input === 'string' ? input : input instanceof Request ? input.url : input.toString();
    const t0 = performance.now();
    _log('api_request', `${init?.method || 'GET'} ${url}`, init?.body ? JSON.parse(init.body as string) : undefined);
    try {
      const resp = await orig(input, init);
      const ms = Math.round(performance.now() - t0);
      _log('api_response', `${init?.method || 'GET'} ${url} → ${resp.status} (${ms}ms)`);
      return resp;
    } catch (e) {
      _log('api_error', `${init?.method || 'GET'} ${url} → ${e}`);
      throw e;
    }
  };
}

// ═══ User Action Logger ═══
export function logAction(action: string, data?: unknown) {
  _log('user_action', action, data);
}

// ═══ WebSocket Logger ═══
export function logWSEvent(event: string, data?: unknown) {
  _log('ws_event', event, data);
}

// ═══ State Change Logger ═══
export function logState(store: string, change: string) {
  _log('state_change', `${store}: ${change}`);
}

// ═══ Init ═══
export function initDebug() {
  interceptFetch();
  _log('user_action', 'Debug monitor started');
  console.log('%c[DM] Debug monitor active — check sessionStorage dm_debug_logs', 'font-weight:bold;color:#6366f1');
}

// ═══ Export for inspection ═══
export function getLogs(): DebugEntry[] {
  return [...logs];
}

export function exportLogs(): string {
  return JSON.stringify(logs, null, 2);
}


// ═══ Auto-sync to backend ═══
let _syncTimer: ReturnType<typeof setInterval> | null = null;
export function enableBackendSync(intervalMs: number = 5000) {
  if (_syncTimer) return;
  _syncTimer = setInterval(async () => {
    if (logs.length === 0) return;
    const toSend = logs.splice(0, 50);  // Take and clear
    try {
      await fetch('/v6/debug/logs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ entries: toSend, url: window.location.href }),
      });
    } catch {}
  }, intervalMs);
}

export function disableBackendSync() {
  if (_syncTimer) { clearInterval(_syncTimer); _syncTimer = null; }
}
// Attach to window for console access
if (typeof window !== 'undefined') {
  (window as Record<string, unknown>).__dm_debug = { getLogs, exportLogs };
}

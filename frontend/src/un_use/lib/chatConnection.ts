/** Global WebSocket + message buffer — survives page navigation */
import type { ChatMessage } from '../types/api';

const WS_URL = 'ws://127.0.0.1:8000/v4/ws';
const MSG_KEY = 'dm_chat_msgs';
const SID_KEY = 'dm_chat_sid';

type Listener = (msg: ChatMessage) => void;

class ChatConnection {
  private ws: WebSocket | null = null;
  private listeners = new Set<Listener>();
  private pending: string = '';

  connect() {
    if (this.ws?.readyState === WebSocket.OPEN) return;
    try {
      this.ws = new WebSocket(WS_URL);
      this.ws.onmessage = (e) => {
        try {
          const d = JSON.parse(e.data);
          if (d.event_type === 'MESSAGE' && d.payload?.content) {
            const ai: ChatMessage = { id: Date.now().toString(), role: 'assistant', content: d.payload.content, timestamp: Date.now() };
            this.listeners.forEach(fn => fn(ai));
          }
        } catch {}
      };
      this.ws.onclose = () => setTimeout(() => this.connect(), 3000); // auto-reconnect
    } catch {}
  }

  subscribe(fn: Listener) { this.listeners.add(fn); return () => { this.listeners.delete(fn); }; }

  static loadMessages(): ChatMessage[] {
    try { return JSON.parse(sessionStorage.getItem(MSG_KEY) || '[]'); } catch { return []; }
  }
  static saveMessages(msgs: ChatMessage[]) { sessionStorage.setItem(MSG_KEY, JSON.stringify(msgs.slice(-100))); }
  static getSessionId(): string | null { return sessionStorage.getItem(SID_KEY); }
  static setSessionId(sid: string) { sessionStorage.setItem(SID_KEY, sid); }

  loadMessages(): ChatMessage[] { return ChatConnection.loadMessages(); }
  saveMessages(msgs: ChatMessage[]) { ChatConnection.saveMessages(msgs); }
  getSessionId(): string | null { return ChatConnection.getSessionId(); }
  setSessionId(sid: string) { ChatConnection.setSessionId(sid); }
}

export const chatConnection = new ChatConnection();

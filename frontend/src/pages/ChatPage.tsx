import { useState, useCallback, useEffect, useRef } from 'react';
import ChatPanel from '../components/ChatPanel';
import type { ChatMessage } from '../types/api';
import type { ConnectionState } from '../types/ui';
import { createSession, sendMessage } from '../api/session';
import type { ProviderInfo } from '../components/ProviderSelector';

const WS_URL = 'ws://127.0.0.1:8000/v4/ws';

export function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>(() => {
    try { return JSON.parse(sessionStorage.getItem('dm_chat_msgs')||'[]'); } catch { return []; }
  });
  const [isThinking, setIsThinking] = useState(false);
  const [error, setError] = useState<string|null>(null);
  const [sessionId, setSessionId] = useState<string|null>(() =>
    sessionStorage.getItem('dm_chat_sid')
  );
  const [activeProvider, setActiveProvider] = useState<ProviderInfo|null>(null);
  const [connectionState, setConnectionState] = useState<ConnectionState>({status:'connecting',latencyMs:null,lastError:null});
  const wsRef = useRef<WebSocket|null>(null);

  // Persist messages
  useEffect(() => {
    sessionStorage.setItem('dm_chat_msgs', JSON.stringify(messages.slice(-100)));
    if (sessionId) sessionStorage.setItem('dm_chat_sid', sessionId);
  }, [messages, sessionId]);

  // Init session + connect WS
  useEffect(() => {
    if (sessionId) { setConnectionState({status:'open',latencyMs:null,lastError:null}); return; }
    createSession().then(resp => {
      setSessionId(resp.session_id);
      setConnectionState({status:'open',latencyMs:null,lastError:null});
    }).catch(e => setConnectionState({status:'error',latencyMs:null,lastError:e.message}));

    return () => { if (wsRef.current) wsRef.current.close(); };
  }, []);

  // Connect WebSocket for real-time
  useEffect(() => {
    try {
      const ws = new WebSocket(WS_URL);
      ws.onopen = () => setConnectionState(prev => ({...prev,status:'open'}));
      ws.onclose = () => {}; // silent
      ws.onerror = () => {}; // silent
      ws.onmessage = (e) => {
        try {
          const d = JSON.parse(e.data);
          if (d.event_type === 'MESSAGE' && d.payload?.content) {
            const ai: ChatMessage = {id:Date.now().toString(),role:'assistant',content:d.payload.content,timestamp:Date.now()};
            setMessages(prev => [...prev, ai]);
          }
        } catch {}
      };
      wsRef.current = ws;
    } catch {}
    return () => { if (wsRef.current) wsRef.current.close(); };
  }, []);

  const handleUserMessage = useCallback(async (content: string) => {
    if (!sessionId || !content.trim() || isThinking) return;
    const user: ChatMessage = {id:Date.now().toString(),role:'user',content,timestamp:Date.now()};
    setMessages(prev => [...prev, user]);
    setIsThinking(true);
    // Try REST, WS is real-time fallback
    try {
      const resp = await sendMessage(sessionId, content, activeProvider?.name, activeProvider?.model);
      if (resp.content && resp.content !== '(no reply)' && resp.content !== '(empty)') {
        const ai: ChatMessage = {id:(Date.now()+1).toString(),role:'assistant',content:resp.content,timestamp:Date.now()};
        setMessages(prev => prev[prev.length-1]?.id === ai.id ? prev : [...prev, ai]);
      }
    } catch (e: any) { setError(e.message||'发送失败'); }
    finally { setIsThinking(false); }
  }, [sessionId, isThinking, activeProvider]);

  return (
    <div className="h-full flex flex-col">
      <ChatPanel messages={messages} isThinking={isThinking} thinkingSteps={[]}
        error={error} connectionState={connectionState}
        onSendMessage={handleUserMessage} onClearError={()=>setError(null)}
        onReconnect={()=>window.location.reload()} onClearMessages={()=>{setMessages([]);sessionStorage.removeItem('dm_chat_msgs');}}
        onSelectProvider={setActiveProvider} activeProvider={activeProvider} />
    </div>
  );
}

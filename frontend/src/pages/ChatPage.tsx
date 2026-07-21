import { useState, useCallback, useEffect } from 'react';
import ChatPanel from '../components/ChatPanel';
import type { ChatMessage } from '../types/api';
import type { ConnectionState } from '../types/ui';
import { createSession, sendMessage } from '../api/session';
import type { ProviderInfo } from '../components/ProviderSelector';
import { chatConnection } from '../lib/chatConnection';

export function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>(chatConnection.loadMessages);
  const [isThinking, setIsThinking] = useState(false);
  const [error, setError] = useState<string|null>(null);
  const [sessionId, setSessionId] = useState<string|null>(chatConnection.getSessionId);
  const [activeProvider, setActiveProvider] = useState<ProviderInfo|null>(null);
  const [connectionState, setConnectionState] = useState<ConnectionState>({status:'connecting',latencyMs:null,lastError:null});

  // Persist on every change — survives page switch
  useEffect(() => {
    chatConnection.saveMessages(messages);
    if (sessionId) chatConnection.setSessionId(sessionId);
  }, [messages, sessionId]);

  // Global WS — never unmounts, auto-reconnects
  useEffect(() => {
    chatConnection.connect();
    const unsub = chatConnection.subscribe((ai) => {
      setMessages(prev => {
        const last = prev[prev.length-1];
        if (last?.role === 'assistant' && Date.now() - last.timestamp < 30000) {
          // Append to current streaming message
          const updated = { ...last, content: last.content + ai.content };
          return [...prev.slice(0,-1), updated];
        }
        return [...prev, ai];
      });
    });
    return unsub;
  }, []);

  // Init session (once, survives remount via chatConnection state)
  useEffect(() => {
    if (sessionId) { setConnectionState({status:'open',latencyMs:null,lastError:null}); return; }
    createSession().then(resp => {
      setSessionId(resp.session_id);
      setConnectionState({status:'open',latencyMs:null,lastError:null});
    }).catch(e => setConnectionState({status:'error',latencyMs:null,lastError:e.message}));
  }, []);

  const handleUserMessage = useCallback(async (content: string) => {
    if (!sessionId || !content.trim() || isThinking) return;
    const user: ChatMessage = {id:Date.now().toString(),role:'user',content,timestamp:Date.now()};
    setMessages(prev => [...prev, user]);
    setIsThinking(true);
    try {
      const resp = await sendMessage(sessionId, content, activeProvider?.name, activeProvider?.model);
      if (resp.content && resp.content !== '(no reply)' && resp.content !== '(empty)') {
        const ai: ChatMessage = {id:(Date.now()+1).toString(),role:'assistant',content:resp.content,timestamp:Date.now()};
        setMessages(prev => [...prev, ai]);
      }
    } catch (e: any) { setError(e.message||'发送失败'); }
    finally { setIsThinking(false); }
  }, [sessionId, isThinking, activeProvider]);

  return (
    <div className="h-full flex flex-col">
      <ChatPanel messages={messages} isThinking={isThinking} thinkingSteps={[]}
        error={error} connectionState={connectionState}
        onSendMessage={handleUserMessage} onClearError={()=>setError(null)}
        onReconnect={()=>{chatConnection.connect();setConnectionState({status:'open',latencyMs:null,lastError:null});}}
        onClearMessages={()=>{setMessages([]);chatConnection.saveMessages([]);}}
        onSelectProvider={setActiveProvider} activeProvider={activeProvider} />
    </div>
  );
}

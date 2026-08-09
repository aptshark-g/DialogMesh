import { useEffect } from 'react';
import ChatPanel from '../components/ChatPanel';
import { createSession, sendMessage } from '../api/session';
import { useChatStore } from '../stores/chatStore';

export function ChatPage() {
  const messages = useChatStore(s => s.messages);
  const sessionId = useChatStore(s => s.sessionId);
  const isThinking = useChatStore(s => s.isThinking);
  const activeProvider = useChatStore(s => s.activeProvider);
  const addUser = useChatStore(s => s.addUserMessage);
  const addAI = useChatStore(s => s.addAIMessage);
  const setThinking = useChatStore(s => s.setThinking);
  const setSessionId = useChatStore(s => s.setSessionId);
  const clearChat = useChatStore(s => s.clear);

  // Init session once — survives remount because store persists sessionId
  useEffect(() => {
    if (sessionId) return;
    createSession().then(r => setSessionId(r.session_id)).catch(() => {});
  }, []);

  const handleSend = async (content: string) => {
    if (!content.trim() || isThinking) return;
    let sid = useChatStore.getState().sessionId;
    if (!sid) {
      try {
        const resp = await createSession();
        sid = resp.session_id;
        useChatStore.getState().setSessionId(sid);
      } catch (e) {
        console.error('Failed to create session:', e);
        return;
      }
    }
    addUser(content);
    setThinking(true);
    try {
      const resp = await sendMessage(sid, content);
      const reply = resp.content || '';
      if (reply && reply !== '(no reply)' && reply !== '(empty)')
        addAI(reply, {
          taskGraph: resp.task_graph ?? undefined,
          metadata: { taskGraph: resp.task_graph ?? undefined, latencyMs: resp.latency_ms },
        });
    } catch (e: any) { console.error('Send failed:', e); } finally { setThinking(false); }
  };

  return (
    <div className="h-full flex flex-col">
      <ChatPanel
        messages={messages} isThinking={isThinking} thinkingSteps={[]}
        error={null} connectionState={{status:'open',latencyMs:null,lastError:null}}
        onSendMessage={handleSend} onClearError={() => {}}
        onReconnect={() => window.location.reload()}
        onClearMessages={clearChat}
        onSelectProvider={useChatStore(s => s.setActiveProvider)}
        activeProvider={activeProvider}
      />
    </div>
  );
}

import { useEffect } from 'react';
import ChatPanel from '../components/ChatPanel';
import { createSession } from '../api/session';
import { useChatStore } from '../stores/chatStore';
import { useChatSend } from '../hooks/useChatSend';

export function ChatPage() {
  const messages = useChatStore(s => s.messages);
  const sessionId = useChatStore(s => s.sessionId);
  const isThinking = useChatStore(s => s.isThinking);
  const activeProvider = useChatStore(s => s.activeProvider);
  const setSessionId = useChatStore(s => s.setSessionId);
  const clearChat = useChatStore(s => s.clear);

  // Init session once — survives remount because store persists sessionId
  useEffect(() => {
    if (sessionId) return;
    createSession().then(r => setSessionId(r.session_id)).catch(() => {});
  }, []);

  const { send: handleSend } = useChatSend();

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

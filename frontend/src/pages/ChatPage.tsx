import { useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import ChatPanel from '../components/ChatPanel';
import { createSession, getHistory } from '../api/session';
import { useChatStore } from '../stores/chatStore';
import { useChatSend } from '../hooks/useChatSend';

export function ChatPage() {
  const messages = useChatStore(s => s.messages);
  const sessionId = useChatStore(s => s.sessionId);
  const isThinking = useChatStore(s => s.isThinking);
  const thinkingText = useChatStore(s => s.thinkingText);
  const activeProvider = useChatStore(s => s.activeProvider);
  const setSessionId = useChatStore(s => s.setSessionId);
  const clearChat = useChatStore(s => s.clear);

  // P3 路由驱动会话:/chat=恢复或新建; /chat/new=强制新会话; /chat/:id=切换并载入历史
  const { sessionId: routeId } = useParams();
  const navigate = useNavigate();
  const loadSession = useChatStore(s => s.loadSession);

  useEffect(() => {
    if (!routeId) {
      if (!sessionId) createSession().then(r => setSessionId(r.session_id)).catch(() => {});
      return;
    }
    if (routeId === 'new') {
      clearChat();
      createSession()
        .then(r => { setSessionId(r.session_id); navigate('/chat', { replace: true }); })
        .catch(() => {});
      return;
    }
    if (routeId === sessionId) { navigate('/chat', { replace: true }); return; }
    getHistory(routeId)
      .then((h) => {
        loadSession(routeId, h.messages.map((r) => ({
          id: r.message_id,
          role: r.role,
          content: r.content,
          timestamp: Date.parse(r.timestamp) || Date.now(),
          intent: r.intent,
        })));
      })
      // 历史读不到也允许进入(会话文件可能无 v3 历史),首发消息失败会显式报错
      .catch(() => loadSession(routeId, []));
  }, [routeId]);

  const { send: handleSend } = useChatSend();

  return (
    <div className="h-full flex flex-col">
      <ChatPanel
        messages={messages} isThinking={isThinking}
        thinkingSteps={thinkingText
          ? [{ step: 1, description: thinkingText.slice(0, 300), timestamp: Date.now() }]
          : []}
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

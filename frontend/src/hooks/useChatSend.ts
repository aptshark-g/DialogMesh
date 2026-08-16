/** useChatSend — 发送逻辑共享 hook(P1-A)。
 *  主槽 ChatPage 与副槽迷你对话(ChatSideSurface)共用同一条发送路径:
 *  确保会话存在 → 追加用户消息 → 调用后端 → 追加 AI 回复。
 */
import { createSession, sendMessage } from '../api/session';
import { useChatStore } from '../stores/chatStore';

export function useChatSend() {
  const isThinking = useChatStore((s) => s.isThinking);

  const send = async (content: string) => {
    if (!content.trim() || useChatStore.getState().isThinking) return;
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
    const { addUserMessage, addAIMessage, setThinking } = useChatStore.getState();
    addUserMessage(content);
    setThinking(true);
    try {
      const resp = await sendMessage(sid, content);
      const reply = resp.content || '';
      if (reply && reply !== '(no reply)' && reply !== '(empty)')
        addAIMessage(reply, {
          taskGraph: resp.task_graph ?? undefined,
          metadata: { taskGraph: resp.task_graph ?? undefined, latencyMs: resp.latency_ms },
        });
    } catch (e) {
      console.error('Send failed:', e);
    } finally {
      setThinking(false);
    }
  };

  return { send, isThinking };
}

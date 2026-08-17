/** useChatSend — 发送逻辑共享 hook(P1-A)。
 *  主槽 ChatPage 与副槽迷你对话(ChatSideSurface)共用同一条发送路径:
 *  确保会话存在 → 追加用户消息 → 流式调用后端(SSE) → 边收边填充。
 *  2026-08-17: 一次性 POST → 流式 SSE(思考过程 reasoning + 内容 content
 *  逐块填充, 与网页 AI 对话体验一致)。
 */
import { createSession } from '../api/session';
import { useChatStore } from '../stores/chatStore';

const API = import.meta.env.VITE_API_BASE_URL || '';

function parseSSELine(line: string): { event?: string; delta?: string; content?: string; nodes?: unknown[]; message?: string } | null {
  const t = line.trim();
  if (!t.startsWith('data:')) return null;
  const payload = t.slice(5).trim();
  if (payload === '[DONE]') return null;
  try {
    return JSON.parse(payload);
  } catch {
    return null;
  }
}

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
    const { addUserMessage, streamStart, streamAppend, streamFinish, setThinking, setThinkingText } = useChatStore.getState();
    addUserMessage(content);
    setThinking(true);
    const replyId = `stream-${Date.now()}`;
    streamStart(replyId);
    try {
      const resp = await fetch(`${API}/v3/session/${encodeURIComponent(sid)}/message/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
      });
      if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`);
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';
      let reasoningBuf = '';
      let finalContent = '';
      let taskGraph: unknown[] | undefined;
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop() || '';
        for (const line of lines) {
          const ev = parseSSELine(line);
          if (!ev) continue;
          if (ev.event === 'reasoning' && ev.delta) {
            reasoningBuf += ev.delta;
            setThinkingText(reasoningBuf);
          } else if (ev.event === 'content' && ev.delta) {
            finalContent += ev.delta;
            streamAppend(replyId, ev.delta);
          } else if (ev.event === 'task_graph') {
            taskGraph = ev.nodes;
          } else if (ev.event === 'done') {
            finalContent = ev.content || finalContent;
          } else if (ev.event === 'error' && ev.message) {
            throw new Error(ev.message);
          }
        }
      }
      const state = useChatStore.getState();
      streamFinish(replyId, {
        content: finalContent || state.messages.find(m => m.id === replyId)?.content || '',
        taskGraph: taskGraph as never,
        metadata: {
          taskGraph: taskGraph as never,
          thinkingSteps: reasoningBuf
            ? [{ step: 1, description: reasoningBuf.slice(0, 400), detail: reasoningBuf }]
            : [],
        },
      });
    } catch (e) {
      console.error('Send failed:', e);
      streamFinish(replyId, {
        content: `⚠️ 发送失败：${e instanceof Error ? e.message : '未知错误'}`,
        status: 'error' as const,
      });
    } finally {
      setThinking(false);
      setThinkingText('');
    }
  };

  return { send, isThinking };
}

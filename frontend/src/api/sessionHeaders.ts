// B5（2026-08-07）: 浏览器会话身份。
// RateLimitMiddleware 按 x-session-id 分桶；不带时所有请求共享 anonymous 桶
// （burst=20, refill 1/s），页面加载瞬时 10+ 并发请求即触发 429，
// 前端 catch(null) 吞掉后表现为"图谱/任务页一直空/一直加载"。
// 用 sessionStorage 持久（每标签页一个身份），会话内稳定，新标签页新桶。
const KEY = 'dm_session_id';

export function getSessionId(): string {
  let id = sessionStorage.getItem(KEY);
  if (!id) {
    id = `web_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
    sessionStorage.setItem(KEY, id);
  }
  return id;
}

export function sessionHeaders(): Record<string, string> {
  return { 'x-session-id': getSessionId() };
}

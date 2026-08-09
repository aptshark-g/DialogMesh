import { test as base } from '@playwright/test';

/**
 * B5 (2026-08-07): RateLimitMiddleware 的 session key = `x-session-id` header，
 * 前端默认不带 → 所有请求共享 anonymous 桶（session_burst=20）。
 * 测试/轮询请求过快会触发 429，故在交互动作前统一加节流延时。
 */
export const test = base.extend({
  page: async ({ page }, use) => {
    const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
    const origDown = page.mouse.down.bind(page.mouse);
    const origClick = page.click.bind(page);
    const origDblclick = page.dblclick.bind(page);
    const origHover = page.hover.bind(page);
    page.mouse.down = async (opts) => { await sleep(200); return origDown(opts); };
    page.click = async (sel, opts) => { await sleep(200); return origClick(sel, opts); };
    page.dblclick = async (sel, opts) => { await sleep(200); return origDblclick(sel, opts); };
    page.hover = async (sel, opts) => { await sleep(200); return origHover(sel, opts); };
    await use(page);
  },
});

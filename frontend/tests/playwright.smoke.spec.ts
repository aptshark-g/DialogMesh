import { test, expect } from '@playwright/test';

test('chromium channel launches and loads app', async ({ browser }) => {
  // Playwright 默认用下载的 chromium 内核；无内核时用系统 Chrome
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.goto('http://localhost:5173', { waitUntil: 'domcontentloaded', timeout: 20000 });
  await expect(page).toHaveTitle(/DialogMesh|Vite|React/i, { timeout: 15000 });
  await ctx.close();
});

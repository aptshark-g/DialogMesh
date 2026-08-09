import { test, expect } from '@playwright/test';

/**
 * B5（2026-08-07）: 13 页真数据绑定 smoke。
 * 每页: 无 pageerror / 无 429 / 无 5xx / 主内容渲染。
 * 数据层关键页额外断言: 图谱页节点 > 0（真数据）、网关页显示 switch 真 provider。
 * 环境: vite dev 5173 同源代理（vite.config.ts server.proxy → 8000）。
 */

const BENIGN_CONSOLE = ['ERR_NETWORK_ACCESS_DENIED', 'favicon'];

const PAGES: { path: string; heading?: string; marker?: string }[] = [
  { path: '/', heading: 'DialogMesh' },
  { path: '/chat', marker: 'input, textarea' },
  { path: '/graph', heading: '对话树图谱' },
  { path: '/profile', heading: '认知画像' },
  { path: '/tasks', heading: '任务规划' },
  { path: '/gateway', heading: '网关 & Provider' },
  { path: '/pipeline', heading: '业务管道' },
  { path: '/deepchain', heading: '深层链' },
  { path: '/meta', heading: '元认知中心' },
  { path: '/behavior', heading: '行为发现' },
  { path: '/engineering', heading: '工程链工作台' },
  { path: '/sessions', heading: 'Session 管理' },
  { path: '/settings', heading: '设置' },
];

for (const p of PAGES) {
  test(`page ${p.path} renders without JS errors or bad status`, async ({ page }) => {
    const errors: string[] = [];
    const badStatus: string[] = [];
    page.on('pageerror', (e) => errors.push(`PAGEERROR: ${e.message}`));
    page.on('console', (m) => {
      if (m.type() !== 'error') return;
      if (BENIGN_CONSOLE.some((b) => m.text().includes(b))) return;
      errors.push(`CONSOLE: ${m.text().slice(0, 300)}`);
    });
    page.on('response', (r) => {
      if (r.status() === 429 || r.status() >= 500) badStatus.push(`${r.status()} ${r.url()}`);
    });

    await page.goto(`http://localhost:5173${p.path}`, { waitUntil: 'domcontentloaded', timeout: 20000 });
    if (p.heading) {
      await expect(
        page.getByRole('heading', { name: p.heading }).first()
      ).toBeVisible({ timeout: 15000 });
    } else {
      await expect(page.locator(p.marker as string).first()).toBeVisible({ timeout: 15000 });
    }
    // 等异步数据落地后再收口错误断言
    await page.waitForTimeout(1500);
    expect(errors, `JS errors on ${p.path}`).toEqual([]);
    expect(badStatus, `bad HTTP status on ${p.path}`).toEqual([]);
  });
}

test('graph page renders real nodes (>0)', async ({ page }) => {
  await page.goto('http://localhost:5173/graph', { waitUntil: 'domcontentloaded', timeout: 20000 });
  await expect(page.locator('.react-flow__node').first()).toBeVisible({ timeout: 20000 });
  const count = await page.locator('.react-flow__node').count();
  expect(count).toBeGreaterThan(0);
});

test('gateway page shows real provider from switch', async ({ page }) => {
  await page.goto('http://localhost:5173/gateway', { waitUntil: 'domcontentloaded', timeout: 20000 });
  await expect(page.getByText('deepseek', { exact: false }).first()).toBeVisible({ timeout: 15000 });
});

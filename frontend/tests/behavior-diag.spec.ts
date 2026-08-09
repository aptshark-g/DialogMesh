import { test, expect } from '@playwright/test';

test('behavior page crash diagnosis on 4173', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (err) => errors.push('PAGEERROR: ' + err.message + '\n' + (err.stack || '').split('\n').slice(0, 4).join('\n')));
  page.on('console', (msg) => { if (msg.type() === 'error') errors.push('CONSOLE: ' + msg.text().slice(0, 300)); });

  await page.goto('http://localhost:4173/behavior', { waitUntil: 'domcontentloaded', timeout: 20000 });
  await page.waitForTimeout(4000);
  console.log('BEHAVIOR_ERRORS:', JSON.stringify(errors.slice(0, 6), null, 1));
  const body = (await page.locator('body').innerText()).slice(0, 300);
  console.log('BODY:', JSON.stringify(body));
  expect(true).toBe(true);
});

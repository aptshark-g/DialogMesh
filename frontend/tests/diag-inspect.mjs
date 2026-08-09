import { chromium } from '@playwright/test';
const browser = await chromium.launch({ headless: true, args: ['--no-proxy-server', '--disable-extensions'] });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
await page.goto('http://localhost:5173/graph?sid=b84e1b45-4f5', { waitUntil: 'domcontentloaded', timeout: 20000 });
await page.waitForSelector('.react-flow__node', { timeout: 20000 });
await page.waitForTimeout(1200);

// 右键第一个节点
const node = page.locator('.react-flow__node').first();
await node.click({ button: 'right' });
await page.waitForTimeout(400);
const menuText = await page.evaluate(() => {
  const btns = Array.from(document.querySelectorAll('button')).filter(b => b.textContent?.includes('右侧显示详情'));
  return btns.map(b => b.textContent?.trim());
});
console.log('MENU item:', JSON.stringify(menuText));

// 点击"在右侧显示详情"
const inspectBtn = page.getByRole('button', { name: /在右侧显示详情/ }).first();
await inspectBtn.click();
await page.waitForTimeout(800);

const dock = await page.evaluate(() => {
  const aside = document.querySelector('[aria-label="调整右栏宽度"]')?.closest('aside');
  const text = aside?.textContent || '';
  return {
    open: !!aside,
    width: aside ? Math.round(aside.getBoundingClientRect().width) : 0,
    hasTitle: text.includes('节点详情'),
    hasId: text.includes('ID'),
    hasRaw: text.includes('原文'),
    snippet: text.slice(0, 200).replace(/\n+/g, ' | '),
  };
});
console.log('DOCK:', JSON.stringify(dock, null, 1));
console.log('ERRORS:', JSON.stringify(errors));
await browser.close();

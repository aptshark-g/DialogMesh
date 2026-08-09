import { expect } from '@playwright/test';
import { test } from './throttle';

const GRAPH_URL = 'http://localhost:5173/graph';

async function openGraph(page: import('@playwright/test').Page) {
  await page.goto(GRAPH_URL, { waitUntil: 'domcontentloaded', timeout: 20000 });
  // 等 ReactFlow 渲染且至少一个节点出现（数据异步加载）
  await expect(page.locator('.react-flow__node').first()).toBeVisible({ timeout: 20000 });
  // 等加载遮罩退场 + fitView 定位完成，避免遮罩吞掉鼠标事件
  await page.waitForTimeout(800);
}

test('graph page loads ReactFlow with real nodes', async ({ page }) => {
  await openGraph(page);
  // ReactFlow 渲染在 .react-flow 容器内
  const flow = page.locator('.react-flow');
  await expect(flow).toBeVisible();
  const nodeCount = await page.locator('.react-flow__node').count();
  expect(nodeCount).toBeGreaterThan(0);
});

test('node drag moves node position', async ({ page }) => {
  await openGraph(page);
  const node = page.locator('.react-flow__node').first();
  await expect(node).toBeVisible();

  const before = await node.boundingBox();
  expect(before).not.toBeNull();

  // 鼠标拖拽：按下 → 移动 → 松开（ReactFlow 用 pointer 事件）
  await page.mouse.move(before!.x + before!.width / 2, before!.y + before!.height / 2);
  await page.mouse.down();
  await page.mouse.move(before!.x + before!.width / 2 + 80, before!.y + before!.height / 2 + 60, { steps: 10 });
  await page.mouse.up();

  // 等待位置更新
  await page.waitForTimeout(500);
  const after = await node.boundingBox();
  expect(after).not.toBeNull();
  const dx = Math.abs((after!.x + after!.width / 2) - (before!.x + before!.width / 2));
  const dy = Math.abs((after!.y + after!.height / 2) - (before!.y + before!.height / 2));
  // 节点应移动（允许 snapGrid 16px 取整）
  expect(dx + dy).toBeGreaterThan(30);
});

test('pane drag pans the canvas (transform changes)', async ({ page }) => {
  await openGraph(page);

  const pane = page.locator('.react-flow__pane');
  await expect(pane).toBeVisible();
  const viewport = page.locator('.react-flow__viewport');
  // ReactFlow 的 viewport transform 是 CSS style（v11），不是 SVG attribute
  const before = await viewport.evaluate((el) => el.style.transform);

  const box = await pane.boundingBox();
  expect(box).not.toBeNull();
  await page.mouse.move(box!.x + 300, box!.y + 300);
  await page.mouse.down();
  await page.mouse.move(box!.x + 450, box!.y + 400, { steps: 10 });
  await page.mouse.up();
  await page.waitForTimeout(500);

  const after = await viewport.evaluate((el) => el.style.transform);
  expect(after).not.toBe(before);
});

test('right-click on node opens context menu', async ({ page }) => {
  await openGraph(page);
  const node = page.locator('.react-flow__node').first();
  await expect(node).toBeVisible();

  await node.click({ button: 'right' });
  // 上下文菜单（编辑名称 / 删除节点 等按钮）
  await expect(page.getByRole('button', { name: '编辑名称' })).toBeVisible({ timeout: 5000 });
  await expect(page.getByRole('button', { name: '删除节点' })).toBeVisible({ timeout: 5000 });
});

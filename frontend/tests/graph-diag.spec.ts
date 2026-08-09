import { test, expect } from '@playwright/test';

test('diagnose graph page rendering', async ({ page }) => {
  const errors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  page.on('pageerror', (err) => errors.push('PAGEERROR: ' + err.message));
  page.on('requestfailed', (req) => errors.push('REQFAIL: ' + req.url() + ' ' + (req.failure()?.errorText || '')));

  await page.goto('http://localhost:4173/graph', { waitUntil: 'domcontentloaded', timeout: 20000 });
  await page.waitForTimeout(3000);

  const bodyText = (await page.locator('body').innerText()).slice(0, 400);
  console.log('BODY_TEXT:', JSON.stringify(bodyText));
  console.log('CONSOLE_ERRORS:', JSON.stringify(errors.slice(0, 10)));
  console.log('REACT_FLOW_COUNT:', await page.locator('.react-flow').count());
  const flowBox = await page.locator('.react-flow').boundingBox();
  console.log('FLOW_BOX:', JSON.stringify(flowBox));
  const flowVisible = await page.locator('.react-flow').isVisible();
  console.log('FLOW_VISIBLE:', flowVisible);
  // what covers the flow? elements with higher z-index / fixed overlay
  const overlays = await page.evaluate(() => {
    const flow = document.querySelector('.react-flow');
    if (!flow) return null;
    const fr = flow.getBoundingClientRect();
    const els = document.elementsFromPoint(fr.x + fr.width / 2, fr.y + fr.height / 2);
    return els.slice(0, 8).map((el) => {
      const r = el.getBoundingClientRect();
      return el.tagName + '.' + (el.className?.toString().slice(0, 50) || '') +
        ' z=' + getComputedStyle(el).zIndex + ' pe=' + getComputedStyle(el).pointerEvents +
        ' pos=' + Math.round(r.width) + 'x' + Math.round(r.height);
    });
  });
  console.log('ELEMENTS_AT_CENTER:', JSON.stringify(overlays));
  console.log('URL:', page.url());
  await page.screenshot({ path: 'test-results/graph-diag.png' });
  expect(true).toBe(true);
});

test('second load of graph page still renders nodes', async ({ page }) => {
  const responses: string[] = [];
  const failures: string[] = [];
  const consoleErrors: string[] = [];
  page.on('response', (resp) => {
    if (resp.url().includes('/v6/graph')) responses.push(resp.status() + ' ' + resp.url());
  });
  page.on('requestfailed', (req) => failures.push(req.url() + ' => ' + (req.failure()?.errorText || '?')));
  page.on('console', (msg) => { if (msg.type() === 'error') consoleErrors.push(msg.text()); });
  page.on('pageerror', (err) => consoleErrors.push('PAGEERROR: ' + err.message));

  // 第一次打开
  await page.goto('http://localhost:4173/graph', { waitUntil: 'domcontentloaded', timeout: 20000 });
  await page.waitForTimeout(3000);
  const firstCount = await page.locator('.react-flow__node').count();
  console.log('FIRST_NODE_COUNT:', firstCount);
  console.log('FAILURES1:', JSON.stringify(failures.slice(0, 5)));
  console.log('CONSOLE1:', JSON.stringify(consoleErrors.slice(0, 5)));

  // 第二次打开（同 context，新导航）
  responses.length = 0;
  failures.length = 0;
  consoleErrors.length = 0;
  await page.goto('http://localhost:4173/graph', { waitUntil: 'domcontentloaded', timeout: 20000 });
  await page.waitForTimeout(3000);
  const secondCount = await page.locator('.react-flow__node').count();
  console.log('SECOND_NODE_COUNT:', secondCount);
  console.log('GRAPH_RESPONSES:', JSON.stringify(responses));
  console.log('FAILURES2:', JSON.stringify(failures.slice(0, 5)));
  console.log('CONSOLE2:', JSON.stringify(consoleErrors.slice(0, 5)));
  const emptyText = await page.locator('body').innerText();
  console.log('EMPTY_HINT:', JSON.stringify(emptyText.includes('暂无图数据') ? 'no-data' : (emptyText.includes('加载中') ? 'loading' : 'other')));
  expect(true).toBe(true);
});

test('probe CORS from page context', async ({ page }) => {
  await page.goto('http://localhost:4173/', { waitUntil: 'domcontentloaded', timeout: 20000 });
  const probe = await page.evaluate(async () => {
    try {
      const resp = await fetch('http://localhost:8000/v6/graph', {
        headers: { Accept: 'application/json' },
      });
      const hdrs: Record<string, string> = {};
      resp.headers.forEach((v, k) => { hdrs[k] = v; });
      return { ok: resp.status, acao: hdrs['access-control-allow-origin'] || null, cors: hdrs['access-control-allow-credentials'] || null, n: Object.keys(hdrs).length };
    } catch (e) {
      return { error: String(e) };
    }
  });
  console.log('CORS_PROBE:', JSON.stringify(probe));
  expect(true).toBe(true);
});

test('probe CORS via playwright api client vs browser', async ({ page, request }) => {
  // Playwright API 客户端（Node 层，不经浏览器）
  const apiResp = await request.get('http://localhost:8000/v6/graph', {
    headers: { Origin: 'http://localhost:4173' },
  });
  console.log('API_STATUS:', apiResp.status());
  console.log('API_ACAO:', apiResp.headers()['access-control-allow-origin']);
  console.log('API_BODY_NODES:', (await apiResp.json()).nodes?.length);

  // 浏览器内 fetch
  await page.goto('http://localhost:4173/', { waitUntil: 'domcontentloaded', timeout: 20000 });
  const browserProbe = await page.evaluate(async () => {
    const resp = await fetch('http://localhost:8000/v6/graph');
    const headers: Record<string, string> = {};
    resp.headers.forEach((v, k) => { headers[k] = v; });
    return { status: resp.status, headers, ok: resp.ok };
  });
  console.log('BROWSER_PROBE:', JSON.stringify(browserProbe));
  expect(true).toBe(true);
});

test('graph page nodes render via proxy (5173)', async ({ page }) => {
  const failures: string[] = [];
  const consoleErrors: string[] = [];
  page.on('requestfailed', (req) => failures.push(req.url() + ' => ' + (req.failure()?.errorText || '?')));
  page.on('console', (msg) => { if (msg.type() === 'error') consoleErrors.push(msg.text()); });

  await page.goto('http://localhost:5173/graph', { waitUntil: 'domcontentloaded', timeout: 20000 });
  await page.waitForTimeout(4000);
  const nodeCount = await page.locator('.react-flow__node').count();
  console.log('PROXY_NODE_COUNT:', nodeCount);
  console.log('PROXY_FAILURES:', JSON.stringify(failures.slice(0, 6)));
  console.log('PROXY_CONSOLE:', JSON.stringify(consoleErrors.slice(0, 6)));
  // 图谱区域正文
  const hint = await page.evaluate(() => {
    const el = document.querySelector('.react-flow')?.parentElement;
    return el ? el.innerText.slice(0, 120) : 'no-flow';
  });
  console.log('PROXY_HINT:', JSON.stringify(hint));
  expect(true).toBe(true);
});

test('reactflow pointer event diagnosis', async ({ page }) => {
  await page.goto('http://localhost:5173/graph', { waitUntil: 'domcontentloaded', timeout: 20000 });
  await expect(page.locator('.react-flow__node').first()).toBeVisible({ timeout: 20000 });

  // 1) 在 ReactFlow 内部注入事件探针，捕获 pointer/mouse 事件是否到达画布
  const probe = await page.evaluate(() => {
    const pane = document.querySelector('.react-flow__pane');
    const node = document.querySelector('.react-flow__node');
    if (!pane || !node) return { error: 'no pane/node' };
    const events: string[] = [];
    const handler = (e: Event) => {
      const t = e.target as Element;
      events.push(e.type + '@' + (t.className?.toString().slice(0, 40) || t.tagName));
    };
    // 顶层捕获所有 pointer/mouse 事件，标注目标
    document.addEventListener('pointerdown', handler, true);
    document.addEventListener('pointermove', handler, true);
    document.addEventListener('pointerup', handler, true);
    document.addEventListener('mousedown', handler, true);
    document.addEventListener('mousemove', handler, true);
    document.addEventListener('mouseup', handler, true);
    // 存到全局供后续读取
    (window as any).__probeEvents = events;

    // 2) 检查样式: pointer-events / user-select / touch-action
    const ps = getComputedStyle(pane);
    const ns = getComputedStyle(node);
    // 3) 检查 ReactFlow 是否处于 draggable 状态
    const rf = document.querySelector('.react-flow');
    const flowClass = rf?.getAttribute('class') || '';
    const nodeClass = node.getAttribute('class') || '';
    const paneStyle = {
      pointerEvents: ps.pointerEvents,
      touchAction: ps.touchAction,
      userSelect: ps.userSelect,
      position: ps.position,
      zIndex: ps.zIndex,
    };
    const nodeStyle = {
      pointerEvents: ns.pointerEvents,
      touchAction: ns.touchAction,
      userSelect: ns.userSelect,
    };
    return { paneStyle, nodeStyle, flowClass, nodeClass, captured: 0 };
  });

  // 3) 实际拖拽一次
  const node = page.locator('.react-flow__node').first();
  const nb = await node.boundingBox();
  await page.mouse.move(nb!.x + nb!.width / 2, nb!.y + nb!.height / 2);
  await page.mouse.down();
  await page.mouse.move(nb!.x + nb!.width / 2 + 60, nb!.y + nb!.height / 2 + 40, { steps: 8 });
  await page.mouse.up();
  await page.waitForTimeout(300);

  // 4) 读探针捕获
  const events = await page.evaluate(() => {
    const pane = document.querySelector('.react-flow__pane');
    return (pane as any).__probeEvents || [];
  });
  console.log('STYLE_PROBE:', JSON.stringify(probe));
  console.log('EVENT_PROBE:', JSON.stringify(events.slice(0, 20)));
  // 节点 transform 前后
  const viewport = await page.locator('.react-flow__viewport').getAttribute('transform');
  console.log('VIEWPORT_AFTER:', viewport);
  expect(true).toBe(true);
});

test('elementsFromPoint at node center', async ({ page }) => {
  await page.goto('http://localhost:5173/graph', { waitUntil: 'domcontentloaded', timeout: 20000 });
  await expect(page.locator('.react-flow__node').first()).toBeVisible({ timeout: 20000 });
  const info = await page.evaluate(() => {
    const node = document.querySelector('.react-flow__node');
    if (!node) return { error: 'no node' };
    const r = node.getBoundingClientRect();
    const x = r.x + r.width / 2, y = r.y + r.height / 2;
    const chain = document.elementsFromPoint(x, y).map((el) => {
      const er = el.getBoundingClientRect();
      const cs = getComputedStyle(el);
      return {
        tag: el.tagName,
        cls: (el.className?.toString() || '').slice(0, 60),
        pe: cs.pointerEvents,
        z: cs.zIndex,
        rect: Math.round(er.width) + 'x' + Math.round(er.height),
      };
    });
    return { x: Math.round(x), y: Math.round(y), chain };
  });
  console.log('ELEMENTS_CHAIN:', JSON.stringify(info));
  expect(true).toBe(true);
});

test('viewport transform and node positions', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (err) => errors.push('PAGEERROR: ' + err.message));
  page.on('console', (msg) => { if (msg.type() === 'error') errors.push(msg.text().slice(0, 200)); });
  await page.goto('http://localhost:5173/graph', { waitUntil: 'domcontentloaded', timeout: 20000 });
  await page.waitForTimeout(4000);
  console.log('GRAPH_ERRORS:', JSON.stringify(errors.slice(0, 5)));
  console.log('NODE_COUNT:', await page.locator('.react-flow__node').count());
  await expect(page.locator('.react-flow__node').first()).toBeVisible({ timeout: 20000 });
  const info = await page.evaluate(() => {
    const vp = document.querySelector('.react-flow__viewport');
    const nodes = Array.from(document.querySelectorAll('.react-flow__node')).slice(0, 5);
    const rf = document.querySelector('.react-flow');
    const flowBox = rf?.getBoundingClientRect();
    return {
      viewportTransform: vp?.getAttribute('transform'),
      flowRect: flowBox ? { x: Math.round(flowBox.x), y: Math.round(flowBox.y), w: Math.round(flowBox.width), h: Math.round(flowBox.height) } : null,
      nodes: nodes.map((n) => {
        const r = n.getBoundingClientRect();
        return { id: n.getAttribute('data-id')?.slice(0, 8), x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) };
      }),
    };
  });
  console.log('VIEWPORT_INFO:', JSON.stringify(info));
  expect(true).toBe(true);
});

test('mouse events reach document at all?', async ({ page }) => {
  await page.goto('http://localhost:5173/', { waitUntil: 'domcontentloaded', timeout: 20000 });
  // 挂一个 document click 监听 + 一个 body mousemove 监听
  await page.evaluate(() => {
    const hits: string[] = [];
    document.addEventListener('click', (e) => {
      hits.push('click@' + ((e.target as Element)?.tagName || '?'));
    }, true);
    document.addEventListener('mousemove', () => hits.push('mousemove'), true);
    document.addEventListener('pointermove', () => hits.push('pointermove'), true);
    (window as any).__hits = hits;
  });
  // Playwright mouse 事件
  await page.mouse.move(400, 400);
  await page.mouse.move(420, 420, { steps: 5 });
  await page.mouse.click(500, 500);
  await page.waitForTimeout(300);
  const hits = await page.evaluate(() => (window as any).__hits);
  console.log('MOUSE_HITS:', JSON.stringify(hits));
  // 对比: page.click 走 Playwright 的 locator 点击
  await page.locator('body').click();
  const hits2 = await page.evaluate(() => (window as any).__hits);
  console.log('MOUSE_HITS2:', JSON.stringify(hits2));
  expect(true).toBe(true);
});

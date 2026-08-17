// P1-E 质感基调截图: 暗色主屏 / 暗色 omnibox 玻璃 / 浅色 omnibox / 浅色主屏
import { chromium } from 'playwright';

const BASE = 'http://localhost:4180/';
const OUT = '../docs/only/frontend/uiTest/';

const ctxMock = {
  session_id: 'shot-p1e', token_budget: 4000, token_used: 1532,
  entries: [
    { id: 'e1', domain: 'D', content: '认知融合层把对话状态编译为可注入的运行时上下文', score: 0.92, tokens: 420, pinned: true },
    { id: 'e2', domain: 'K', content: 'v6 网关负责 Switch 代理与密钥下发', score: 0.81, tokens: 356, pinned: false },
    { id: 'e3', domain: 'behavior', content: '用户偏好: 技术术语保留英文, 渐进修改不重写', score: 0.77, tokens: 388, pinned: false },
    { id: 'e4', domain: 'P', content: '画像五条维度在对话中持续校准', score: 0.64, tokens: 368, pinned: false },
  ],
};
const profileMock = {
  user_id: 'u-shot', confidence: 0.62,
  oceAN_dims: { '开放性': 0.5, '尽责性': 0.5, '外向性': 0.5, '宜人性': 0.5, '神经质': 0.5 },
};

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1600, height: 950 } });
await page.route('**/v6/context**', r => r.fulfill({ json: ctxMock }));
await page.route('**/v6/profile**', r => r.fulfill({ json: profileMock }));
await page.goto(BASE, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);

// 1. 暗色主屏(展开右侧面板看卡片去描边)
const expand = page.getByLabel('展开右侧面板');
if (await expand.count()) { await expand.first().click(); await page.waitForTimeout(600); }
await page.screenshot({ path: OUT + 'real_p1e_dark_main.png' });

// 2. 暗色 omnibox 玻璃
await page.getByLabel('打开万能搜索').click();
await page.waitForTimeout(500);
await page.screenshot({ path: OUT + 'real_p1e_dark_omnibox.png' });
await page.keyboard.press('Escape');
await page.waitForTimeout(400);

// 3. 切浅色
await page.getByLabel('切换到亮色模式').click();
await page.waitForTimeout(600);
await page.screenshot({ path: OUT + 'real_p1e_light_main.png' });

// 4. 浅色 omnibox
await page.getByLabel('打开万能搜索').click();
await page.waitForTimeout(500);
await page.screenshot({ path: OUT + 'real_p1e_light_omnibox.png' });

await browser.close();
console.log('SHOTS_OK');

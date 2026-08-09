import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: 60000,
  // B5（2026-08-07）: 测试自举 dev server（5173），proxy 仅 dev 模式生效，
  // 浏览器只见同源，绕开系统 Chrome 的 CORS 剥离问题
  webServer: {
    // 2026-08-08: 5173 dev 启动不稳 → 改用 4173 preview（同样配了 proxy）
    command: 'npm run preview -- --port 4173',
    url: 'http://localhost:4173',
    reuseExistingServer: true,
    timeout: 60000,
  },
  use: {
    headless: process.env.PW_HEADED ? false : true,
    viewport: { width: 1440, height: 900 },
    launchOptions: {
      args: [
        '--disable-extensions',
        '--disable-plugins',
        '--no-proxy-server',
        '--disable-background-networking',
      ],
    },
  },
  workers: 1,
});

# B5 前端 UI 测试方案 — Playwright + vite 同源代理（2026-08-07）

> 状态: 规划 | 触发: B5 图谱页 ReactFlow 鼠标交互验证（TROUBLESHOOTING §10
> 遗留）+ 系统 Chrome 剥离 CORS 响应头（实测）

---

## 一、背景与实测发现

### 1.1 B5 图谱页验证目标
- 验证 ReactFlow 鼠标交互（节点拖拽/画布平移/右键菜单）在当前环境真实可用
- TROUBLESHOOTING §10 曾记录 React 19 + ReactFlow 11 鼠标交互完全失效
  （环境阻断），本轮需用 UI 级测试重新验证

### 1.2 实测发现：系统 Chrome 剥离 CORS 响应头
- 后端 v6_app 已配置 `CORSMiddleware(allow_origins=["*"])`（代码正确）
- `curl -H "Origin: http://localhost:4173"` → 返回 `access-control-allow-origin: *` ✅
- Playwright API 客户端（Node 层）→ `ACAO: *` + 20 节点 ✅
- 但浏览器内 `fetch('http://localhost:8000/v6/graph')` → 200，响应头仅
  `content-length` + `content-type`，**ACAO 被剥离** → CORS 拦截 → 图谱无数据
- 有头/无头模式一致；`--disable-extensions` + `--no-proxy-server` 无效
- 结论: 系统 Chrome 环境对 CORS 响应头有干扰（组策略/安全软件注入），
  **非后端配置问题**

### 1.3 为什么绕开 CORS 而不是修它
- 后端 CORS 配置已正确（curl/API 客户端双重证明），无法从代码侧再修
- 系统 Chrome 行为不可控（用户级环境），不适合作为依赖
- 业界标准做法: 前端开发/测试走 dev server 同源代理，浏览器只见同源，
  CORS 根本不参与

---

## 二、方案（Playwright 官方推荐模式）

### 2.1 vite dev server proxy（同源代理）
`frontend/vite.config.ts` 加 `server.proxy`:

```ts
server: {
  proxy: {
    '/v6': 'http://localhost:8000',
    '/v3': 'http://localhost:8000',
    '/v4': 'http://localhost:8000',
  },
},
```

- 浏览器请求 `http://localhost:5173/v6/graph` → vite 转发到 8000 → 同源响应
- CORS 不参与（浏览器视角只有 5173 一个源）
- 生产形态同构（nginx 反代），非测试专用 hack

### 2.2 Playwright `webServer`（测试自举）
`frontend/playwright.config.ts` 加:

```ts
webServer: {
  command: 'npm run dev',
  url: 'http://localhost:5173',
  reuseExistingServer: true,
},
```

- 测试自动拉起 dev server（5173），无需手动维护服务
- 测试 URL 用 5173（proxy 仅 dev 模式生效）

### 2.3 测试基建
- `frontend/tests/` 目录（已建）:
  - `playwright.smoke.spec.ts` — 启动冒烟（已过）
  - `graph-interaction.spec.ts` — 图谱鼠标交互（拖拽/平移/右键菜单）
  - `graph-diag.spec.ts` — 诊断辅助（CORS 探测等，保留为调试工具）
- `playwright.config.ts` — channel: chrome（复用系统 Chrome，无内核下载）

---

## 三、验收门槛

1. 图谱页在 5173 下渲染 20 节点（真数据，非 mock）
2. 节点拖拽后位置变化 > 30px（ReactFlow 交互真实可用）
3. 画布平移改变 viewport transform
4. 右键节点弹出上下文菜单（编辑名称/删除节点）
5. `npx playwright test` 全绿

---

## 四、遗留/后续

- 系统 Chrome 剥离 CORS 是环境级问题，已通过同源代理绕开；
  若未来换内核（Playwright 自带 chromium 下载成功），可回退直接连 8000
- 13 页全量 smoke 后续在此基建上扩展（每页一个 spec）
- vite dev server 作为测试标准入口后，preview（4173）仅用于产物验证

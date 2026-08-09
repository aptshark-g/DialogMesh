import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // B5 UI 测试（2026-08-07）: 前端走 dev server 同源代理，绕开
      // 系统 Chrome 剥离 CORS 响应头的环境问题（详见
      // docs/only/frontend/B5_UI_TEST_PLAN_20260807.md）
      '/v6': 'http://localhost:8000',
      '/v3': 'http://localhost:8000',
      '/v4': 'http://localhost:8000',
    },
  },
  preview: {
    proxy: {
      // 4173 (vite preview) 同样需要代理: BASE_URL 为相对路径时,
      // /v6|/v3|/v4 必须转发到后端, 否则 404 / Backend Offline
      '/v6': 'http://localhost:8000',
      '/v3': 'http://localhost:8000',
      '/v4': 'http://localhost:8000',
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  build: {
    rollupOptions: {
      input: {
        index: 'index.html',
        background: 'src/background.ts',
      },
      output: {
        manualChunks: (id: string) => {
          const normalized = id.replace(/\\/g, '/')
          if (normalized.includes('/node_modules/recharts/')) return 'vendor-recharts'
          if (normalized.includes('/node_modules/react-force-graph-2d/')) return 'vendor-force-graph'
          if (normalized.includes('/node_modules/@reactflow/')) return 'vendor-reactflow'
        },
        entryFileNames: (chunkInfo) => {
          return chunkInfo.name === 'background' ? 'background.js' : 'assets/[name]-[hash].js'
        },
      },
    },
  },
})

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'

export default defineConfig({
  plugins: [react()],
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

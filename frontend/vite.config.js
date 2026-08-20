import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Vite 开发服务器配置：
// 前端 5173 端口，/api 请求代理到 Flask 后端 5000 端口（避免跨域）
export default defineConfig({
  plugins: [vue()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/zrender')) return 'renderer'
          if (id.includes('node_modules/echarts')) return 'charts'
          if (id.includes('node_modules/vue')) return 'vue'
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
    },
  },
})

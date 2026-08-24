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
    // 固定监听 IPv4 回环地址，确保 README 中的 127.0.0.1:5173 可以直接访问。
    // Windows 上仅使用默认 localhost 时，Vite 可能只监听 ::1（IPv6）。
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
    },
  },
})

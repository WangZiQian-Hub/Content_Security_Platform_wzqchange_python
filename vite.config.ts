import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      // 本项目（模型服务）：/llm-api/v1/xxx -> http://127.0.0.1:8001/api/v1/xxx
      '/llm-api': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/llm-api/, '/api'),
      },
      // 原业务后端：/api/v1/xxx 继续保持不变。
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})

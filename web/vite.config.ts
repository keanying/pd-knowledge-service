import { fileURLToPath, URL } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

/**
 * 管理后台走 BFF 登录：浏览器只持有 pdk-api 下发的 HttpOnly Cookie，不接触令牌。
 * 开发时把 /api 与 /auth 代理到本地 pdk-api（同源访问）；pdk-api 需设置 PDK_WEB_URL=http://127.0.0.1:5175。
 */
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const api = env.PDK_DEV_TARGET || 'http://127.0.0.1:8000'
  return {
    base: env.VITE_BASE || '/',
    plugins: [vue(), tailwindcss()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
        '@viewui-fonts': fileURLToPath(new URL('./node_modules/view-ui-plus/src/styles/common/iconfont/fonts', import.meta.url)),
      },
    },
    css: { preprocessorOptions: { less: { javascriptEnabled: true } } },
    build: { outDir: 'dist', emptyOutDir: true, chunkSizeWarningLimit: 2000 },
    server: {
      host: '127.0.0.1',
      port: 5175,
      proxy: Object.fromEntries(['/api', '/auth'].map((p) => [p, { target: api, xfwd: true }])),
    },
  }
})

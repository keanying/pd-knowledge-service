import { fileURLToPath, URL } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

/** 门户经 pda-gateway 登录（HttpOnly Cookie）。开发时把 /pda 与 /auth 代理到网关；网关需设置 PDA_WEB_URL=http://127.0.0.1:5176。 */
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const gw = env.PDA_DEV_TARGET || 'http://127.0.0.1:8100'
  return {
    plugins: [vue(), tailwindcss()],
    resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
    build: { outDir: 'dist', emptyOutDir: true },
    server: {
      host: '127.0.0.1',
      port: 5176,
      proxy: Object.fromEntries(['/pda', '/auth'].map((p) => [p, { target: gw }])),
    },
  }
})

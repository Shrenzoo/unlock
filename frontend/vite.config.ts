import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  if (process.env.VERCEL || process.env.CF_PAGES || mode === 'public') {
    let api: URL
    try { api = new URL(env.VITE_UNLOCK_API) } catch {
      throw new Error('Set VITE_UNLOCK_API to the HTTPS Modal read-only API origin before publishing.')
    }
    if (api.protocol !== 'https:' || !api.hostname.endsWith('.modal.run') || api.username || api.password || api.search || api.hash || api.pathname !== '/') {
      throw new Error('VITE_UNLOCK_API must be a Modal HTTPS origin without credentials, path, query or fragment.')
    }
    if (env.VITE_UNLOCK_JUDGE_API) {
      const judge = new URL(env.VITE_UNLOCK_JUDGE_API)
      if (judge.protocol !== 'https:' || !judge.hostname.endsWith('.modal.run') || judge.username || judge.password || judge.pathname !== '/' || judge.search || judge.hash) throw new Error('Judge API must be a credential-free HTTPS Modal origin.')
    }
    if (env.VITE_UNLOCK_MODE === 'fixture') {
      throw new Error('Public builds must use the real read-only engineering API, not illustrative fixture mode.')
    }
  }
  return {
    plugins: [react()],
    resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
    server: { port: 5183 },
    build: {
      // three.js and R3F are inherently large; they sit in their own long-cached vendor chunks
      chunkSizeWarningLimit: 760,
      rollupOptions: {
        output: {
          manualChunks: {
            three: ['three'],
            r3f: ['@react-three/fiber', '@react-three/drei'],
            motion: ['gsap', 'lenis'],
          },
        },
      },
    },
  }
})

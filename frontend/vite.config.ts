import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  if (process.env.VERCEL && (!env.VITE_UNLOCK_API?.startsWith('https://') || /localhost|127\.0\.0\.1/.test(env.VITE_UNLOCK_API))) {
    throw new Error('Set VITE_UNLOCK_API to the HTTPS Modal read-only API URL before deploying to Vercel.')
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

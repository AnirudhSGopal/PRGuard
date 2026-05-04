import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const proxyTarget = process.env.VITE_API_PROXY_TARGET

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: proxyTarget
      ? {
          '/auth': {
            target: proxyTarget,
            changeOrigin: true,
          },
          '/api': {
            target: proxyTarget,
            changeOrigin: true,
          },
          '/webhook': {
            target: proxyTarget,
            changeOrigin: true,
          },
          '/admin': {
            target: proxyTarget,
            changeOrigin: true,
          },
          '/user': {
            target: proxyTarget,
            changeOrigin: true,
          },
          '/health': {
            target: proxyTarget,
            changeOrigin: true,
          },
        }
      : undefined,
  },
})

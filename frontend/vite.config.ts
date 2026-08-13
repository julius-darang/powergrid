import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev server proxies /api to the local FastAPI backend so the React app
// can call `/api/...` without CORS or absolute URLs. Production builds
// deploy as static assets; the API host is configurable via VITE_API_BASE.
// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: false,
      },
    },
  },
})

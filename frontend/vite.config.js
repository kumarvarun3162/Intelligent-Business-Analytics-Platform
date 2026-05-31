// frontend/vite.config.js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      // In dev, proxy /api calls to the backend so same-origin logic works
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      }
    }
  },
  build: {
  outDir: 'dist',
  emptyOutDir: true,
  chunkSizeWarningLimit: 3500,
},
  optimizeDeps: {
    include: ['plotly.js-dist-min'],
  },
})
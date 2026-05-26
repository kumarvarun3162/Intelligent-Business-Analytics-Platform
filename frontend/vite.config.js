// frontend/vite.config.js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173 },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          plotly: ['plotly.js-dist-min'],
          react:  ['react', 'react-dom'],
        },
      },
    },
    chunkSizeWarningLimit: 3000,
  },
  optimizeDeps: {
    include: ['plotly.js-dist-min'],
  },
})
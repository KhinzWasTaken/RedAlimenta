import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// En desarrollo, Vite reenvía /api al backend FastAPI (puerto 8000).
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})

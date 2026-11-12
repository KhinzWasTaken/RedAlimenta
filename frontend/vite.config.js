import { readFileSync } from 'node:fs'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// En desarrollo, Vite hace de puerta de entrada: reparte cada prefijo de /api al servicio que lo atiende
// según infra/rutas.json (la misma tabla que usará el gateway del Sprint 6).
const { servicios } = JSON.parse(readFileSync(new URL('../infra/rutas.json', import.meta.url), 'utf-8'))
const proxy = Object.fromEntries(
  Object.values(servicios)
    .flatMap((s) => s.prefijos.map((p) => [p, `http://127.0.0.1:${s.puerto}`]))
    .sort((a, b) => b[0].length - a[0].length),
)

export default defineConfig({
  plugins: [react()],
  server: { host: true, port: 5173, proxy },
  preview: { host: true, port: 4173, proxy },
})

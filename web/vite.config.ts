import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
const webRoot = fileURLToPath(new URL('.', import.meta.url))
const backend = 'http://127.0.0.1:8765'
const devOrigins = new Set(['http://127.0.0.1:5173', 'http://localhost:5173'])
export default defineConfig({
  plugins: [react(), {
    name: 'runtime-license-notices',
    async closeBundle() {
      const notices = await Promise.all(['react','react-dom','scheduler'].map(async name =>
        `${name}\n${await fs.readFile(path.join(webRoot,'node_modules',name,'LICENSE'),'utf8')}`))
      await fs.writeFile(path.join(webRoot,'../fat12lab/static/THIRD_PARTY_NOTICES.txt'),notices.join('\n\n'))
    },
  }],
  build: { outDir: '../fat12lab/static', emptyOutDir: true },
  server: {
    host: '127.0.0.1', port: 5173, strictPort: true,
    proxy: {
      '/api': {
        target: backend, changeOrigin: true,
        configure(proxy) {
          // Only map the two known local development origins. Foreign origins
          // retain their value and are rejected by the Python service.
          proxy.on('proxyReq', (request, incoming) => {
            if (devOrigins.has(String(incoming.headers.origin))) request.setHeader('Origin', backend)
          })
        },
      },
    },
  },
})

import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const root = path.dirname(fileURLToPath(import.meta.url))

function readBackendAddress() {
  const text = fs.readFileSync(path.join(root, 'config.ini'), 'utf8')
  const match = text.match(/^\s*address\s*=\s*(\S+)/m)
  if (!match) {
    throw new Error('frontend/config.ini must set the backend address')
  }
  return match[1]
}

export default defineConfig({
  plugins: [react()],
  define: {
    __BACKEND_ADDRESS__: JSON.stringify(readBackendAddress()),
  },
  server: {
    host: 'localhost',
    port: 17777,
    strictPort: true,
  },
})

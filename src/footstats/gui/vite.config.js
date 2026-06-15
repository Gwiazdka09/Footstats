import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [tailwindcss(), react()],
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/polityka-prywatnosci': 'http://localhost:8000',
      '/regulamin': 'http://localhost:8000',
      '/manifest.json': 'http://localhost:8000',
      '/sw.js': 'http://localhost:8000',
    },
  },
})

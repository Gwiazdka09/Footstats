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
  test: {
    // jsdom, bo testujemy komponenty — bez DOM `render()` nie ma gdzie rysować.
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.js'],
    // Testy NIE mogą bić po sieci ani po produkcji — odpowiednik reguły
    // `tests-no-prod.md` po stronie backendu. `fetch` jest zaślepiony w setupie.
    restoreMocks: true,
    clearMocks: true,
    include: ['src/**/*.test.{js,jsx}'],
  },
})

import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, './resources/js'),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    coverage: {
      provider: 'v8',
      include: ['resources/js/**/*.{ts,vue,js}'],
      exclude: ['resources/js/**/*.spec.*', 'resources/js/**/__tests__/**', 'resources/js/types/**', 'resources/js/**/*.d.ts', 'resources/js/app.ts', 'resources/js/ssr.ts'],
      reporter: ['text', 'html', 'json', 'json-summary'],
      thresholds: { statements: 60, branches: 50, functions: 55, lines: 60 },
    },
    setupFiles: ['./vitest.setup.ts'],
    include: ['resources/js/**/*.spec.ts', 'resources/js/**/*.spec.tsx'],
  },
})


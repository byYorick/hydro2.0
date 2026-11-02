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
      // Baseline includes unimported files too (58.59/49.94/56.35/59.84).
      // Keep global coverage from regressing and stricter guarantees on shared controls.
      thresholds: {
        statements: 58, branches: 49, functions: 56, lines: 59,
        'resources/js/Components/fieldValue.ts': {
          statements: 100, branches: 100, functions: 100, lines: 100,
        },
      },
    },
    setupFiles: ['./vitest.setup.ts'],
    include: ['resources/js/**/*.spec.ts', 'resources/js/**/*.spec.tsx'],
  },
})


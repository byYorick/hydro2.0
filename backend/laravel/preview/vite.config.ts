import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  root: resolve(__dirname),
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, '../resources/js'),
    },
  },
  server: {
    host: '127.0.0.1',
    port: 4179,
    strictPort: true,
  },
})

import type { PlaywrightTestConfig } from '@playwright/test'

const config: PlaywrightTestConfig = {
  webServer: {
    command: 'rm -f public/hot && php artisan e2e:auth-bootstrap --email=agronomist@example.com --role=admin --with-zone >/dev/null 2>&1 || true && php artisan serve --host=127.0.0.1 --port=8000',
    port: 8000,
    reuseExistingServer: false,
    timeout: 60000,
    env: {
      APP_ENV: process.env.PW_APP_ENV ?? 'testing',
      APP_URL: 'http://127.0.0.1:8000',
      VITE_HOT_FILE: '/tmp/laravel-vite-hot-disabled',
      CACHE_DRIVER: process.env.CACHE_DRIVER ?? 'file',
      SESSION_DRIVER: process.env.SESSION_DRIVER ?? 'file',
      QUEUE_CONNECTION: process.env.QUEUE_CONNECTION ?? 'sync',
    },
  },
  use: {
    baseURL: 'http://127.0.0.1:8000',
    headless: true,
  },
  testDir: 'tests/E2E',
}

export default config

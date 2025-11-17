import type { PlaywrightTestConfig } from '@playwright/test'

const config: PlaywrightTestConfig = {
  webServer: {
    command: 'php artisan serve --host=127.0.0.1 --port=8000',
    port: 8000,
    reuseExistingServer: true,
    timeout: 30000,
  },
  use: {
    baseURL: 'http://127.0.0.1:8000',
    headless: true,
  },
  testDir: 'tests/e2e',
}

export default config


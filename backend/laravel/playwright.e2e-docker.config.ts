import type { PlaywrightTestConfig } from '@playwright/test'

/**
 * Playwright для tests/E2E против уже поднятого docker-compose.e2e (порт 8081).
 * Не стартует php artisan serve локально.
 */
const config: PlaywrightTestConfig = {
  testDir: 'tests/E2E',
  timeout: 90_000,
  expect: { timeout: 20_000 },
  retries: 1,
  workers: 1,
  use: {
    baseURL: process.env.LARAVEL_URL || 'http://localhost:8081',
    headless: process.env.HEADLESS !== 'false',
  },
}

export default config

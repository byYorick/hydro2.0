import { defineConfig, devices } from '@playwright/test';

const envWorkers = process.env.PW_WORKERS ? Number(process.env.PW_WORKERS) : undefined;
// По умолчанию 1 worker: E2E Laravel + testZone fixtures не выдерживают параллельную нагрузку.
const workerCount = Number.isFinite(envWorkers) && envWorkers && envWorkers > 0 ? envWorkers : 1;
const reportDir = process.env.PW_REPORT_DIR || '/tmp/hydro-pw-reports';

export default defineConfig({
  testDir: './specs',
  timeout: 90_000,
  expect: { timeout: 20_000 },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 1,
  workers: process.env.CI ? 1 : workerCount,
  reporter: [
    ['html', { outputFolder: `${reportDir}/html` }],
    ['junit', { outputFile: `${reportDir}/junit.xml` }],
  ],
  use: {
    baseURL: process.env.LARAVEL_URL || 'http://localhost:8081',
    trace: 'on-first-retry',
    video: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'setup',
      testDir: './playwright/.auth',
      testMatch: /setup\.ts/,
      use: {
        baseURL: process.env.LARAVEL_URL || 'http://localhost:8081',
      },
    },
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        headless: process.env.HEADLESS !== 'false',
        storageState: process.env.CI ? './playwright/.auth/storageState.json' : './playwright/.auth/user.json',
      },
      dependencies: ['setup'],
    },
    {
      name: 'smoke',
      testMatch: '**/00-smoke.spec.ts',
      use: {
        ...devices['Desktop Chrome'],
        headless: process.env.HEADLESS !== 'false',
        // Smoke тесты не требуют авторизации - проверяют отсутствие 500 ошибок
      },
      // Нет dependencies - smoke тесты работают без setup
    },
  ],
  webServer: process.env.SKIP_WEBSERVER ? undefined : {
    command: 'echo "Assuming Laravel is running via docker-compose.e2e.yml"',
    url: process.env.LARAVEL_URL || 'http://localhost:8081',
    reuseExistingServer: !process.env.CI,
    timeout: 120000,
  },
});

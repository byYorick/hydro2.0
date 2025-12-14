import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './specs',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [
    ['html', { outputFolder: '../reports/playwright' }],
    ['junit', { outputFile: '../reports/playwright/junit.xml' }],
  ],
  use: {
    baseURL: process.env.LARAVEL_URL || 'http://localhost:8081',
    trace: 'on-first-retry',
    video: 'retain-on-failure',
    screenshot: 'only-on-failure',
    storageState: './playwright/.auth/user.json',
  },
  projects: [
    {
      name: 'setup',
      testMatch: /.*\.setup\.ts/,
    },
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], headless: false },
      dependencies: ['setup'],
    },
  ],
  webServer: {
    command: 'echo "Assuming Laravel is running via docker-compose.e2e.yml"',
    url: process.env.LARAVEL_URL || 'http://localhost:8081',
    reuseExistingServer: !process.env.CI,
    timeout: 120000,
  },
});


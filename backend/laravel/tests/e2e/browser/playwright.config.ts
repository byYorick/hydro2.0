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
  ],
  webServer: process.env.SKIP_WEBSERVER ? undefined : {
    command: 'echo "Assuming Laravel is running via docker-compose.e2e.yml"',
    url: process.env.LARAVEL_URL || 'http://localhost:8081',
    reuseExistingServer: !process.env.CI,
    timeout: 120000,
  },
});


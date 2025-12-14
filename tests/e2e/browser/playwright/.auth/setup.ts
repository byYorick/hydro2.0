import { test as setup, expect } from '@playwright/test';

const authFile = './playwright/.auth/user.json';

setup('authenticate', async ({ page }) => {
  const email = process.env.E2E_AUTH_EMAIL || 'admin@hydro.local';
  const password = process.env.E2E_AUTH_PASSWORD || 'password';
  const baseURL = process.env.LARAVEL_URL || 'http://localhost:8081';

  await page.goto(`${baseURL}/login`);

  // Заполняем форму логина
  await page.fill('[data-testid="login-email"]', email);
  await page.fill('[data-testid="login-password"]', password);
  await page.click('[data-testid="login-submit"]');

  // Ждем редиректа на Dashboard
  await page.waitForURL(`${baseURL}/dashboard`, { timeout: 10000 });

  // Проверяем, что мы авторизованы (проверяем наличие элементов Dashboard)
  await expect(page.locator('[data-testid="dashboard-zones-count"]').or(page.locator('h1'))).toBeVisible();

  // Сохраняем состояние авторизации
  await page.context().storageState({ path: authFile });
});


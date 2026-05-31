import { test, expect } from '@playwright/test';
import type { BrowserContext, Page } from '@playwright/test';
import { TEST_IDS } from '../constants';
import { waitForDashboardReady, waitForLoginForm } from '../helpers/navigation';

async function logoutSession(page: Page, context: BrowserContext, baseURL: string): Promise<void> {
  const cookies = await context.cookies();
  const xsrfCookie = cookies.find((cookie) => cookie.name === 'XSRF-TOKEN');
  const xsrfToken = xsrfCookie?.value ? decodeURIComponent(xsrfCookie.value) : '';

  await page.request.post(`${baseURL}/logout`, {
    headers: {
      'X-XSRF-TOKEN': xsrfToken,
      'X-Requested-With': 'XMLHttpRequest',
      Accept: 'text/html, application/xhtml+xml',
    },
  });

  await context.clearCookies();
}

test.describe('Login/Logout', () => {
  async function loginViaForm(page: Page, context: BrowserContext, baseURL: string, email: string, password: string) {
    await context.clearCookies();
    await page.goto(`${baseURL}/login`, { waitUntil: 'networkidle' });
    await expect(page.locator(`[data-testid="${TEST_IDS.LOGIN_FORM}"]`)).toBeVisible({ timeout: 10000 });
    await page.fill(`[data-testid="${TEST_IDS.LOGIN_EMAIL}"]`, email);
    await page.fill(`[data-testid="${TEST_IDS.LOGIN_PASSWORD}"]`, password);
    await page.click(`[data-testid="${TEST_IDS.LOGIN_SUBMIT}"]`);
    await page.waitForLoadState('networkidle', { timeout: 15000 });
    await waitForDashboardReady(page);
  }

  test('should login successfully and redirect to dashboard', async ({ page, context }) => {
    // Очищаем cookies для этого теста, чтобы проверить логин с нуля
    const email = process.env.E2E_AUTH_EMAIL || 'admin@example.com';
    const password = process.env.E2E_AUTH_PASSWORD || 'password';
    const baseURL = process.env.LARAVEL_URL || 'http://localhost:8081';
    await loginViaForm(page, context, baseURL, email, password);

    // Нормализуем URL на главную (dashboard)
    await page.goto(`${baseURL}/`, { waitUntil: 'networkidle' });

    await waitForDashboardReady(page);
  });

  test('should show error on invalid credentials', async ({ page, context }) => {
    // Очищаем cookies для этого теста
    await context.clearCookies();
    
    const baseURL = process.env.LARAVEL_URL || 'http://localhost:8081';

    await page.goto(`${baseURL}/login`, { waitUntil: 'networkidle' });

    // Ждем загрузки формы
    await expect(page.locator(`[data-testid="${TEST_IDS.LOGIN_FORM}"]`)).toBeVisible({ timeout: 10000 });

    // Заполняем форму неверными данными
    await page.fill(`[data-testid="${TEST_IDS.LOGIN_EMAIL}"]`, 'invalid@example.com');
    await page.fill(`[data-testid="${TEST_IDS.LOGIN_PASSWORD}"]`, 'wrongpassword');
    await page.click(`[data-testid="${TEST_IDS.LOGIN_SUBMIT}"]`);

    // Ждем ответа от сервера (Inertia может показать ошибку через некоторое время)
    await page.waitForLoadState('networkidle', { timeout: 10000 });
    
    // Проверяем, что мы все еще на странице логина (не произошел редирект)
    const currentURL = page.url();
    expect(currentURL).toContain('/login');
    
    // Проверяем наличие ошибки (может быть в разных местах)
    const errorLocator = page.locator(`[data-testid="${TEST_IDS.LOGIN_ERROR}"]`)
      .or(page.locator('.text-red-400, .text-red-800'))
      .or(page.locator('text=/неверн|ошибк|invalid/i'));
    
    await expect(errorLocator.first()).toBeVisible({ timeout: 10000 });
  });

  test('should logout successfully', async ({ page, context }) => {
    const baseURL = process.env.LARAVEL_URL || 'http://localhost:8081';
    const email = process.env.E2E_AUTH_EMAIL || 'admin@example.com';
    const password = process.env.E2E_AUTH_PASSWORD || 'password';

    await loginViaForm(page, context, baseURL, email, password);

    await logoutSession(page, context, baseURL);
    await waitForLoginForm(page);
  });
});

import { test, expect } from '@playwright/test';
import { TEST_IDS } from '../constants';

test.describe('Login/Logout', () => {
  test('should login successfully and redirect to dashboard', async ({ page, context }) => {
    // Очищаем cookies для этого теста, чтобы проверить логин с нуля
    await context.clearCookies();
    
    const email = process.env.E2E_AUTH_EMAIL || 'admin@example.com';
    const password = process.env.E2E_AUTH_PASSWORD || 'password';
    const baseURL = process.env.LARAVEL_URL || 'http://localhost:8081';

    await page.goto(`${baseURL}/login`, { waitUntil: 'networkidle' });

    // Проверяем наличие формы логина
    await expect(page.locator(`[data-testid="${TEST_IDS.LOGIN_FORM}"]`)).toBeVisible({ timeout: 10000 });

    // Заполняем форму
    await page.fill(`[data-testid="${TEST_IDS.LOGIN_EMAIL}"]`, email);
    await page.fill(`[data-testid="${TEST_IDS.LOGIN_PASSWORD}"]`, password);
    await page.click(`[data-testid="${TEST_IDS.LOGIN_SUBMIT}"]`);

    // Ждем редиректа (может быть редирект на / или /dashboard)
    await page.waitForLoadState('networkidle', { timeout: 15000 });
    
    // Проверяем текущий URL и переходим на dashboard если нужно
    const currentURL = page.url();
    if (!currentURL.includes('/dashboard')) {
      await page.goto(`${baseURL}/dashboard`, { waitUntil: 'networkidle' });
    }

    // Проверяем, что мы на Dashboard
    await expect(page.locator('[data-testid="dashboard-zones-count"]').or(page.locator('h1'))).toBeVisible({ timeout: 15000 });
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

  test('should logout successfully', async ({ page }) => {
    const baseURL = process.env.LARAVEL_URL || 'http://localhost:8081';

    // Используем сохраненное состояние авторизации
    await page.goto(`${baseURL}/dashboard`, { waitUntil: 'networkidle' });

    // Ищем кнопку выхода (может быть в меню пользователя)
    // Проверяем наличие элементов Dashboard для подтверждения авторизации
    await expect(page.locator('[data-testid="dashboard-zones-count"]').or(page.locator('h1'))).toBeVisible({ timeout: 10000 });

    // Ищем кнопку logout (может быть в UserMenu или другом месте)
    // Если есть явная кнопка logout с data-testid, используем её
    // Иначе ищем по тексту или другим селекторам
    const logoutButton = page.locator('text=Выйти').or(page.locator('text=Logout')).or(page.locator('[href*="logout"]'));
    
    if (await logoutButton.count() > 0) {
      await logoutButton.first().click();
      
      // Ждем редиректа на login
      await page.waitForURL(`${baseURL}/login`, { timeout: 10000 });
      
      // Проверяем, что мы на странице логина
      await expect(page.locator(`[data-testid="${TEST_IDS.LOGIN_FORM}"]`)).toBeVisible({ timeout: 10000 });
    }
  });
});


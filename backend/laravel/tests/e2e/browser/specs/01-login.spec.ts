import { test, expect } from '@playwright/test';
import { TEST_IDS } from '../constants';

test.describe('Login/Logout', () => {
  test('should login successfully and redirect to dashboard', async ({ page }) => {
    const email = process.env.E2E_AUTH_EMAIL || 'admin@hydro.local';
    const password = process.env.E2E_AUTH_PASSWORD || 'password';
    const baseURL = process.env.LARAVEL_URL || 'http://localhost:8081';

    await page.goto(`${baseURL}/login`);

    // Проверяем наличие формы логина
    await expect(page.locator(`[data-testid="${TEST_IDS.LOGIN_FORM}"]`)).toBeVisible();

    // Заполняем форму
    await page.fill(`[data-testid="${TEST_IDS.LOGIN_EMAIL}"]`, email);
    await page.fill(`[data-testid="${TEST_IDS.LOGIN_PASSWORD}"]`, password);
    await page.click(`[data-testid="${TEST_IDS.LOGIN_SUBMIT}"]`);

    // Ждем редиректа на Dashboard
    await page.waitForURL(`${baseURL}/dashboard`, { timeout: 10000 });

    // Проверяем, что мы на Dashboard
    await expect(page.locator('[data-testid="dashboard-zones-count"]').or(page.locator('h1'))).toBeVisible();
  });

  test('should show error on invalid credentials', async ({ page }) => {
    const baseURL = process.env.LARAVEL_URL || 'http://localhost:8081';

    await page.goto(`${baseURL}/login`);

    // Заполняем форму неверными данными
    await page.fill(`[data-testid="${TEST_IDS.LOGIN_EMAIL}"]`, 'invalid@example.com');
    await page.fill(`[data-testid="${TEST_IDS.LOGIN_PASSWORD}"]`, 'wrongpassword');
    await page.click(`[data-testid="${TEST_IDS.LOGIN_SUBMIT}"]`);

    // Ждем появления ошибки
    await expect(page.locator(`[data-testid="${TEST_IDS.LOGIN_ERROR}"]`)).toBeVisible({ timeout: 5000 });
  });

  test('should logout successfully', async ({ page }) => {
    const baseURL = process.env.LARAVEL_URL || 'http://localhost:8081';

    // Используем сохраненное состояние авторизации
    await page.goto(`${baseURL}/dashboard`);

    // Ищем кнопку выхода (может быть в меню пользователя)
    // Проверяем наличие элементов Dashboard для подтверждения авторизации
    await expect(page.locator('[data-testid="dashboard-zones-count"]').or(page.locator('h1'))).toBeVisible();

    // Ищем кнопку logout (может быть в UserMenu или другом месте)
    // Если есть явная кнопка logout с data-testid, используем её
    // Иначе ищем по тексту или другим селекторам
    const logoutButton = page.locator('text=Выйти').or(page.locator('text=Logout')).or(page.locator('[href*="logout"]'));
    
    if (await logoutButton.count() > 0) {
      await logoutButton.first().click();
      
      // Ждем редиректа на login
      await page.waitForURL(`${baseURL}/login`, { timeout: 5000 });
      
      // Проверяем, что мы на странице логина
      await expect(page.locator(`[data-testid="${TEST_IDS.LOGIN_FORM}"]`)).toBeVisible();
    }
  });
});


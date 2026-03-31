import { test as setup, expect } from '@playwright/test';

const authFile = './playwright/.auth/user.json';

setup('authenticate', async ({ page }) => {
  const email = process.env.E2E_AUTH_EMAIL || 'agronomist@example.com';
  const password = process.env.E2E_AUTH_PASSWORD || 'password';
  const baseURL = process.env.LARAVEL_URL || 'http://localhost:8081';

  // Переходим на страницу логина
  await page.goto(`${baseURL}/login`, { waitUntil: 'domcontentloaded' });
  
  // Ждем загрузки JavaScript и формы (Inertia.js может загружаться асинхронно)
  await page.waitForLoadState('networkidle', { timeout: 30000 });
  await page.waitForTimeout(2000); // Дополнительная задержка для Vue компонентов
  
  // Ждем загрузки формы (используем более гибкий селектор)
  await page.waitForSelector('[data-testid="login-form"], form[action*="login"], input[type="email"][name="email"]', { timeout: 30000 });
  await page.waitForSelector('[data-testid="login-email"], input[type="email"][name="email"]', { timeout: 10000 });
  await page.waitForSelector('[data-testid="login-password"], input[type="password"][name="password"]', { timeout: 10000 });

  // Заполняем форму
  await page.fill('[data-testid="login-email"]', email);
  await page.fill('[data-testid="login-password"]', password);
  
  // Ждем немного для инициализации формы
  await page.waitForTimeout(500);
  
  // Отправляем форму
  await page.click('[data-testid="login-submit"]');
  
  // Ждем появления признаков авторизации (URL может остаться /login из-за preserveUrl)
  const dashboardIndicator = page.locator('[data-testid="dashboard-zones-count"]')
    .or(page.locator('nav a[href="/zones"]'));
  let authenticated = false;

  for (let i = 0; i < 20; i++) {
    await page.waitForTimeout(1000);

    const errorVisible = await page.locator('[data-testid="login-error"]').isVisible().catch(() => false);
    if (errorVisible) {
      const errorText = await page.locator('[data-testid="login-error"]').textContent();
      throw new Error(`Login failed: ${errorText || 'Unknown error'}`);
    }

    const dashboardVisible = await dashboardIndicator.first().isVisible().catch(() => false);
    if (dashboardVisible) {
      authenticated = true;
      break;
    }
  }

  if (!authenticated) {
    const currentURL = page.url();
    throw new Error(`Login did not complete. Current URL: ${currentURL}`);
  }

  // Нормализуем URL на главную (dashboard)
  await page.goto(`${baseURL}/`, { waitUntil: 'domcontentloaded' });

  // Ждем устойчивый post-login индикатор. h1 на dashboard не гарантирован,
  // поэтому опираемся на навигацию и видимые dashboard widgets.
  const readyIndicators = [
    page.locator('[data-testid="dashboard-zones-count"]'),
    page.locator('[data-testid^="zone-card-"]').first(),
    page.locator('nav a[href="/zones"]'),
    page.locator('nav a[href="/alerts"]'),
  ];

  await expect.poll(
    async () => {
      for (const locator of readyIndicators) {
        if (await locator.isVisible().catch(() => false)) {
          return true;
        }
      }

      return false;
    },
    {
      timeout: 20000,
      message: 'Dashboard did not expose any stable authenticated indicator after login',
    },
  ).toBe(true);

  // Сохраняем состояние авторизации
  await page.context().storageState({ path: authFile });
});

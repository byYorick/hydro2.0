import { test as setup, expect } from '@playwright/test';

const authFile = './playwright/.auth/user.json';

setup('authenticate', async ({ page }) => {
  const email = process.env.E2E_AUTH_EMAIL || 'admin@example.com';
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
  
  // Ждем навигации (может быть редирект на / или /dashboard)
  let navigated = false;
  for (let i = 0; i < 15; i++) {
    await page.waitForTimeout(1000);
    const currentURL = page.url();
    
    // Проверяем наличие ошибки
    const errorVisible = await page.locator('[data-testid="login-error"]').isVisible().catch(() => false);
    if (errorVisible) {
      const errorText = await page.locator('[data-testid="login-error"]').textContent();
      throw new Error(`Login failed: ${errorText || 'Unknown error'}`);
    }
    
    // Если мы не на странице логина, значит логин прошел
    if (!currentURL.includes('/login')) {
      navigated = true;
      break;
    }
  }
  
  if (!navigated) {
    const currentURL = page.url();
    throw new Error(`Failed to navigate away from login. Current URL: ${currentURL}`);
  }
  
  // Если мы на главной странице, переходим на dashboard
  const currentURL = page.url();
  if (currentURL === `${baseURL}/` || currentURL === baseURL) {
    await page.goto(`${baseURL}/dashboard`, { waitUntil: 'networkidle' });
  } else if (!currentURL.includes('/dashboard')) {
    // Если мы на другой странице, переходим на dashboard
    await page.goto(`${baseURL}/dashboard`, { waitUntil: 'networkidle' });
  }
  
  // Ждем загрузки dashboard
  await page.waitForLoadState('networkidle', { timeout: 20000 });
  
  // Проверяем, что мы авторизованы - ищем заголовок или любой элемент dashboard
  await page.waitForSelector('h1, [data-testid="dashboard-zones-count"]', { timeout: 15000 });

  // Сохраняем состояние авторизации
  await page.context().storageState({ path: authFile });
});


import { test, expect } from '../fixtures/test-data';

test.describe('UI Smoke Tests - No 500 Errors', () => {
  test('should open Dashboard page without 500 errors', async ({ page }) => {
    // Переходим на Dashboard
    const response = await page.goto('/dashboard', { waitUntil: 'networkidle' });

    // Проверяем, что нет 500 ошибки
    expect(response?.status()).not.toBe(500);
    expect(response?.status()).not.toBe(502);
    expect(response?.status()).not.toBe(503);
    expect(response?.status()).not.toBe(504);

    // Проверяем, что страница загружается (есть какой-то контент)
    await page.waitForLoadState('networkidle', { timeout: 20000 });

    // Проверяем наличие основного контента (не обязательно dashboard элементов)
    const body = page.locator('body');
    await expect(body).toBeVisible();
  });

  test('should open Greenhouse page without 500 errors', async ({ page }) => {
    // Переходим на Greenhouse (может быть greenhouse или greenhouses)
    let response;
    try {
      response = await page.goto('/greenhouse', { waitUntil: 'networkidle' });
    } catch {
      // Если /greenhouse не существует, пробуем /greenhouses
      response = await page.goto('/greenhouses', { waitUntil: 'networkidle' });
    }

    // Проверяем, что нет 500 ошибки
    expect(response?.status()).not.toBe(500);
    expect(response?.status()).not.toBe(502);
    expect(response?.status()).not.toBe(503);
    expect(response?.status()).not.toBe(504);

    // Проверяем, что страница загружается
    await page.waitForLoadState('networkidle', { timeout: 20000 });
    const body = page.locator('body');
    await expect(body).toBeVisible();
  });

  test('should open Zone page without 500 errors', async ({ page }) => {
    // Переходим на Zone (может быть zones)
    let response;
    try {
      response = await page.goto('/zone', { waitUntil: 'networkidle' });
    } catch {
      // Если /zone не существует, пробуем /zones
      response = await page.goto('/zones', { waitUntil: 'networkidle' });
    }

    // Проверяем, что нет 500 ошибки
    expect(response?.status()).not.toBe(500);
    expect(response?.status()).not.toBe(502);
    expect(response?.status()).not.toBe(503);
    expect(response?.status()).not.toBe(504);

    // Проверяем, что страница загружается
    await page.waitForLoadState('networkidle', { timeout: 20000 });
    const body = page.locator('body');
    await expect(body).toBeVisible();
  });

  test('should open Cycle Center page without 500 errors', async ({ page }) => {
    // Переходим на Cycle Center (может быть cycles, grow-cycles, cycle-center)
    let response;
    try {
      response = await page.goto('/cycle-center', { waitUntil: 'networkidle' });
    } catch {
      try {
        response = await page.goto('/cycles', { waitUntil: 'networkidle' });
      } catch {
        response = await page.goto('/grow-cycles', { waitUntil: 'networkidle' });
      }
    }

    // Проверяем, что нет 500 ошибки
    expect(response?.status()).not.toBe(500);
    expect(response?.status()).not.toBe(502);
    expect(response?.status()).not.toBe(503);
    expect(response?.status()).not.toBe(504);

    // Проверяем, что страница загружается
    await page.waitForLoadState('networkidle', { timeout: 20000 });
    const body = page.locator('body');
    await expect(body).toBeVisible();
  });

  test('should handle 404 gracefully for non-existent pages', async ({ page }) => {
    // Проверяем, что 404 обрабатывается корректно (не 500)
    const response = await page.goto('/non-existent-page-12345', { waitUntil: 'networkidle' });

    // 404 допустимо, но не 500
    expect(response?.status()).not.toBe(500);
    expect(response?.status()).not.toBe(502);
    expect(response?.status()).not.toBe(503);
    expect(response?.status()).not.toBe(504);
  });
});

test.describe('API Smoke Tests - No 500 Errors', () => {
  test('should call effective-targets batch API without 500 errors', async ({ request }) => {
    // Проверяем API endpoint для effective targets batch
    const response = await request.post('/api/internal/effective-targets/batch', {
      data: {
        zone_ids: [1, 2, 3] // Тестовые ID, которые могут не существовать
      }
    });

    // Проверяем, что нет 500 ошибки (может быть 401, 422, но не 500)
    expect(response.status()).not.toBe(500);
    expect(response.status()).not.toBe(502);
    expect(response.status()).not.toBe(503);
    expect(response.status()).not.toBe(504);
  });

  test('should call zones API without 500 errors', async ({ request }) => {
    // Проверяем API endpoint для зон
    const response = await request.get('/zones');

    // Проверяем, что нет 500 ошибки
    expect(response.status()).not.toBe(500);
    expect(response.status()).not.toBe(502);
    expect(response.status()).not.toBe(503);
    expect(response.status()).not.toBe(504);
  });

  test('should call greenhouses API without 500 errors', async ({ request }) => {
    // Проверяем API endpoint для теплиц
    const response = await request.get('/greenhouses');

    // Проверяем, что нет 500 ошибки
    expect(response.status()).not.toBe(500);
    expect(response.status()).not.toBe(502);
    expect(response.status()).not.toBe(503);
    expect(response.status()).not.toBe(504);
  });

  test('should call cycle-center API without 500 errors', async ({ request }) => {
    // Проверяем API endpoint для cycle center
    const response = await request.get('/cycle-center');

    // Проверяем, что нет 500 ошибки
    expect(response.status()).not.toBe(500);
    expect(response.status()).not.toBe(502);
    expect(response.status()).not.toBe(503);
    expect(response.status()).not.toBe(504);
  });

  test('should call zone detail API without 500 errors', async ({ request }) => {
    // Проверяем API endpoint для детальной информации о зоне
    const response = await request.get('/zones/1'); // Тестовый ID

    // Проверяем, что нет 500 ошибки (может быть 404, но не 500)
    expect(response.status()).not.toBe(500);
    expect(response.status()).not.toBe(502);
    expect(response.status()).not.toBe(503);
    expect(response.status()).not.toBe(504);
  });
});

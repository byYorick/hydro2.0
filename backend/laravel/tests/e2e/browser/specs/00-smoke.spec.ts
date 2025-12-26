import { test, expect } from '../fixtures/test-data';

test.describe('UI Smoke Tests - No 500 Errors', () => {
  test('should open Dashboard page without 500 errors', async ({ page }) => {
    // Добавляем X-Inertia заголовок для правильной обработки Laravel
    await page.setExtraHTTPHeaders({
      'X-Inertia': 'true',
      'X-Inertia-Version': '1',
    });

    // Переходим на Dashboard (требует авторизации, поэтому ожидаем редирект)
    const response = await page.goto('/dashboard', { waitUntil: 'networkidle' });

    // Проверяем, что получаем редирект на login (302) или что нет 500 ошибки
    if (response?.status() === 302) {
      // Редирект на login - это нормально для неавторизованного пользователя
      expect(response.headers()['location']).toContain('/login');
    } else {
      // Если не редирект, проверяем что нет 500 ошибки
      expect(response?.status()).not.toBe(500);
      expect(response?.status()).not.toBe(502);
      expect(response?.status()).not.toBe(503);
      expect(response?.status()).not.toBe(504);
    }

    // Проверяем, что страница загружается (редирект на login или dashboard)
    await page.waitForLoadState('networkidle', { timeout: 20000 });

    // Проверяем наличие основного контента
    const body = page.locator('body');
    await expect(body).toBeVisible();
  });

  test('should open Greenhouse page without 500 errors', async ({ page }) => {
    // Добавляем X-Inertia заголовок для правильной обработки Laravel
    await page.setExtraHTTPHeaders({
      'X-Inertia': 'true',
      'X-Inertia-Version': '1',
    });

    // Переходим на Greenhouse (может быть greenhouse или greenhouses)
    let response;
    try {
      response = await page.goto('/greenhouse', { waitUntil: 'networkidle' });
    } catch {
      // Если /greenhouse не существует, пробуем /greenhouses
      response = await page.goto('/greenhouses', { waitUntil: 'networkidle' });
    }

    // Проверяем, что нет 500 ошибки (302 редирект на login - нормально)
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
    // Добавляем X-Inertia заголовок для правильной обработки Laravel
    await page.setExtraHTTPHeaders({
      'X-Inertia': 'true',
      'X-Inertia-Version': '1',
    });

    // Переходим на Zone (может быть zones)
    let response;
    try {
      response = await page.goto('/zone', { waitUntil: 'networkidle' });
    } catch {
      // Если /zone не существует, пробуем /zones
      response = await page.goto('/zones', { waitUntil: 'networkidle' });
    }

    // Проверяем, что нет 500 ошибки (302 редирект на login - нормально)
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
    // Добавляем X-Inertia заголовок для правильной обработки Laravel
    await page.setExtraHTTPHeaders({
      'X-Inertia': 'true',
      'X-Inertia-Version': '1',
    });

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

    // Проверяем, что нет 500 ошибки (302 редирект на login - нормально)
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
    // Добавляем X-Inertia заголовок для правильной обработки Laravel
    await page.setExtraHTTPHeaders({
      'X-Inertia': 'true',
      'X-Inertia-Version': '1',
    });

    // Проверяем, что 404 обрабатывается корректно (не 500)
    const response = await page.goto('/non-existent-page-12345', { waitUntil: 'networkidle' });

    // 404 допустимо для несуществующих страниц, но не 500
    // Ожидаем 404 или редирект на login (302)
    if (response?.status() === 302) {
      // Редирект на login - это нормально для неавторизованного пользователя
      expect(response.headers()['location']).toContain('/login');
    } else {
      // Для несуществующих страниц ожидаем 404
      expect(response?.status()).toBe(404);
    }
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

    // Проверяем, что нет 500 ошибки (302 редирект на login - нормально) (может быть 401, 422, но не 500)
    expect(response.status()).not.toBe(500);
    expect(response.status()).not.toBe(502);
    expect(response.status()).not.toBe(503);
    expect(response.status()).not.toBe(504);
  });

  test('should call zones API without 500 errors', async ({ request }) => {
    // Проверяем API endpoint для зон
    const response = await request.get('/zones');

    // Проверяем, что нет 500 ошибки (302 редирект на login - нормально)
    expect(response.status()).not.toBe(500);
    expect(response.status()).not.toBe(502);
    expect(response.status()).not.toBe(503);
    expect(response.status()).not.toBe(504);
  });

  test('should call greenhouses API without 500 errors', async ({ request }) => {
    // Проверяем API endpoint для теплиц
    const response = await request.get('/greenhouses');

    // Проверяем, что нет 500 ошибки (302 редирект на login - нормально)
    expect(response.status()).not.toBe(500);
    expect(response.status()).not.toBe(502);
    expect(response.status()).not.toBe(503);
    expect(response.status()).not.toBe(504);
  });

  test('should call grow-cycles API without 500 errors', async ({ request }) => {
    // Проверяем API endpoint для grow cycles
    const response = await request.get('/api/grow-cycles');

    // Проверяем, что нет 500 ошибки (302 редирект на login - нормально)
    expect(response.status()).not.toBe(500);
    expect(response.status()).not.toBe(502);
    expect(response.status()).not.toBe(503);
    expect(response.status()).not.toBe(504);
  });

  test('should call zone detail API without 500 errors', async ({ request }) => {
    // Проверяем API endpoint для детальной информации о зоне
    const response = await request.get('/zones/1'); // Тестовый ID

    // Проверяем, что нет 500 ошибки (302 редирект на login - нормально) (может быть 404, но не 500)
    expect(response.status()).not.toBe(500);
    expect(response.status()).not.toBe(502);
    expect(response.status()).not.toBe(503);
    expect(response.status()).not.toBe(504);
  });
});

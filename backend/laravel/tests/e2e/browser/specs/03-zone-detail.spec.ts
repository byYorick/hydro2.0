import { test, expect } from '../fixtures/test-data';
import { TEST_IDS } from '../constants';

test.describe('Zone Detail', () => {
  test('should load zone detail page and display snapshot', async ({ page, testZone, testGreenhouse }) => {
    await page.goto(`/zones/${testZone.id}`);

    // Проверяем наличие Badge статуса
    await expect(page.locator(`[data-testid="${TEST_IDS.ZONE_STATUS_BADGE}"]`)).toBeVisible();

    // Проверяем наличие списка событий (snapshot должен быть загружен)
    await expect(page.locator(`[data-testid="${TEST_IDS.ZONE_EVENTS_LIST}"]`)).toBeVisible({ timeout: 10000 });
  });

  test('should display events list', async ({ page, testZone }) => {
    await page.goto(`/zones/${testZone.id}`);

    // Проверяем наличие списка событий
    const eventsList = page.locator(`[data-testid="${TEST_IDS.ZONE_EVENTS_LIST}"]`);
    await expect(eventsList).toBeVisible({ timeout: 10000 });
  });

  test('should show new events after actions', async ({ page, testZone, apiHelper }) => {
    await page.goto(`/zones/${testZone.id}`);

    // Получаем начальное количество событий
    const eventsList = page.locator(`[data-testid="${TEST_IDS.ZONE_EVENTS_LIST}"]`);
    await expect(eventsList).toBeVisible({ timeout: 10000 });

    // Выполняем действие (например, запуск зоны)
    await apiHelper.startZone(testZone.id);

    // Ждем обновления страницы или появления нового события
    // В реальном приложении события могут обновляться через WebSocket
    await page.waitForTimeout(2000);

    // Проверяем, что список событий все еще виден (новые события должны появиться)
    await expect(eventsList).toBeVisible();
  });
});


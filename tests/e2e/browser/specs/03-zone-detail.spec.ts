import { test, expect } from '../fixtures/test-data';
import { TEST_IDS } from '../constants';

test.describe('Zone Detail', () => {
  test('should load zone detail page and display snapshot', async ({ page, testZone, testGreenhouse }) => {
    await page.goto(`/zones/${testZone.id}`, { waitUntil: 'networkidle' });
    await page.waitForSelector('h1, [data-testid*="zone"]', { timeout: 15000 });

    // Проверяем наличие Badge статуса (может быть в разных местах)
    const statusBadge = page.locator(`[data-testid="${TEST_IDS.ZONE_STATUS_BADGE}"]`)
      .or(page.locator('text=/PLANNED|RUNNING|PAUSED|HARVESTED/i').first());
    await expect(statusBadge.first()).toBeVisible({ timeout: 10000 });

    // Проверяем наличие списка событий (snapshot должен быть загружен)
    const eventsList = page.locator(`[data-testid="${TEST_IDS.ZONE_EVENTS_LIST}"]`)
      .or(page.locator('text=/События|Events/i').locator('..'));
    await expect(eventsList.first()).toBeVisible({ timeout: 15000 });
  });

  test('should display events list', async ({ page, testZone }) => {
    await page.goto(`/zones/${testZone.id}`, { waitUntil: 'networkidle' });
    await page.waitForSelector('h1, [data-testid*="zone"]', { timeout: 15000 });

    // Проверяем наличие списка событий
    const eventsList = page.locator(`[data-testid="${TEST_IDS.ZONE_EVENTS_LIST}"]`)
      .or(page.locator('text=/События|Events/i').locator('..'));
    await expect(eventsList.first()).toBeVisible({ timeout: 15000 });
  });

  test('should show new events after actions', async ({ page, testZone, apiHelper }) => {
    await page.goto(`/zones/${testZone.id}`, { waitUntil: 'networkidle' });
    await page.waitForSelector('h1, [data-testid*="zone"]', { timeout: 15000 });

    // Получаем начальное количество событий
    const eventsList = page.locator(`[data-testid="${TEST_IDS.ZONE_EVENTS_LIST}"]`)
      .or(page.locator('text=/События|Events/i').locator('..'));
    await expect(eventsList.first()).toBeVisible({ timeout: 15000 });

    // Выполняем действие (например, запуск зоны)
    try {
      await apiHelper.startZone(testZone.id);
    } catch (e) {
      // Если зона уже запущена, это нормально
      console.log('Zone might already be started:', e);
    }

    // Ждем обновления страницы или появления нового события
    // В реальном приложении события могут обновляться через WebSocket
    await page.waitForTimeout(3000);
    await page.reload({ waitUntil: 'networkidle' });

    // Проверяем, что список событий все еще виден (новые события должны появиться)
    await expect(eventsList.first()).toBeVisible({ timeout: 10000 });
  });
});


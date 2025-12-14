import { test, expect } from '../fixtures/test-data';
import { TEST_IDS } from '../constants';

test.describe('WebSocket Degradation', () => {
  test('should show WS connection indicator', async ({ page }) => {
    await page.goto('/dashboard');

    // Проверяем наличие индикатора WebSocket
    const wsIndicator = page.locator(`[data-testid="${TEST_IDS.WS_STATUS_INDICATOR}"]`);
    await expect(wsIndicator).toBeVisible({ timeout: 10000 });
  });

  test('should show disconnected state when network is offline', async ({ page }) => {
    await page.goto('/dashboard');

    // Проверяем начальное состояние (должно быть connected)
    const wsIndicator = page.locator(`[data-testid="${TEST_IDS.WS_STATUS_INDICATOR}"]`);
    await expect(wsIndicator).toBeVisible({ timeout: 10000 });

    // Отключаем сеть
    await page.context().setOffline(true);

    // Ждем обновления статуса
    await page.waitForTimeout(2000);

    // Проверяем, что статус изменился на disconnected
    const wsDisconnected = page.locator(`[data-testid="${TEST_IDS.WS_STATUS_DISCONNECTED}"]`);
    await expect(wsDisconnected).toBeVisible({ timeout: 10000 });
  });

  test('should reconnect and show connected state when network is restored', async ({ page }) => {
    await page.goto('/dashboard');

    // Отключаем сеть
    await page.context().setOffline(true);
    await page.waitForTimeout(2000);

    // Проверяем disconnected состояние
    const wsDisconnected = page.locator(`[data-testid="${TEST_IDS.WS_STATUS_DISCONNECTED}"]`);
    await expect(wsDisconnected).toBeVisible({ timeout: 10000 });

    // Включаем сеть обратно
    await page.context().setOffline(false);

    // Ждем переподключения
    await page.waitForTimeout(5000);

    // Проверяем, что статус изменился на connected
    const wsConnected = page.locator(`[data-testid="${TEST_IDS.WS_STATUS_CONNECTED}"]`);
    await expect(wsConnected).toBeVisible({ timeout: 15000 });
  });

  test('should show events after reconnection', async ({ page, testZone }) => {
    await page.goto(`/zones/${testZone.id}`);

    // Проверяем наличие списка событий
    const eventsList = page.locator(`[data-testid="${TEST_IDS.ZONE_EVENTS_LIST}"]`);
    await expect(eventsList).toBeVisible({ timeout: 10000 });

    // Отключаем сеть
    await page.context().setOffline(true);
    await page.waitForTimeout(2000);

    // Включаем сеть обратно
    await page.context().setOffline(false);

    // Ждем переподключения и обновления событий
    await page.waitForTimeout(5000);

    // Проверяем, что список событий все еще виден (события должны появиться после reconnect)
    await expect(eventsList).toBeVisible();
  });
});


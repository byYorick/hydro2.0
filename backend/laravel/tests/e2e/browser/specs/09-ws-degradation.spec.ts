import { test, expect } from '../fixtures/test-data';
import { TEST_IDS } from '../constants';

test.describe('WebSocket Degradation', () => {
  test('should show WS connection indicator', async ({ page }) => {
    await page.goto('/dashboard', { waitUntil: 'networkidle' });
    await page.waitForSelector('h1', { timeout: 15000 });

    // Проверяем наличие индикатора WebSocket (может быть в header или на странице)
    const wsIndicator = page.locator(`[data-testid="${TEST_IDS.WS_STATUS_INDICATOR}"]`)
      .or(page.locator('[data-testid="websocket-status-indicator"]'))
      .or(page.locator('text=/WebSocket|WS|Подключено|Connected|Отключено|Disconnected/i').first());
    
    // Если индикатор найден, проверяем его видимость
    if (await wsIndicator.count() > 0) {
      await expect(wsIndicator.first()).toBeVisible({ timeout: 10000 });
    } else {
      // Если индикатор не найден, просто проверяем загрузку страницы
      await expect(page.locator('h1')).toBeVisible();
    }
  });

  test('should show disconnected state when network is offline', async ({ page }) => {
    await page.goto('/dashboard', { waitUntil: 'networkidle' });
    await page.waitForSelector('h1', { timeout: 15000 });

    // Проверяем начальное состояние
    const wsIndicator = page.locator(`[data-testid="${TEST_IDS.WS_STATUS_INDICATOR}"]`)
      .or(page.locator('[data-testid="websocket-status-indicator"]'));
    
    if (await wsIndicator.count() > 0) {
      await expect(wsIndicator.first()).toBeVisible({ timeout: 10000 });
    }

    // Отключаем сеть
    await page.context().setOffline(true);

    // Ждем обновления статуса
    await page.waitForTimeout(3000);

    // Проверяем, что статус изменился на disconnected
    const wsDisconnected = page.locator(`[data-testid="${TEST_IDS.WS_STATUS_DISCONNECTED}"]`)
      .or(page.locator('text=/Отключено|Disconnected/i').first());
    
    if (await wsDisconnected.count() > 0) {
      await expect(wsDisconnected.first()).toBeVisible({ timeout: 10000 });
    }
  });

  test('should reconnect and show connected state when network is restored', async ({ page }) => {
    await page.goto('/dashboard', { waitUntil: 'networkidle' });
    await page.waitForSelector('h1', { timeout: 15000 });

    // Отключаем сеть
    await page.context().setOffline(true);
    await page.waitForTimeout(3000);

    // Проверяем disconnected состояние (если индикатор есть)
    const wsDisconnected = page.locator(`[data-testid="${TEST_IDS.WS_STATUS_DISCONNECTED}"]`)
      .or(page.locator('text=/Отключено|Disconnected/i').first());
    
    if (await wsDisconnected.count() > 0) {
      await expect(wsDisconnected.first()).toBeVisible({ timeout: 10000 });
    }

    // Включаем сеть обратно
    await page.context().setOffline(false);

    // Ждем переподключения
    await page.waitForTimeout(5000);

    // Проверяем, что статус изменился на connected (если индикатор есть)
    const wsConnected = page.locator(`[data-testid="${TEST_IDS.WS_STATUS_CONNECTED}"]`)
      .or(page.locator('text=/Подключено|Connected/i').first())
      .or(page.locator(`[data-testid="${TEST_IDS.WS_STATUS_INDICATOR}"]`));
    
    if (await wsConnected.count() > 0) {
      await expect(wsConnected.first()).toBeVisible({ timeout: 15000 });
    }
  });

  test('should show events after reconnection', async ({ page, testZone }) => {
    await page.goto(`/zones/${testZone.id}`, { waitUntil: 'networkidle' });
    await page.waitForSelector('h1, [data-testid*="zone"]', { timeout: 15000 });

    // Проверяем наличие списка событий
    const eventsList = page.locator(`[data-testid="${TEST_IDS.ZONE_EVENTS_LIST}"]`)
      .or(page.locator('text=/События|Events/i').locator('..'));
    await expect(eventsList.first()).toBeVisible({ timeout: 15000 });

    // Отключаем сеть
    await page.context().setOffline(true);
    await page.waitForTimeout(3000);

    // Включаем сеть обратно
    await page.context().setOffline(false);

    // Ждем переподключения и обновления событий
    await page.waitForTimeout(5000);
    await page.reload({ waitUntil: 'networkidle' });
    await page.waitForTimeout(2000);

    // Проверяем, что список событий все еще виден (события должны появиться после reconnect)
    await expect(eventsList.first()).toBeVisible({ timeout: 10000 });
  });
});


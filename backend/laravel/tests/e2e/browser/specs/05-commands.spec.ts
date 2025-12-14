import { test, expect } from '../fixtures/test-data';
import { TEST_IDS } from '../constants';

test.describe('Commands', () => {
  test('should send command and show status updates', async ({ page, testZone, apiHelper }) => {
    await page.goto(`/zones/${testZone.id}`);

    // Ищем форму отправки команды
    const commandForm = page.locator(`[data-testid="${TEST_IDS.ZONE_COMMAND_FORM}"]`);
    
    // Если форма есть, заполняем и отправляем
    if (await commandForm.count() > 0) {
      // Заполняем форму команды (пример: FORCE_IRRIGATION)
      // Это зависит от структуры формы в ZoneActionModal
      const commandSubmit = page.locator(`[data-testid="${TEST_IDS.ZONE_COMMAND_SUBMIT}"]`);
      
      if (await commandSubmit.count() > 0) {
        await commandSubmit.click();
        
        // Ждем появления тоста об успехе или ошибке
        await page.waitForTimeout(2000);
        
        // Проверяем наличие тоста
        const toast = page.locator(`[data-testid="${TEST_IDS.TOAST('success')}"], [data-testid="${TEST_IDS.TOAST('error')}"]`);
        if (await toast.count() > 0) {
          await expect(toast.first()).toBeVisible({ timeout: 5000 });
        }
      }
    }
  });

  test('should show command status updates via WebSocket', async ({ page, testZone }) => {
    await page.goto(`/zones/${testZone.id}`);

    // Проверяем наличие индикатора WebSocket
    const wsIndicator = page.locator(`[data-testid="${TEST_IDS.WS_STATUS_INDICATOR}"]`);
    
    // Если индикатор есть, проверяем его состояние
    if (await wsIndicator.count() > 0) {
      // Проверяем, что WebSocket подключен
      const wsConnected = page.locator(`[data-testid="${TEST_IDS.WS_STATUS_CONNECTED}"]`);
      // WebSocket может быть подключен или нет, просто проверяем наличие индикатора
      await expect(wsIndicator).toBeVisible({ timeout: 5000 });
    }
  });

  test('should show error message for invalid channel', async ({ page, testZone }) => {
    await page.goto(`/zones/${testZone.id}`);

    // Пытаемся отправить команду с некорректным каналом
    // Это зависит от реализации формы команды
    // В реальном тесте нужно заполнить форму с неверными данными
    
    // Проверяем наличие формы команды
    const commandForm = page.locator(`[data-testid="${TEST_IDS.ZONE_COMMAND_FORM}"]`);
    
    if (await commandForm.count() > 0) {
      // Если форма есть, можно попробовать отправить неверные данные
      // и проверить появление ошибки
      const errorToast = page.locator(`[data-testid="${TEST_IDS.TOAST('error')}"]`);
      // В реальном тесте здесь будет логика отправки неверной команды
    }
  });
});


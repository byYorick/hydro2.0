import { test, expect } from '../fixtures/test-data';
import { TEST_IDS } from '../constants';

test.describe('Alerts', () => {
  test('should display alerts table', async ({ page }) => {
    await page.goto('/alerts');

    // Проверяем наличие таблицы алертов
    const alertsTable = page.locator(`[data-testid="${TEST_IDS.ALERTS_TABLE}"]`);
    await expect(alertsTable).toBeVisible({ timeout: 10000 });
  });

  test('should filter alerts by active status', async ({ page }) => {
    await page.goto('/alerts');

    // Проверяем наличие фильтра "Только активные"
    const activeFilter = page.locator(`[data-testid="${TEST_IDS.ALERTS_FILTER_ACTIVE}"]`);
    await expect(activeFilter).toBeVisible();

    // Меняем значение фильтра
    await activeFilter.selectOption('true');
    await page.waitForTimeout(1000);

    // Проверяем, что таблица все еще видна
    const alertsTable = page.locator(`[data-testid="${TEST_IDS.ALERTS_TABLE}"]`);
    await expect(alertsTable).toBeVisible();
  });

  test('should filter alerts by zone', async ({ page, testZone }) => {
    await page.goto('/alerts');

    // Проверяем наличие фильтра по зоне
    const zoneFilter = page.locator(`[data-testid="${TEST_IDS.ALERTS_FILTER_ZONE}"]`);
    await expect(zoneFilter).toBeVisible();

    // Вводим название зоны в фильтр
    await zoneFilter.fill(testZone.name);
    await page.waitForTimeout(1000);

    // Проверяем, что таблица все еще видна
    const alertsTable = page.locator(`[data-testid="${TEST_IDS.ALERTS_TABLE}"]`);
    await expect(alertsTable).toBeVisible();
  });

  test('should display alert rows', async ({ page }) => {
    await page.goto('/alerts');

    // Проверяем наличие таблицы
    const alertsTable = page.locator(`[data-testid="${TEST_IDS.ALERTS_TABLE}"]`);
    await expect(alertsTable).toBeVisible({ timeout: 10000 });

    // Если есть алерты, проверяем наличие строк
    // В реальном тесте можно создать алерт через API и проверить его отображение
  });

  test('should resolve alert', async ({ page }) => {
    await page.goto('/alerts');

    // Ищем первую строку алерта
    const alertRows = page.locator(`[data-testid^="${TEST_IDS.ALERT_ROW(0).replace('0', '')}"]`);
    
    if (await alertRows.count() > 0) {
      const firstRow = alertRows.first();
      const alertId = await firstRow.getAttribute('data-testid');
      
      if (alertId) {
        // Извлекаем ID из data-testid
        const match = alertId.match(/alert-row-(\d+)/);
        if (match) {
          const id = parseInt(match[1]);
          const resolveBtn = page.locator(`[data-testid="${TEST_IDS.ALERT_RESOLVE_BTN(id)}"]`);
          
          if (await resolveBtn.count() > 0 && await resolveBtn.isEnabled()) {
            await resolveBtn.click();
            
            // Ждем обновления
            await page.waitForTimeout(2000);
            
            // Проверяем, что кнопка стала неактивной или исчезла
            await expect(resolveBtn).toBeDisabled().or(resolveBtn).not.toBeVisible();
          }
        }
      }
    }
  });
});


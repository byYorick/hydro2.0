import { test, expect } from '../fixtures/test-data';
import { TEST_IDS } from '../constants';

test.describe('Dashboard Overview', () => {
  test('should display zones count card', async ({ page, testZone }) => {
    await page.goto('/dashboard');

    // Проверяем наличие карточки количества зон
    await expect(page.locator(`[data-testid="${TEST_IDS.DASHBOARD_ZONES_COUNT}"]`)).toBeVisible();
  });

  test('should display zone cards with statuses', async ({ page, testZone, apiHelper }) => {
    // Создаем зону с разными статусами для проверки
    const greenhouse = await apiHelper.createTestGreenhouse();
    const zone1 = await apiHelper.createTestZone(greenhouse.id, { status: 'PLANNED' });
    const zone2 = await apiHelper.createTestZone(greenhouse.id, { status: 'RUNNING' });
    const zone3 = await apiHelper.createTestZone(greenhouse.id, { status: 'PAUSED' });

    try {
      await page.goto('/dashboard');

      // Проверяем наличие карточек зон
      await expect(page.locator(`[data-testid="${TEST_IDS.ZONE_CARD(zone1.id)}"]`)).toBeVisible({ timeout: 10000 });
      await expect(page.locator(`[data-testid="${TEST_IDS.ZONE_CARD(zone2.id)}"]`)).toBeVisible();
      await expect(page.locator(`[data-testid="${TEST_IDS.ZONE_CARD(zone3.id)}"]`)).toBeVisible();

      // Проверяем статусы на карточках
      await expect(page.locator(`[data-testid="${TEST_IDS.ZONE_CARD(zone1.id)}"] [data-testid="${TEST_IDS.ZONE_CARD_STATUS}"]`)).toBeVisible();
      await expect(page.locator(`[data-testid="${TEST_IDS.ZONE_CARD(zone2.id)}"] [data-testid="${TEST_IDS.ZONE_CARD_STATUS}"]`)).toBeVisible();
      await expect(page.locator(`[data-testid="${TEST_IDS.ZONE_CARD(zone3.id)}"] [data-testid="${TEST_IDS.ZONE_CARD_STATUS}"]`)).toBeVisible();
    } finally {
      // Очистка
      await apiHelper.cleanupTestData({
        zones: [zone1.id, zone2.id, zone3.id],
        greenhouses: [greenhouse.id],
      });
    }
  });

  test('should display alerts count', async ({ page }) => {
    await page.goto('/dashboard');

    // Проверяем наличие карточки алертов
    await expect(page.locator(`[data-testid="${TEST_IDS.DASHBOARD_ALERTS_COUNT}"]`)).toBeVisible();
  });

  test('should display events panel', async ({ page }) => {
    await page.goto('/dashboard');

    // Проверяем наличие панели событий
    await expect(page.locator(`[data-testid="${TEST_IDS.DASHBOARD_EVENTS_PANEL}"]`)).toBeVisible();
  });

  test('should filter events by kind', async ({ page }) => {
    await page.goto('/dashboard');

    // Проверяем наличие фильтров событий
    await expect(page.locator(`[data-testid="${TEST_IDS.DASHBOARD_EVENT_FILTER('ALL')}"]`)).toBeVisible();
    await expect(page.locator(`[data-testid="${TEST_IDS.DASHBOARD_EVENT_FILTER('ALERT')}"]`)).toBeVisible();
    await expect(page.locator(`[data-testid="${TEST_IDS.DASHBOARD_EVENT_FILTER('WARNING')}"]`)).toBeVisible();
    await expect(page.locator(`[data-testid="${TEST_IDS.DASHBOARD_EVENT_FILTER('INFO')}"]`)).toBeVisible();

    // Кликаем на фильтр ALERT
    await page.click(`[data-testid="${TEST_IDS.DASHBOARD_EVENT_FILTER('ALERT')}"]`);
  });

  test('should navigate to zone detail on zone card click', async ({ page, testZone, testGreenhouse }) => {
    await page.goto('/dashboard');

    // Ждем появления карточки зоны
    const zoneCard = page.locator(`[data-testid="${TEST_IDS.ZONE_CARD(testZone.id)}"]`);
    await expect(zoneCard).toBeVisible({ timeout: 10000 });

    // Кликаем на ссылку "Подробнее"
    const zoneLink = zoneCard.locator(`[data-testid="${TEST_IDS.ZONE_CARD_LINK}"]`);
    await zoneLink.click();

    // Проверяем редирект на детальную страницу зоны
    await page.waitForURL(`/zones/${testZone.id}`, { timeout: 5000 });
    await expect(page.locator(`[data-testid="${TEST_IDS.ZONE_STATUS_BADGE}"]`)).toBeVisible();
  });
});


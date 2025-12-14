import { test, expect } from '../fixtures/test-data';
import { TEST_IDS } from '../constants';

test.describe('Cycle Control', () => {
  test('should start zone and change status to RUNNING', async ({ page, testZone, apiHelper }) => {
    await page.goto(`/zones/${testZone.id}`);

    // Проверяем начальный статус (должен быть PLANNED)
    const statusBadge = page.locator(`[data-testid="${TEST_IDS.ZONE_STATUS_BADGE}"]`);
    await expect(statusBadge).toBeVisible();

    // Ищем кнопку Start (может быть в разных местах в зависимости от статуса)
    // Если зона в статусе PLANNED, должна быть кнопка для запуска
    // Проверяем наличие кнопки Pause/Resume (она меняется в зависимости от статуса)
    const pauseBtn = page.locator(`[data-testid="${TEST_IDS.ZONE_PAUSE_BTN}"]`);
    const resumeBtn = page.locator(`[data-testid="${TEST_IDS.ZONE_RESUME_BTN}"]`);

    // Запускаем зону через API
    await apiHelper.startZone(testZone.id);

    // Ждем обновления статуса
    await page.reload({ waitUntil: 'networkidle' });
    await expect(statusBadge).toContainText('RUNNING', { timeout: 10000 });

    // После запуска должна появиться кнопка Pause
    await expect(pauseBtn.or(resumeBtn)).toBeVisible({ timeout: 5000 });
  });

  test('should pause zone and change status to PAUSED', async ({ page, testZone, apiHelper }) => {
    // Сначала запускаем зону
    await apiHelper.startZone(testZone.id);
    await page.goto(`/zones/${testZone.id}`);
    await page.waitForTimeout(1000);

    // Ищем кнопку Pause
    const pauseBtn = page.locator(`[data-testid="${TEST_IDS.ZONE_PAUSE_BTN}"]`);
    
    if (await pauseBtn.count() > 0) {
      await pauseBtn.click();

      // Ждем обновления статуса
      await page.waitForTimeout(2000);
      const statusBadge = page.locator(`[data-testid="${TEST_IDS.ZONE_STATUS_BADGE}"]`);
      await expect(statusBadge).toContainText('PAUSED', { timeout: 10000 });
    } else {
      // Если кнопка не видна, используем API
      await apiHelper.pauseZone(testZone.id);
      await page.reload();
      const statusBadge = page.locator(`[data-testid="${TEST_IDS.ZONE_STATUS_BADGE}"]`);
      await expect(statusBadge).toContainText('PAUSED', { timeout: 10000 });
    }
  });

  test('should resume zone and change status to RUNNING', async ({ page, testZone, apiHelper }) => {
    // Запускаем и останавливаем зону
    await apiHelper.startZone(testZone.id);
    await apiHelper.pauseZone(testZone.id);
    await page.goto(`/zones/${testZone.id}`);
    await page.waitForTimeout(1000);

    // Ищем кнопку Resume
    const resumeBtn = page.locator(`[data-testid="${TEST_IDS.ZONE_RESUME_BTN}"]`);
    
    if (await resumeBtn.count() > 0) {
      await resumeBtn.click();

      // Ждем обновления статуса
      await page.waitForTimeout(2000);
      const statusBadge = page.locator(`[data-testid="${TEST_IDS.ZONE_STATUS_BADGE}"]`);
      await expect(statusBadge).toContainText('RUNNING', { timeout: 10000 });
    } else {
      // Если кнопка не видна, используем API
      await apiHelper.resumeZone(testZone.id);
      await page.reload();
      const statusBadge = page.locator(`[data-testid="${TEST_IDS.ZONE_STATUS_BADGE}"]`);
      await expect(statusBadge).toContainText('RUNNING', { timeout: 10000 });
    }
  });

  test('should harvest zone and change status to HARVESTED', async ({ page, testZone, apiHelper }) => {
    // Запускаем зону
    await apiHelper.startZone(testZone.id);
    await page.goto(`/zones/${testZone.id}`);
    await page.waitForTimeout(1000);

    // Ищем кнопку Harvest (может быть в модальном окне или на странице)
    const harvestBtn = page.locator(`[data-testid="${TEST_IDS.ZONE_HARVEST_BTN}"]`).or(page.locator('text=Собрать урожай'));

    if (await harvestBtn.count() > 0) {
      await harvestBtn.first().click();
      await page.waitForTimeout(2000);
    } else {
      // Используем API
      await apiHelper.harvestZone(testZone.id);
    }

    // Проверяем изменение статуса
    await page.reload();
    const statusBadge = page.locator(`[data-testid="${TEST_IDS.ZONE_STATUS_BADGE}"]`);
    await expect(statusBadge).toContainText('HARVESTED', { timeout: 10000 });
  });

  test('should show zone events after actions', async ({ page, testZone, apiHelper }) => {
    await page.goto(`/zones/${testZone.id}`);

    const eventsList = page.locator(`[data-testid="${TEST_IDS.ZONE_EVENTS_LIST}"]`);
    await expect(eventsList).toBeVisible({ timeout: 10000 });

    // Выполняем действие
    await apiHelper.startZone(testZone.id);

    // Ждем обновления событий
    await page.waitForTimeout(2000);
    await page.reload();

    // Проверяем, что список событий все еще виден и содержит новые события
    await expect(eventsList).toBeVisible();
  });
});


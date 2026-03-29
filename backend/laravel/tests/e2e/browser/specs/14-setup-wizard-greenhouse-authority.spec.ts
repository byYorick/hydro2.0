import { test, expect } from '../fixtures/test-data';

test.describe('Setup Wizard Greenhouse Authority', () => {
  test('should load and save greenhouse climate profile from authority document', async ({ page, apiHelper, testGreenhouse, testZone }) => {
    test.setTimeout(120000);
    const seededNodes = await apiHelper.seedGreenhouseClimateNodes(`wizard-${Date.now()}`);

    try {
      const profilePayload = {
        active_mode: 'setup',
        profiles: {
          setup: {
            mode: 'setup',
            is_active: true,
            updated_at: new Date().toISOString(),
            subsystems: {
              climate: {
                enabled: true,
                execution: {
                  interval_sec: 900,
                  temperature: { day: 27, night: 21 },
                  humidity: { day: 61, night: 72 },
                  vent_control: { min_open_percent: 20, max_open_percent: 80 },
                  external_guard: { enabled: true, temp_min: 5, temp_max: 30, humidity_max: 85 },
                  manual_override: { enabled: true, timeout_minutes: 45 },
                  schedule: [
                    { start: '06:00', end: '18:00', profile: 'day' },
                    { start: '18:00', end: '06:00', profile: 'night' },
                  ],
                },
              },
            },
          },
        },
      };

      await apiHelper.updateAutomationConfig('greenhouse', testGreenhouse.id, 'greenhouse.logic_profile', profilePayload);

      await page.goto('/setup/wizard', { waitUntil: 'networkidle' });
      await expect(page.locator('[data-testid="setup-wizard-greenhouse-select"]')).toBeVisible({ timeout: 15000 });

      await page.locator('[data-testid="setup-wizard-greenhouse-select"]').selectOption(String(testGreenhouse.id));
      await page.waitForTimeout(1500);
      await page.locator('[data-testid="setup-wizard-zone-select"]').selectOption(String(testZone.id));
      await page.waitForTimeout(1000);

      const climateEnabled = page.locator('[data-testid="greenhouse-climate-enabled"]');
      await expect(climateEnabled).toBeChecked();
      await expect(page.locator('[data-testid="greenhouse-climate-day-temp"]')).toHaveValue('27');
      await expect(page.locator('[data-testid="greenhouse-climate-interval"]')).toHaveValue('15');

      const climateSensorCheckbox = page
        .locator('label')
        .filter({ hasText: seededNodes.climateSensor.name })
        .locator('input[type="checkbox"]')
        .first();
      const ventActuatorCheckbox = page
        .locator('label')
        .filter({ hasText: seededNodes.ventActuator.name })
        .locator('input[type="checkbox"]')
        .nth(1);

      await expect(climateSensorCheckbox).toBeVisible({ timeout: 15000 });
      await expect(ventActuatorCheckbox).toBeVisible({ timeout: 15000 });

      await climateSensorCheckbox.check();
      await ventActuatorCheckbox.check();

      await page.locator('[data-testid="greenhouse-climate-day-temp"]').fill('28');
      await page.locator('[data-testid="greenhouse-climate-day-temp"]').press('Tab');
      await page.locator('[data-testid="greenhouse-climate-apply"]').click();

      await expect.poll(async () => {
        const savedDocument = await apiHelper.getAutomationConfig('greenhouse', testGreenhouse.id, 'greenhouse.logic_profile');
        return savedDocument.profiles?.setup?.subsystems?.climate?.execution?.temperature?.day
          ?? savedDocument.payload?.profiles?.setup?.subsystems?.climate?.execution?.temperature?.day
          ?? null;
      }, { timeout: 15000 }).toBe(28);

      const savedDocument = await apiHelper.getAutomationConfig('greenhouse', testGreenhouse.id, 'greenhouse.logic_profile');
      expect(savedDocument.active_mode ?? savedDocument.payload?.active_mode).toBe('setup');
    } finally {
      await apiHelper.cleanupNodesByUids(seededNodes.uids).catch(() => {});
    }
  });
});

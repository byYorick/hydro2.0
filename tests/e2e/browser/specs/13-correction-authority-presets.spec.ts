import { test, expect } from '../fixtures/test-data';

test.describe('Correction Authority Presets', () => {
  test('should create, apply, update and delete correction preset from authority form', async ({ page, apiHelper, testZone }) => {
    test.setTimeout(120000);

    const presetName = `PW Correction ${Date.now()}`;
    let presetId: number | null = null;

    try {
      await page.goto(`/zones/${testZone.id}?tab=automation`, { waitUntil: 'networkidle' });
      await page.getByRole('button', { name: 'Коррекция и калибровка' }).click();

      const details = page.locator('[data-testid="zone-correction-config-details"]');
      await details.scrollIntoViewIfNeeded();
      await details.locator('summary').click();

      await expect(page.locator('[data-testid="correction-config-form"]')).toBeVisible({ timeout: 15000 });
      await page.locator('[data-testid="correction-config-tab-base"]').click();

      const baseKpInput = page.locator('[data-testid="correction-config-base-controllers.ph.kp"]').first();
      await baseKpInput.fill('6.2');
      await page.locator('[data-testid="correction-config-new-preset"]').click();
      await page.locator('[data-testid="correction-config-new-preset-name"]').fill(presetName);
      await page.locator('[data-testid="correction-config-save-preset"]').click();
      await expect(page.locator('[data-testid="correction-config-new-preset-name"]')).toBeHidden({ timeout: 15000 });

      const createdPreset = (await apiHelper.listAutomationPresets('zone.correction'))
        .find((preset) => preset.name === presetName);
      expect(createdPreset).toBeTruthy();
      presetId = createdPreset?.id ?? null;
      expect(presetId).not.toBeNull();

      await expect(page.locator(`[data-testid="correction-config-preset-${presetId}"]`)).toBeVisible({ timeout: 15000 });
      await baseKpInput.fill('7.4');
      await page.locator('[data-testid="correction-config-update-preset"]').click();
      await page.waitForTimeout(750);

      await page.locator('[data-testid="correction-config-reset-defaults"]').click();
      await page.locator(`[data-testid="correction-config-preset-${presetId}"]`).click();
      const conflictBanner = page.locator('[data-testid="correction-config-conflict-banner"]');
      if (await conflictBanner.isVisible().catch(() => false)) {
        await page.getByRole('button', { name: 'Применить и затереть' }).click();
      }
      await expect(baseKpInput).toHaveValue('7.4');

      await page.locator('[data-testid="correction-config-preset-menu"]').click();
      await page.locator('[data-testid="correction-config-delete-preset"]').click();
      await page.waitForTimeout(1500);

      const remainingPresets = await apiHelper.listAutomationPresets('zone.correction');
      expect(remainingPresets.some((preset) => preset.id === presetId)).toBe(false);
      presetId = null;
    } finally {
      if (presetId !== null) {
        await apiHelper.deleteAutomationPreset(presetId).catch(() => {});
      }
    }
  });
});

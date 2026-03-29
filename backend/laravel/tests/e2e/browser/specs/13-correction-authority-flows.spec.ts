import { test, expect } from '../fixtures/test-data';

test.describe('Correction Authority Flows', () => {
  test('should refresh readiness after process calibration and PID saves', async ({ page, testZone }) => {
    test.setTimeout(120000);

    await page.goto(`/zones/${testZone.id}?tab=automation`, { waitUntil: 'networkidle' });
    await page.getByRole('button', { name: 'Коррекция и калибровка' }).click();

    const readinessCard = page.locator('[data-testid="correction-runtime-readiness-card"]');
    await expect(readinessCard).toBeVisible({ timeout: 15000 });
    await expect(page.locator('[data-testid="correction-readiness-process-btn"]')).toBeVisible({ timeout: 15000 });
    await expect(page.locator('[data-testid="correction-readiness-pid-btn"]')).toBeVisible({ timeout: 15000 });

    for (const mode of ['solution_fill', 'tank_recirc', 'irrigation'] as const) {
      await page.locator(`[data-testid="process-calibration-mode-${mode}"]`).click();
      await page.locator('[data-testid="process-calibration-save"]').click();
      await expect(page.getByText(/Process calibration обновлена/).last()).toBeVisible({ timeout: 15000 });
    }

    const pidSummary = page.getByText('Расширенная тонкая настройка PID и autotune');
    await pidSummary.click();
    await expect(page.locator('[data-testid="pid-config-form"]')).toBeVisible({ timeout: 10000 });

    await page.locator('[data-testid="pid-config-type-ph"]').click();
    await page.locator('[data-testid="pid-config-save"]').click();
    await page.waitForTimeout(1000);

    await page.locator('[data-testid="pid-config-type-ec"]').click();
    await page.locator('[data-testid="pid-config-save"]').click();
    await page.waitForTimeout(1000);

    await expect(page.locator('[data-testid="correction-readiness-process-btn"]')).toHaveCount(0, { timeout: 15000 });
    await expect(page.locator('[data-testid="correction-readiness-pid-btn"]')).toHaveCount(0, { timeout: 15000 });
  });

  test('should create, apply, update and delete correction preset from authority form', async ({ page, apiHelper, testZone }) => {
    test.setTimeout(120000);

    const presetName = `PW Correction ${Date.now()}`;
    let presetId: number | null = null;

    try {
      await apiHelper.updateAutomationConfig('zone', testZone.id, 'zone.correction', {
        preset_id: null,
        base_config: {},
        phase_overrides: {},
      });

      await page.goto(`/zones/${testZone.id}?tab=automation`, { waitUntil: 'networkidle' });
      await page.getByRole('button', { name: 'Коррекция и калибровка' }).click();

      const details = page.locator('[data-testid="zone-correction-config-details"]');
      await details.scrollIntoViewIfNeeded();
      await details.locator('summary').click();

      await expect(page.locator('[data-testid="correction-config-form"]')).toBeVisible({ timeout: 15000 });

      const baseKpInput = page.locator('[data-testid="correction-config-base-controllers.ph.kp"]').first();
      await expect(baseKpInput).toBeVisible({ timeout: 15000 });
      await baseKpInput.fill('6.2');
      await page.locator('[data-testid="correction-config-new-preset-name"]').fill(presetName);
      await page.locator('[data-testid="correction-config-save-preset"]').click();
      await expect.poll(async () => {
        return (await apiHelper.listAutomationPresets('zone.correction'))
          .find((preset) => preset.name === presetName)?.id ?? null;
      }, { timeout: 15000 }).not.toBeNull();

      const createdPreset = (await apiHelper.listAutomationPresets('zone.correction'))
        .find((preset) => preset.name === presetName);
      expect(createdPreset).toBeTruthy();
      presetId = createdPreset?.id ?? null;
      expect(presetId).not.toBeNull();

      await baseKpInput.fill('7.4');
      await page.locator('[data-testid="correction-config-update-preset"]').click();
      await expect.poll(async () => {
        const preset = (await apiHelper.listAutomationPresets('zone.correction'))
          .find((item) => item.id === presetId);
        return Number(preset?.payload?.base?.controllers?.ph?.kp ?? preset?.config?.base?.controllers?.ph?.kp ?? 0);
      }, { timeout: 15000 }).toBe(7.4);

      await page.locator('[data-testid="correction-config-reset-defaults"]').click();
      await page.locator('[data-testid="correction-config-preset-select"]').selectOption(String(presetId));
      await page.locator('[data-testid="correction-config-apply-preset"]').click();
      await expect(baseKpInput).toHaveValue('7.4');

      await page.locator('[data-testid="correction-config-delete-preset"]').click();
      await expect.poll(async () => {
        const remainingPresets = await apiHelper.listAutomationPresets('zone.correction');
        return remainingPresets.some((preset) => preset.id === presetId);
      }, { timeout: 15000 }).toBe(false);

      presetId = null;
    } finally {
      if (presetId !== null) {
        await apiHelper.deleteAutomationPreset(presetId).catch(() => {});
      }
    }
  });
});

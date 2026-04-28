import { test, expect } from '../fixtures/test-data';

test.describe('Correction Authority Flows', () => {
  test('should apply correction live edit and record timeline entry', async ({ page, apiHelper, testZone }) => {
    test.setTimeout(120000);

    await apiHelper.primeZoneForLiveEdit(
      testZone.id,
      new Date(Date.now() + 60 * 60 * 1000).toISOString(),
    );

    await page.goto('/testing/login?email=agronomist@example.com', { waitUntil: 'load' });
    await page.goto(`/zones/${testZone.id}?tab=automation`, { waitUntil: 'networkidle' });

    const liveEditCard = page.locator('[data-testid="correction-live-edit"]');
    await expect(liveEditCard).toBeVisible({ timeout: 15000 });

    await page.locator('[data-testid="correction-live-correction-target"]').selectOption('tank_recirc');
    await page.locator('[data-testid="correction-live-calibration-target"]').selectOption('tank_recirc');
    await liveEditCard.getByText('PID-контур EC').click();
    await page.locator('[data-testid="correction-live-field-controllers__ec__kp"]').fill('0.91');
    await page.locator('[data-testid="correction-live-calibration-field-transport_delay_sec"]').fill('14');
    await page.locator('[data-testid="correction-live-reason"]').fill('playwright phase 6.2 live edit');
    await expect(page.locator('[data-testid="correction-live-correction-dirty"]')).toContainText('1 полей');
    await expect(page.locator('[data-testid="correction-live-calibration-dirty"]')).toContainText('1 полей');

    await apiHelper.applyCorrectionLiveEdit(testZone.id, {
      reason: 'playwright phase 6.2 live edit',
      phase: 'tank_recirc',
      correction_patch: {
        'controllers.ec.kp': 0.91,
      },
      calibration_patch: {
        transport_delay_sec: 14,
      },
    });

    await page.goto(`/zones/${testZone.id}?tab=automation`, { waitUntil: 'networkidle' });
    await expect(page.locator('[data-testid="correction-live-edit"]')).toBeVisible({ timeout: 15000 });
    await page.locator('[data-testid="correction-live-correction-target"]').selectOption('tank_recirc');
    await page.locator('[data-testid="correction-live-calibration-target"]').selectOption('tank_recirc');
    await page.locator('[data-testid="correction-live-edit"]').getByText('PID-контур EC').click();
    await page.locator('[data-testid="correction-live-reload"]').click();
    await expect(page.locator('[data-testid="correction-live-field-controllers__ec__kp"]')).toHaveValue('0.91');
    await expect(page.locator('[data-testid="correction-live-calibration-field-transport_delay_sec"]')).toHaveValue('14');

    const correctionDocument = await apiHelper.getAutomationConfig('zone', testZone.id, 'zone.correction');
    expect(Number(correctionDocument?.payload?.phase_overrides?.tank_recirc?.controllers?.ec?.kp ?? 0)).toBe(0.91);

    const calibrationDocument = await apiHelper.getAutomationConfig(
      'zone',
      testZone.id,
      'zone.process_calibration.tank_recirc',
    );
    expect(Number(calibrationDocument?.payload?.transport_delay_sec ?? 0)).toBe(14);

    await page.locator('[data-testid="config-changes-namespace"]').selectOption('zone.correction.live');
    const changesList = page.locator('[data-testid="config-changes-list"]');
    await expect(changesList).toContainText('zone.correction.live', { timeout: 15000 });
    await expect(changesList).toContainText('playwright phase 6.2 live edit');
  });

  test('should refresh readiness after process calibration and PID saves', async ({ page, testZone }) => {
    test.setTimeout(120000);

    await page.goto('/testing/login?email=agronomist@example.com', { waitUntil: 'load' });
    await page.goto(`/zones/${testZone.id}?tab=automation`, { waitUntil: 'networkidle' });
    await page.getByRole('button', { name: 'Коррекция и калибровка' }).click();

    const readinessCard = page.locator('[data-testid="correction-runtime-readiness-card"]');
    await expect(readinessCard).toBeVisible({ timeout: 15000 });
    await expect(page.locator('[data-testid="correction-readiness-process-btn"]')).toBeVisible({ timeout: 15000 });

    for (const mode of ['solution_fill', 'tank_recirc', 'irrigation'] as const) {
      await page.locator(`[data-testid="process-calibration-tab-${mode}"]`).click();
      const delayInput = page.locator('[data-testid="process-calibration-input-transport_delay_sec"]');
      await delayInput.fill(String(mode === 'solution_fill' ? 6 : mode === 'tank_recirc' ? 7 : 8));
      const saveButton = page.locator('[data-testid="process-calibration-save"]');
      if (await saveButton.isEnabled().catch(() => false)) {
        await saveButton.click();
        await page.waitForTimeout(1000);
      }
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
        phase_overrides: {},
      });

      await page.goto('/testing/login?email=agronomist@example.com', { waitUntil: 'load' });
      await page.goto(`/zones/${testZone.id}?tab=automation`, { waitUntil: 'networkidle' });
      await page.getByRole('button', { name: 'Коррекция и калибровка' }).click();

      const details = page.locator('[data-testid="zone-correction-config-details"]');
      await details.scrollIntoViewIfNeeded();
      await details.locator('summary').click();

      await expect(page.locator('[data-testid="correction-config-form"]')).toBeVisible({ timeout: 15000 });
      await page.locator('[data-testid="correction-config-tab-base"]').click();

      const baseKpInput = page.locator('[data-testid="correction-config-base-controllers.ph.kp"]').first();
      await expect(baseKpInput).toBeVisible({ timeout: 15000 });
      await baseKpInput.fill('6.2');
      await page.locator('[data-testid="correction-config-new-preset"]').click();
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

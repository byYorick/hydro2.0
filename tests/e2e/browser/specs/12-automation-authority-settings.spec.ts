import { test, expect } from '../fixtures/test-data';

test.describe('Automation Authority Settings', () => {
  test('should save runtime settings via authority UI and refresh system bundle', async ({ page, apiHelper }) => {
    test.setTimeout(120000);

    const settingKey = 'automation_engine.scheduler_due_grace_sec';
    const inputTestId = `settings-automation-engine-input-${settingKey}`;
    const initialDocument = await apiHelper.getAutomationConfig('system', 0, 'system.runtime');
    const initialValue = Number(initialDocument?.payload?.[settingKey] ?? 15);
    const nextValue = initialValue + 7;

    try {
      await page.goto('/settings', { waitUntil: 'load' });
      await expect(page.locator('[data-testid="settings-automation-engine-card"]')).toBeVisible({ timeout: 15000 });

      const input = page.locator(`[data-testid="${inputTestId}"]`);
      await expect(input).toBeVisible({ timeout: 10000 });
      await input.focus();
      await input.fill(String(nextValue));
      await input.blur();
      await expect(input).toHaveValue(String(nextValue));

      const saveButton = page.locator('[data-testid="settings-automation-engine-save"]');
      await expect(saveButton).toBeEnabled({ timeout: 10000 });
      await saveButton.click();
      await expect.poll(async () => {
        const updatedDocument = await apiHelper.getAutomationConfig('system', 0, 'system.runtime');
        return Number(updatedDocument?.payload?.[settingKey] ?? 0);
      }, { timeout: 30000 }).toBe(nextValue);

      await page.reload({ waitUntil: 'load' });
      await expect(page.locator(`[data-testid="${inputTestId}"]`)).toHaveValue(String(nextValue));
    } finally {
      await apiHelper.resetAutomationConfig('system', 0, 'system.runtime').catch(() => {});
    }
  });
});

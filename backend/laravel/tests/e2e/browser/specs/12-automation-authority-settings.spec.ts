import { test, expect } from '../fixtures/test-data';

test.describe('Automation Authority Settings', () => {
  test('should save runtime settings via authority UI and refresh system bundle', async ({ page, apiHelper }) => {
    test.setTimeout(90000);

    const settingKey = 'automation_engine.scheduler_due_grace_sec';
    const inputTestId = `settings-automation-engine-input-${settingKey}`;
    const initialDocument = await apiHelper.getAutomationConfig('system', 0, 'system.runtime');
    const initialValue = Number(initialDocument?.payload?.[settingKey] ?? 15);
    const nextValue = initialValue + 7;
    const beforeBundle = await apiHelper.getAutomationBundle('system', 0);

    try {
      await page.goto('/settings', { waitUntil: 'networkidle' });
      await expect(page.locator('[data-testid="settings-automation-engine-card"]')).toBeVisible({ timeout: 15000 });

      const input = page.locator(`[data-testid="${inputTestId}"]`);
      await expect(input).toBeVisible({ timeout: 10000 });
      await input.fill(String(nextValue));

      await page.locator('[data-testid="settings-automation-engine-save"]').click();
      await expect(page.locator('[data-testid="toast-success"]')).toBeVisible({ timeout: 15000 });

      const updatedDocument = await apiHelper.getAutomationConfig('system', 0, 'system.runtime');
      expect(Number(updatedDocument?.payload?.[settingKey] ?? 0)).toBe(nextValue);

      await apiHelper.validateAutomationBundle('system', 0);
      const afterBundle = await apiHelper.getAutomationBundle('system', 0);
      expect(afterBundle.bundle_revision).not.toBe(beforeBundle.bundle_revision);
      expect(afterBundle.scope_type).toBe('system');
    } finally {
      await apiHelper.resetAutomationConfig('system', 0, 'system.runtime').catch(() => {});
    }
  });
});

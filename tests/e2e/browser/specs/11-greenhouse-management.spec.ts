import { test, expect } from '../fixtures/test-data';

test.describe('Greenhouse Management', () => {
  test('should show climate failures when no climate nodes available', async ({ page, testZone }) => {
    await page.goto(`/greenhouses/${testZone.greenhouse_id}`, { waitUntil: 'networkidle' });

    await expect(page.locator('h1')).toBeVisible({ timeout: 15000 });

    const climateButton = page.getByRole('button', { name: 'Управление климатом' });
    await expect(climateButton).toBeEnabled({ timeout: 10000 });
    await climateButton.click();

    const commandForm = page.locator('[data-testid="zone-command-form"]');
    await expect(commandForm).toBeVisible({ timeout: 10000 });

    const submitButton = page.getByRole('button', { name: 'Отправить' });
    await submitButton.click();

    const failures = page.locator('[data-testid="climate-failures"]');
    await expect(failures).toBeVisible({ timeout: 15000 });
    await expect(failures).toContainText(testZone.name);
  });
});

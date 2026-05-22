import { test, expect } from '../fixtures/test-data';

test.describe('Greenhouse climate page', () => {
  test('should load climate dashboard for greenhouse', async ({ page, testZone }) => {
    test.setTimeout(90000);
    await page.goto(`/greenhouses/${testZone.greenhouse_id}/climate`, { waitUntil: 'domcontentloaded' });

    await expect(page.locator('[data-testid="greenhouse-climate-dashboard"]')).toBeVisible({ timeout: 30000 });
    await expect(page.getByRole('heading', { name: 'Климат теплицы' })).toBeVisible({ timeout: 15000 });
    await expect(page.getByText('Режим', { exact: true }).first()).toBeVisible({ timeout: 15000 });
  });
});

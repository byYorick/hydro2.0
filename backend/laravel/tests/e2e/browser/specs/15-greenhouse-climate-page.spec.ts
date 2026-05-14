import { test, expect } from '../fixtures/test-data';

test.describe('Greenhouse climate page', () => {
  test('should load climate dashboard for greenhouse', async ({ page, testZone }) => {
    await page.goto('/testing/login?email=agronomist@example.com', { waitUntil: 'load' });
    await page.goto(`/greenhouses/${testZone.greenhouse_id}/climate`, { waitUntil: 'networkidle' });

    await expect(page.getByRole('heading', { name: 'Климат теплицы' })).toBeVisible({ timeout: 15000 });
    await expect(page.locator('[data-testid="greenhouse-climate-dashboard"]')).toBeVisible({ timeout: 15000 });
    await expect(page.getByText('Режим')).toBeVisible({ timeout: 15000 });
  });
});

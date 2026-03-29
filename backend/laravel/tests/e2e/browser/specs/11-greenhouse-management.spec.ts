import { test, expect } from '../fixtures/test-data';

test.describe('Greenhouse Management', () => {
  test('should show climate failures when no climate nodes available', async ({ page, testZone }) => {
    await page.goto(`/greenhouses/${testZone.greenhouse_id}`, { waitUntil: 'networkidle' });

    await expect(page.locator('h1')).toBeVisible({ timeout: 15000 });
    await expect(page.getByRole('heading', { level: 4, name: 'Климат теплицы' })).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('Профиль климата ещё не сохранён')).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('В обслуживании сейчас 0 / 0 climate/weather нод.')).toBeVisible({ timeout: 10000 });
  });
});

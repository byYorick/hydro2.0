import { test, expect } from '../fixtures/test-data';
import { TEST_IDS } from '../constants';

test.describe('Analytics', () => {
  test('should render analytics filters and chart container', async ({ page }) => {
    await page.goto('/analytics', { waitUntil: 'networkidle' });
    await page.waitForSelector('h1', { timeout: 15000 });

    const zoneFilter = page.locator(`[data-testid="${TEST_IDS.ANALYTICS_FILTER_ZONE}"]`);
    const metricFilter = page.locator(`[data-testid="${TEST_IDS.ANALYTICS_FILTER_METRIC}"]`);
    const periodFilter = page.locator(`[data-testid="${TEST_IDS.ANALYTICS_FILTER_PERIOD}"]`);
    const chart = page.locator(`[data-testid="${TEST_IDS.ANALYTICS_CHART}"]`);

    await expect(zoneFilter).toBeVisible({ timeout: 10000 });
    await expect(metricFilter).toBeVisible({ timeout: 10000 });
    await expect(periodFilter).toBeVisible({ timeout: 10000 });
    await expect(chart).toBeVisible({ timeout: 10000 });
  });
});

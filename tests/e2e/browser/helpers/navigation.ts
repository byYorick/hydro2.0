import { expect, type Page } from '@playwright/test';

export async function waitForDashboardReady(page: Page): Promise<void> {
  await expect.poll(
    async () => {
      const indicators = [
        page.locator('[data-testid="dashboard-zones-count"]'),
        page.getByRole('heading', { name: 'Операционный центр' }),
        page.getByText('Зоны (всего / в работе)'),
        page.locator('nav a[href="/zones"]'),
        page.getByText('Последние события'),
        page.locator('[data-testid="ws-status-indicator"]'),
        page.getByText('В работе', { exact: true }),
        page.getByText('Активные зоны', { exact: true }),
      ];

      for (const indicator of indicators) {
        if (await indicator.first().isVisible().catch(() => false)) {
          return true;
        }
      }

      return false;
    },
    { timeout: 30000, message: 'Dashboard did not expose any stable ready indicator' },
  ).toBe(true);
}

export async function waitForLoginForm(page: Page): Promise<void> {
  await page.goto('/login', { waitUntil: 'domcontentloaded' });
  await expect(page.locator('[data-testid="login-form"]')).toBeVisible({ timeout: 15000 });
}

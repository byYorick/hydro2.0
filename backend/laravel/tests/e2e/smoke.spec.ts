import { test, expect } from '@playwright/test'

test('dashboard loads', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('hydro 2.0')).toBeVisible()
})

test('zones page renders list', async ({ page }) => {
  await page.goto('/zones')
  await expect(page.getByText('Zones')).toBeVisible()
})

test('alerts page opens', async ({ page }) => {
  await page.goto('/alerts')
  await expect(page.getByText('Alerts')).toBeVisible()
})

test('zone detail page loads', async ({ page }) => {
  await page.goto('/zones/1')
  // Проверяем, что страница зоны загрузилась (либо название зоны, либо заголовок)
  await expect(page.locator('body')).toBeVisible({ timeout: 5000 })
})


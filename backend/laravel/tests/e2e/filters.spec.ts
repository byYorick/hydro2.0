import { test, expect } from '@playwright/test'

test('zones filters work', async ({ page }) => {
  await page.goto('/zones')
  await expect(page.getByText('Zones')).toBeVisible()
  const search = page.locator('input[placeholder="Имя зоны..."]')
  await search.fill('non-existent-zone-xyz')
  await expect(page.getByText('Нет зон по текущим фильтрам')).toBeVisible()
})

test('devices filters work', async ({ page }) => {
  await page.goto('/devices')
  await expect(page.getByText('Devices')).toBeVisible()
  const typeSelect = page.locator('select')
  await typeSelect.selectOption('EC')
  await expect(page.locator('tbody tr')).toHaveCountGreaterThan(0)
})

test('alerts active filter toggles', async ({ page }) => {
  await page.goto('/alerts')
  await expect(page.getByText('Alerts')).toBeVisible()
  const filter = page.locator('select')
  await filter.selectOption('false') // Все
  await expect(page.locator('tbody tr')).toHaveCountGreaterThan(0)
})



import { expect, test } from '@playwright/test'

async function loginAsAdmin(page) {
  await page.goto('/testing/login/1', { waitUntil: 'load' })
  await page.waitForURL('**/', { timeout: 60000 })
}

async function inertiaComponent(page) {
  return await page.evaluate(() => {
    const payload = document.getElementById('app')?.dataset?.page
    return payload ? JSON.parse(payload).component : null
  })
}

test.describe('Dashboard Smoke', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page)
  })

  test('shows realtime header statuses', async ({ page }) => {
    const component = await inertiaComponent(page)
    expect(component).not.toBeNull()
    expect(component).toMatch(/^Dashboard/)
  })

  test('allows navigating to zones list', async ({ page }) => {
    await page.goto('/zones')
    await expect(page).toHaveURL(/\/zones/)
    const component = await inertiaComponent(page)
    expect(component).toBe('Zones/Index')
  })
})


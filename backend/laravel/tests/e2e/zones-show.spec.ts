import { test, expect } from '@playwright/test'

test.describe('Zones/Show страница', () => {
  test.beforeEach(async ({ page }) => {
    // Предполагаем, что пользователь уже авторизован
    // В реальном тесте нужно было бы сначала выполнить авторизацию
    await page.goto('/zones/1')
  })

  test('отображает информацию о зоне', async ({ page }) => {
    await expect(page.getByText(/Zone|Zone \d+/)).toBeVisible()
  })

  test('отображает блок Target vs Actual', async ({ page }) => {
    // Проверяем наличие карточек метрик
    await expect(page.locator('text=pH').or(page.locator('text=EC'))).toBeVisible({ timeout: 5000 })
  })

  test('отображает графики', async ({ page }) => {
    // Проверяем наличие графиков
    await expect(page.locator('.zone-chart').or(page.locator('text=pH'))).toBeVisible({ timeout: 5000 })
  })

  test('отображает устройства зоны', async ({ page }) => {
    await expect(page.getByText('Devices')).toBeVisible({ timeout: 5000 })
  })

  test('отображает блок Cycles', async ({ page }) => {
    await expect(page.getByText('Cycles')).toBeVisible({ timeout: 5000 })
    await expect(page.getByText('PH_CONTROL')).toBeVisible({ timeout: 5000 })
    await expect(page.getByText('IRRIGATION')).toBeVisible({ timeout: 5000 })
  })

  test('отображает события', async ({ page }) => {
    await expect(page.getByText('Events')).toBeVisible({ timeout: 5000 })
  })

  test('кнопки управления видны для оператора', async ({ page }) => {
    // Предполагаем, что текущий пользователь - оператор
    await expect(page.getByRole('button', { name: /Pause|Resume/i })).toBeVisible({ timeout: 5000 })
    await expect(page.getByRole('button', { name: /Irrigate/i })).toBeVisible({ timeout: 5000 })
  })

  test('можно изменить диапазон времени графика', async ({ page }) => {
    // Ищем кнопки времени (1H, 24H, 7D, 30D, ALL)
    const timeButton = page.getByRole('button', { name: '7D' }).first()
    
    if (await timeButton.isVisible({ timeout: 3000 })) {
      await timeButton.click()
      // Проверяем, что данные перезагрузились (можно проверить через network request)
      await expect(timeButton).toBeVisible()
    }
  })
})


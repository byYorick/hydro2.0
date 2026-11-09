import { expect, test } from '@playwright/test'

test('настройки AE3 валидируют черновик, отменяют правки и сохраняют только выбранный параметр', async ({ page }) => {
  await page.goto('/testing/login?email=agronomist@example.com')
  await page.goto('/settings')
  await page.getByRole('tab', { name: 'Параметры движка' }).click()
  const field = page.getByTestId('settings-automation-engine-input-automation_engine.scheduler_due_grace_sec')
  const save = page.getByTestId('settings-automation-engine-save')
  await expect(field).toBeVisible()
  const original = await field.inputValue()
  const changed = original === '42' ? '43' : '42'
  await expect(save).toBeDisabled()

  await field.fill('')
  await expect(page.getByText('Введите число.', { exact: true })).toBeVisible()
  await expect(save).toBeDisabled()
  await field.fill(changed)
  const navigationWarning = page.waitForEvent('dialog').then(async dialog => {
    expect(dialog.message()).toContain('не сохранены')
    await dialog.dismiss()
  })
  await page.locator('a[href="/zones"]').first().click()
  await navigationWarning
  await expect(page).toHaveURL(/\/settings$/)
  await expect(field).toHaveValue(changed)
  await page.getByTestId('settings-automation-engine-discard').click()
  await expect(field).toHaveValue(original)
  await expect(save).toBeDisabled()

  await field.fill(changed)
  const requestPromise = page.waitForRequest(request => request.method() === 'PUT' && request.url().endsWith('/system/0/system.runtime'))
  await save.click()
  const request = await requestPromise
  expect(request.postDataJSON()).toEqual({ payload: { 'automation_engine.scheduler_due_grace_sec': Number(changed) } })
  await expect(save).toBeDisabled()
  await page.reload()
  await page.getByRole('tab', { name: 'Параметры движка' }).click()
  await expect(field).toHaveValue(changed)

  // Restore the one parameter changed in this isolated testing database.
  await field.fill(original)
  await save.click()
  await expect(save).toBeDisabled()
  await expect(page.getByTestId('automation-runtime-changed-count')).toHaveCount(0)
})

test('мобильный редактор коррекции помещается на экран и сохраняет черновик между разделами', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/testing/login?email=agronomist@example.com')
  const response = await page.request.get('/api/zones')
  expect(response.ok()).toBeTruthy()
  const payload = await response.json()
  const zone = (payload.data?.data ?? payload.data)[0]
  expect(zone, 'bootstrap must provide a zone').toBeTruthy()
  await page.goto(`/zones/${zone.id}?tab=automation&auto=solution#zone-pid-config-panel-shared`)
  const workspace = page.getByTestId('zone-correction-workspace')
  const form = page.getByTestId('pid-config-form')
  await expect(form).toBeVisible()
  const mainBounds = await page.locator('main').boundingBox()
  expect(mainBounds).toBeTruthy()
  expect(mainBounds!.x + mainBounds!.width).toBeLessThanOrEqual(390)
  const formBounds = await form.boundingBox()
  expect(formBounds!.x + formBounds!.width).toBeLessThanOrEqual(390)

  const field = form.locator('input[type="number"]:not([readonly]):not([disabled])').first()
  await field.fill('0.05')
  await workspace.getByRole('button', { name: 'Процесс', exact: true }).click()
  await expect(form).toBeHidden()
  await workspace.getByRole('button', { name: 'PID', exact: true }).click()
  await expect(field).toHaveValue('0.05')
})

test('профиль зоны открывается как понятный мобильный редактор', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/testing/login?email=agronomist@example.com')
  const response = await page.request.get('/api/zones')
  expect(response.ok()).toBeTruthy()
  const payload = await response.json()
  const zone = (payload.data?.data ?? payload.data)[0]
  await page.goto(`/zones/${zone.id}?tab=automation&auto=settings`)
  await expect(page.getByRole('heading', { name: 'Профиль зоны' }).first()).toBeVisible()
  await page.getByRole('button', { name: 'Редактировать в мастере запуска' }).first().click()
  const dialog = page.getByRole('dialog', { name: 'Профиль зоны' })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByRole('button', { name: 'Сохранить и применить' })).toBeVisible()
  await dialog.getByRole('button', { name: 'Отмена' }).click()
  await expect(dialog).toHaveCount(0)
})

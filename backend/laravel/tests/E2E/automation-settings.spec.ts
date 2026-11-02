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

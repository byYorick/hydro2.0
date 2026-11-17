import { expect, test } from '@playwright/test'

test('системный редактор сохраняет черновик при отмене перехода и не превращает пустое поле в ноль', async ({ page }) => {
  await page.goto('/testing/login?email=agronomist@example.com')
  await page.goto('/system/settings')
  await page.getByTestId('system-settings-tab-pump_calibration').click()
  const field = page.getByTestId('authority-field-ml_per_sec_min')
  const save = page.getByTestId('system-settings-save')
  await expect(field).toBeVisible()
  const original = await field.inputValue()
  await expect(save).toBeDisabled()
  await field.fill('')
  await expect(page.getByText('Введите число.', { exact: true })).toBeVisible()
  await expect(save).toBeDisabled()
  await field.fill(original === '0.02' ? '0.03' : '0.02')
  await expect(save).toBeEnabled()
  const navigationWarning = page.waitForEvent('dialog').then(async dialog => {
    expect(dialog.message()).toContain('не сохранены')
    await dialog.dismiss()
  })
  await page.getByTestId('system-settings-tab-automation_defaults').click()
  await navigationWarning
  await expect(field).toBeVisible()
  await page.getByTestId('system-settings-discard').click()
  await expect(field).toHaveValue(original)
  await expect(save).toBeDisabled()
})

for (const width of [1280, 390]) {
  test(`решение о поливе объясняет порог без заявления о подаче воды, экран ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    await page.goto('/testing/login?email=agronomist@example.com')
    const response = await page.request.get('/api/zones')
    const payload = await response.json()
    const zone = (payload.data?.data ?? payload.data)[0]
    expect(zone).toBeTruthy()
    await page.route(`**/api/zones/${zone.id}/state`, route => route.fulfill({ json: {
      zone_id: zone.id, state: 'READY', state_label: 'Готов к поливу', current_stage: 'complete_ready', workflow_phase: 'ready',
      state_details: { started_at: null, elapsed_sec: 0, progress_percent: 100, failed: false },
      system_config: { tanks_count: 2, system_type: 'drip', clean_tank_capacity_l: 300, nutrient_tank_capacity_l: 280 },
      current_levels: { clean_tank_level_percent: 80, nutrient_tank_level_percent: 80, ph: 5.8, ec: 1.6 },
      active_processes: { pump_in: false, circulation_pump: false, ph_correction: false, ec_correction: false, active_doses: [] },
      timeline: [], next_state: null, estimated_completion_sec: null,
      irrigation_decision: {
        task_id: 101, task_status: 'completed', outcome: 'run', strategy: 'smart_soil_v1', reason_code: 'smart_soil_below_min',
        evaluated_at: new Date().toISOString(), degraded: false, config: { hysteresis_pct: 2 },
        details: { zone_average_pct: 35, run_below_pct: 38, sensor_count: 2, active_sensor_count: 2, samples: 6 },
      },
    } }))
    await page.goto(`/zones/${zone.id}?tab=automation&auto=process`)
    const card = page.getByTestId('automation-decision-card')
    await expect(card).toBeVisible()
    await expect(card.getByText('Полив разрешён', { exact: true })).toBeVisible()
    await expect(card.getByText('35%', { exact: true })).toBeVisible()
    await expect(card.getByText('38%', { exact: true })).toBeVisible()
    await expect(card.getByText(/Разрешение полива не подтверждает подачу воды/)).toBeVisible()
    const bounds = await card.boundingBox()
    if (!bounds) throw new Error('Карточка решения должна быть видна')
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(width)
    await expect(card.locator('details')).not.toHaveAttribute('open', '')
  })
}

test('системные настройки предлагают понятные варианты условий полива', async ({ page }) => {
  await page.goto('/testing/login?email=agronomist@example.com')
  await page.goto('/system/settings')
  await page.getByTestId('system-settings-tab-automation_defaults').click()
  await page.getByTestId('authority-field-search').fill('полив')
  const strategy = page.getByTestId('authority-field-water_irrigation_decision_strategy')
  await expect(strategy).toBeVisible()
  await expect(strategy).toContainText('По расписанию')
  await expect(strategy).toContainText('По влажности субстрата')
  await expect(page.getByTestId('authority-field-water_irrigation_ec_component')).toContainText('Только pH, без коррекции EC')
})

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

import { expect, test, type Page } from '@playwright/test'

async function openProcess(page: Page, initial: 'live' | 'empty' | 'unknown' | 'stale' = 'live') {
  await page.goto('/testing/login?email=agronomist@example.com')
  const body = await (await page.request.get('/api/zones')).json()
  const zone = (body.data?.data ?? body.data)[0]
  expect(zone).toBeTruthy()
  let failed = initial === 'empty'
  const captured = new Date(Date.now() - (initial === 'stale' ? 180000 : 0)).toISOString()
  const snapshot = { zone_id: zone.id, state: 'IRRIGATING', current_stage: 'irrigation_run', current_stage_label: 'Выполнение полива', workflow_phase: 'irrigating', state_details: { elapsed_sec: 12, progress_percent: 20, stage_deadline_remaining_sec: 100 }, current_levels: initial === 'unknown' ? {} : { clean_tank_level_percent: 80, nutrient_tank_level_percent: 20, ph: 5.8, ec: 1.4 }, active_processes: { pump_in: true }, timeline: [], state_meta: { source: initial === 'stale' ? 'cache' : 'live', is_stale: initial === 'stale', served_at: new Date().toISOString(), observed_at: captured }, observability: { overall_health: 'active', runtime: { task_id: 901, task_is_active: true, task_status: 'running', current_stage: 'irrigation_run', stage_elapsed_sec: 12, stage_deadline_remaining_sec: 100 }, hang_hints: [] } }
  await page.route(`**/api/zones/${zone.id}/state`, route => failed ? route.fulfill({ status: 503, json: { message: 'fixture' } }) : route.fulfill({ json: snapshot }))
  await page.route('**/api/system/scheduler/observability', route => route.fulfill({ json: { status: 'ok', data: { enabled: false, cycle_observation: 'disabled', pending_intents: 0, oldest_pending_age_sec: null, cycle_overrun_sec: null } } }))
  await page.goto(`/zones/${zone.id}?tab=automation&auto=process`)
  return { fail: () => { failed = true }, recover: () => { failed = false } }
}
for (const width of [390, 900, 1440]) {
  test(`выполнение автоматики объясняет данные и помещается на экране ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    await openProcess(page)
    await expect(page.getByTestId('automation-state-freshness')).toContainText('Время последнего успешного получения состояния')
    await expect(page.getByText(/Схема этапа по данным задачи/)).toBeVisible()
    await expect(page.getByText(/До предельного срока:/)).toBeVisible()
    const panel = page.getByTestId('automation-observability-panel')
    await panel.scrollIntoViewIfNeeded()
    await expect(panel.getByText('Этап не распознан', { exact: true })).toHaveCount(0)
    await expect(panel.getByText(/ограничение ожидания, а не прогноз завершения/)).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width)
  })
}
test('недоступное состояние не показывается как простой оборудования и восстанавливается', async ({ page }) => {
  const fixture = await openProcess(page, 'empty')
  await expect(page.getByTestId('automation-state-empty')).toBeVisible()
  await expect(page.getByText('Система в ожидании', { exact: true })).toHaveCount(0)
  fixture.recover()
  await page.getByTestId('automation-state-refresh').click()
  await expect(page.getByTestId('automation-state-empty')).toHaveCount(0)
  await expect(page.getByTestId('automation-observability-panel')).toBeVisible()
})
test('потеря связи сохраняет диагностику и приостанавливает схему', async ({ page }) => {
  const fixture = await openProcess(page)
  await expect(page.getByTestId('automation-state-freshness')).toBeVisible()
  fixture.fail()
  await page.getByTestId('automation-state-refresh').click()
  await expect(page.getByText(/Показаны ранее полученные данные/)).toBeVisible()
  await expect(page.getByTestId('automation-diagram-unavailable')).toContainText('Схема приостановлена')
  await expect(page.getByText('Задача в работе', { exact: true })).toHaveCount(0)
  await expect(page.getByTestId('automation-observability-panel')).toBeVisible()
})
test('неизвестные уровни не выдаются за пустые баки', async ({ page }) => {
  await openProcess(page, 'unknown')
  await expect(page.getByTestId('automation-diagram-unavailable')).toContainText('Нет данных об уровнях баков')
  await expect(page.getByText('Нет данных', { exact: true })).toHaveCount(2)
})

test('возраст кэша относится к исходным данным, а не к свежему ответу', async ({ page }) => {
  await openProcess(page, 'stale')
  await expect(page.getByText(/последнее успешное получение 03:/)).toBeVisible()
  await expect(page.getByTestId('automation-diagram-unavailable')).toContainText('Схема приостановлена')
  await expect(page.getByText('Задача в работе', { exact: true })).toHaveCount(0)
})

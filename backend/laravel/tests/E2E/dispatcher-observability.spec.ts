import { expect, test, type Page } from '@playwright/test'
import { openZoneSchedulerTab } from './openZoneSchedulerTab'

async function openDispatcher(page: Page) {
  await page.goto('/testing/login?email=agronomist@example.com')
  const response = await page.request.get('/api/zones')
  const body = await response.json()
  const zone = (body.data?.data ?? body.data)[0]
  expect(zone).toBeTruthy()
  const now = new Date()
  const at = (seconds: number) => new Date(now.getTime() + seconds * 1000).toISOString()
  const failed = { execution_id: '212', task_id: '212', zone_id: zone.id, task_type: 'irrigation_start', schedule_task_type: 'irrigation', status: 'failed', is_active: false, created_at: at(-600), completed_at: at(-500), irrigation_mode: 'normal', error_code: 'fixture_timeout', human_error_message: 'Насос не подтвердил выполнение', chain: [] }
  const workspace = {
    control: { automation_runtime: 'ae3', control_mode: 'auto', allowed_manual_steps: [], generated_at: at(0), timezone: 'Europe/Moscow' },
    capabilities: { executable_task_types: ['irrigation', 'lighting', 'diagnostics'], planned_task_types: ['irrigation'], non_executable_planned_task_types: [], diagnostics_available: true },
    plan: { horizon: '24h', lanes: [{ task_type: 'irrigation', label: 'Полив', mode: 'interval', enabled: true, executable: true }], windows: [{ plan_window_id: 'future', zone_id: zone.id, task_type: 'irrigation', schedule_key: 'fixture', trigger_at: at(300), state: 'planned', mode: 'interval', origin: 'effective_targets', label: 'Полив' }], summary: { planned_total: 1, suppressed_total: 0, missed_total: 0 } },
    execution: { active_run: { execution_id: '211', task_id: '211', zone_id: zone.id, task_type: 'irrigation_start', schedule_task_type: 'irrigation', status: 'waiting_command', is_active: true, created_at: at(-300), accepted_at: at(-280), requested_duration_sec: 60, current_stage: 'irrigation_check' }, recent_runs: [failed], counters: { active: 1, completed_24h: 3, failed_24h: 1 } },
    manual_schedules: [],
  }
  let failRefresh = false
  await page.route(`**/api/zones/${zone.id}/schedule-workspace**`, route => failRefresh ? route.fulfill({ status: 503, json: { message: 'fixture' } }) : route.fulfill({ json: { status: 'ok', data: workspace } }))
  await page.route(`**/api/zones/${zone.id}/executions/212`, route => route.fulfill({ json: { status: 'ok', data: failed } }))
  await page.route(`**/api/system/scheduler/observability`, route => route.fulfill({ json: { status: 'ok', data: { scope: 'global', enabled: true, dispatch_interval_sec: 60, generated_at: at(0), last_cycle_at: at(-180), last_cycle_age_sec: 180, cycle_observation: 'delayed', pending_intents: 3, oldest_pending_age_sec: 90, cycle_duration_p99_sec: 1, cycle_overrun_sec: 0 } } }))
  await page.goto(`/zones/${zone.id}`)
  await openZoneSchedulerTab(page)
  await expect(page.getByTestId('scheduler-kpi-row')).toBeVisible()
  return { zoneId: zone.id, failNextRefresh: () => { failRefresh = true } }
}

for (const width of [390, 900, 1440]) {
  test(`диспетчер объясняет план и прошедшее время, экран ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    await openDispatcher(page)
    const root = page.getByTestId('scheduler-root')
    await expect(root.getByText(/с момента приёма задачи/)).toBeVisible()
    await expect(root.getByText('таймер истёк', { exact: false })).toHaveCount(0)
    await expect(root.getByText(/Наступление времени не гарантирует запуск/)).toBeVisible()
    await expect(root.getByText(/Нового записанного обхода нет/)).toBeVisible()
    await expect(root.getByText(/Europe\/Moscow/)).toBeVisible()
    const row = page.getByTestId('scheduler-runs-row-212')
    await row.scrollIntoViewIfNeeded()
    const bounds = await row.boundingBox()
    expect(bounds).toBeTruthy()
    if (bounds) expect(bounds.x + bounds.width).toBeLessThanOrEqual(width)
  })
}

test('повтор полива требует осмысленного подтверждения и не дублируется во время запроса', async ({ page }) => {
  const { zoneId } = await openDispatcher(page)
  await page.getByTestId('scheduler-runs-row-212').click()
  const retry = page.getByTestId('scheduler-chain-retry')
  await expect(retry).toBeVisible()
  let requests = 0
  let release!: () => void
  const pending = new Promise<void>(resolve => { release = resolve })
  await page.route(`**/api/zones/${zoneId}/executions/212/retry`, async route => {
    requests++
    await pending
    await route.fulfill({ status: 201, json: { status: 'ok', data: { intent_id: 313 } } })
  })
  page.once('dialog', async dialog => { expect(dialog.message()).toContain('начнётся подача воды'); await dialog.accept() })
  try {
    await retry.click()
    await expect(retry).toBeDisabled()
    await expect(retry).toContainText('Создание запроса')
    await expect.poll(() => requests).toBe(1)
  } finally { release() }
  await expect(page.getByText(/Повторный запрос полива №313 создан/)).toBeVisible()
})

test('ошибка обновления сохраняет старый план с явным предупреждением', async ({ page }) => {
  const { failNextRefresh } = await openDispatcher(page)
  failNextRefresh()
  await page.getByRole('button', { name: 'Обновить данные планировщика', exact: true }).click()
  await expect(page.getByText(/Показанные данные получены ранее/)).toBeVisible()
  await expect(page.getByTestId('scheduler-runs-row-212')).toBeVisible()
})

test('ручное расписание не превращает пустую длительность в минимальный полив', async ({ page }) => {
  await openDispatcher(page)
  await page.getByTestId('scheduler-manage-schedules').click()
  await page.getByTestId('manual-schedule-create').click()
  await expect(page.getByTestId('manual-schedule-task-type-ventilation')).toBeDisabled()
  const input = page.getByTestId('manual-schedule-duration')
  await input.fill('')
  await expect(input).toHaveValue('')
  await expect(page.getByTestId('manual-schedule-submit')).toBeDisabled()
  await input.fill('3601')
  await expect(input).toHaveValue('3601')
  await expect(page.getByTestId('manual-schedule-modal').getByText('Длительность от 1 до 3600 с.', { exact: true }).first()).toBeVisible()
  await expect(page.getByTestId('manual-schedule-submit')).toBeDisabled()
  await input.fill('1')
  await expect(page.getByTestId('manual-schedule-submit')).toBeEnabled()
})

test('ошибка фонового состояния остаётся на панели без повторных всплывающих сообщений', async ({ page }) => {
  const { zoneId } = await openDispatcher(page)
  await page.route(`**/api/zones/${zoneId}/state`, route => route.fulfill({ status: 503, json: { message: 'fixture-state-unavailable' } }))
  await page.getByRole('button', { name: 'Обновить данные планировщика', exact: true }).click()
  await expect(page.getByText(/Не удалось обновить состояние процесса/)).toBeVisible()
  await expect(page.getByText('Ошибка: fixture-state-unavailable', { exact: true })).toHaveCount(0)
})

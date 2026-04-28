import { expect, test } from '@playwright/test'

type ExecutionRun = {
  execution_id: string
  task_id: string
  zone_id: number
  task_type: string
  status: string
  chain?: Array<{
    step: 'SNAPSHOT' | 'DECISION' | 'TASK' | 'DISPATCH' | 'RUNNING' | 'COMPLETE' | 'FAIL' | 'SKIP'
    at?: string | null
    ref: string
    detail: string
    status: 'ok' | 'err' | 'skip' | 'run' | 'warn'
    live?: boolean
  }>
  current_stage?: string | null
  error_code?: string | null
  human_error_message?: string | null
  is_active?: boolean
  created_at?: string | null
  updated_at?: string | null
  scheduled_for?: string | null
  due_at?: string | null
  expires_at?: string | null
  lifecycle?: Array<{ status: string; at: string; source?: string | null }>
  timeline?: Array<{
    event_id: string
    event_type: string
    at: string
    reason_code?: string | null
    error_code?: string | null
    reason?: string | null
  }>
}

async function loginAsAdmin(page: import('@playwright/test').Page): Promise<void> {
  await page.goto('/testing/login?email=agronomist@example.com', { waitUntil: 'load' })
  await page.waitForSelector('#app[data-page]', { state: 'attached', timeout: 60000 })
}

async function resolveFirstZoneId(page: import('@playwright/test').Page): Promise<number | null> {
  const apiResponse = await page.request.get('/api/zones')
  if (apiResponse.ok()) {
    const payload = await apiResponse.json()
    const apiItems = Array.isArray(payload?.data?.data)
      ? payload.data.data
      : (Array.isArray(payload?.data) ? payload.data : [])

    const firstApiItem = apiItems[0]
    const apiId = firstApiItem?.id
    if (typeof apiId === 'number') return apiId
    if (typeof apiId === 'string' && apiId.trim() !== '') {
      const parsedId = Number.parseInt(apiId, 10)
      if (Number.isFinite(parsedId)) return parsedId
    }
  }

  await page.goto('/zones', { waitUntil: 'load' })
  await page.waitForSelector('#app[data-page]', { state: 'attached', timeout: 60000 })

  return await page.evaluate(() => {
    const payload = document.getElementById('app')?.dataset?.page
    if (!payload) return null

    const parsed = JSON.parse(payload)
    const zones = parsed?.props?.zones
    if (!Array.isArray(zones) || zones.length === 0) return null

    const id = zones[0]?.id
    if (typeof id === 'number') return id
    if (typeof id === 'string' && id.trim() !== '') {
      const parsedId = Number.parseInt(id, 10)
      return Number.isFinite(parsedId) ? parsedId : null
    }
    return null
  })
}

const baseRuns: ExecutionRun[] = [
  {
    execution_id: '601',
    task_id: 'ae-task-601',
    zone_id: 1,
    task_type: 'irrigation',
    status: 'completed',
    current_stage: 'finished',
    created_at: '2026-02-10T08:00:00Z',
    updated_at: '2026-02-10T08:01:00Z',
    scheduled_for: '2026-02-10T08:00:00Z',
    due_at: '2026-02-10T08:00:30Z',
    expires_at: '2026-02-10T08:05:00Z',
  },
  {
    execution_id: '602',
    task_id: 'ae-task-602',
    zone_id: 1,
    task_type: 'irrigation',
    status: 'running',
    current_stage: 'clean_fill',
    created_at: '2026-02-10T08:10:00Z',
    updated_at: '2026-02-10T08:10:20Z',
    scheduled_for: '2026-02-10T08:10:00Z',
    due_at: '2026-02-10T08:10:30Z',
    expires_at: '2026-02-10T08:15:00Z',
  },
  {
    execution_id: '603',
    task_id: 'ae-task-603',
    zone_id: 1,
    task_type: 'irrigation',
    status: 'failed',
    current_stage: 'timeout',
    created_at: '2026-02-10T08:20:00Z',
    updated_at: '2026-02-10T08:22:30Z',
    scheduled_for: '2026-02-10T08:20:00Z',
    due_at: '2026-02-10T08:20:30Z',
    expires_at: '2026-02-10T08:25:00Z',
  },
]

const detailsByExecutionId: Record<string, ExecutionRun> = {
  '601': {
    ...baseRuns[0],
    chain: [
      { step: 'SNAPSHOT', ref: 'workspace', detail: 'Targets and schedule loaded', status: 'ok', at: '2026-02-10T08:00:00Z' },
      { step: 'DECISION', ref: 'intent', detail: 'cycle_start_initiated', status: 'ok', at: '2026-02-10T08:00:00Z' },
      { step: 'TASK', ref: 'ae-task-601', detail: 'Task accepted by AE3', status: 'ok', at: '2026-02-10T08:00:05Z' },
      { step: 'COMPLETE', ref: 'done', detail: 'done', status: 'ok', at: '2026-02-10T08:01:00Z' },
    ],
    lifecycle: [
      { status: 'accepted', at: '2026-02-10T08:00:00Z', source: 'intent' },
      { status: 'completed', at: '2026-02-10T08:01:00Z', source: 'ae_task' },
    ],
    timeline: [
      {
        event_id: 'evt-601-1',
        event_type: 'TASK_RECEIVED',
        at: '2026-02-10T08:00:00Z',
        reason_code: 'cycle_start_initiated',
      },
      {
        event_id: 'evt-601-2',
        event_type: 'TASK_FINISHED',
        at: '2026-02-10T08:01:00Z',
        reason_code: 'done',
      },
    ],
  },
  '602': {
    ...baseRuns[1],
    is_active: true,
    chain: [
      { step: 'SNAPSHOT', ref: 'workspace', detail: 'Targets and schedule loaded', status: 'ok', at: '2026-02-10T08:10:00Z' },
      { step: 'DECISION', ref: 'intent', detail: 'cycle_start_initiated', status: 'ok', at: '2026-02-10T08:10:00Z' },
      { step: 'RUNNING', ref: 'clean_fill', detail: 'clean_fill', status: 'run', live: true, at: '2026-02-10T08:10:10Z' },
      { step: 'DISPATCH', ref: 'pump_start', detail: 'pump_start', status: 'run', live: true, at: '2026-02-10T08:10:20Z' },
    ],
    lifecycle: [
      { status: 'accepted', at: '2026-02-10T08:10:00Z', source: 'intent' },
      { status: 'running', at: '2026-02-10T08:10:05Z', source: 'ae_task' },
    ],
    timeline: [
      {
        event_id: 'evt-602-1',
        event_type: 'TASK_RECEIVED',
        at: '2026-02-10T08:10:00Z',
        reason_code: 'cycle_start_initiated',
      },
      {
        event_id: 'evt-602-2',
        event_type: 'AE_CURRENT_STAGE',
        at: '2026-02-10T08:10:10Z',
        reason_code: 'clean_fill',
      },
      {
        event_id: 'evt-602-3',
        event_type: 'COMMAND_DISPATCHED',
        at: '2026-02-10T08:10:20Z',
        reason_code: 'pump_start',
      },
    ],
  },
  '603': {
    ...baseRuns[2],
    error_code: 'cycle_start_refill_timeout',
    human_error_message: 'Бак чистой воды не заполнился до таймаута',
    chain: [
      { step: 'SNAPSHOT', ref: 'workspace', detail: 'Targets and schedule loaded', status: 'ok', at: '2026-02-10T08:20:00Z' },
      { step: 'DECISION', ref: 'intent', detail: 'cycle_start_initiated', status: 'ok', at: '2026-02-10T08:20:00Z' },
      { step: 'FAIL', ref: 'cycle_start_refill_timeout', detail: 'Бак чистой воды не заполнился до таймаута', status: 'err', at: '2026-02-10T08:22:30Z' },
    ],
    lifecycle: [
      { status: 'accepted', at: '2026-02-10T08:20:00Z', source: 'intent' },
      { status: 'failed', at: '2026-02-10T08:22:30Z', source: 'ae_task' },
    ],
    timeline: [
      {
        event_id: 'evt-603-1',
        event_type: 'TASK_RECEIVED',
        at: '2026-02-10T08:20:00Z',
        reason_code: 'cycle_start_initiated',
      },
      {
        event_id: 'evt-603-2',
        event_type: 'TASK_FINISHED',
        at: '2026-02-10T08:22:30Z',
        reason_code: 'cycle_start_refill_timeout',
        error_code: 'cycle_start_refill_timeout',
        reason: 'Бак чистой воды не заполнился до таймаута',
      },
    ],
  },
}

test.describe('Scheduler workspace lifecycle на вкладке Планировщик', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page)
    const zoneId = await resolveFirstZoneId(page)
    test.skip(zoneId === null, 'Нет зон в тестовой БД для проверки scheduler workspace UI')

    await page.route(`**/api/zones/${zoneId}/schedule-workspace**`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'ok',
          data: {
            control: {
              automation_runtime: 'ae3',
              control_mode: 'auto',
              allowed_manual_steps: [],
              generated_at: '2026-02-10T08:22:30Z',
              timezone: 'Europe/Simferopol',
            },
            capabilities: {
              executable_task_types: ['irrigation', 'lighting', 'diagnostics'],
              planned_task_types: ['irrigation', 'lighting'],
              non_executable_planned_task_types: [],
              diagnostics_available: true,
            },
            plan: {
              horizon: '24h',
              lanes: [
                { task_type: 'irrigation', label: 'Полив', mode: 'interval', executable: true },
                { task_type: 'lighting', label: 'Свет', mode: 'config', executable: true },
              ],
              windows: [
                {
                  plan_window_id: 'pw-1',
                  zone_id: zoneId,
                  task_type: 'irrigation',
                  label: 'Irrigation window',
                  schedule_key: 'irrigation:interval',
                  trigger_at: '2026-02-10T08:25:00Z',
                  origin: 'schedule-loader',
                  state: 'planned',
                  mode: 'interval',
                },
              ],
              summary: {
                planned_total: 1,
                suppressed_total: 0,
                missed_total: 0,
              },
            },
            execution: {
              active_run: { ...baseRuns[1], zone_id: zoneId },
              recent_runs: baseRuns.map((run) => ({ ...run, zone_id: zoneId })),
              counters: {
                active: 1,
                completed_24h: 1,
                failed_24h: 1,
              },
            },
          },
        }),
      })
    })

    await page.route(`**/api/zones/${zoneId}/executions/*`, async (route) => {
      const executionId = route.request().url().split('/').pop() ?? ''
      const details = detailsByExecutionId[executionId]

      if (!details) {
        await route.fulfill({
          status: 404,
          contentType: 'application/json',
          body: JSON.stringify({ status: 'error', message: 'Execution not found' }),
        })
        return
      }

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok', data: { ...details, zone_id: zoneId } }),
      })
    })

    await page.goto(`/zones/${zoneId}`, { waitUntil: 'load' })
    await page.getByRole('tab', { name: 'Планировщик' }).click()
    await expect(page.getByTestId('scheduler-root')).toBeVisible()
    await expect(page.getByText('Планировщик зоны')).toBeVisible()
    await expect(page.getByRole('button', { name: /#601/ })).toBeVisible()
  })

  test('показывает completed run с lifecycle и timeline', async ({ page }) => {
    await page.getByRole('button', { name: /#601/ }).click()

    const chain = page.getByTestId('scheduler-causal-chain')
    await expect(chain).toBeVisible()
    await expect(chain.getByText('ЦЕПОЧКА РЕШЕНИЙ')).toBeVisible()
    await expect(chain.getByText('SNAPSHOT')).toBeVisible()
    await expect(chain.getByTestId('scheduler-chain-step-COMPLETE')).toBeVisible()
    await expect(chain.getByText('done').first()).toBeVisible()
  })

  test('показывает running run с текущим stage', async ({ page }) => {
    await page.getByRole('button', { name: /#602/ }).click()

    const chain = page.getByTestId('scheduler-causal-chain')
    await expect(chain).toBeVisible()
    await expect(chain.getByText('RUNNING')).toBeVisible()
    await expect(chain.getByText('clean_fill').first()).toBeVisible()
    await expect(chain.getByText('DISPATCH')).toBeVisible()
    await expect(chain.getByText('pump_start').first()).toBeVisible()
  })

  test('показывает failed run с reason и error code', async ({ page }) => {
    await page.getByRole('button', { name: /#603/ }).click()

    const chain = page.getByTestId('scheduler-causal-chain')
    await expect(chain).toBeVisible()
    await expect(chain.getByTestId('scheduler-chain-step-FAIL')).toBeVisible()
    await expect(chain.getByText('cycle_start_refill_timeout').first()).toBeVisible()
    await expect(chain.getByText('Бак чистой воды не заполнился до таймаута').first()).toBeVisible()
  })
})

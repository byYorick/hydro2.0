import { expect, test } from '@playwright/test'

type SchedulerTaskStatus = {
  task_id: string
  zone_id: number
  task_type: string
  status: string
  created_at: string
  updated_at: string
  scheduled_for: string | null
  correlation_id: string | null
  action_required?: boolean | null
  decision?: string | null
  reason_code?: string | null
  reason?: string | null
  error?: string | null
  error_code?: string | null
  lifecycle: Array<{ status: string; at: string }>
  timeline: Array<{
    event_id: string
    event_type: string
    at: string
    reason_code?: string | null
    reason?: string | null
    error_code?: string | null
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

const listItems: SchedulerTaskStatus[] = [
  {
    task_id: 'st-skip',
    zone_id: 1,
    task_type: 'irrigation',
    status: 'completed',
    created_at: '2026-02-10T08:00:00Z',
    updated_at: '2026-02-10T08:01:00Z',
    scheduled_for: '2026-02-10T08:00:00Z',
    correlation_id: 'sch:z1:irrigation:skip',
    lifecycle: [
      { status: 'accepted', at: '2026-02-10T08:00:00Z' },
      { status: 'completed', at: '2026-02-10T08:01:00Z' },
    ],
    timeline: [],
  },
  {
    task_id: 'st-refill',
    zone_id: 1,
    task_type: 'diagnostics',
    status: 'completed',
    created_at: '2026-02-10T08:10:00Z',
    updated_at: '2026-02-10T08:11:00Z',
    scheduled_for: '2026-02-10T08:10:00Z',
    correlation_id: 'sch:z1:diagnostics:refill',
    lifecycle: [
      { status: 'accepted', at: '2026-02-10T08:10:00Z' },
      { status: 'completed', at: '2026-02-10T08:11:00Z' },
    ],
    timeline: [],
  },
  {
    task_id: 'st-timeout',
    zone_id: 1,
    task_type: 'diagnostics',
    status: 'failed',
    created_at: '2026-02-10T08:20:00Z',
    updated_at: '2026-02-10T08:22:30Z',
    scheduled_for: '2026-02-10T08:20:00Z',
    correlation_id: 'sch:z1:diagnostics:timeout',
    lifecycle: [
      { status: 'accepted', at: '2026-02-10T08:20:00Z' },
      { status: 'running', at: '2026-02-10T08:20:01Z' },
      { status: 'failed', at: '2026-02-10T08:22:30Z' },
    ],
    timeline: [],
  },
]

const detailsByTaskId: Record<string, SchedulerTaskStatus> = {
  'st-skip': {
    ...listItems[0],
    action_required: false,
    decision: 'skip',
    reason_code: 'irrigation_not_required',
    reason: 'Влажность субстрата в целевом диапазоне',
    error: null,
    error_code: null,
    timeline: [
      {
        event_id: 'evt-skip-1',
        event_type: 'TASK_STARTED',
        at: '2026-02-10T08:00:00Z',
      },
      {
        event_id: 'evt-skip-2',
        event_type: 'DECISION_MADE',
        reason_code: 'irrigation_not_required',
        at: '2026-02-10T08:00:10Z',
      },
      {
        event_id: 'evt-skip-3',
        event_type: 'TASK_FINISHED',
        at: '2026-02-10T08:01:00Z',
      },
    ],
  },
  'st-refill': {
    ...listItems[1],
    action_required: true,
    decision: 'run',
    reason_code: 'tank_refill_started',
    reason: 'Запущено наполнение бака и запланирована отложенная проверка',
    error: null,
    error_code: null,
    timeline: [
      {
        event_id: 'evt-refill-1',
        event_type: 'CYCLE_START_INITIATED',
        at: '2026-02-10T08:10:00Z',
      },
      {
        event_id: 'evt-refill-2',
        event_type: 'TANK_REFILL_STARTED',
        reason_code: 'tank_refill_started',
        at: '2026-02-10T08:10:20Z',
      },
      {
        event_id: 'evt-refill-3',
        event_type: 'SELF_TASK_ENQUEUED',
        reason_code: 'tank_refill_in_progress',
        at: '2026-02-10T08:10:21Z',
      },
    ],
  },
  'st-timeout': {
    ...listItems[2],
    action_required: true,
    decision: 'fail',
    reason_code: 'cycle_start_refill_timeout',
    reason: 'Бак чистой воды не заполнился до таймаута',
    error: 'cycle_start_refill_timeout',
    error_code: 'cycle_start_refill_timeout',
    timeline: [
      {
        event_id: 'evt-timeout-1',
        event_type: 'CYCLE_START_INITIATED',
        at: '2026-02-10T08:20:00Z',
      },
      {
        event_id: 'evt-timeout-2',
        event_type: 'TANK_REFILL_TIMEOUT',
        reason_code: 'cycle_start_refill_timeout',
        error_code: 'cycle_start_refill_timeout',
        at: '2026-02-10T08:22:30Z',
      },
      {
        event_id: 'evt-timeout-3',
        event_type: 'TASK_FINISHED',
        at: '2026-02-10T08:22:30Z',
      },
    ],
  },
}

test.describe('Scheduler lifecycle в вкладке Автоматизация', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page)
    const zoneId = await resolveFirstZoneId(page)
    test.skip(zoneId === null, 'Нет зон в тестовой БД для проверки lifecycle UI')

    await page.route(`**/api/zones/${zoneId}/scheduler-tasks**`, async (route) => {
      const url = new URL(route.request().url())
      const pathname = url.pathname

      if (pathname === `/api/zones/${zoneId}/scheduler-tasks`) {
        const responseItems = listItems.map((item) => ({ ...item, zone_id: zoneId }))
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ status: 'ok', data: responseItems }),
        })
        return
      }

      const taskId = pathname.split('/').pop() ?? ''
      const details = detailsByTaskId[taskId]
      if (!details) {
        await route.fulfill({
          status: 404,
          contentType: 'application/json',
          body: JSON.stringify({ status: 'error', message: 'Task not found' }),
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
    await page.getByRole('tab', { name: 'Автоматизация' }).click()
    await expect(page.getByRole('heading', { name: 'Scheduler Task Lifecycle' })).toBeVisible()
    await expect(page.locator('li', { hasText: 'st-skip' })).toBeVisible()
  })

  test('показывает сценарий completed+skip (действие не требуется)', async ({ page }) => {
    await page.locator('li', { hasText: 'st-skip' }).getByRole('button', { name: 'Открыть' }).click()

    await expect(page.getByText('task_id:')).toBeVisible()
    await expect(page.getByText('st-skip').first()).toBeVisible()
    await expect(page.getByText('Пропустить')).toBeVisible()
    await expect(page.getByText('Действие не требуется (irrigation_not_required)').first()).toBeVisible()
    await expect(page.getByText('Решение принято')).toBeVisible()
  })

  test('показывает сценарий refill in progress с self-task', async ({ page }) => {
    await page.locator('li', { hasText: 'st-refill' }).getByRole('button', { name: 'Открыть' }).click()

    await expect(page.getByText('st-refill').first()).toBeVisible()
    await expect(page.getByText('Выполнить')).toBeVisible()
    await expect(page.getByText('Наполнение бака запущено (tank_refill_started)').first()).toBeVisible()
    await expect(page.getByText('Запуск цикла инициирован')).toBeVisible()
    await expect(page.getByText('Запущено наполнение бака')).toBeVisible()
    await expect(page.getByText('Запланирована отложенная проверка')).toBeVisible()
  })

  test('показывает сценарий timeout с reason/error кодами', async ({ page }) => {
    await page.locator('li', { hasText: 'st-timeout' }).getByRole('button', { name: 'Открыть' }).click()

    await expect(page.getByText('st-timeout').first()).toBeVisible()
    await expect(page.getByText('Ошибка').first()).toBeVisible()
    await expect(page.locator('dd', { hasText: 'Таймаут наполнения бака (cycle_start_refill_timeout)' }).first()).toBeVisible()
    await expect(page.getByText('Таймаут наполнения бака').first()).toBeVisible()
  })
})

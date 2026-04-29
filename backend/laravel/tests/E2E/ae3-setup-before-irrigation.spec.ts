import { expect, test } from '@playwright/test'

type ExecutionRun = {
  execution_id: string
  task_id: string
  zone_id: number
  task_type: string
  status: string
  current_stage?: string | null
  workflow_phase?: string | null
  is_active?: boolean
}

async function loginAsAdmin(page: import('@playwright/test').Page): Promise<void> {
  await page.goto('/testing/login?email=agronomist@example.com', { waitUntil: 'load' })
  await page.waitForSelector('#app[data-page]', { state: 'attached', timeout: 60000 })
}

async function resolveFirstZoneId(page: import('@playwright/test').Page): Promise<number | null> {
  const response = await page.request.get('/api/zones')
  if (response.ok()) {
    const payload = await response.json()
    const zones = Array.isArray(payload?.data?.data)
      ? payload.data.data
      : (Array.isArray(payload?.data) ? payload.data : [])
    const id = zones[0]?.id
    if (typeof id === 'number') return id
    if (typeof id === 'string' && id.trim() !== '') {
      const parsed = Number.parseInt(id, 10)
      if (Number.isFinite(parsed)) return parsed
    }
  }
  return null
}

test('AE3 scheduler не запускает irrigation до READY', async ({ page }) => {
  await loginAsAdmin(page)
  const zoneId = await resolveFirstZoneId(page)
  test.skip(zoneId === null, 'Нет зон в тестовой БД для e2e smoke сценария')

  let phase: 'setup_pending' | 'ready' = 'setup_pending'

  const cycleStartRun: ExecutionRun = {
    execution_id: '701',
    task_id: 'ae-task-701',
    zone_id: zoneId!,
    task_type: 'cycle_start',
    status: 'running',
    current_stage: 'clean_fill',
    workflow_phase: 'tank_filling',
    is_active: true,
  }
  const irrigationRun: ExecutionRun = {
    execution_id: '702',
    task_id: 'ae-task-702',
    zone_id: zoneId!,
    task_type: 'irrigation_start',
    status: 'running',
    current_stage: 'await_ready',
    workflow_phase: 'ready',
    is_active: true,
  }

  await page.route(`**/api/zones/${zoneId}/schedule-workspace**`, async (route) => {
    const recentRuns = phase === 'setup_pending'
      ? [cycleStartRun]
      : [{ ...cycleStartRun, status: 'completed', is_active: false, current_stage: 'done', workflow_phase: 'ready' }, irrigationRun]

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
            generated_at: new Date().toISOString(),
            timezone: 'UTC',
          },
          capabilities: {
            executable_task_types: ['irrigation', 'lighting', 'diagnostics'],
            planned_task_types: ['irrigation', 'lighting'],
            non_executable_planned_task_types: [],
            diagnostics_available: true,
          },
          plan: {
            horizon: '24h',
            lanes: [{ task_type: 'irrigation', label: 'Полив', mode: 'interval', executable: true }],
            windows: [],
            summary: { planned_total: 0, suppressed_total: 0, missed_total: 0 },
          },
          execution: {
            active_run: recentRuns.find((run) => run.is_active) ?? null,
            recent_runs: recentRuns,
            counters: {
              active: recentRuns.filter((run) => run.is_active).length,
              completed_24h: 0,
              failed_24h: 0,
            },
            latest_failure: null,
          },
        },
      }),
    })
  })

  await page.route(`**/api/zones/${zoneId}/scheduler-diagnostics**`, async (route) => {
    const diagnostics = phase === 'setup_pending'
      ? {
          status: 'ok',
          data: {
            zone_id: zoneId,
            generated_at: new Date().toISOString(),
            sources: { dispatcher_tasks: true, scheduler_logs: true },
            summary: {
              tracked_tasks_total: 1,
              active_tasks_total: 1,
              overdue_tasks_total: 0,
              stale_tasks_total: 0,
              recent_logs_total: 1,
              last_log_at: new Date().toISOString(),
            },
            dispatcher_tasks: [
              {
                task_id: '701',
                task_type: 'cycle_start',
                status: 'running',
                schedule_key: 'cycle_start:auto',
              },
            ],
            recent_logs: [
              {
                log_id: 9001,
                task_name: `zone_${zoneId}_irrigation`,
                status: 'skipped',
                created_at: new Date().toISOString(),
                details: {
                  reason: 'zone_setup_pending',
                  workflow_phase: 'tank_filling',
                },
              },
            ],
          },
        }
      : {
          status: 'ok',
          data: {
            zone_id: zoneId,
            generated_at: new Date().toISOString(),
            sources: { dispatcher_tasks: true, scheduler_logs: true },
            summary: {
              tracked_tasks_total: 2,
              active_tasks_total: 1,
              overdue_tasks_total: 0,
              stale_tasks_total: 0,
              recent_logs_total: 1,
              last_log_at: new Date().toISOString(),
            },
            dispatcher_tasks: [
              {
                task_id: '702',
                task_type: 'irrigation_start',
                status: 'running',
                schedule_key: 'irrigation:interval',
              },
            ],
            recent_logs: [
              {
                log_id: 9002,
                task_name: `zone_${zoneId}_irrigation`,
                status: 'dispatched',
                created_at: new Date().toISOString(),
                details: {
                  reason: 'ok',
                  workflow_phase: 'ready',
                },
              },
            ],
          },
        }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(diagnostics),
    })
  })

  await page.goto(`/zones/${zoneId}`, { waitUntil: 'load' })
  await page.getByRole('tab', { name: 'Планировщик' }).click()

  await expect(page.getByTestId('scheduler-runs-row-701')).toBeVisible()
  await expect(page.getByTestId('scheduler-runs-row-702')).toHaveCount(0)

  phase = 'ready'
  await page.reload({ waitUntil: 'load' })
  await page.getByRole('tab', { name: 'Планировщик' }).click()

  await expect(page.getByTestId('scheduler-runs-row-702')).toBeVisible()
})

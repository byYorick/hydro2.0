import { test, expect } from '../fixtures/test-data';
import { TEST_IDS } from '../constants';

function decodeHtmlAttribute(value: string): string {
  return value
    .replace(/&quot;/g, '"')
    .replace(/&#039;/g, "'")
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>');
}

function encodeHtmlAttribute(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

async function injectZoneEventsIntoInertiaPage(page: import('@playwright/test').Page, zoneId: number, events: Array<Record<string, unknown>>) {
  await page.route(new RegExp(`/zones/${zoneId}(?:\\?.*)?$`), async (route) => {
    const response = await route.fetch();
    const html = await response.text();

    const match = html.match(/id="app"[^>]*data-page="([^"]+)"/);
    if (!match) {
      await route.fulfill({ response, body: html });
      return;
    }

    const pageJson = JSON.parse(decodeHtmlAttribute(match[1]));
    pageJson.props = {
      ...pageJson.props,
      events,
    };

    const nextHtml = html.replace(
      match[0],
      match[0].replace(match[1], encodeHtmlAttribute(JSON.stringify(pageJson))),
    );

    await route.fulfill({
      response,
      body: nextHtml,
      headers: {
        ...response.headers(),
        'content-type': 'text/html; charset=utf-8',
      },
    });
  });
}

test.describe('Zone Detail', () => {
  test('should load zone detail page and display snapshot', async ({ page, testZone, testGreenhouse }) => {
    await page.goto(`/zones/${testZone.id}`, { waitUntil: 'networkidle' });
    await page.waitForSelector('h1, [data-testid*="zone"]', { timeout: 15000 });

    // Проверяем наличие Badge статуса (может быть в разных местах)
    const statusBadge = page.locator(`[data-testid="${TEST_IDS.ZONE_STATUS_BADGE}"]`)
      .or(page.locator('text=/PLANNED|RUNNING|PAUSED|HARVESTED/i').first());
    await expect(statusBadge.first()).toBeVisible({ timeout: 10000 });

    // Проверяем наличие списка событий (snapshot должен быть загружен)
    const eventsList = page.locator(`[data-testid="${TEST_IDS.ZONE_EVENTS_LIST}"]`)
      .or(page.locator('text=/События|Events/i').locator('..'));
    await expect(eventsList.first()).toBeVisible({ timeout: 15000 });
  });

  test('should display events list', async ({ page, testZone }) => {
    await page.goto(`/zones/${testZone.id}`, { waitUntil: 'networkidle' });
    await page.waitForSelector('h1, [data-testid*="zone"]', { timeout: 15000 });

    // Проверяем наличие списка событий
    const eventsList = page.locator(`[data-testid="${TEST_IDS.ZONE_EVENTS_LIST}"]`)
      .or(page.locator('text=/События|Events/i').locator('..'));
    await expect(eventsList.first()).toBeVisible({ timeout: 15000 });
  });

  test('should show new events after actions', async ({ page, testZone, apiHelper }) => {
    await page.goto(`/zones/${testZone.id}`, { waitUntil: 'networkidle' });
    await page.waitForSelector('h1, [data-testid*="zone"]', { timeout: 15000 });

    // Получаем начальное количество событий
    const eventsList = page.locator(`[data-testid="${TEST_IDS.ZONE_EVENTS_LIST}"]`)
      .or(page.locator('text=/События|Events/i').locator('..'));
    await expect(eventsList.first()).toBeVisible({ timeout: 15000 });

    // Выполняем действие (например, запуск зоны)
    try {
      await apiHelper.startZone(testZone.id);
    } catch (e) {
      // Если зона уже запущена, это нормально
      console.log('Zone might already be started:', e);
    }

    // Ждем обновления страницы или появления нового события
    // В реальном приложении события могут обновляться через WebSocket
    await page.waitForTimeout(3000);
    await page.reload({ waitUntil: 'networkidle' });

    // Проверяем, что список событий все еще виден (новые события должны появиться)
    await expect(eventsList.first()).toBeVisible({ timeout: 10000 });
  });

  test('should group correlated AE3 runtime events on events tab', async ({ page, testZone }) => {
    await injectZoneEventsIntoInertiaPage(page, testZone.id, [
      {
        id: 9003,
        kind: 'EC_DOSING',
        message: 'EC: подача питания',
        occurred_at: '2026-04-10T08:20:25Z',
        payload: {
          task_id: 28,
          correction_window_id: 'task:28:irrigating:irrigation_check',
          workflow_phase: 'irrigating',
          stage: 'irrigation_check',
          selected_action: 'ec',
          snapshot_event_id: 1699,
          event_schema_version: 2,
        },
      },
      {
        id: 9002,
        kind: 'IRRIGATION_CORRECTION_STARTED',
        message: 'Полив: окно inline-коррекции открыто',
        occurred_at: '2026-04-10T08:20:22Z',
        payload: {
          task_id: 28,
          correction_window_id: 'task:28:irrigating:irrigation_check',
          workflow_phase: 'irrigating',
          stage: 'irrigation_check',
          selected_action: 'ec',
          channel: 'pump_a',
          node_uid: 'nd-test-ec-1',
          snapshot_event_id: 1699,
          caused_by_event_id: 1698,
          event_schema_version: 2,
        },
      },
      {
        id: 9001,
        kind: 'CORRECTION_DECISION_MADE',
        message: 'Коррекция: выбран следующий шаг',
        occurred_at: '2026-04-10T08:20:20Z',
        payload: {
          task_id: 28,
          correction_window_id: 'task:28:irrigating:irrigation_check',
          workflow_phase: 'irrigating',
          stage: 'irrigation_check',
          selected_action: 'ec',
          decision_reason: 'ec_first_in_window',
          needs_ec: true,
          needs_ph_down: true,
        },
      },
      {
        id: 8999,
        kind: 'ALERT_CREATED',
        message: 'Тревога создана',
        occurred_at: '2026-04-10T08:19:20Z',
        payload: {
          severity: 'warning',
        },
      },
    ]);

    await page.goto(`/zones/${testZone.id}?tab=events`, { waitUntil: 'networkidle' });
    await expect(page.getByRole('tab', { name: 'События' })).toBeVisible({ timeout: 15000 });

    await expect(page.getByText('AE задача #28 · Окно irrigation_check')).toBeVisible({ timeout: 15000 });
    await expect(page.getByText('irrigating / irrigation_check')).toBeVisible({ timeout: 15000 });
    await expect(page.getByText('3 события')).toBeVisible({ timeout: 15000 });
    await expect(page.getByText('Тревога создана').first()).toBeVisible({ timeout: 15000 });

    await page.getByText('Полив: окно inline-коррекции открыто').last().click();

    await expect(page.getByText('Snapshot event ID:')).toBeVisible({ timeout: 15000 });
    await expect(page.getByText('1699')).toBeVisible({ timeout: 15000 });
    await expect(page.getByText('Причинное событие ID:')).toBeVisible({ timeout: 15000 });
    await expect(page.getByText('1698')).toBeVisible({ timeout: 15000 });
    await expect(page.getByText('Schema version:')).toBeVisible({ timeout: 15000 });
  });

  test('should open zone alert details from alerts tab', async ({ page, apiHelper, testZone }) => {
    test.setTimeout(60000);

    const alert = await apiHelper.seedZoneAlert(testZone.id);

    try {
      await page.goto(`/zones/${testZone.id}?tab=alerts`, { waitUntil: 'load' });
      await expect(page.getByRole('tab', { name: 'Алерты' })).toBeVisible({ timeout: 15000 });

      const alertRow = page.locator('[data-testid^="zone-alert-row-"]').first();
      await expect(alertRow).toBeVisible({ timeout: 15000 });

      await alertRow.click();

      const detailsModal = page.locator('[data-testid="zone-alert-details-modal"]').last();
      await expect(detailsModal).toBeVisible({ timeout: 15000 });
      await expect(detailsModal).toContainText('Детали алерта');
      await expect(detailsModal).toContainText(/тип/i);
      await expect(detailsModal).toContainText(/статус/i);

      const hasCode = await detailsModal.getByText('Код').isVisible().catch(() => false);
      const hasPayload = await detailsModal.getByText('Payload details').isVisible().catch(() => false);
      expect(hasCode || hasPayload).toBe(true);
    } finally {
      await apiHelper.deleteAlert(alert.id).catch(() => {});
    }
  });

  test('should render scheduler workspace and execution details on scheduler tab', async ({ page, apiHelper, testGreenhouse }) => {
    test.setTimeout(60000);

    const zone = await apiHelper.createTestZone(testGreenhouse.id);
    const executionId = '501';
    const now = Date.now();
    const scheduledFor = new Date(now - 2 * 60 * 1000).toISOString();
    const dueAt = new Date(now - 60 * 1000).toISOString();
    const expiresAt = new Date(now - 5 * 1000).toISOString();

    try {
      await page.route(new RegExp(`/api/zones/${zone.id}/schedule-workspace(?:\\?.*)?$`), async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            status: 'ok',
            data: {
              control: {
                automation_runtime: 'ae3',
                control_mode: 'semi',
                allowed_manual_steps: ['clean_fill_start', 'solution_fill_stop'],
                generated_at: new Date().toISOString(),
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
                    plan_window_id: 'pw-e2e-1',
                    zone_id: zone.id,
                    task_type: 'irrigation',
                    schedule_key: 'irrigation:interval',
                    trigger_at: scheduledFor,
                    origin: 'schedule-loader',
                    state: 'planned',
                    mode: 'interval',
                    label: 'Irrigation window',
                  },
                ],
                summary: {
                  planned_total: 1,
                  suppressed_total: 0,
                  missed_total: 0,
                },
              },
              execution: {
                active_run: {
                  execution_id: executionId,
                  task_id: 'ae-task-501',
                  zone_id: zone.id,
                  task_type: 'irrigation',
                  status: 'running',
                  current_stage: 'clean_fill',
                  created_at: scheduledFor,
                  updated_at: expiresAt,
                  scheduled_for: scheduledFor,
                  due_at: dueAt,
                  expires_at: expiresAt,
                },
                recent_runs: [
                  {
                    execution_id: executionId,
                    task_id: 'ae-task-501',
                    zone_id: zone.id,
                    task_type: 'irrigation',
                    status: 'running',
                    current_stage: 'clean_fill',
                    created_at: scheduledFor,
                    updated_at: expiresAt,
                    scheduled_for: scheduledFor,
                    due_at: dueAt,
                    expires_at: expiresAt,
                  },
                ],
                counters: {
                  active: 1,
                  completed_24h: 2,
                  failed_24h: 0,
                },
              },
            },
          }),
        });
      });

      await page.route(new RegExp(`/api/zones/${zone.id}/executions/${executionId}(?:\\?.*)?$`), async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            status: 'ok',
            data: {
              execution_id: executionId,
              task_id: 'ae-task-501',
              zone_id: zone.id,
              task_type: 'irrigation',
              status: 'running',
              created_at: scheduledFor,
              updated_at: expiresAt,
              scheduled_for: scheduledFor,
              due_at: dueAt,
              expires_at: expiresAt,
              current_stage: 'clean_fill',
              lifecycle: [
                { status: 'accepted', at: scheduledFor, source: 'intent' },
                { status: 'running', at: dueAt, source: 'ae_task' },
              ],
              timeline: [
                {
                  event_id: 'evt-e2e-1',
                  event_seq: 1,
                  event_type: 'TASK_RECEIVED',
                  at: scheduledFor,
                  reason_code: 'cycle_start_initiated',
                },
                {
                  event_id: 'evt-e2e-2',
                  event_seq: 2,
                  event_type: 'AE_CURRENT_STAGE',
                  at: dueAt,
                  reason_code: 'clean_fill',
                },
                {
                  event_id: 'evt-e2e-3',
                  event_seq: 3,
                  event_type: 'COMMAND_DISPATCHED',
                  at: expiresAt,
                  reason_code: 'pump_start',
                },
              ],
            },
          }),
        });
      });

      await page.goto(`/zones/${zone.id}`, { waitUntil: 'load' });
      await page.getByRole('tab', { name: 'Планировщик' }).click();
      await expect(page.getByRole('heading', { level: 3, name: 'Планировщик зоны' })).toBeVisible({ timeout: 15000 });

      await expect(page.getByText('Live sync')).toBeVisible({ timeout: 15000 });
      await expect(page.getByText('Окна').first()).toBeVisible({ timeout: 15000 });
      await expect(page.getByText('исполнимых').first()).toBeVisible({ timeout: 15000 });
      await expect(page.getByText('Активные').first()).toBeVisible({ timeout: 15000 });
      await expect(page.getByText('сейчас').first()).toBeVisible({ timeout: 15000 });
      await expect(page.getByText('Полив').first()).toBeVisible({ timeout: 15000 });
      await expect(page.getByText('Лента исполнений')).toBeVisible({ timeout: 15000 });
      await page.getByRole('button', { name: /#501/ }).click();

      await expect(page.getByText('#501').last()).toBeVisible({ timeout: 15000 });
      await expect(page.locator('[data-testid="scheduler-causal-chain"]')).toBeVisible({ timeout: 15000 });
    } finally {
      await apiHelper.deleteZone(zone.id).catch(() => {});
    }
  });

  test('should switch scheduler horizon and render recent runs', async ({ page, apiHelper, testGreenhouse }) => {
    const zone = await apiHelper.createTestZone(testGreenhouse.id);
    const nowIso = new Date().toISOString();

    try {
      await page.route(new RegExp(`/api/zones/${zone.id}/schedule-workspace(?:\\?.*)?$`), async (route) => {
        const url = new URL(route.request().url());
        const horizon = url.searchParams.get('horizon') ?? '24h';
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
                generated_at: nowIso,
                timezone: 'Europe/Simferopol',
              },
              capabilities: {
                executable_task_types: ['irrigation'],
                planned_task_types: ['irrigation'],
                diagnostics_available: true,
              },
              plan: {
                horizon,
                lanes: [
                  { task_type: 'irrigation', label: 'Полив', mode: horizon === '7d' ? 'calendar' : 'interval', executable: true },
                ],
                windows: [
                  {
                    plan_window_id: `pw-${horizon}`,
                    zone_id: zone.id,
                    task_type: 'irrigation',
                    schedule_key: `irrigation:${horizon}`,
                    trigger_at: nowIso,
                    origin: 'schedule-loader',
                    state: 'planned',
                    mode: horizon === '7d' ? 'calendar' : 'interval',
                    label: 'Irrigation window',
                  },
                ],
                summary: {
                  planned_total: 1,
                  suppressed_total: 0,
                  missed_total: 0,
                },
              },
              execution: {
                active_run: null,
                recent_runs: [
                  {
                    execution_id: '701',
                    task_id: 'ae-task-701',
                    zone_id: zone.id,
                    task_type: 'irrigation',
                    status: 'completed',
                    current_stage: 'finished',
                    updated_at: nowIso,
                  },
                  {
                    execution_id: '702',
                    task_id: 'ae-task-702',
                    zone_id: zone.id,
                    task_type: 'irrigation',
                    status: 'failed',
                    current_stage: 'timeout',
                    updated_at: nowIso,
                  },
                ],
                counters: {
                  active: 0,
                  completed_24h: 1,
                  failed_24h: 1,
                },
              },
            },
          }),
        });
      });

      await page.route(new RegExp(`/api/zones/${zone.id}/executions/701(?:\\?.*)?$`), async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            status: 'ok',
            data: {
              execution_id: '701',
              task_id: 'ae-task-701',
              zone_id: zone.id,
              task_type: 'irrigation',
              status: 'completed',
              created_at: nowIso,
              updated_at: nowIso,
              scheduled_for: nowIso,
              due_at: nowIso,
              expires_at: nowIso,
              current_stage: 'finished',
              lifecycle: [{ status: 'completed', at: nowIso, source: 'ae_task' }],
              timeline: [{ event_id: 'evt-701', event_type: 'TASK_FINISHED', at: nowIso, reason_code: 'done' }],
            },
          }),
        });
      });

      await page.goto(`/zones/${zone.id}`, { waitUntil: 'networkidle' });
      await page.getByRole('tab', { name: 'Планировщик' }).click();
      await expect(page.getByRole('heading', { level: 3, name: 'Планировщик зоны' })).toBeVisible({ timeout: 15000 });
      await expect(page.getByRole('button', { name: '24h' })).toBeVisible({ timeout: 15000 });
      await expect(page.getByText('Недавние исполнения')).toBeVisible({ timeout: 15000 });
      await expect(page.getByRole('button', { name: '7d' })).toBeVisible({ timeout: 15000 });
      await expect(page.getByRole('button', { name: /#701/ })).toBeVisible({ timeout: 15000 });
      await expect(page.getByRole('button', { name: /#702/ })).toBeVisible({ timeout: 15000 });

      await page.getByRole('button', { name: '7d' }).click();
      await expect(page.getByRole('button', { name: '7d' })).toBeVisible({ timeout: 15000 });

      await page.getByRole('button', { name: /#701/ }).click();
      await expect(page.getByText('#701').last()).toBeVisible({ timeout: 15000 });
      await expect(page.locator('[data-testid="scheduler-causal-chain"]')).toBeVisible({ timeout: 15000 });
    } finally {
      await apiHelper.deleteZone(zone.id).catch(() => {});
    }
  });

  test('should render scheduler sync page on scheduler tab', async ({ page, apiHelper, testGreenhouse }) => {
    const zone = await apiHelper.createTestZone(testGreenhouse.id);
    const executionId = '880';
    const nowIso = new Date().toISOString();

    try {
      await page.route(new RegExp(`/api/zones/${zone.id}/schedule-workspace(?:\\?.*)?$`), async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            status: 'ok',
            data: {
              control: {
                automation_runtime: 'ae3',
                control_mode: 'semi',
                allowed_manual_steps: ['clean_fill_start', 'solution_fill_stop'],
                generated_at: nowIso,
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
                windows: [],
                summary: {
                  planned_total: 0,
                  suppressed_total: 0,
                  missed_total: 0,
                },
              },
              execution: {
                active_run: {
                  execution_id: executionId,
                  task_id: 'ae-task-880',
                  zone_id: zone.id,
                  task_type: 'irrigation',
                  status: 'running',
                  current_stage: 'clean_fill',
                  created_at: nowIso,
                  updated_at: nowIso,
                  scheduled_for: nowIso,
                },
                recent_runs: [
                  {
                    execution_id: executionId,
                    task_id: 'ae-task-880',
                    zone_id: zone.id,
                    task_type: 'irrigation',
                    status: 'running',
                    current_stage: 'clean_fill',
                    created_at: nowIso,
                    updated_at: nowIso,
                  },
                ],
                counters: {
                  active: 1,
                  completed_24h: 0,
                  failed_24h: 0,
                },
              },
            },
          }),
        });
      });

      await page.route(new RegExp(`/api/zones/${zone.id}/executions/${executionId}(?:\\?.*)?$`), async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            status: 'ok',
            data: {
              execution_id: executionId,
              task_id: 'ae-task-880',
              zone_id: zone.id,
              task_type: 'irrigation',
              status: 'running',
              created_at: nowIso,
              updated_at: nowIso,
              scheduled_for: nowIso,
              due_at: nowIso,
              expires_at: nowIso,
              current_stage: 'clean_fill',
              lifecycle: [
                { status: 'accepted', at: nowIso, source: 'intent' },
              ],
              timeline: [
                {
                  event_id: 'evt-sync-1',
                  event_seq: 1,
                  event_type: 'TASK_RECEIVED',
                  at: nowIso,
                  reason_code: 'cycle_start_initiated',
                },
              ],
            },
          }),
        });
      });

      await page.goto(`/zones/${zone.id}`, { waitUntil: 'networkidle' });
      await page.getByRole('tab', { name: 'Планировщик' }).click();

      await expect(page.getByRole('heading', { level: 3, name: 'Планировщик зоны' })).toBeVisible({ timeout: 15000 });
      await expect(page.getByText('Live sync')).toBeVisible({ timeout: 15000 });
      await expect(page.getByText('полуавто').first()).toBeVisible({ timeout: 15000 });
      await expect(page.getByText('Активные').first()).toBeVisible({ timeout: 15000 });
      await expect(page.getByText('1').first()).toBeVisible({ timeout: 15000 });
      await expect(page.getByText('Активного run нет')).not.toBeVisible();
      await expect(page.getByRole('button', { name: new RegExp(`#${executionId}`) })).toBeVisible({ timeout: 15000 });
    } finally {
      await apiHelper.deleteZone(zone.id).catch(() => {});
    }
  });
});

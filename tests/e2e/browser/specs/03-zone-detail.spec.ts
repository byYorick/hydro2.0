import type { Page } from '@playwright/test';
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

async function installSchedulerWorkspaceMocks(
  page: Page,
  zoneId: number,
  runs: Array<Record<string, unknown>>,
  details: Record<string, Record<string, unknown>>,
): Promise<void> {
  await page.route(new RegExp(`/api/zones/${zoneId}/schedule-workspace(?:\\?.*)?$`), async (route) => {
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
          },
          capabilities: {
            executable_task_types: ['irrigation', 'diagnostics'],
            planned_task_types: ['irrigation', 'diagnostics'],
            diagnostics_available: false,
          },
          plan: {
            horizon: '24h',
            lanes: [],
            windows: [],
            summary: { planned_total: 0, suppressed_total: 0, missed_total: 0 },
          },
          execution: {
            active_run: null,
            recent_runs: runs,
            counters: { active: 0, completed_24h: 2, failed_24h: 1 },
          },
        },
      }),
    });
  });

  await page.route(new RegExp(`/api/zones/${zoneId}/state(?:\\?.*)?$`), async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', data: { zone_id: zoneId, control_mode: 'auto' } }),
    });
  });

  await page.route(new RegExp(`/api/zones/${zoneId}/scheduler-diagnostics(?:\\?.*)?$`), async (route) => {
    await route.fulfill({ status: 403, contentType: 'application/json', body: '{}' });
  });

  await page.route(new RegExp(`/api/zones/${zoneId}/executions/([^/?]+)(?:\\?.*)?$`), async (route) => {
    const id = route.request().url().match(/\/executions\/([^/?]+)/)?.[1] ?? '';
    const payload = details[id];
    await route.fulfill({
      status: payload ? 200 : 404,
      contentType: 'application/json',
      body: JSON.stringify(payload ? { status: 'ok', data: payload } : { status: 'error', code: 'NOT_FOUND' }),
    });
  });
}

function chainStep(step: string, status: string, detail: string, ref: string): Record<string, unknown> {
  return {
    step,
    status,
    detail,
    ref,
    at: new Date().toISOString(),
  };
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

  test('should render scheduler task SLA and timeline on automation tab', async ({ page, apiHelper, testGreenhouse }) => {
    const zone = await apiHelper.createTestZone(testGreenhouse.id);
    const executionId = '501';
    const run = {
      execution_id: executionId,
      task_id: 'st-e2e-expired',
      zone_id: zone.id,
      task_type: 'diagnostics',
      status: 'failed',
      decision_outcome: 'fail',
      decision_reason_code: 'task_expired',
      error_code: 'task_expired',
      error_message: 'Задача получена после expires_at и не может быть исполнена',
      correlation_id: `sch:z${zone.id}:diagnostics:e2e-expired`,
      updated_at: new Date().toISOString(),
      chain: [
        chainStep('SNAPSHOT', 'ok', 'Задача получена', 'evt-e2e-1'),
        chainStep('DECISION', 'skip', 'SLA нарушен: expires_at', 'evt-e2e-2'),
        chainStep('FAIL', 'err', 'task_expired', 'evt-e2e-3'),
      ],
    };

    try {
      await installSchedulerWorkspaceMocks(page, zone.id, [run], { [executionId]: run });

      await page.goto(`/zones/${zone.id}?tab=scheduler`, { waitUntil: 'networkidle' });
      await expect(page.locator('[data-testid="scheduler-root"]')).toBeVisible({ timeout: 15000 });
      await page.locator(`[data-testid="scheduler-runs-row-${executionId}"]`).click();

      await expect(page.locator('[data-testid="scheduler-causal-chain"]')).toBeVisible({ timeout: 15000 });
      await expect(page.locator('[data-testid="scheduler-chain-error"]')).toContainText('task_expired');
      await expect(page.locator('[data-testid="scheduler-chain-step-SNAPSHOT"]')).toContainText('Задача получена');
      await expect(page.locator('[data-testid="scheduler-chain-step-DECISION"]')).toContainText('SLA нарушен: expires_at');
      await expect(page.locator('[data-testid="scheduler-chain-step-FAIL"]')).toContainText('task_expired');
    } finally {
      await apiHelper.deleteZone(zone.id).catch(() => {});
    }
  });

  test('should display DONE confirmation and scheduler task presets', async ({ page, apiHelper, testGreenhouse }) => {
    const zone = await apiHelper.createTestZone(testGreenhouse.id);
    const doneExecutionId = '502';
    const unconfirmedExecutionId = '503';
    const failedExecutionId = '504';
    const doneRun = {
      execution_id: doneExecutionId,
      task_id: 'st-e2e-done-confirmed',
      zone_id: zone.id,
      task_type: 'irrigation',
      status: 'completed',
      decision_outcome: 'run',
      command_submitted: true,
      command_effect_confirmed: true,
      commands_total: 1,
      commands_effect_confirmed: 1,
      updated_at: new Date().toISOString(),
      chain: [
        chainStep('SNAPSHOT', 'ok', 'soil moisture ниже target', 'evt-done-1'),
        chainStep('DECISION', 'ok', 'RUN irrigation', 'cw-done'),
        chainStep('DISPATCH', 'ok', 'DONE подтвержден', 'cmd-done'),
      ],
    };
    const unconfirmedRun = {
      ...doneRun,
      execution_id: unconfirmedExecutionId,
      task_id: 'st-e2e-done-unconfirmed',
      command_effect_confirmed: false,
      commands_effect_confirmed: 0,
      chain: [
        chainStep('SNAPSHOT', 'ok', 'soil moisture ниже target', 'evt-unconfirmed-1'),
        chainStep('DECISION', 'ok', 'RUN irrigation', 'cw-unconfirmed'),
        chainStep('DISPATCH', 'warn', 'DONE не подтвержден', 'cmd-unconfirmed'),
      ],
    };
    const failedRun = {
      execution_id: failedExecutionId,
      task_id: 'st-e2e-failed',
      zone_id: zone.id,
      task_type: 'diagnostics',
      status: 'failed',
      decision_outcome: 'fail',
      decision_reason_code: 'cycle_start_refill_timeout',
      error_code: 'cycle_start_refill_timeout',
      updated_at: new Date().toISOString(),
      chain: [chainStep('FAIL', 'err', 'cycle_start_refill_timeout', 'evt-failed')],
    };

    try {
      await installSchedulerWorkspaceMocks(page, zone.id, [doneRun, unconfirmedRun, failedRun], {
        [doneExecutionId]: doneRun,
        [unconfirmedExecutionId]: unconfirmedRun,
        [failedExecutionId]: failedRun,
      });

      await page.goto(`/zones/${zone.id}?tab=scheduler`, { waitUntil: 'networkidle' });
      await expect(page.locator('[data-testid="scheduler-root"]')).toBeVisible({ timeout: 15000 });
      await expect(page.locator(`[data-testid="scheduler-runs-row-${doneExecutionId}"]`)).toBeVisible();
      await expect(page.locator(`[data-testid="scheduler-runs-row-${unconfirmedExecutionId}"]`)).toBeVisible();
      await expect(page.locator(`[data-testid="scheduler-runs-row-${failedExecutionId}"]`)).toBeVisible();

      await page.locator(`[data-testid="scheduler-runs-row-${doneExecutionId}"]`).click();
      await expect(page.locator('[data-testid="scheduler-chain-step-DISPATCH"]')).toContainText('DONE подтвержден');

      await page.locator(`[data-testid="scheduler-runs-row-${failedExecutionId}"]`).click();
      await expect(page.locator('[data-testid="scheduler-chain-error"]')).toContainText('cycle_start_refill_timeout');
    } finally {
      await apiHelper.deleteZone(zone.id).catch(() => {});
    }
  });
});

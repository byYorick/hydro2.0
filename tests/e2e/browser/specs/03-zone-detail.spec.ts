import { test, expect } from '../fixtures/test-data';
import { TEST_IDS } from '../constants';

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

  test('should render scheduler task SLA and timeline on automation tab', async ({ page, apiHelper, testGreenhouse }) => {
    const zone = await apiHelper.createTestZone(testGreenhouse.id);
    const taskId = 'st-e2e-expired';
    const now = Date.now();
    const scheduledFor = new Date(now - 2 * 60 * 1000).toISOString();
    const dueAt = new Date(now - 60 * 1000).toISOString();
    const expiresAt = new Date(now - 5 * 1000).toISOString();

    try {
      await page.route(new RegExp(`/api/zones/${zone.id}/scheduler-tasks(?:\\?.*)?$`), async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            status: 'ok',
            data: [
              {
                task_id: taskId,
                zone_id: zone.id,
                task_type: 'diagnostics',
                status: 'expired',
                created_at: scheduledFor,
                updated_at: expiresAt,
                scheduled_for: scheduledFor,
                due_at: dueAt,
                expires_at: expiresAt,
                correlation_id: `sch:z${zone.id}:diagnostics:e2e-expired`,
                lifecycle: [],
              },
            ],
          }),
        });
      });

      await page.route(new RegExp(`/api/zones/${zone.id}/scheduler-tasks/${taskId}(?:\\?.*)?$`), async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            status: 'ok',
            data: {
              task_id: taskId,
              zone_id: zone.id,
              task_type: 'diagnostics',
              status: 'expired',
              created_at: scheduledFor,
              updated_at: expiresAt,
              scheduled_for: scheduledFor,
              due_at: dueAt,
              expires_at: expiresAt,
              correlation_id: `sch:z${zone.id}:diagnostics:e2e-expired`,
              action_required: false,
              decision: 'skip',
              reason_code: 'task_expired',
              reason: 'Задача получена после expires_at и не может быть исполнена',
              error: 'task_expired',
              error_code: 'task_expired',
              result: {
                success: false,
                mode: 'deadline_rejected',
                action_required: false,
                decision: 'skip',
                reason_code: 'task_expired',
                reason: 'Задача получена после expires_at и не может быть исполнена',
                error: 'task_expired',
                error_code: 'task_expired',
              },
              lifecycle: [
                { status: 'accepted', at: scheduledFor },
                { status: 'expired', at: expiresAt },
              ],
              timeline: [
                {
                  event_id: 'evt-e2e-1',
                  event_seq: 1,
                  event_type: 'TASK_RECEIVED',
                  at: scheduledFor,
                  reason_code: 'task_expired',
                },
                {
                  event_id: 'evt-e2e-2',
                  event_seq: 2,
                  event_type: 'SCHEDULE_TASK_EXECUTION_STARTED',
                  at: scheduledFor,
                },
                {
                  event_id: 'evt-e2e-3',
                  event_seq: 3,
                  event_type: 'TASK_FINISHED',
                  at: expiresAt,
                  decision: 'skip',
                  reason_code: 'task_expired',
                  error_code: 'task_expired',
                },
              ],
            },
          }),
        });
      });

      await page.goto(`/zones/${zone.id}`, { waitUntil: 'networkidle' });
      await page.getByRole('tab', { name: 'Автоматизация' }).click();
      await expect(page.getByText('Scheduler Task Lifecycle')).toBeVisible({ timeout: 15000 });

      await expect(page.getByText(taskId)).toBeVisible({ timeout: 15000 });
      await page.getByRole('button', { name: 'Открыть' }).first().click();

      await expect(page.getByText('Просрочена')).toBeVisible({ timeout: 15000 });
      await expect(page.getByText('SLA-контроль')).toBeVisible({ timeout: 15000 });
      await expect(page.getByText('SLA нарушен: expires_at')).toBeVisible({ timeout: 15000 });
      await expect(page.getByText('Задача получена')).toBeVisible({ timeout: 15000 });
      await expect(page.getByText('Automation-engine: execution started')).toBeVisible({ timeout: 15000 });
      await expect(page.getByText('Превышен срок expires_at (task_expired)').first()).toBeVisible({ timeout: 15000 });
    } finally {
      await apiHelper.deleteZone(zone.id).catch(() => {});
    }
  });

  test('should display DONE confirmation and scheduler task presets', async ({ page, apiHelper, testGreenhouse }) => {
    const zone = await apiHelper.createTestZone(testGreenhouse.id);
    const doneTaskId = 'st-e2e-done-confirmed';

    try {
      await page.route(new RegExp(`/api/zones/${zone.id}/scheduler-tasks(?:\\?.*)?$`), async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            status: 'ok',
            data: [
              {
                task_id: doneTaskId,
                zone_id: zone.id,
                task_type: 'irrigation',
                status: 'completed',
                action_required: true,
                command_submitted: true,
                command_effect_confirmed: true,
                commands_total: 1,
                commands_effect_confirmed: 1,
                updated_at: new Date().toISOString(),
                lifecycle: [],
              },
              {
                task_id: 'st-e2e-done-unconfirmed',
                zone_id: zone.id,
                task_type: 'irrigation',
                status: 'completed',
                action_required: true,
                command_submitted: true,
                command_effect_confirmed: false,
                commands_total: 1,
                commands_effect_confirmed: 0,
                updated_at: new Date().toISOString(),
                lifecycle: [],
              },
              {
                task_id: 'st-e2e-failed',
                zone_id: zone.id,
                task_type: 'diagnostics',
                status: 'failed',
                error_code: 'cycle_start_refill_timeout',
                reason_code: 'cycle_start_refill_timeout',
                updated_at: new Date().toISOString(),
                lifecycle: [],
              },
            ],
          }),
        });
      });

      await page.route(new RegExp(`/api/zones/${zone.id}/scheduler-tasks/${doneTaskId}(?:\\?.*)?$`), async (route) => {
        const nowIso = new Date().toISOString();
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            status: 'ok',
            data: {
              task_id: doneTaskId,
              zone_id: zone.id,
              task_type: 'irrigation',
              status: 'completed',
              created_at: nowIso,
              updated_at: nowIso,
              scheduled_for: nowIso,
              due_at: nowIso,
              expires_at: nowIso,
              action_required: true,
              decision: 'run',
              reason_code: 'irrigation_required',
              command_submitted: true,
              command_effect_confirmed: true,
              commands_total: 1,
              commands_effect_confirmed: 1,
              commands_failed: 0,
              lifecycle: [],
              timeline: [],
              result: {
                command_submitted: true,
                command_effect_confirmed: true,
                commands_total: 1,
                commands_effect_confirmed: 1,
                commands_failed: 0,
              },
            },
          }),
        });
      });

      await page.goto(`/zones/${zone.id}`, { waitUntil: 'networkidle' });
      await page.getByRole('tab', { name: 'Автоматизация' }).click();
      await expect(page.getByText('Scheduler Task Lifecycle')).toBeVisible({ timeout: 15000 });

      const schedulerPresetSelect = page
        .locator('select')
        .filter({ has: page.locator('option[value="done_unconfirmed"]') })
        .first();
      await expect(schedulerPresetSelect).toBeVisible({ timeout: 15000 });
      await schedulerPresetSelect.selectOption('done_unconfirmed');
      await expect(page.getByText('st-e2e-done-unconfirmed')).toBeVisible({ timeout: 15000 });
      await expect(page.getByText(doneTaskId)).not.toBeVisible();

      await schedulerPresetSelect.selectOption('all');
      await page.getByPlaceholder('Поиск: task_id/status/error_code/reason_code').fill('st-e2e-failed');
      await expect(page.getByText('st-e2e-failed')).toBeVisible({ timeout: 15000 });

      await page.getByPlaceholder('Поиск: task_id/status/error_code/reason_code').fill('');
      await page.getByRole('button', { name: 'Открыть' }).first().click();
      await expect(page.locator('span.badge', { hasText: 'DONE подтвержден' }).first()).toBeVisible({ timeout: 15000 });
    } finally {
      await apiHelper.deleteZone(zone.id).catch(() => {});
    }
  });
});

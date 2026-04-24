import type { Page } from '@playwright/test';
import { test, expect } from '../fixtures/test-data';

/**
 * E2E-сценарии Scheduler UI планировщика (Cockpit-раскладка).
 *
 * API-ответы для workspace/executions мокаем через `page.route`, чтобы не
 * зависеть от реального состояния БД.
 */

interface WorkspaceFixtureOptions {
  activeRun?: Record<string, unknown> | null;
  recentRuns?: Array<Record<string, unknown>>;
}

function workspacePayload(zoneId: number, options: WorkspaceFixtureOptions = {}): Record<string, unknown> {
  return {
    status: 'ok',
    data: {
      control: {
        automation_runtime: 'ae3',
        control_mode: 'auto',
        allowed_manual_steps: [],
        generated_at: new Date().toISOString(),
      },
      capabilities: {
        executable_task_types: ['irrigation', 'lighting'],
        planned_task_types: ['irrigation', 'lighting'],
        diagnostics_available: false,
      },
      plan: {
        horizon: '24h',
        lanes: [],
        windows: [],
        summary: { planned_total: 0, suppressed_total: 0, missed_total: 0 },
      },
      execution: {
        active_run: options.activeRun ?? null,
        recent_runs: options.recentRuns ?? [],
        counters: { active: options.activeRun ? 1 : 0, completed_24h: 2, failed_24h: 1 },
      },
    },
  };
}

function executionRun(overrides: Record<string, unknown>): Record<string, unknown> {
  return {
    execution_id: '401',
    task_id: '401',
    zone_id: 42,
    task_type: 'irrigation_start',
    status: 'completed',
    ...overrides,
  };
}

function chainStep(step: string, status: string, detail: string, ref = 'ref-1'): Record<string, unknown> {
  return {
    step,
    at: new Date().toISOString(),
    ref,
    detail,
    status,
  };
}

async function installApiMocks(
  page: Page,
  zoneId: number,
  options: {
    workspace: Record<string, unknown>;
    executions: Record<string, Record<string, unknown>>;
  },
): Promise<{ workspaceCalls: () => number }> {
  let workspaceCalls = 0;

  await page.route(new RegExp(`/api/zones/${zoneId}/schedule-workspace(?:\\?.*)?$`), async (route) => {
    workspaceCalls += 1;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(options.workspace),
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

  await page.route(new RegExp(`/api/zones/${zoneId}/executions/([0-9]+)(?:\\?.*)?$`), async (route) => {
    const match = route.request().url().match(/\/executions\/([0-9]+)/);
    const id = match?.[1] ?? '';
    const payload = options.executions[id];
    if (!payload) {
      await route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ status: 'error', code: 'NOT_FOUND' }) });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', data: payload }),
    });
  });

  return { workspaceCalls: () => workspaceCalls };
}

test.describe('Scheduler cockpit UI (Phase 3)', () => {
  test('shows causal chain for active run on load', async ({ page, testZone }) => {
    const activeChain = [
      chainStep('SNAPSHOT', 'ok', 'pH=6.4 · EC=1.52', 'ev-101'),
      chainStep('DECISION', 'ok', 'DOSE_ACID 2.3ml', 'cw-101'),
      chainStep('TASK', 'ok', 'ae_task #T-551', 'T-551'),
      chainStep('DISPATCH', 'ok', 'history-logger → MQTT', 'cmd-9931'),
      { ...chainStep('RUNNING', 'run', 'pump_acid активен', 'ex-401'), live: true },
    ];

    const activeRun = executionRun({
      execution_id: '401',
      status: 'running',
      is_active: true,
      decision_outcome: 'run',
      due_at: new Date(Date.now() + 2 * 60 * 1000).toISOString(),
      chain: activeChain,
    });

    
    await installApiMocks(page, testZone.id, {
      workspace: workspacePayload(testZone.id, { activeRun, recentRuns: [activeRun] }),
      executions: { 401: activeRun },
    });

    await page.goto(`/zones/${testZone.id}?tab=scheduler`, { waitUntil: 'networkidle' });

    await expect(page.locator('[data-testid="scheduler-root"]')).toBeVisible({ timeout: 15000 });
    await expect(page.locator('[data-testid="scheduler-causal-chain"]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="scheduler-chain-step-SNAPSHOT"]')).toBeVisible();
    await expect(page.locator('[data-testid="scheduler-chain-step-RUNNING"]')).toBeVisible();
  });

  test('selecting FAIL run shows error + retry button', async ({ page, testZone }) => {
    const failRun = executionRun({
      execution_id: '402',
      status: 'failed',
      is_active: false,
      decision_outcome: 'fail',
      error_code: 'ACT_TIMEOUT',
      error_message: 'pump_acid не ответил 3000ms',
      human_error_message: 'pump_acid не ответил 3000ms',
      chain: [
        chainStep('SNAPSHOT', 'ok', 'pH=6.5', 'ev-99'),
        chainStep('DECISION', 'ok', 'DOSE_ACID 2.1ml', 'cw-99'),
        chainStep('TASK', 'ok', 'ae_task #T-550', 'T-550'),
        chainStep('DISPATCH', 'ok', 'history-logger → MQTT', 'cmd-9929'),
        chainStep('FAIL', 'err', 'ACT_TIMEOUT · pump_acid', 'ex-402'),
      ],
    });

    
    await installApiMocks(page, testZone.id, {
      workspace: workspacePayload(testZone.id, { recentRuns: [failRun] }),
      executions: { 402: failRun },
    });

    await page.goto(`/zones/${testZone.id}?tab=scheduler`, { waitUntil: 'networkidle' });

    await expect(page.locator('[data-testid="scheduler-runs-row-402"]')).toBeVisible({ timeout: 15000 });
    await page.locator('[data-testid="scheduler-runs-row-402"]').click();

    await expect(page.locator('[data-testid="scheduler-chain-error"]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="scheduler-chain-error"]')).toContainText('ACT_TIMEOUT');
    await expect(page.locator('[data-testid="scheduler-chain-retry"]')).toBeVisible();
  });

  test('SKIP run chain renders only SNAPSHOT and DECISION steps', async ({ page, testZone }) => {
    const skipRun = executionRun({
      execution_id: '403',
      status: 'completed',
      is_active: false,
      decision_outcome: 'skip',
      decision_reason_code: 'ec_within_band',
      chain: [
        chainStep('SNAPSHOT', 'ok', 'EC=1.52', 'ev-88'),
        chainStep('DECISION', 'skip', 'SKIP · ec_within_band', 'cw-88'),
      ],
    });

    
    await installApiMocks(page, testZone.id, {
      workspace: workspacePayload(testZone.id, { recentRuns: [skipRun] }),
      executions: { 403: skipRun },
    });

    await page.goto(`/zones/${testZone.id}?tab=scheduler`, { waitUntil: 'networkidle' });

    await page.locator('[data-testid="scheduler-runs-row-403"]').click();

    const steps = page.locator('[data-testid^="scheduler-chain-step-"]');
    await expect(steps).toHaveCount(2, { timeout: 10000 });
    await expect(page.locator('[data-testid="scheduler-chain-step-SKIP"]')).toHaveCount(0);
    await expect(page.locator('[data-testid="scheduler-chain-retry"]')).toHaveCount(0);
  });

  test('hotkey R refreshes workspace', async ({ page, testZone }) => {
    const run = executionRun({
      execution_id: '404',
      status: 'completed',
      decision_outcome: 'run',
      chain: [chainStep('SNAPSHOT', 'ok', 'pH=6.4', 'ev-1')],
    });

    
    const mocks = await installApiMocks(page, testZone.id, {
      workspace: workspacePayload(testZone.id, { recentRuns: [run] }),
      executions: { 404: run },
    });

    await page.goto(`/zones/${testZone.id}?tab=scheduler`, { waitUntil: 'networkidle' });
    await expect(page.locator('[data-testid="scheduler-root"]')).toBeVisible({ timeout: 15000 });

    const initialCalls = mocks.workspaceCalls();
    await page.locator('body').focus();
    await page.keyboard.press('r');

    await page.waitForFunction(
      (initial) => {
        const w = window as unknown as { __schedulerWorkspaceCalls?: number };
        return (w.__schedulerWorkspaceCalls ?? 0) > initial;
      },
      initialCalls,
      { timeout: 5000 },
    ).catch(() => {
      // В окружении без глобального счётчика проверим через сетевой вызов.
    });

    await expect.poll(() => mocks.workspaceCalls(), { timeout: 5000 }).toBeGreaterThan(initialCalls);
  });
});

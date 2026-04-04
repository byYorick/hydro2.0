import { flushPromises, mount } from '@vue/test-utils'
import { computed } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiGetMock = vi.hoisted(() => vi.fn())
const roleState = vi.hoisted(() => ({ canDiagnose: true }))

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    showToast: vi.fn(),
  }),
}))

vi.mock('@/composables/useApi', () => ({
  useApi: () => ({
    get: apiGetMock,
  }),
}))

vi.mock('@/utils/logger', () => ({
  logger: {
    warn: vi.fn(),
    error: vi.fn(),
  },
}))

vi.mock('@/composables/useRole', () => ({
  useRole: () => ({
    canDiagnose: computed(() => roleState.canDiagnose),
  }),
}))

vi.mock('@/Components/Badge.vue', () => ({
  default: {
    name: 'Badge',
    props: ['variant'],
    template: '<span><slot /></span>',
  },
}))

vi.mock('@/Components/Button.vue', () => ({
  default: {
    name: 'Button',
    props: ['variant', 'disabled', 'size'],
    emits: ['click'],
    template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
  },
}))

import ZoneSchedulerTab from '../ZoneSchedulerTab.vue'

function buildStateResponse(overrides: Record<string, unknown> = {}) {
  return {
    data: {
      zone_id: 42,
      state: 'TANK_RECIRC',
      state_label: 'Рециркуляция раствора',
      state_details: {
        started_at: '2026-02-10T08:00:00Z',
        elapsed_sec: 0,
        progress_percent: 0,
        failed: false,
      },
      workflow_phase: 'tank_recirc',
      current_stage: 'prepare_recirculation_check',
      active_processes: {
        pump_in: false,
        circulation_pump: true,
        ph_correction: false,
        ec_correction: true,
      },
      decision: {
        outcome: 'degraded_run',
        reason_code: 'smart_soil_telemetry_missing_or_stale',
        degraded: true,
        strategy: 'smart_soil_v1',
      },
      timeline: [],
      next_state: null,
      estimated_completion_sec: null,
      system_config: {
        tanks_count: 2,
        system_type: 'drip',
        clean_tank_capacity_l: null,
        nutrient_tank_capacity_l: null,
      },
      current_levels: {
        clean_tank_level_percent: 0,
        nutrient_tank_level_percent: 0,
        ph: null,
        ec: null,
      },
      control_mode: 'semi',
      allowed_manual_steps: [],
      ...overrides,
    },
  }
}

function buildExecutionDetail(overrides: Record<string, unknown> = {}) {
  return {
    data: {
      status: 'ok',
      data: {
        execution_id: '401',
        task_id: '401',
        zone_id: 42,
        task_type: 'irrigation',
        status: 'running',
        current_stage: 'startup',
        scheduled_for: '2026-02-10T08:00:00Z',
        due_at: '2026-02-10T08:05:00Z',
        expires_at: '2026-02-10T08:10:00Z',
        decision_outcome: 'degraded_run',
        decision_reason_code: 'smart_soil_telemetry_missing_or_stale',
        decision_degraded: true,
        decision_strategy: 'smart_soil_v1',
        decision_bundle_revision: 'bundle-live-1234567890',
        decision_config: {
          lookback_sec: 1800,
          min_samples: 3,
          stale_after_sec: 600,
          hysteresis_pct: 2,
        },
        replay_count: 1,
        lifecycle: [
          { status: 'accepted', at: '2026-02-10T08:00:00Z', source: 'ae_tasks' },
          { status: 'running', at: '2026-02-10T08:01:00Z', source: 'ae_tasks' },
        ],
        timeline: [
          {
            event_id: 'evt-1',
            event_type: 'AE_TASK_STARTED',
            at: '2026-02-10T08:01:00Z',
            stage: 'startup',
          },
          {
            event_id: 'evt-2',
            event_type: 'AE_TASK_STARTED',
            at: '2026-02-10T08:02:00Z',
            stage: 'decision_gate',
          },
          {
            event_id: 'evt-3',
            event_type: 'TASK_FINISHED',
            at: '2026-02-10T08:03:00Z',
            decision: 'skip',
            reason_code: 'smart_soil_within_band',
            details: {
              zone_average_pct: 53.4,
              sensor_count: 2,
              samples: 6,
            },
          },
        ],
        ...overrides,
      },
    },
  }
}

function buildWorkspaceResponse(overrides: Record<string, unknown> = {}) {
  return {
    data: {
      status: 'ok',
      data: {
        control: {
          automation_runtime: 'ae3',
          control_mode: 'semi',
          allowed_manual_steps: ['clean_fill_start'],
          generated_at: '2026-02-10T08:00:30Z',
        },
        capabilities: {
          executable_task_types: ['irrigation', 'lighting'],
          planned_task_types: ['irrigation', 'lighting'],
          non_executable_planned_task_types: [],
          ae3_irrigation_only_dispatch: true,
          diagnostics_available: true,
        },
        plan: {
          horizon: '24h',
          lanes: [
            { task_type: 'irrigation', label: 'Полив', mode: 'interval', executable: true },
            { task_type: 'lighting', label: 'Свет', mode: 'schedule', executable: true },
          ],
          windows: [
            {
              plan_window_id: 'pw-1',
              zone_id: 42,
              task_type: 'irrigation',
              label: 'Полив',
              schedule_key: 'zone:42|type:irrigation|interval=1800',
              trigger_at: '2026-02-10T09:00:00Z',
              origin: 'effective_targets',
              state: 'planned',
              mode: 'interval',
            },
            {
              plan_window_id: 'pw-2',
              zone_id: 42,
              task_type: 'lighting',
              label: 'Свет',
              schedule_key: 'zone:42|type:lighting|photoperiod',
              trigger_at: '2026-02-10T10:00:00Z',
              origin: 'effective_targets',
              state: 'planned',
              mode: 'schedule',
            },
          ],
          summary: {
            planned_total: 2,
            suppressed_total: 0,
            missed_total: 0,
          },
        },
        execution: {
          active_run: {
            execution_id: '401',
            task_id: '401',
            zone_id: 42,
            task_type: 'irrigation',
            status: 'running',
            current_stage: 'startup',
            scheduled_for: '2026-02-10T08:00:00Z',
            decision_outcome: 'degraded_run',
            decision_reason_code: 'smart_soil_telemetry_missing_or_stale',
            decision_degraded: true,
            replay_count: 1,
          },
          recent_runs: [
            {
              execution_id: '401',
              task_id: '401',
              zone_id: 42,
              task_type: 'irrigation',
              status: 'running',
              current_stage: 'startup',
              decision_outcome: 'degraded_run',
              decision_reason_code: 'smart_soil_telemetry_missing_or_stale',
              decision_degraded: true,
              replay_count: 1,
              created_at: '2026-02-10T08:00:00Z',
              updated_at: '2026-02-10T08:01:00Z',
            },
          ],
          counters: {
            active: 1,
            completed_24h: 2,
            failed_24h: 1,
          },
          latest_failure: {
            source: 'zone_automation_intents',
            task_type: 'irrigation',
            status: 'failed',
            error_code: 'start_cycle_zone_busy',
            error_message: 'Intent skipped: zone busy',
            human_error_message: 'Повторный запуск отклонён: по зоне уже есть активный intent или выполняемая задача.',
            at: '2026-02-10T08:00:00Z',
          },
        },
        ...overrides,
      },
    },
  }
}

function buildDiagnosticsResponse() {
  return {
    data: {
      status: 'ok',
      data: {
        zone_id: 42,
        generated_at: '2026-02-10T08:00:30Z',
        sources: {
          dispatcher_tasks: true,
          scheduler_logs: true,
        },
        summary: {
          tracked_tasks_total: 1,
          active_tasks_total: 1,
          overdue_tasks_total: 0,
          stale_tasks_total: 0,
          recent_logs_total: 1,
          last_log_at: '2026-02-10T08:00:00Z',
        },
        dispatcher_tasks: [
          {
            task_id: '401',
            task_type: 'irrigation',
            schedule_key: 'zone:42|type:irrigation|interval=1800',
            status: 'running',
            due_at: '2026-02-10T08:05:00Z',
            last_polled_at: '2026-02-10T08:01:30Z',
          },
        ],
        recent_logs: [
          {
            log_id: 11,
            task_name: 'laravel_scheduler_task_irrigation_zone_42',
            status: 'running',
            created_at: '2026-02-10T08:00:00Z',
          },
        ],
      },
    },
  }
}

function installApiMocks(options?: {
  state?: ReturnType<typeof buildStateResponse>
  workspace?: ReturnType<typeof buildWorkspaceResponse>
  diagnostics?: ReturnType<typeof buildDiagnosticsResponse>
  executionDetails?: Record<string, ReturnType<typeof buildExecutionDetail>>
}) {
  const state = options?.state ?? buildStateResponse()
  const workspace = options?.workspace ?? buildWorkspaceResponse()
  const diagnostics = options?.diagnostics ?? buildDiagnosticsResponse()
  const executionDetails = options?.executionDetails ?? {
    '401': buildExecutionDetail(),
  }

  apiGetMock.mockImplementation((url: string) => {
    if (url.includes('/state')) {
      return Promise.resolve(state)
    }

    const executionMatch = url.match(/\/executions\/(\d+)/)
    if (executionMatch) {
      return Promise.resolve(executionDetails[executionMatch[1]])
    }

    if (url.includes('/scheduler-diagnostics')) {
      return Promise.resolve(diagnostics)
    }

    return Promise.resolve(workspace)
  })
}

describe('ZoneSchedulerTab.vue', () => {
  beforeEach(() => {
    apiGetMock.mockReset()
    installApiMocks()
  })

  it('показывает workspace планировщика на основе нового contract', async () => {
    roleState.canDiagnose = true
    const wrapper = mount(ZoneSchedulerTab, {
      props: {
        zoneId: 42,
        targets: {} as any,
      },
    })

    await flushPromises()

    expect(apiGetMock).toHaveBeenCalledWith('/api/zones/42/schedule-workspace', expect.any(Object))
    expect(apiGetMock).toHaveBeenCalledWith('/api/zones/42/state')
    expect(apiGetMock).toHaveBeenCalledWith('/api/zones/42/executions/401')
    expect(apiGetMock).toHaveBeenCalledWith('/api/zones/42/scheduler-diagnostics')
    expect(wrapper.text()).toContain('Планировщик зоны')
    expect(wrapper.text()).toContain('Что происходит сейчас')
    expect(wrapper.text()).toContain('Требует внимания')
    expect(wrapper.text()).toContain('Ближайшие исполнимые окна')
    expect(wrapper.text()).toContain('Исполнения')
    expect(wrapper.text()).toContain('Детали run')
    expect(wrapper.text()).toContain('Рециркуляция раствора')
    expect(wrapper.text()).toContain('Последняя ошибка: Полив · Повторный запуск отклонён: по зоне уже есть активный intent или выполняемая задача.')
    expect(wrapper.text()).toContain('Полив')
    expect(wrapper.text()).toContain('Свет')
    expect(wrapper.text()).toContain('Деградированный запуск')
    expect(wrapper.text()).toContain('Нет свежей soil telemetry, поэтому используется degraded path.')
    expect(wrapper.text()).toContain('Setup replay: 1')
    expect(wrapper.text()).toContain('locked bundle bundle-live-')
    expect(wrapper.text()).toContain('locked config lookback 1800s · min_samples 3 · stale 600s · hysteresis 2%')
    expect(wrapper.text()).toContain('running')
    expect(wrapper.text()).toContain('Lifecycle')
    expect(wrapper.text()).toContain('AE_TASK_STARTED')
    expect(wrapper.text()).toContain('startup -> decision_gate')
    expect(wrapper.text()).toContain('Пропуск')
    expect(wrapper.text()).toContain('Средняя влажность уже внутри целевого диапазона.')
    expect(wrapper.text()).toContain('Telemetry: сенсоров 2, samples 6.')
    expect(wrapper.text()).not.toContain('без reason_code')
    expect(wrapper.text()).toContain('Инженерная диагностика')
    expect(wrapper.text()).toContain('Dispatcher tasks')
    expect(wrapper.text()).toContain('Scheduler logs')
  })

  it('показывает явный fail label для decision-controller и детали strategy в timeline', async () => {
    roleState.canDiagnose = true
    installApiMocks({
      workspace: buildWorkspaceResponse({
        execution: {
          active_run: null,
          recent_runs: [
            {
              execution_id: '402',
              task_id: '402',
              zone_id: 42,
              task_type: 'irrigation',
              status: 'failed',
              current_stage: 'decision_gate',
              decision_outcome: 'fail',
              decision_reason_code: 'irrigation_decision_strategy_unknown',
              decision_degraded: false,
              created_at: '2026-02-10T08:00:00Z',
              updated_at: '2026-02-10T08:01:00Z',
            },
          ],
          counters: {
            active: 0,
            completed_24h: 2,
            failed_24h: 1,
          },
          latest_failure: {
            source: 'ae_tasks',
            task_type: 'irrigation',
            status: 'failed',
            error_code: 'irrigation_decision_strategy_unknown',
            error_message: 'Irrigation decision-controller returned fail',
            human_error_message: null,
            at: '2026-02-10T08:00:00Z',
          },
        },
      }),
      executionDetails: {
        '402': buildExecutionDetail({
          execution_id: '402',
          task_id: '402',
          status: 'failed',
          current_stage: 'decision_gate',
          decision_outcome: 'fail',
          decision_reason_code: 'irrigation_decision_strategy_unknown',
          decision_degraded: false,
          replay_count: 0,
          lifecycle: [
            { status: 'accepted', at: '2026-02-10T08:00:00Z', source: 'ae_tasks' },
            { status: 'failed', at: '2026-02-10T08:01:00Z', source: 'ae_tasks' },
          ],
          timeline: [
            {
              event_id: 'evt-fail-1',
              event_type: 'TASK_FINISHED',
              at: '2026-02-10T08:01:00Z',
              decision: 'fail',
              reason_code: 'irrigation_decision_strategy_unknown',
              details: {
                strategy: 'bad_strategy',
              },
            },
          ],
        }),
      },
    })

    const wrapper = mount(ZoneSchedulerTab, {
      props: {
        zoneId: 42,
        targets: {} as any,
      },
    })

    await flushPromises()

    expect(apiGetMock).toHaveBeenCalledWith('/api/zones/42/executions/402')
    expect(wrapper.text()).toContain('Сбой decision-controller')
    expect(wrapper.text()).toContain('Указана неизвестная стратегия decision-controller.')
    expect(wrapper.text()).toContain('Strategy: bad_strategy.')
  })

  it('не запрашивает diagnostics для operator-only сценария', async () => {
    roleState.canDiagnose = false

    const wrapper = mount(ZoneSchedulerTab, {
      props: {
        zoneId: 42,
        targets: {} as any,
      },
    })

    await flushPromises()

    expect(apiGetMock).toHaveBeenCalledWith('/api/zones/42/schedule-workspace', expect.any(Object))
    expect(apiGetMock).toHaveBeenCalledWith('/api/zones/42/state')
    expect(apiGetMock).toHaveBeenCalledWith('/api/zones/42/executions/401')
    expect(apiGetMock).not.toHaveBeenCalledWith('/api/zones/42/scheduler-diagnostics')
    expect(wrapper.text()).not.toContain('Инженерная диагностика')
  })
})

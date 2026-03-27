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

describe('ZoneSchedulerTab.vue', () => {
  beforeEach(() => {
    apiGetMock.mockReset()

    apiGetMock.mockImplementation((url: string) => {
      if (url.includes('/state')) {
        return Promise.resolve({
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
          },
        })
      }

      if (url.includes('/executions/401')) {
        return Promise.resolve({
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
                  stage: 'prepare_recirculation_check',
                },
              ],
            },
          },
        })
      }

      if (url.includes('/scheduler-diagnostics')) {
        return Promise.resolve({
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
        })
      }

      return Promise.resolve({
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
              executable_task_types: ['irrigation'],
              planned_task_types: ['irrigation', 'lighting'],
              diagnostics_available: true,
            },
            plan: {
              horizon: '24h',
              lanes: [
                { task_type: 'irrigation', label: 'Полив', mode: 'interval', executable: true },
                { task_type: 'lighting', label: 'Свет', mode: 'schedule', executable: false },
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
              ],
              summary: {
                planned_total: 1,
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
              },
              recent_runs: [
                {
                  execution_id: '401',
                  task_id: '401',
                  zone_id: 42,
                  task_type: 'irrigation',
                  status: 'running',
                  current_stage: 'startup',
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
                at: '2026-02-10T08:00:00Z',
              },
            },
          },
        },
      })
    })
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
    expect(wrapper.text()).toContain('Последняя ошибка: Полив · start_cycle_zone_busy')
    expect(wrapper.text()).toContain('Полив')
    expect(wrapper.text()).toContain('Свет')
    expect(wrapper.text()).toContain('run')
    expect(wrapper.text()).toContain('running')
    expect(wrapper.text()).toContain('Lifecycle')
    expect(wrapper.text()).toContain('AE_TASK_STARTED')
    expect(wrapper.text()).toContain('startup -> prepare_recirculation_check')
    expect(wrapper.text()).not.toContain('без reason_code')
    expect(wrapper.text()).toContain('Инженерная диагностика')
    expect(wrapper.text()).toContain('Dispatcher tasks')
    expect(wrapper.text()).toContain('Scheduler logs')
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

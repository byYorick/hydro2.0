import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import type { AutomationState } from '@/types/Automation'
import AutomationObservabilityPanel from '../AutomationObservabilityPanel.vue'

const routerVisit = vi.fn()

vi.mock('@inertiajs/vue3', () => ({
  router: {
    visit: (...args: unknown[]) => routerVisit(...args),
  },
}))

vi.mock('@/Components/Badge.vue', () => ({
  default: {
    name: 'Badge',
    props: ['variant'],
    template: '<span data-testid="health-badge" :data-variant="variant"><slot /></span>',
  },
}))

vi.mock('@/composables/useSchedulerDispatchMetrics', () => ({
  useSchedulerDispatchMetrics: () => ({
    metrics: { value: null },
    loading: { value: false },
    error: { value: null },
    refreshedAt: { value: null },
  }),
}))

function buildState(overrides: Partial<AutomationState> = {}): AutomationState {
  return {
    zone_id: 7,
    state: 'TANK_FILLING',
    state_label: 'Набор бака с раствором',
    state_details: {
      started_at: '2026-06-23T10:00:00Z',
      elapsed_sec: 300,
      progress_percent: 25,
      failed: false,
    },
    system_config: {
      tanks_count: 2,
      system_type: 'drip',
      clean_tank_capacity_l: 300,
      nutrient_tank_capacity_l: 280,
    },
    current_levels: {
      clean_tank_level_percent: 80,
      nutrient_tank_level_percent: 15,
      buffer_tank_level_percent: null,
      ph: 5.9,
      ec: 1.4,
    },
    active_processes: {
      pump_in: true,
      circulation_pump: false,
      ph_correction: false,
      ec_correction: false,
    },
    timeline: [],
    next_state: 'TANK_RECIRC',
    estimated_completion_sec: 120,
    observability: {
      overall_health: 'critical',
      runtime: {
        task_is_active: true,
        task_status: 'waiting_command',
        waiting_command: true,
        current_stage: 'clean_fill_check',
        stage_elapsed_sec: 360,
        task_id: 9001,
        topology: 'two_tank_drip_substrate_trays',
        pending_manual_step: 'prepare_recirculation_stop',
      },
      hang_hints: [
        {
          code: 'waiting_command_stuck',
          severity: 'critical',
          message: 'Задача ждёт ответ по команде слишком долго',
          recommendation: 'Проверьте history-logger и MQTT.',
          details: {
            intent_id: 101,
            age_sec: 540,
            current_stage: 'clean_fill_check',
          },
        },
        {
          code: 'scheduler_intent_pending',
          severity: 'warning',
          message: 'Intent планировщика ожидает исполнения',
          recommendation: 'Проверьте scheduler-dispatch.',
        },
      ],
      scheduler: {
        pending_count: 1,
        active_count: 1,
      },
      nodes: {
        nodes: [],
        offline_required: ['pump-node-1'],
      },
    },
    ...overrides,
  }
}

describe('AutomationObservabilityPanel', () => {
  it('renders hang hints and critical health badge', () => {
    const wrapper = mount(AutomationObservabilityPanel, {
      props: {
        automationState: buildState(),
      },
    })

    expect(wrapper.find('[data-testid="automation-observability-panel"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Диагностика FSM')
    expect(wrapper.text()).toContain('Задача ждёт ответ по команде слишком долго')
    expect(wrapper.text()).toContain('waiting_command_stuck')
    expect(wrapper.text()).toContain('scheduler_intent_pending')
    expect(wrapper.text()).toContain('pump-node-1')
    expect(wrapper.find('[data-testid="automation-causal-strip"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('task #9001')
    expect(wrapper.text()).toContain('intent_id=101')
    expect(wrapper.text()).toContain('age_sec=540')
    expect(wrapper.text()).toContain('two_tank_drip_substrate_trays')
    expect(wrapper.text()).toContain('prepare_recirculation_stop')

    const badge = wrapper.find('[data-testid="health-badge"]')
    expect(badge.attributes('data-variant')).toBe('danger')
    expect(badge.text()).toContain('Критично')
  })

  it('renders irrigation decision card when decision is present', () => {
    const wrapper = mount(AutomationObservabilityPanel, {
      props: {
        automationState: buildState({
          decision: {
            outcome: 'irrigate',
            reason_code: 'soil_below_threshold',
            strategy: 'smart_soil_v1',
            bundle_revision: 'rev-42',
            degraded: true,
          },
        }),
      },
    })

    const card = wrapper.find('[data-testid="automation-decision-card"]')
    expect(card.exists()).toBe(true)
    expect(card.text()).toContain('irrigate')
    expect(card.text()).toContain('smart_soil_v1')
    expect(card.text()).toContain('soil_below_threshold')
    expect(card.text()).toContain('rev-42')
    expect(card.text()).toContain('degraded')
  })

  it('opens events tab with task_id from causal strip link', async () => {
    routerVisit.mockClear()
    const wrapper = mount(AutomationObservabilityPanel, {
      props: {
        automationState: buildState({
          observability: {
            overall_health: 'active',
            runtime: {
              zone_id: 7,
              task_id: 9001,
              task_is_active: true,
              task_status: 'running',
              correction_step: 'corr_check',
            },
            hang_hints: [],
            correction: {
              latest_skip: {
                event_id: 55,
                event_type: 'CORRECTION_SKIPPED_COOLDOWN',
                age_sec: 12,
              },
              last_dose: {
                ph: { no_effect_count: 1 },
                ec: { no_effect_count: 0 },
              },
            },
          },
        }),
      },
    })

    const strip = wrapper.find('[data-testid="automation-causal-strip"]')
    expect(strip.exists()).toBe(true)
    expect(strip.text()).toContain('task #9001 → running → corr_check → CORRECTION_SKIPPED_COOLDOWN')
    expect(strip.text()).toContain('skip_event_id=55')
    expect(strip.text()).toContain('ph_no_effect=1')

    await wrapper.find('[data-testid="automation-causal-events-link"]').trigger('click')
    expect(routerVisit).toHaveBeenCalledWith('/zones/7?tab=events&task_id=9001')
  })

  it('renders without error when automation state is null', () => {
    const wrapper = mount(AutomationObservabilityPanel, {
      props: {
        automationState: null,
      },
    })

    expect(wrapper.find('[data-testid="automation-observability-panel"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('Явных признаков зависания не обнаружено')
  })

  it('shows healthy message when task is active without hints', () => {
    const wrapper = mount(AutomationObservabilityPanel, {
      props: {
        automationState: buildState({
          observability: {
            overall_health: 'active',
            runtime: {
              task_is_active: true,
              task_status: 'running',
              current_stage: 'solution_fill_check',
            },
            hang_hints: [],
          },
        }),
      },
    })

    expect(wrapper.text()).toContain('Явных признаков зависания не обнаружено')
    expect(wrapper.find('[data-testid="health-badge"]').attributes('data-variant')).toBe('info')
  })

  it('hides stage deadline countdown when task is failed', () => {
    const wrapper = mount(AutomationObservabilityPanel, {
      props: {
        automationState: buildState({
          state_details: {
            started_at: '2026-06-29T10:29:47Z',
            elapsed_sec: 777,
            progress_percent: 0,
            failed: true,
            error_code: 'startup_recovery_unconfirmed_command',
          },
          observability: {
            overall_health: 'warning',
            runtime: {
              task_id: 6,
              task_status: 'failed',
              task_is_active: false,
              current_stage: 'irrigation_check',
              stage_elapsed_sec: 777,
              stage_deadline_remaining_sec: 212,
            },
            hang_hints: [],
          },
        }),
      },
    })

    expect(wrapper.text()).toContain('Дедлайн этапа')
    expect(wrapper.text()).not.toContain('осталось')
    expect(wrapper.text()).toContain('—')
  })

  it('shows failed stage context without stale correction step', () => {
    const wrapper = mount(AutomationObservabilityPanel, {
      props: {
        automationState: buildState({
          observability: {
            overall_health: 'idle',
            runtime: {
              task_id: 7,
              task_status: 'failed',
              task_is_active: false,
              failed_stage: 'prepare_recirculation_check',
              current_stage: null,
              stage_elapsed_sec: 57,
              correction_step: null,
            },
            hang_hints: [],
          },
        }),
      },
    })

    expect(wrapper.text()).toContain('Подготовка рециркуляции (сбой)')
    expect(wrapper.text()).not.toContain('corr_dose_ph')
    expect(wrapper.text()).toContain('00:57')
  })

  it('renders correction dosing block for cooldown skip', () => {
    const wrapper = mount(AutomationObservabilityPanel, {
      props: {
        automationState: buildState({
          workflow_phase: 'irrigating',
          observability: {
            overall_health: 'active',
            runtime: {
              task_is_active: true,
              task_status: 'running',
              workflow_phase: 'irrigating',
              correction_step: 'corr_check',
            },
            hang_hints: [],
            correction: {
              latest_skip: {
                event_type: 'CORRECTION_SKIPPED_COOLDOWN',
                payload: { retry_after_sec: 90 },
              },
              readiness: {
                targets_in_tolerance: false,
                workflow_ready: true,
              },
            },
          },
        }),
      },
    })

    expect(wrapper.find('[data-testid="automation-correction-dosing"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Коррекция / дозирование')
    expect(wrapper.text()).toContain('Коррекция: кулдаун PID')
    expect(wrapper.text()).toContain('±%: нет')
    expect(wrapper.text()).toContain('ready: да')
  })

  it('renders detailed failure block for historical terminal failure', () => {
    const wrapper = mount(AutomationObservabilityPanel, {
      props: {
        automationState: buildState({
          workflow_phase: 'idle',
          last_terminal_failure: {
            task_id: 3,
            failed_at: '2026-06-30T07:49:53+00:00',
            error_code: 'startup_recovery_unconfirmed_command',
            error_message: 'У задачи 3 отсутствует подтверждённая внешняя команда во время startup recovery',
          },
          observability: {
            overall_health: 'idle',
            runtime: {
              zone_id: 1,
              task_id: 3,
              task_status: 'failed',
              task_is_active: false,
              failed_stage: 'prepare_recirculation_start',
              workflow_phase: 'idle',
              stage_elapsed_sec: 27,
            },
            hang_hints: [],
          },
        }),
      },
    })

    expect(wrapper.find('[data-testid="automation-fsm-failure-details"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('startup_recovery_unconfirmed_command')
    expect(wrapper.text()).toContain('Запуск рециркуляции')
    expect(wrapper.text()).toContain('prepare_recirculation_start')
    expect(wrapper.text()).toContain('#3')
    expect(wrapper.find('[data-testid="health-badge"]').attributes('data-variant')).toBe('warning')
  })
})

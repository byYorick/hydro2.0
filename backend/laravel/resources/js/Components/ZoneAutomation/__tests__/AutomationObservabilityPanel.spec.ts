import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import type { AutomationState } from '@/types/Automation'
import AutomationObservabilityPanel from '../AutomationObservabilityPanel.vue'

vi.mock('@/Components/Badge.vue', () => ({
  default: {
    name: 'Badge',
    props: ['variant'],
    template: '<span data-testid="health-badge" :data-variant="variant"><slot /></span>',
  },
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
      },
      hang_hints: [
        {
          code: 'waiting_command_stuck',
          severity: 'critical',
          message: 'Задача ждёт ответ по команде слишком долго',
          recommendation: 'Проверьте history-logger и MQTT.',
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

    const badge = wrapper.find('[data-testid="health-badge"]')
    expect(badge.attributes('data-variant')).toBe('danger')
    expect(badge.text()).toContain('Критично')
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
})

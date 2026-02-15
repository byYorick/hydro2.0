import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/Components/StatusIndicator.vue', () => ({
  default: {
    name: 'StatusIndicator',
    props: ['status', 'variant', 'pulse', 'showLabel'],
    template: '<div data-testid="status-indicator">{{ status }}</div>',
  },
}))

vi.mock('@/utils/env', () => ({
  readBooleanEnv: () => false,
}))

vi.mock('@/utils/echoClient', () => ({
  getEchoInstance: () => null,
  onWsStateChange: () => () => {},
}))

vi.mock('@/utils/logger', () => ({
  logger: {
    debug: vi.fn(),
    warn: vi.fn(),
  },
}))

import AutomationProcessPanel from '../AutomationProcessPanel.vue'

describe('AutomationProcessPanel', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          zone_id: 5,
          state: 'TANK_RECIRC',
          state_label: 'Рециркуляция бака',
          state_details: {
            started_at: '2026-02-14T18:00:00Z',
            elapsed_sec: 120,
            progress_percent: 68,
          },
          system_config: {
            tanks_count: 2,
            system_type: 'drip',
            clean_tank_capacity_l: 300,
            nutrient_tank_capacity_l: 280,
          },
          current_levels: {
            clean_tank_level_percent: 96,
            nutrient_tank_level_percent: 88,
            ph: 5.8,
            ec: 1.6,
          },
          active_processes: {
            pump_in: false,
            circulation_pump: true,
            ph_correction: true,
            ec_correction: true,
          },
          timeline: [
            {
              event: 'SCHEDULE_TASK_ACCEPTED',
              label: 'Scheduler: задача принята',
              timestamp: '2026-02-14T18:00:00Z',
              active: false,
            },
            {
              event: 'SCHEDULE_TASK_EXECUTION_FINISHED',
              label: 'Финиш исполнения scheduler-task (prepare_targets_reached)',
              timestamp: '2026-02-14T18:02:00Z',
              active: true,
            },
          ],
          next_state: 'READY',
          estimated_completion_sec: 90,
        }),
      })
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('показывает setup-этапы и человеко-понятный timeline', async () => {
    const wrapper = mount(AutomationProcessPanel, {
      props: {
        zoneId: 5,
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('Этапы setup режима')
    expect(wrapper.text()).toContain('Сейчас: Параллельная коррекция pH/EC')
    expect(wrapper.text()).toContain('Набор бака с чистой водой')
    expect(wrapper.text()).toContain('Набор бака с раствором')
    expect(wrapper.text()).toContain('Завершение setup и переход в рабочий режим')
    expect(wrapper.text()).toContain('Параллельная коррекция: Финиш исполнения scheduler-task')
    expect(wrapper.text()).toContain('Целевые pH/EC достигнуты')
  })
})


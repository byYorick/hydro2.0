import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
const apiGetMock = vi.hoisted(() => vi.fn())

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
vi.mock('@/composables/useApi', () => ({
  useApi: () => ({
    get: apiGetMock,
  }),
}))

import AutomationProcessPanel from '../AutomationProcessPanel.vue'

describe('AutomationProcessPanel', () => {
  beforeEach(() => {
    apiGetMock.mockReset()
    apiGetMock.mockResolvedValue({
      data: {
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
      },
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('показывает setup-этапы и человеко-понятный timeline', async () => {
    const wrapper = mount(AutomationProcessPanel, {
      props: {
        zoneId: 5,
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('Этапы workflow')
    expect(wrapper.text()).toContain('Сейчас: Рециркуляция раствора')
    expect(wrapper.text()).toContain('Наполнение баков')
    expect(wrapper.text()).toContain('Раствор готов')
    expect(wrapper.text()).toContain('Рециркуляция после полива')
    expect(wrapper.text()).toContain('Параллельная коррекция: Финиш исполнения scheduler-task')
    expect(wrapper.text()).toContain('Целевые pH/EC достигнуты')
  })

  it('не показывает одновременно running для clean_fill и solution_fill', async () => {
    apiGetMock.mockResolvedValueOnce({
      data: {
          zone_id: 5,
          state: 'TANK_FILLING',
          state_label: 'Набор бака с раствором',
          state_details: {
            started_at: '2026-02-14T18:00:00Z',
            elapsed_sec: 80,
            progress_percent: 42,
          },
          system_config: {
            tanks_count: 2,
            system_type: 'drip',
            clean_tank_capacity_l: 300,
            nutrient_tank_capacity_l: 280,
          },
          current_levels: {
            clean_tank_level_percent: 95,
            nutrient_tank_level_percent: 30,
            ph: 5.8,
            ec: 1.5,
          },
          active_processes: {
            pump_in: true,
            circulation_pump: false,
            ph_correction: true,
            ec_correction: true,
          },
          timeline: [
            {
              event: 'TASK_STARTED',
              label: 'Automation-engine: выполнение начато (clean_fill_started)',
              timestamp: '2026-02-14T18:00:10Z',
              active: false,
            },
            {
              event: 'TASK_STARTED',
              label: 'Automation-engine: выполнение начато (solution_fill_in_progress)',
              timestamp: '2026-02-14T18:01:20Z',
              active: true,
            },
          ],
          next_state: 'TANK_RECIRC',
          estimated_completion_sec: 120,
      },
    })

    const wrapper = mount(AutomationProcessPanel, {
      props: {
        zoneId: 5,
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('Сейчас: Наполнение баков')
    expect((wrapper.text().match(/Выполняется/g) ?? []).length).toBe(1)
  })

  it('не подменяет COMMAND_DISPATCHED сообщением о завершении этапа', async () => {
    apiGetMock.mockResolvedValueOnce({
      data: {
        zone_id: 5,
        state: 'TANK_FILLING',
        state_label: 'Набор бака с раствором',
        state_details: {
          started_at: '2026-02-14T18:00:00Z',
          elapsed_sec: 40,
          progress_percent: 24,
        },
        system_config: {
          tanks_count: 2,
          system_type: 'drip',
          clean_tank_capacity_l: 300,
          nutrient_tank_capacity_l: 280,
        },
        current_levels: {
          clean_tank_level_percent: 96,
          nutrient_tank_level_percent: 35,
          ph: 5.8,
          ec: 1.5,
        },
        active_processes: {
          pump_in: true,
          circulation_pump: false,
          ph_correction: true,
          ec_correction: true,
        },
        timeline: [
          {
            event: 'COMMAND_DISPATCHED',
            label: 'Команда отправлена узлу (clean_fill_completed)',
            timestamp: '2026-02-14T18:00:40Z',
            active: true,
          },
        ],
        next_state: 'TANK_RECIRC',
        estimated_completion_sec: 120,
      },
    })

    const wrapper = mount(AutomationProcessPanel, {
      props: {
        zoneId: 5,
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('Набор чистой воды: Команда отправлена узлу')
    expect(wrapper.text()).not.toContain('Набор чистой воды: Команда отправлена узлу — Бак чистой воды наполнен')
  })

  it('показывает человеко-понятный label для recovery stale событий', async () => {
    apiGetMock.mockResolvedValueOnce({
      data: {
        zone_id: 5,
        state: 'TANK_RECIRC',
        state_label: 'Рециркуляция бака',
        state_details: {
          started_at: '2026-02-14T18:00:00Z',
          elapsed_sec: 80,
          progress_percent: 40,
        },
        system_config: {
          tanks_count: 2,
          system_type: 'drip',
          clean_tank_capacity_l: 300,
          nutrient_tank_capacity_l: 280,
        },
        current_levels: {
          clean_tank_level_percent: 92,
          nutrient_tank_level_percent: 88,
          ph: 5.8,
          ec: 1.6,
        },
        active_processes: {
          pump_in: false,
          circulation_pump: true,
          ph_correction: false,
          ec_correction: false,
        },
        timeline: [
          {
            event: 'WORKFLOW_RECOVERY_STALE_STOPPED',
            timestamp: '2026-02-14T18:01:00Z',
            active: true,
          },
        ],
        next_state: 'READY',
        estimated_completion_sec: 60,
      },
    })

    const wrapper = mount(AutomationProcessPanel, {
      props: {
        zoneId: 5,
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('Залипшая фаза сброшена (авто-восстановление)')
  })
})

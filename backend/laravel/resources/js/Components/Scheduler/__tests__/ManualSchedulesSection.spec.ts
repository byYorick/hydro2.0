import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import ManualSchedulesSection from '../ManualSchedulesSection.vue'
import type { PlanWindow, ZoneManualSchedule } from '@/composables/zoneScheduleWorkspaceTypes'

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({ showToast: vi.fn() }),
}))

vi.mock('@/services/api', () => ({
  api: {
    zones: {
      createManualSchedule: vi.fn(),
      updateManualSchedule: vi.fn(),
      deleteManualSchedule: vi.fn(),
    },
  },
}))

function schedule(overrides: Partial<ZoneManualSchedule> = {}): ZoneManualSchedule {
  return {
    id: 1,
    zone_id: 42,
    task_type: 'lighting',
    schedule_kind: 'time',
    time_at: '08:00',
    enabled: true,
    summary: 'Свет в 08:00',
    ...overrides,
  }
}

function planWindow(overrides: Partial<PlanWindow> = {}): PlanWindow {
  return {
    plan_window_id: 'pw-1',
    zone_id: 42,
    task_type: 'lighting',
    label: 'Свет',
    schedule_key: 'zone:42|manual:1',
    trigger_at: '2026-06-20T08:00:00Z',
    origin: 'manual',
    state: 'planned',
    mode: 'time',
    manual_schedule_id: 1,
    ...overrides,
  }
}

const baseProps = {
  zoneId: 42,
  canManage: true,
  laneLabel: (taskType: string) => taskType,
  executableTaskTypes: ['irrigation', 'lighting', 'diagnostics'],
  planWindows: [] as PlanWindow[],
}

describe('ManualSchedulesSection.vue', () => {
  it('показывает skeleton при loading и скрывает пустое состояние', () => {
    const wrapper = mount(ManualSchedulesSection, {
      props: {
        ...baseProps,
        loading: true,
        schedules: [],
      },
      global: {
        stubs: {
          ManualScheduleFormModal: true,
          Modal: true,
          Button: true,
          Badge: true,
        },
      },
    })

    expect(wrapper.find('[data-testid="manual-schedules-loading"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('Нет ручных правил')
  })

  it('показывает «выполнено» для завершённого once', () => {
    const wrapper = mount(ManualSchedulesSection, {
      props: {
        ...baseProps,
        schedules: [
          schedule({
            id: 7,
            schedule_kind: 'once',
            enabled: false,
            last_dispatched_at: '2026-06-19T10:00:00Z',
            summary: 'Свет · однократно',
          }),
        ],
      },
      global: {
        stubs: {
          ManualScheduleFormModal: true,
          Modal: true,
          Button: true,
          Badge: true,
        },
      },
    })

    expect(wrapper.text()).toContain('выполнено')
  })

  it('берёт ближайший запуск из planWindows', () => {
    const wrapper = mount(ManualSchedulesSection, {
      props: {
        ...baseProps,
        schedules: [schedule({ id: 1 })],
        planWindows: [planWindow({ manual_schedule_id: 1, trigger_at: '2026-06-20T12:00:00Z' })],
      },
      global: {
        stubs: {
          ManualScheduleFormModal: true,
          Modal: true,
          Button: true,
          Badge: true,
        },
      },
    })

    expect(wrapper.text()).toMatch(/через|сегодня|завтра|UTC/i)
  })
})

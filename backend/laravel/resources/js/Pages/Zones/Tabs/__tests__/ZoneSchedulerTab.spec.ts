import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiGetMock = vi.hoisted(() => vi.fn())
const apiPostMock = vi.hoisted(() => vi.fn())

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    showToast: vi.fn(),
  }),
}))

vi.mock('@/composables/useApi', () => ({
  useApi: () => ({
    get: apiGetMock,
    post: apiPostMock,
  }),
}))

vi.mock('@/composables/useWebSocket', () => ({
  useWebSocket: () => ({
    subscribeToZoneCommands: vi.fn(() => vi.fn()),
    subscribeToGlobalEvents: vi.fn(() => vi.fn()),
    unsubscribeAll: vi.fn(),
  }),
}))

vi.mock('@/Components/Badge.vue', () => ({
  default: {
    name: 'Badge',
    props: ['variant'],
    template: '<span><slot /></span>',
  },
}))

vi.mock('@/Components/AutomationSchedulerDevCard.vue', () => ({
  default: {
    name: 'AutomationSchedulerDevCard',
    props: ['schedulerTaskStatus', 'schedulerTasksUpdatedAt'],
    template: `
      <section class="scheduler-dev-card">
        <h4>Задачи автоматики</h4>
        <p v-if="schedulerTaskStatus">active: {{ schedulerTaskStatus.task_id }}</p>
        <p v-if="schedulerTasksUpdatedAt">updated: {{ schedulerTasksUpdatedAt }}</p>
      </section>
    `,
  },
}))

vi.mock('@/Pages/Zones/Tabs/ZoneAutomationSchedulerTaskDetailsCard.vue', () => ({
  default: {
    name: 'ZoneAutomationSchedulerTaskDetailsCard',
    props: ['schedulerTaskStatus', 'schedulerTaskSla', 'schedulerTaskDone', 'schedulerTaskTimeline'],
    template: `
      <section class="scheduler-task-details">
        <h4>Детали задачи #{{ schedulerTaskStatus.task_id }}</h4>
        <p v-if="schedulerTaskSla">sla: {{ schedulerTaskSla.label }}</p>
        <p v-if="schedulerTaskDone">done: {{ schedulerTaskDone.label }}</p>
        <p v-if="schedulerTaskTimeline">timeline: {{ schedulerTaskTimeline.length }}</p>
      </section>
    `,
  },
}))

vi.mock('@/utils/logger', () => ({
  logger: {
    warn: vi.fn(),
    error: vi.fn(),
  },
}))

import ZoneSchedulerTab from '../ZoneSchedulerTab.vue'

describe('ZoneSchedulerTab.vue', () => {
  beforeEach(() => {
    apiGetMock.mockReset()
    apiPostMock.mockReset()

    apiGetMock.mockImplementation((url: string) => {
      if (url.includes('/control-mode')) {
        return Promise.resolve({
          data: {
            data: {
              control_mode: 'semi',
              allowed_manual_steps: ['clean_fill_start', 'solution_fill_stop'],
            },
          },
        })
      }

      if (url.includes('/scheduler-tasks/')) {
        return Promise.resolve({
          data: {
            status: 'ok',
            data: {
              task_id: 'st-42',
              zone_id: 42,
              task_type: 'irrigation',
              status: 'running',
              created_at: '2026-02-10T08:00:00Z',
              updated_at: '2026-02-10T08:01:00Z',
              scheduled_for: '2026-02-10T08:00:00Z',
              due_at: '2026-02-10T08:02:00Z',
              expires_at: '2026-02-10T08:05:00Z',
              correlation_id: null,
              lifecycle: [],
              timeline: [],
            },
          },
        })
      }

      return Promise.resolve({
        data: {
          status: 'ok',
          data: [
            {
              task_id: 'st-42',
              zone_id: 42,
              task_type: 'irrigation',
              status: 'running',
              updated_at: '2026-02-10T08:01:00Z',
              lifecycle: [],
            },
          ],
        },
      })
    })
  })

  it('показывает отдельную вкладку планировщика зоны и синхронизацию с Laravel scheduler', async () => {
    const wrapper = mount(ZoneSchedulerTab, {
      props: {
        zoneId: 42,
        targets: {} as any,
      },
    })

    await flushPromises()

    expect(apiGetMock).toHaveBeenCalledWith('/api/zones/42/scheduler-tasks', expect.any(Object))
    expect(wrapper.text()).toContain('Планировщик зоны #42')
    expect(wrapper.text()).toContain('Linear-style план задач')
    expect(wrapper.text()).toContain('Лента задач')
    expect(wrapper.text()).toContain('Шаги выполнения')
    expect(wrapper.text()).toContain('Контекст')
    expect(wrapper.text()).toContain('Live sync')
    expect(wrapper.text()).toContain('Активно 1')
    expect(wrapper.text()).toContain('полуавто')
    expect(wrapper.text()).toContain('Детали задачи #st-42')
    expect(wrapper.text()).toContain('Задачи автоматики')
    expect(wrapper.text()).toContain('updated:')
  })
})

import { mount, flushPromises } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'

const getMock = vi.hoisted(() => vi.fn())

vi.mock('@/composables/useApi', () => ({
  useApi: () => ({
    get: getMock,
  }),
}))

vi.mock('@/Layouts/AppLayout.vue', () => ({
  default: { name: 'AppLayout', template: '<div><slot /></div>' },
}))

import LogsIndex from '../Index.vue'

const serviceOptions = [
  { key: 'scheduler', label: 'Scheduler', description: 'Планировщик задач' },
  { key: 'mqtt-bridge', label: 'MQTT Bridge', description: 'MQTT события' },
]

const logsPayload = [
  {
    id: 1,
    service: 'scheduler',
    level: 'INFO',
    message: 'Job started',
    context: { task_name: 'sync' },
    created_at: '2025-01-01T10:00:00Z',
  },
  {
    id: 2,
    service: 'mqtt-bridge',
    level: 'ERROR',
    message: 'Connection lost',
    context: { node_id: 5 },
    created_at: '2025-01-01T10:02:00Z',
  },
]

const metaPayload = {
  page: 1,
  per_page: 50,
  total: 2,
  last_page: 1,
}

const responsePayload = {
  data: {
    data: logsPayload,
    meta: metaPayload,
  },
}

describe('Logs/Index.vue', () => {
  beforeEach(() => {
    getMock.mockReset()
    getMock.mockResolvedValue(responsePayload)
  })

  it('renders service tabs and shows service badges for all services', async () => {
    const wrapper = mount(LogsIndex, {
      props: {
        serviceOptions,
      },
    })

    await flushPromises()

    expect(getMock).toHaveBeenCalledWith('/logs/service', {
      params: expect.objectContaining({
        page: 1,
        per_page: 50,
        exclude_services: ['history-logger', 'history-locker'],
      }),
    })

    const tabs = wrapper.find('[data-testid="logs-service-tabs"]')
    const tabLabels = tabs.findAll('button[role="tab"]').map((button) => button.text())
    expect(tabLabels).toContain('Все сервисы')
    expect(tabLabels).toContain('Scheduler')
    expect(tabLabels).toContain('MQTT Bridge')

    const serviceBadges = wrapper.findAll('[data-testid="service-log-service"]')
    expect(serviceBadges.length).toBe(2)

    wrapper.unmount()
  })

  it('fetches logs for a selected service when tab changes', async () => {
    getMock
      .mockResolvedValueOnce(responsePayload)
      .mockResolvedValueOnce({
        data: {
          data: [logsPayload[0]],
          meta: {
            page: 1,
            per_page: 50,
            total: 1,
            last_page: 1,
          },
        },
      })

    const wrapper = mount(LogsIndex, {
      props: {
        serviceOptions,
      },
    })

    await flushPromises()

    const tabs = wrapper.find('[data-testid="logs-service-tabs"]')
    const schedulerTab = tabs.findAll('button[role="tab"]').find((button) => button.text().includes('Scheduler'))
    expect(schedulerTab).toBeTruthy()

    await schedulerTab?.trigger('click')
    await flushPromises()

    expect(getMock).toHaveBeenLastCalledWith('/logs/service', {
      params: expect.objectContaining({
        page: 1,
        per_page: 50,
        exclude_services: ['history-logger', 'history-locker'],
        service: 'scheduler',
      }),
    })

    wrapper.unmount()
  })
})

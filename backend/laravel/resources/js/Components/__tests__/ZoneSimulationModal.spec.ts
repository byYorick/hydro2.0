import { mount } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

vi.mock('@/Components/Button.vue', () => ({
  default: {
    name: 'Button',
    props: ['disabled', 'variant', 'type'],
    template: '<button :disabled="disabled"><slot /></button>',
  },
}))

vi.mock('@/Components/ChartBase.vue', () => ({
  default: {
    name: 'ChartBase',
    props: ['option'],
    template: '<div class="chart-base" />',
  },
}))

const apiGetMock = vi.fn()
const apiPostMock = vi.fn()

vi.mock('@/composables/useApi', () => ({
  useApi: () => ({
    api: {
      get: (url: string, config?: any) => apiGetMock(url, config),
      post: apiPostMock,
    },
  }),
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    showToast: vi.fn(),
  }),
}))

vi.mock('@/composables/useLoading', () => ({
  useLoading: () => ({
    loading: ref(false),
    startLoading: vi.fn(),
    stopLoading: vi.fn(),
  }),
}))

vi.mock('@/composables/useTheme', () => ({
  useTheme: () => ({
    theme: ref('dark'),
  }),
}))

vi.mock('@/utils/logger', () => ({
  logger: {
    error: vi.fn(),
    debug: vi.fn(),
  },
}))

import ZoneSimulationModal from '../ZoneSimulationModal.vue'

describe('ZoneSimulationModal.vue', () => {
  beforeEach(() => {
    apiGetMock.mockReset()
    apiPostMock.mockReset()
    apiGetMock.mockResolvedValue({
      data: {
        data: {
          data: [],
        },
      },
    })
  })

  it('автоматически заполняет дрейф по initial_state', async () => {
    const wrapper = mount(ZoneSimulationModal, {
      props: {
        show: true,
        zoneId: 1,
        initialTelemetry: {
          ph: 6.0,
          ec: 1.2,
          temperature: 20.0,
          humidity: 60.0,
        },
      },
    })

    await new Promise((resolve) => setTimeout(resolve, 0))
    await wrapper.vm.$nextTick()

    const driftPh = wrapper.find('#simulation-drift-ph').element as HTMLInputElement
    const driftEc = wrapper.find('#simulation-drift-ec').element as HTMLInputElement
    const driftTempAir = wrapper.find('#simulation-drift-temp-air').element as HTMLInputElement
    const driftHumidity = wrapper.find('#simulation-drift-humidity').element as HTMLInputElement
    const driftNoise = wrapper.find('#simulation-drift-noise').element as HTMLInputElement

    expect(Number(driftPh.value)).toBeCloseTo(0.24, 3)
    expect(Number(driftEc.value)).toBeCloseTo(0.084, 3)
    expect(Number(driftTempAir.value)).toBeCloseTo(0.04, 3)
    expect(Number(driftHumidity.value)).toBeCloseTo(0.12, 3)
    expect(Number(driftNoise.value)).toBeCloseTo(0.024, 3)
  })

  it('показывает новые события симуляции сверху', async () => {
    const originalEventSource = global.EventSource
    const addListenerMock = vi.fn()
    const closeMock = vi.fn()

    class MockEventSource {
      addEventListener = addListenerMock
      close = closeMock
      constructor() {}
    }

    // @ts-expect-error - EventSource mock for tests
    global.EventSource = MockEventSource

    const events = [
      {
        id: 1,
        service: 'laravel',
        stage: 'job',
        status: 'running',
        message: 'Старое событие',
        occurred_at: '2026-02-01T10:00:00Z',
      },
      {
        id: 2,
        service: 'automation-engine',
        stage: 'command_publish',
        status: 'sent',
        message: 'Новое событие',
        occurred_at: '2026-02-01T10:01:00Z',
      },
    ]

    apiGetMock.mockImplementation((url: string) => {
      if (url.includes('/simulations/42/events')) {
        return Promise.resolve({ data: { data: events } })
      }
      return Promise.resolve({ data: { data: { data: [] } } })
    })

    try {
      const wrapper = mount(ZoneSimulationModal, {
        props: {
          show: true,
          zoneId: 1,
          activeSimulationId: 42,
          activeSimulationStatus: 'running',
        },
      })

      await new Promise((resolve) => setTimeout(resolve, 0))
      await wrapper.vm.$nextTick()

      const list = wrapper.find('ul.max-h-64')
      const items = list.findAll('li')

      expect(items.length).toBeGreaterThanOrEqual(2)
      expect(items[0].text()).toContain('Новое событие')
      expect(items[1].text()).toContain('Старое событие')
    } finally {
      global.EventSource = originalEventSource
    }
  })
})

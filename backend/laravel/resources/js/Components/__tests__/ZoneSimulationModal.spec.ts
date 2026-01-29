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

    expect(Number(driftPh.value)).toBeCloseTo(0.06, 3)
    expect(Number(driftEc.value)).toBeCloseTo(0.012, 3)
    expect(Number(driftTempAir.value)).toBeCloseTo(0.04, 3)
    expect(Number(driftHumidity.value)).toBeCloseTo(0.12, 3)
    expect(Number(driftNoise.value)).toBeCloseTo(0.012, 3)
  })
})

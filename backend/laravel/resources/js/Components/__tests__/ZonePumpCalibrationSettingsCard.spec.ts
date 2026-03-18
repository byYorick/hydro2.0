import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiGetMock = vi.hoisted(() => vi.fn())
const apiPutMock = vi.hoisted(() => vi.fn())
const showToastMock = vi.hoisted(() => vi.fn())
const pumpSettingsState = vi.hoisted(() => ({
  value: {
    ml_per_sec_min: 0.01,
    ml_per_sec_max: 20,
    age_warning_days: 30,
  } as Record<string, number> | undefined,
}))

vi.mock('@/Components/Card.vue', () => ({
  default: {
    name: 'Card',
    template: '<div><slot /></div>',
  },
}))

vi.mock('@/Components/Button.vue', () => ({
  default: {
    name: 'Button',
    props: ['disabled', 'variant', 'size'],
    emits: ['click'],
    template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
  },
}))

vi.mock('@/Components/Badge.vue', () => ({
  default: {
    name: 'Badge',
    props: ['variant'],
    template: '<span><slot /></span>',
  },
}))

vi.mock('@/composables/useApi', () => ({
  useApi: () => ({
    api: {
      get: apiGetMock,
      put: apiPutMock,
    },
  }),
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    showToast: showToastMock,
  }),
}))

vi.mock('@/composables/usePageProps', () => ({
  usePageProp: () => ({
    value: pumpSettingsState.value,
  }),
}))

import ZonePumpCalibrationSettingsCard from '../ZonePumpCalibrationSettingsCard.vue'

describe('ZonePumpCalibrationSettingsCard.vue', () => {
  beforeEach(() => {
    apiGetMock.mockReset()
    apiPutMock.mockReset()
    showToastMock.mockReset()
    pumpSettingsState.value = {
      ml_per_sec_min: 0.01,
      ml_per_sec_max: 20,
      age_warning_days: 30,
    }

    apiGetMock.mockResolvedValue({
      data: {
        data: {
          preset: { id: 1 },
          base_config: {
            pump_calibration: {},
          },
          phase_overrides: {},
          meta: {
            pump_calibration_field_catalog: [
              {
                key: 'pump',
                label: 'Pump',
                description: 'Pump settings',
                fields: [
                  {
                    path: 'ml_per_sec_min',
                    label: 'Мин. скорость',
                    description: 'Нижний системный порог',
                    type: 'number',
                    step: 0.001,
                  },
                ],
              },
            ],
          },
        },
      },
    })
  })

  it('показывает системное значение в placeholder', async () => {
    const wrapper = mount(ZonePumpCalibrationSettingsCard, {
      props: { zoneId: 7 },
    })

    await flushPromises()

    const input = wrapper.find('input')
    expect(input.attributes('placeholder')).toContain('Система: 0.01')
    expect(wrapper.text()).toContain('Effective: 0.01')
  })

  it('не падает без pumpCalibrationSettings в page props', async () => {
    pumpSettingsState.value = undefined

    const wrapper = mount(ZonePumpCalibrationSettingsCard, {
      props: { zoneId: 7 },
    })

    await flushPromises()

    const input = wrapper.find('input')
    expect(input.attributes('placeholder')).toContain('Система: 0.001')
    expect(wrapper.text()).toContain('Effective: 0.001')
  })
})

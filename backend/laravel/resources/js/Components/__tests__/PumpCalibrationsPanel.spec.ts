import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiGetMock = vi.hoisted(() => vi.fn())
const getPumpCalibrationsMock = vi.hoisted(() => vi.fn())
const updatePumpCalibrationMock = vi.hoisted(() => vi.fn())
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
    },
  }),
}))

vi.mock('@/composables/usePidConfig', () => ({
  usePidConfig: () => ({
    getPumpCalibrations: getPumpCalibrationsMock,
    updatePumpCalibration: updatePumpCalibrationMock,
  }),
}))

vi.mock('@/composables/usePageProps', () => ({
  usePageProp: () => ({
    value: pumpSettingsState.value,
  }),
}))

import PumpCalibrationsPanel from '../PumpCalibrationsPanel.vue'

describe('PumpCalibrationsPanel.vue', () => {
  beforeEach(() => {
    apiGetMock.mockReset()
    getPumpCalibrationsMock.mockReset()
    updatePumpCalibrationMock.mockReset()
    pumpSettingsState.value = {
      ml_per_sec_min: 0.01,
      ml_per_sec_max: 20,
      age_warning_days: 30,
    }

    getPumpCalibrationsMock.mockResolvedValue([
      {
        node_channel_id: 101,
        role: 'ph_acid_pump',
        component: 'ph_down',
        channel_label: 'pH Down',
        node_uid: 'pump-node-1',
        channel: 'pump_ph_down',
        ml_per_sec: 0.55,
        k_ms_per_ml_l: null,
        source: 'manual',
        valid_from: '2026-03-17T09:00:00Z',
        is_active: true,
        calibration_age_days: 2,
      },
      {
        node_channel_id: 102,
        role: 'ph_base_pump',
        component: 'ph_up',
        channel_label: 'pH Up',
        node_uid: 'pump-node-1',
        channel: 'pump_ph_up',
        ml_per_sec: null,
        k_ms_per_ml_l: null,
        source: null,
        valid_from: null,
        is_active: false,
        calibration_age_days: null,
      },
    ])
    apiGetMock.mockResolvedValue({
      data: {
        status: 'ok',
        data: [
          {
            event_id: 11,
            type: 'PUMP_CALIBRATION_FINISHED',
            message: 'Калибровка насоса завершена: 0.55 мл/с',
            created_at: '2026-03-17T09:10:00Z',
            payload: {
              component: 'ph_down',
              node_channel_id: 101,
              source: 'manual',
              ml_per_sec: 0.55,
            },
          },
        ],
      },
    })
  })

  it('показывает history по роли насоса', async () => {
    const wrapper = mount(PumpCalibrationsPanel, {
      props: { zoneId: 7 },
    })

    await flushPromises()

    expect(getPumpCalibrationsMock).toHaveBeenCalledWith(7)
    expect(apiGetMock).toHaveBeenCalledWith('/api/zones/7/events', {
      params: {
        limit: 80,
      },
    })
    expect(wrapper.text()).toContain('Калибровка насоса завершена: 0.55 мл/с')
    expect(wrapper.text()).toContain('Вручную')
    expect(wrapper.text()).toContain('0.55 мл/с')
    expect(wrapper.text()).toContain('1 без калибровки')
  })

  it('перезагружает калибровки после успешного сохранения', async () => {
    getPumpCalibrationsMock
      .mockResolvedValueOnce([
        {
          node_channel_id: 102,
          role: 'ph_base_pump',
          component: 'ph_up',
          channel_label: 'pH Up',
          node_uid: 'pump-node-1',
          channel: 'pump_ph_up',
          ml_per_sec: null,
          k_ms_per_ml_l: null,
          source: null,
          valid_from: null,
          is_active: false,
          calibration_age_days: null,
        },
      ])
      .mockResolvedValueOnce([
        {
          node_channel_id: 102,
          role: 'ph_base_pump',
          component: 'ph_up',
          channel_label: 'pH Up',
          node_uid: 'pump-node-1',
          channel: 'pump_ph_up',
          ml_per_sec: 0.5,
          k_ms_per_ml_l: null,
          source: 'manual_calibration',
          valid_from: '2026-03-23T10:00:00Z',
          is_active: true,
          calibration_age_days: 0,
        },
      ])
    apiGetMock
      .mockResolvedValueOnce({
        data: {
          status: 'ok',
          data: [],
        },
      })
      .mockResolvedValueOnce({
        data: {
          status: 'ok',
          data: [
            {
              event_id: 21,
              type: 'PUMP_CALIBRATION_FINISHED',
              message: 'Калибровка насоса завершена: 0.50 мл/с',
              created_at: '2026-03-23T10:00:00Z',
              payload: {
                component: 'ph_up',
                node_channel_id: 102,
                ml_per_sec: 0.5,
              },
            },
          ],
        },
      })

    const wrapper = mount(PumpCalibrationsPanel, {
      props: { zoneId: 7, saveSuccessSeq: 0 },
    })

    await flushPromises()
    expect(wrapper.text()).toContain('Нет калибровки')

    await wrapper.setProps({ saveSuccessSeq: 1 })
    await flushPromises()

    expect(getPumpCalibrationsMock).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('0.50 мл/с')
    expect(wrapper.text()).toContain('Калибровка (23.03.2026)')
    expect(wrapper.text()).toContain('Калибровка насоса завершена: 0.50 мл/с')
  })

  it('эмитит открытие pump calibration modal из CTA', async () => {
    const wrapper = mount(PumpCalibrationsPanel, {
      props: { zoneId: 7 },
    })

    await flushPromises()
    expect(wrapper.text()).not.toContain('Сохранить')
    expect(wrapper.text()).toContain('Диапазон 0.01-20 мл/с')
    const wizardButton = wrapper.findAll('button').find((button) => button.text() === 'Открыть визард')
    expect(wizardButton).toBeTruthy()
    await wizardButton!.trigger('click')

    expect(wrapper.emitted('open-pump-calibration')).toBeTruthy()
  })

  it('не падает без pumpCalibrationSettings в page props', async () => {
    pumpSettingsState.value = undefined

    const wrapper = mount(PumpCalibrationsPanel, {
      props: { zoneId: 7 },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('Диапазон 0-20 мл/с')
  })
})

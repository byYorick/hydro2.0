import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import PumpCalibrationModal from '../PumpCalibrationModal.vue'

const sampleDevices = [
  {
    id: 1,
    uid: 'pump-node-1',
    type: 'actuator',
    status: 'online',
    channels: [
      { id: 101, node_id: 1, channel: 'pump_npk', type: 'ACTUATOR', metric: null, unit: null },
      { id: 102, node_id: 1, channel: 'pump_ph_up', type: 'ACTUATOR', metric: null, unit: null },
    ],
  },
]

describe('PumpCalibrationModal', () => {
  it('эмитит запуск калибровки с валидным payload', async () => {
    const wrapper = mount(PumpCalibrationModal, {
      props: {
        show: true,
        zoneId: 1,
        devices: sampleDevices,
        loadingRun: false,
        loadingSave: false,
      },
    })

    await wrapper.find('[data-testid="pump-calibration-component"]').setValue('micro')
    await wrapper.find('[data-testid="pump-calibration-channel"]').setValue('102')
    await wrapper.find('[data-testid="pump-calibration-duration"]').setValue('35')
    await wrapper.find('[data-testid="pump-calibration-start-btn"]').trigger('click')

    const emitted = wrapper.emitted('start')
    expect(emitted).toBeTruthy()
    expect(emitted?.[0]?.[0]).toEqual({
      node_channel_id: 102,
      duration_sec: 35,
      component: 'micro',
    })
  })

  it('эмитит сохранение фактического объема с skip_run=true', async () => {
    const wrapper = mount(PumpCalibrationModal, {
      props: {
        show: true,
        zoneId: 1,
        devices: sampleDevices,
        loadingRun: false,
        loadingSave: false,
      },
    })

    await wrapper.find('[data-testid="pump-calibration-component"]').setValue('ph_down')
    await wrapper.find('[data-testid="pump-calibration-channel"]').setValue('101')
    await wrapper.find('[data-testid="pump-calibration-duration"]').setValue('20')
    await wrapper.find('[data-testid="pump-calibration-actual-ml"]').setValue('8.5')
    await wrapper.find('[data-testid="pump-calibration-save-btn"]').trigger('click')

    const emitted = wrapper.emitted('save')
    expect(emitted).toBeTruthy()
    expect(emitted?.[0]?.[0]).toEqual({
      node_channel_id: 101,
      duration_sec: 20,
      actual_ml: 8.5,
      component: 'ph_down',
      skip_run: true,
    })
  })

  it('показывает readiness-подсказку для выбранного dosing path', async () => {
    const wrapper = mount(PumpCalibrationModal, {
      props: {
        show: true,
        zoneId: 1,
        devices: [
          {
            id: 1,
            uid: 'pump-node-1',
            type: 'actuator',
            status: 'online',
            channels: [
              {
                id: 101,
                node_id: 1,
                channel: 'pump_ph_down',
                type: 'ACTUATOR',
                metric: null,
                unit: null,
              },
              {
                id: 102,
                node_id: 1,
                channel: 'pump_ph_up',
                type: 'ACTUATOR',
                metric: null,
                unit: null,
                pump_calibration: {
                  ml_per_sec: 0.72,
                },
              },
            ],
          },
        ],
        loadingRun: false,
        loadingSave: false,
      },
    })

    await wrapper.find('[data-testid="pump-calibration-component"]').setValue('ph_down')
    await wrapper.find('[data-testid="pump-calibration-channel"]').setValue('101')

    const readiness = wrapper.find('[data-testid="pump-calibration-readiness"]')
    expect(readiness.exists()).toBe(true)
    expect(readiness.text()).toContain('Выбранный компонент относится к pH dosing path.')
    expect(readiness.text()).toContain('pH Up: Откалиброван')
    expect(readiness.text()).toContain('pH Down: Текущий выбор без сохранённой калибровки')
    expect(readiness.text()).toContain('После сохранения этот компонент закроет последний пробел в pH dosing path.')
  })
})

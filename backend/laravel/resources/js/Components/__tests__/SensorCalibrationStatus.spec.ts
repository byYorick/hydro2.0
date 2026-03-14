import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import SensorCalibrationStatus from '../SensorCalibrationStatus.vue'

const fetchStatusMock = vi.fn()
const fetchHistoryMock = vi.fn()

vi.mock('@/composables/useSensorCalibration', () => ({
  useSensorCalibration: vi.fn(() => ({
    fetchStatus: fetchStatusMock,
    fetchHistory: fetchHistoryMock,
  })),
}))

describe('SensorCalibrationStatus', () => {
  afterEach(() => {
    fetchStatusMock.mockReset()
    fetchHistoryMock.mockReset()
  })

  it('запрашивает историю по конкретному node_channel_id', async () => {
    fetchStatusMock.mockResolvedValue([
      {
        node_channel_id: 101,
        channel_uid: 'ph_sensor',
        sensor_type: 'ph',
        node_uid: 'node-ph-1',
        last_calibrated_at: null,
        days_since_calibration: null,
        calibration_status: 'never',
        has_active_session: false,
        active_calibration_id: null,
      },
    ])
    fetchHistoryMock.mockResolvedValue([])

    const wrapper = mount(SensorCalibrationStatus, {
      props: {
        zoneId: 1,
        settings: {
          ph_point_1_value: 7,
          ph_point_2_value: 4,
          ec_point_1_tds: 1413,
          ec_point_2_tds: 2764,
          ph_reference_min: 0,
          ph_reference_max: 14,
          ec_tds_reference_max: 10000,
          reminder_days: 30,
          critical_days: 45,
        },
      },
      global: {
        stubs: {
          Card: { template: '<div><slot /></div>' },
          Badge: { template: '<span><slot /></span>' },
          Modal: { template: '<div><slot /></div>' },
          SensorCalibrationWizard: { template: '<div />' },
          Button: { template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>', props: ['disabled'] },
        },
      },
    })

    await flushPromises()

    const historyButton = wrapper.findAll('button').find((button) => button.text() === 'История')
    expect(historyButton).toBeTruthy()

    await historyButton!.trigger('click')
    await flushPromises()

    expect(fetchHistoryMock).toHaveBeenCalledWith({
      sensorType: 'ph',
      nodeChannelId: 101,
      limit: 20,
    })
  })
})

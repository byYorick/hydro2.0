import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import SensorCalibrationWizard from '../SensorCalibrationWizard.vue'

const startCalibrationMock = vi.fn()
const submitPointMock = vi.fn()
const cancelCalibrationMock = vi.fn()
const getCalibrationMock = vi.fn()

vi.mock('@/composables/useSensorCalibration', () => ({
  useSensorCalibration: vi.fn(() => ({
    startCalibration: startCalibrationMock,
    submitPoint: submitPointMock,
    cancelCalibration: cancelCalibrationMock,
    getCalibration: getCalibrationMock,
  })),
}))

describe('SensorCalibrationWizard', () => {
  beforeEach(() => {
    vi.spyOn(window, 'setInterval').mockReturnValue(1 as unknown as ReturnType<typeof setInterval>)
    vi.spyOn(window, 'clearInterval').mockImplementation(() => undefined)
  })

  afterEach(() => {
    vi.restoreAllMocks()
    startCalibrationMock.mockReset()
    submitPointMock.mockReset()
    cancelCalibrationMock.mockReset()
    getCalibrationMock.mockReset()
    document.body.innerHTML = ''
  })

  it('рендерит визард в body через teleport', async () => {
    mount(SensorCalibrationWizard, {
      attachTo: document.body,
      props: {
        open: true,
        zoneId: 1,
        overview: {
          node_channel_id: 101,
          channel_uid: 'ec_sensor',
          sensor_type: 'ec',
          node_uid: 'node-ec-1',
          last_calibrated_at: null,
          days_since_calibration: null,
          calibration_status: 'never',
          has_active_session: false,
          active_calibration_id: null,
        },
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
          Modal: {
            props: ['open', 'title'],
            template: '<div v-if="open" class="modal-stub"><div class="modal-title">{{ title }}</div><slot /></div>',
          },
          Button: { template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>', props: ['disabled'] },
        },
      },
    })

    await flushPromises()

    expect(document.body.textContent).toContain('Калибровка EC-сенсора')
    expect(document.body.textContent).toContain('Канал: ec_sensor')
  })

  it('подхватывает активную сессию при открытии wizard', async () => {
    getCalibrationMock.mockResolvedValue({
      id: 42,
      zone_id: 1,
      node_channel_id: 101,
      sensor_type: 'ph',
      status: 'point_1_pending',
      point_1_reference: 7,
      point_1_command_id: 'cmd-1',
      point_1_sent_at: '2026-03-13T10:00:00.000Z',
      point_1_result: null,
      point_1_error: null,
      point_2_reference: null,
      point_2_command_id: null,
      point_2_sent_at: null,
      point_2_result: null,
      point_2_error: null,
      completed_at: null,
      calibrated_by: 1,
      notes: null,
      meta: {},
      node_channel: { id: 101, channel: 'ph_sensor', node_uid: 'node-ph-1' },
      created_at: '2026-03-13T09:59:00.000Z',
      updated_at: '2026-03-13T10:00:00.000Z',
    })

    const wrapper = mount(SensorCalibrationWizard, {
      attachTo: document.body,
      props: {
        open: true,
        zoneId: 1,
        overview: {
          node_channel_id: 101,
          channel_uid: 'ph_sensor',
          sensor_type: 'ph',
          node_uid: 'node-ph-1',
          last_calibrated_at: null,
          days_since_calibration: null,
          calibration_status: 'never',
          has_active_session: true,
          active_calibration_id: 42,
        },
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
          Modal: { template: '<div><slot /></div>' },
          Button: { template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>', props: ['disabled'] },
        },
      },
    })

    await flushPromises()

    expect(getCalibrationMock).toHaveBeenCalledWith(42)
    expect(startCalibrationMock).not.toHaveBeenCalled()
    expect(document.body.textContent).toContain('point_1_pending')
    expect(document.body.textContent).not.toContain('Начать калибровку')

    wrapper.unmount()
  })
})

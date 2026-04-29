import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import PumpCalibrationDrawer from '../PumpCalibrationDrawer.vue'
import type { Device } from '@/types'
import type { PumpCalibration } from '@/types/PidConfig'

function makePump(overrides: Partial<PumpCalibration>): PumpCalibration {
  return {
    node_channel_id: 0,
    role: 'pump_a',
    component: 'NPK',
    channel_label: 'node · pump_a',
    node_uid: 'node-1',
    channel: 'pump_a',
    ml_per_sec: null,
    k_ms_per_ml_l: null,
    source: null,
    valid_from: null,
    is_active: true,
    ...overrides,
  }
}

describe('PumpCalibrationDrawer', () => {
  it('не перезаписывает initialComponent при пустом initialNodeChannelId', () => {
    const devices: Device[] = [
      {
        id: 1,
        uid: 'node-1',
        type: 'ph',
        status: 'online',
        channels: [
          { id: 101, channel: 'pump_a', type: 'ACTUATOR', metric: null, unit: null },
          { id: 202, channel: 'pump_acid', type: 'ACTUATOR', metric: null, unit: null },
        ],
      },
    ]

    const pumps: PumpCalibration[] = [
      makePump({ role: 'pump_a', node_channel_id: 101, channel: 'pump_a', component: 'NPK' }),
      makePump({ role: 'pump_acid', node_channel_id: 202, channel: 'pump_acid', component: 'pH Down' }),
    ]

    const w = mount(PumpCalibrationDrawer, {
      props: {
        show: true,
        zoneId: 7,
        devices,
        pumps,
        initialComponent: 'ph_down',
        initialNodeChannelId: null,
      },
      global: {
        stubs: {
          teleport: true,
          transition: false,
        },
      },
    })

    expect(w.text()).toContain('pH Down')
    expect(w.text()).toContain('node-1 · pump_acid')
    expect(w.text()).toContain('ch202')
    expect(w.text()).not.toContain('ch101')
  })
})

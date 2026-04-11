import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const sensorCalibrationsListMock = vi.hoisted(() => vi.fn())

vi.mock('@/services/api', () => ({
  api: {
    zones: {
      sensorCalibrationsList: sensorCalibrationsListMock,
      sensorCalibrationStatus: vi.fn(),
      sensorCalibration: vi.fn(),
      sensorCalibrationStart: vi.fn(),
      sensorCalibrationAddPoint: vi.fn(),
      sensorCalibrationCancel: vi.fn(),
    },
  },
}))

import { useSensorCalibration } from '../useSensorCalibration'

describe('useSensorCalibration', () => {
  const mountComposable = () => {
    let composable: ReturnType<typeof useSensorCalibration> | null = null

    const wrapper = mount(defineComponent({
      setup() {
        composable = useSensorCalibration(7)
        return () => null
      },
    }))

    if (!composable) {
      throw new Error('useSensorCalibration not initialized')
    }

    return { wrapper, composable }
  }

  beforeEach(() => {
    sensorCalibrationsListMock.mockReset()
  })

  it('передаёт node_channel_id в history-запрос', async () => {
    sensorCalibrationsListMock.mockResolvedValue([])

    const { wrapper, composable } = mountComposable()

    await composable.fetchHistory({
      sensorType: 'ph',
      nodeChannelId: 101,
      limit: 15,
    })

    expect(sensorCalibrationsListMock).toHaveBeenCalledWith(7, {
      sensor_type: 'ph',
      node_channel_id: 101,
      limit: 15,
    })

    wrapper.unmount()
  })
})

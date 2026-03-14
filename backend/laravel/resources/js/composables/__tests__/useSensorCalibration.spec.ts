import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useSensorCalibration } from '../useSensorCalibration'

vi.mock('../useApi', () => ({
  useApi: vi.fn(() => ({
    api: {
      get: vi.fn(),
      post: vi.fn(),
    },
  })),
}))

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
    vi.clearAllMocks()
  })

  it('передаёт node_channel_id в history-запрос', async () => {
    const { useApi } = await import('../useApi')
    const getMock = vi.fn().mockResolvedValue({ data: { data: [] } })

    vi.mocked(useApi).mockReturnValue({
      api: {
        get: getMock,
        post: vi.fn(),
      },
    } as never)

    const { wrapper, composable } = mountComposable()

    await composable.fetchHistory({
      sensorType: 'ph',
      nodeChannelId: 101,
      limit: 15,
    })

    expect(getMock).toHaveBeenCalledWith('/api/zones/7/sensor-calibrations', {
      params: {
        sensor_type: 'ph',
        node_channel_id: 101,
        limit: 15,
      },
    })

    wrapper.unmount()
  })
})

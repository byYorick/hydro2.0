import { mount } from '@vue/test-utils'
import { describe, it, expect, vi } from 'vitest'
import ZoneTelemetryChart from '../ZoneTelemetryChart.vue'

vi.mock('vue-echarts', () => ({
  default: {
    name: 'VChart',
    template: '<div>Mock Chart</div>',
  },
}))

vi.mock('@/Components/Card.vue', () => ({
  default: { name: 'Card', template: '<div class="card"><slot /></div>' },
}))

vi.mock('@/Components/ChartBase.vue', () => ({
  default: {
    name: 'ChartBase',
    props: ['option'],
    template: '<div class="chart-base"></div>',
  },
}))

function chartOption(wrapper: ReturnType<typeof mount>): Record<string, unknown> {
  const chart = wrapper.findComponent({ name: 'ChartBase' })
  expect(chart.exists()).toBe(true)
  return chart.props('option') as Record<string, unknown>
}

describe('ZoneTelemetryChart - DataZoom (P2-3)', () => {
  it('should enable DataZoom for large datasets (>100 points)', () => {
    const largeDataset = Array.from({ length: 150 }, (_, i) => ({
      ts: Date.now() + i * 1000,
      value: 6.5 + Math.random(),
    }))

    const wrapper = mount(ZoneTelemetryChart, {
      props: {
        data: largeDataset,
        seriesName: 'pH',
        title: 'pH Chart',
      },
    })

    const option = chartOption(wrapper)
    expect(option.dataZoom).toBeDefined()
    expect(Array.isArray(option.dataZoom)).toBe(true)
    expect((option.dataZoom as unknown[]).length).toBeGreaterThan(0)
  })

  it('should not enable slider DataZoom for small datasets (<=50 points)', () => {
    const smallDataset = Array.from({ length: 50 }, (_, i) => ({
      ts: Date.now() + i * 1000,
      value: 6.5 + Math.random(),
    }))

    const wrapper = mount(ZoneTelemetryChart, {
      props: {
        data: smallDataset,
        seriesName: 'pH',
        title: 'pH Chart',
      },
    })

    const option = chartOption(wrapper)
    const dataZoom = option.dataZoom as Array<{ type?: string }>
    const sliderZoom = dataZoom?.find((dz) => dz.type === 'slider')
    expect(sliderZoom).toBeUndefined()
  })

  it('should include inside DataZoom for large datasets', () => {
    const largeDataset = Array.from({ length: 150 }, (_, i) => ({
      ts: Date.now() + i * 1000,
      value: 6.5 + Math.random(),
    }))

    const wrapper = mount(ZoneTelemetryChart, {
      props: {
        data: largeDataset,
        seriesName: 'pH',
        title: 'pH Chart',
      },
    })

    const option = chartOption(wrapper)
    const dataZoom = option.dataZoom as Array<{ type?: string }>

    const insideZoom = dataZoom.find((dz) => dz.type === 'inside')
    const sliderZoom = dataZoom.find((dz) => dz.type === 'slider')

    expect(insideZoom).toBeDefined()
    expect(sliderZoom).toBeDefined()
  })

  it('should adjust grid bottom padding for DataZoom slider', () => {
    const largeDataset = Array.from({ length: 150 }, (_, i) => ({
      ts: Date.now() + i * 1000,
      value: 6.5 + Math.random(),
    }))

    const wrapper = mount(ZoneTelemetryChart, {
      props: {
        data: largeDataset,
        seriesName: 'pH',
        title: 'pH Chart',
      },
    })

    const option = chartOption(wrapper)
    expect((option.grid as { bottom?: number }).bottom).toBe(80)
  })

  it('should use compact grid for small datasets', () => {
    const smallDataset = Array.from({ length: 50 }, (_, i) => ({
      ts: Date.now() + i * 1000,
      value: 6.5 + Math.random(),
    }))

    const wrapper = mount(ZoneTelemetryChart, {
      props: {
        data: smallDataset,
        seriesName: 'pH',
        title: 'pH Chart',
      },
    })

    const option = chartOption(wrapper)
    expect((option.grid as { bottom?: number }).bottom).toBe(40)
  })
})

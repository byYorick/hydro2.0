import { mount } from '@vue/test-utils'
import { describe, it, expect, vi } from 'vitest'
import ZoneTelemetryChart from '../ZoneTelemetryChart.vue'

vi.mock('@/Components/Card.vue', () => ({
  default: { name: 'Card', template: '<div class="card"><slot /></div>' },
}))

vi.mock('@/Components/Button.vue', () => ({
  default: {
    name: 'Button',
    props: ['size', 'variant'],
    template: '<button :class="variant" @click="$emit(\'click\')"><slot /></button>',
  },
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

describe('ZoneTelemetryChart.vue', () => {
  const sampleData = [
    { ts: Date.now() - 60000, value: 5.8 },
    { ts: Date.now(), value: 5.9 },
  ]

  it('отображает заголовок и подсказку по взаимодействию', () => {
    const wrapper = mount(ZoneTelemetryChart, {
      props: {
        title: 'pH',
        seriesName: 'pH',
        data: sampleData,
        timeRange: '24H',
      },
    })

    expect(wrapper.text()).toContain('pH')
    expect(wrapper.text()).toContain('Колесо мыши')
    expect(wrapper.text()).toContain('Перетаскивание')
  })

  it('передаёт в ChartBase option с серией и dataZoom под timeRange', () => {
    const wrapper = mount(ZoneTelemetryChart, {
      props: {
        title: 'pH',
        seriesName: 'pH',
        data: sampleData,
        timeRange: '7D',
      },
    })

    const option = chartOption(wrapper)
    const dataZoom = option.dataZoom as Array<{ start?: number }>
    expect(Array.isArray(option.series)).toBe(true)
    expect((option.series as unknown[]).length).toBeGreaterThan(0)
    expect(dataZoom?.[0]?.start).toBe(70)
  })

  it('передаёт данные в ChartBase', () => {
    const wrapper = mount(ZoneTelemetryChart, {
      props: {
        title: 'EC',
        seriesName: 'EC',
        data: sampleData,
        timeRange: '24H',
      },
    })

    const option = chartOption(wrapper)
    expect(option.series).toBeDefined()
    expect(Array.isArray(option.series)).toBe(true)
    expect(option.series.length).toBeGreaterThan(0)
    expect((option.series as Array<{ name?: string }>)[0].name).toBe('EC')
    expect((option.series as Array<{ data?: unknown }>)[0].data).toBeDefined()
  })

  it('обрабатывает пустые данные', () => {
    const wrapper = mount(ZoneTelemetryChart, {
      props: {
        title: 'pH',
        seriesName: 'pH',
        data: [],
        timeRange: '24H',
      },
    })

    const option = chartOption(wrapper)
    expect(option.series).toBeDefined()
  })
})

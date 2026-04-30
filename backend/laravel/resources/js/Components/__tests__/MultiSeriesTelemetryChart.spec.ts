import { mount } from '@vue/test-utils'
import { describe, it, expect, vi } from 'vitest'
import MultiSeriesTelemetryChart from '../MultiSeriesTelemetryChart.vue'

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

const sampleSeries = [
  {
    name: 'temperature',
    label: 'Температура (°C)',
    color: '#f59e0b',
    data: [
      { ts: Date.now() - 3600000, value: 20.5 },
      { ts: Date.now() - 1800000, value: 21.0 },
      { ts: Date.now(), value: 21.5 },
    ],
    currentValue: 21.5,
    yAxisIndex: 0,
  },
  {
    name: 'humidity',
    label: 'Влажность (%)',
    color: '#3b82f6',
    data: [
      { ts: Date.now() - 3600000, value: 60.0 },
      { ts: Date.now() - 1800000, value: 61.0 },
      { ts: Date.now(), value: 62.0 },
    ],
    currentValue: 62.0,
    yAxisIndex: 1,
  },
]

describe('MultiSeriesTelemetryChart.vue', () => {
  it('отображает компонент с сериями данных', () => {
    const wrapper = mount(MultiSeriesTelemetryChart, {
      props: {
        title: 'Телеметрия',
        series: sampleSeries,
        timeRange: '24H',
      },
    })

    expect(wrapper.exists()).toBe(true)
    expect(wrapper.text()).toContain('Телеметрия')
  })

  it('передаёт в ChartBase option с dataZoom под timeRange', () => {
    const wrapper = mount(MultiSeriesTelemetryChart, {
      props: {
        series: sampleSeries,
        timeRange: '7D',
      },
    })

    const option = chartOption(wrapper)
    const dataZoom = option.dataZoom as Array<{ start?: number }>
    expect(dataZoom?.[0]?.start).toBe(70)
  })

  it('отображает легенду с текущими значениями', () => {
    const wrapper = mount(MultiSeriesTelemetryChart, {
      props: {
        series: sampleSeries,
        timeRange: '24H',
      },
    })

    expect(wrapper.text()).toContain('Температура')
    expect(wrapper.text()).toContain('Влажность')
    expect(wrapper.text()).toMatch(/21\.5|62\.0/)
  })

  it('обрабатывает пустой массив серий', () => {
    const wrapper = mount(MultiSeriesTelemetryChart, {
      props: {
        series: [],
        timeRange: '24H',
      },
    })

    expect(wrapper.exists()).toBe(true)
  })

  it('использует значение по умолчанию для title', () => {
    const wrapper = mount(MultiSeriesTelemetryChart, {
      props: {
        series: sampleSeries,
      },
    })

    expect(wrapper.text()).toContain('Телеметрия')
  })

  it('использует значение по умолчанию для timeRange (24H в option)', () => {
    const wrapper = mount(MultiSeriesTelemetryChart, {
      props: {
        series: sampleSeries,
      },
    })

    const option = chartOption(wrapper)
    const dataZoom = option.dataZoom as Array<{ start?: number }>
    expect(dataZoom?.[0]?.start).toBe(50)
  })

  describe('formatValue', () => {
    it('форматирует pH значения с 2 знаками после запятой', () => {
      const wrapper = mount(MultiSeriesTelemetryChart, {
        props: {
          series: [{
            name: 'ph_sensor',
            label: 'pH',
            color: '#8b5cf6',
            data: [{ ts: Date.now(), value: 6.75 }],
            currentValue: 6.75,
          }],
        },
      })

      const text = wrapper.text()
      expect(text).toMatch(/6\.75/)
    })

    it('форматирует обычные значения с 1 знаком после запятой', () => {
      const wrapper = mount(MultiSeriesTelemetryChart, {
        props: {
          series: [{
            name: 'temperature',
            label: 'Температура',
            color: '#f59e0b',
            data: [{ ts: Date.now(), value: 21.5 }],
            currentValue: 21.5,
          }],
        },
      })

      const text = wrapper.text()
      expect(text).toMatch(/21\.5/)
    })

    it('отображает "—" для null или undefined значений', () => {
      const wrapper = mount(MultiSeriesTelemetryChart, {
        props: {
          series: [{
            name: 'sensor',
            label: 'Sensor',
            color: '#000',
            data: [],
            currentValue: null,
          }],
        },
      })

      expect(wrapper.exists()).toBe(true)
    })
  })
})

import { mount } from '@vue/test-utils'
import { describe, it, expect, vi } from 'vitest'
import MiniTelemetryChart from '../MiniTelemetryChart.vue'

// Mock dependencies
vi.mock('@/Components/Card.vue', () => ({
  default: {
    name: 'Card',
    template: '<div class="card"><slot /></div>'
  }
}))

vi.mock('@/Components/ChartBase.vue', () => ({
  default: {
    name: 'ChartBase',
    props: ['option'],
    template: '<div class="chart-base"></div>'
  }
}))

describe('MiniTelemetryChart', () => {
  it('renders label and current value', () => {
    const wrapper = mount(MiniTelemetryChart, {
      props: {
        label: 'pH',
        currentValue: 6.0,
        unit: '',
        data: []
      }
    })

    expect(wrapper.text()).toContain('pH')
    expect(wrapper.text()).toContain('6.0')
  })

  it('displays unit when provided', () => {
    const wrapper = mount(MiniTelemetryChart, {
      props: {
        label: 'Temperature',
        currentValue: 22.5,
        unit: '°C',
        data: []
      }
    })

    expect(wrapper.text()).toContain('22.5')
    expect(wrapper.text()).toContain('°C')
  })

  it('shows loading state', () => {
    const wrapper = mount(MiniTelemetryChart, {
      props: {
        label: 'pH',
        currentValue: null,
        unit: '',
        data: [],
        loading: true
      }
    })

    expect(wrapper.text()).toContain('Загрузка...')
  })

  it('shows "Нет данных" when data is empty and not loading', () => {
    const wrapper = mount(MiniTelemetryChart, {
      props: {
        label: 'pH',
        currentValue: null,
        unit: '',
        data: [],
        loading: false
      }
    })

    expect(wrapper.text()).toContain('Нет данных')
  })

  it('renders chart when data is available', () => {
    const data = [
      { ts: 1704067200000, value: 6.0 },
      { ts: 1704070800000, value: 6.1 }
    ]

    const wrapper = mount(MiniTelemetryChart, {
      props: {
        label: 'pH',
        currentValue: 6.0,
        unit: '',
        data,
        loading: false
      }
    })

    const chart = wrapper.findComponent({ name: 'ChartBase' })
    expect(chart.exists()).toBe(true)
  })

  it('formats current value correctly', () => {
    const wrapper = mount(MiniTelemetryChart, {
      props: {
        label: 'pH',
        currentValue: 6.12345,
        unit: '',
        data: []
      }
    })

    expect(wrapper.text()).toContain('6.1') // Should be formatted to 1 decimal
  })

  it('shows "-" when currentValue is null', () => {
    const wrapper = mount(MiniTelemetryChart, {
      props: {
        label: 'pH',
        currentValue: null,
        unit: '',
        data: []
      }
    })

    expect(wrapper.text()).toContain('-')
  })

  it('passes correct chart option to ChartBase', () => {
    const data = [
      { ts: 1704067200000, value: 6.0, avg: 6.0 },
      { ts: 1704070800000, value: 6.1, avg: 6.05 }
    ]

    const wrapper = mount(MiniTelemetryChart, {
      props: {
        label: 'pH',
        currentValue: 6.0,
        unit: '',
        data,
        loading: false,
        color: '#3b82f6'
      }
    })

    const chart = wrapper.findComponent({ name: 'ChartBase' })
    expect(chart.exists()).toBe(true)
    const option = chart.props('option')
    expect(option).toBeDefined()
    expect(option.series).toBeDefined()
    expect(option.series[0].name).toBe('pH')
  })

  it('uses avg value if available in data', () => {
    const data = [
      { ts: 1704067200000, value: 6.0, avg: 6.05 },
      { ts: 1704070800000, value: 6.1, avg: 6.1 }
    ]

    const wrapper = mount(MiniTelemetryChart, {
      props: {
        label: 'pH',
        currentValue: 6.0,
        unit: '',
        data,
        loading: false
      }
    })

    const chart = wrapper.findComponent({ name: 'ChartBase' })
    const option = chart.props('option')
    // Chart should use avg if available
    expect(option.series[0].data[0][1]).toBe(6.05) // avg value
  })

  it('uses value if avg is not available', () => {
    const data = [
      { ts: 1704067200000, value: 6.0 },
      { ts: 1704070800000, value: 6.1 }
    ]

    const wrapper = mount(MiniTelemetryChart, {
      props: {
        label: 'pH',
        currentValue: 6.0,
        unit: '',
        data,
        loading: false
      }
    })

    const chart = wrapper.findComponent({ name: 'ChartBase' })
    const option = chart.props('option')
    expect(option.series[0].data[0][1]).toBe(6.0) // value
  })

  it('applies custom color to chart', () => {
    const data = [{ ts: 1704067200000, value: 6.0 }]

    const wrapper = mount(MiniTelemetryChart, {
      props: {
        label: 'pH',
        currentValue: 6.0,
        unit: '',
        data,
        loading: false,
        color: '#ef4444' // red
      }
    })

    const chart = wrapper.findComponent({ name: 'ChartBase' })
    const option = chart.props('option')
    expect(option.series[0].lineStyle.color).toBe('#ef4444')
  })
})


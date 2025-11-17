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
    template: '<button :class="variant" @click="$emit(\'click\')"><slot /></button>' 
  },
}))

vi.mock('@/Components/ChartBase.vue', () => ({
  default: { 
    name: 'ChartBase', 
    props: ['option'],
    template: '<div class="chart-base"></div>' 
  },
}))

describe('ZoneTelemetryChart.vue', () => {
  const sampleData = [
    { ts: Date.now() - 60000, value: 5.8 },
    { ts: Date.now(), value: 5.9 },
  ]

  it('отображает заголовок и кнопки времени', () => {
    const wrapper = mount(ZoneTelemetryChart, {
      props: {
        title: 'pH',
        seriesName: 'pH',
        data: sampleData,
        timeRange: '24H',
      },
    })
    
    expect(wrapper.text()).toContain('pH')
    expect(wrapper.text()).toContain('1H')
    expect(wrapper.text()).toContain('24H')
    expect(wrapper.text()).toContain('7D')
    expect(wrapper.text()).toContain('30D')
    expect(wrapper.text()).toContain('ALL')
  })

  it('выделяет активную кнопку времени', () => {
    const wrapper = mount(ZoneTelemetryChart, {
      props: {
        title: 'pH',
        seriesName: 'pH',
        data: sampleData,
        timeRange: '7D',
      },
    })
    
    const buttons = wrapper.findAll('button')
    const activeButton = buttons.find(btn => btn.classes().includes('default') || !btn.classes().includes('secondary'))
    expect(activeButton?.text()).toBe('7D')
  })

  it('эмитит событие time-range-change при клике на кнопку', async () => {
    const wrapper = mount(ZoneTelemetryChart, {
      props: {
        title: 'pH',
        seriesName: 'pH',
        data: sampleData,
        timeRange: '24H',
      },
    })
    
    const buttons = wrapper.findAll('button')
    const button1H = buttons.find(btn => btn.text() === '1H')
    
    await button1H?.trigger('click')
    
    expect(wrapper.emitted('time-range-change')).toBeTruthy()
    expect(wrapper.emitted('time-range-change')?.[0]).toEqual(['1H'])
  })

  it('передает данные в ChartBase', () => {
    const wrapper = mount(ZoneTelemetryChart, {
      props: {
        title: 'EC',
        seriesName: 'EC',
        data: sampleData,
        timeRange: '24H',
      },
    })
    
    const chartBase = wrapper.findComponent({ name: 'ChartBase' })
    expect(chartBase.exists()).toBe(true)
    
    const option = chartBase.props('option')
    expect(option).toBeDefined()
    expect(option.series).toBeDefined()
    expect(Array.isArray(option.series)).toBe(true)
    expect(option.series.length).toBeGreaterThan(0)
    expect(option.series[0].name).toBe('EC')
    expect(option.series[0].data).toBeDefined()
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
    
    expect(wrapper.text()).toContain('pH')
    const chartBase = wrapper.findComponent({ name: 'ChartBase' })
    expect(chartBase.exists()).toBe(true)
  })
})


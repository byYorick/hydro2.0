import { mount } from '@vue/test-utils'
import { describe, it, expect, vi } from 'vitest'
import ZoneTelemetryChart from '../ZoneTelemetryChart.vue'

// Mock vue-echarts
vi.mock('vue-echarts', () => ({
  default: {
    name: 'VChart',
    template: '<div>Mock Chart</div>'
  }
}))

describe('ZoneTelemetryChart - DataZoom (P2-3)', () => {
  it('should enable DataZoom for large datasets (>100 points)', () => {
    const largeDataset = Array.from({ length: 150 }, (_, i) => ({
      ts: Date.now() + i * 1000,
      value: 6.5 + Math.random()
    }))

    const wrapper = mount(ZoneTelemetryChart, {
      props: {
        data: largeDataset,
        seriesName: 'pH',
        title: 'pH Chart'
      }
    })

    const option = wrapper.vm.option
    expect(option.dataZoom).toBeDefined()
    expect(Array.isArray(option.dataZoom)).toBe(true)
    expect(option.dataZoom.length).toBeGreaterThan(0)
  })

  it('should not enable DataZoom for small datasets (<=100 points)', () => {
    const smallDataset = Array.from({ length: 50 }, (_, i) => ({
      ts: Date.now() + i * 1000,
      value: 6.5 + Math.random()
    }))

    const wrapper = mount(ZoneTelemetryChart, {
      props: {
        data: smallDataset,
        seriesName: 'pH',
        title: 'pH Chart'
      }
    })

    const option = wrapper.vm.option
    expect(option.dataZoom).toBeUndefined()
  })

  it('should include both inside and slider DataZoom types', () => {
    const largeDataset = Array.from({ length: 150 }, (_, i) => ({
      ts: Date.now() + i * 1000,
      value: 6.5 + Math.random()
    }))

    const wrapper = mount(ZoneTelemetryChart, {
      props: {
        data: largeDataset,
        seriesName: 'pH',
        title: 'pH Chart'
      }
    })

    const option = wrapper.vm.option
    const dataZoom = option.dataZoom as any[]
    
    const insideZoom = dataZoom.find((dz: any) => dz.type === 'inside')
    const sliderZoom = dataZoom.find((dz: any) => dz.type === 'slider')

    expect(insideZoom).toBeDefined()
    expect(sliderZoom).toBeDefined()
  })

  it('should adjust grid bottom padding for DataZoom slider', () => {
    const largeDataset = Array.from({ length: 150 }, (_, i) => ({
      ts: Date.now() + i * 1000,
      value: 6.5 + Math.random()
    }))

    const wrapper = mount(ZoneTelemetryChart, {
      props: {
        data: largeDataset,
        seriesName: 'pH',
        title: 'pH Chart'
      }
    })

    const option = wrapper.vm.option
    expect(option.grid.bottom).toBe(80) // Увеличено для DataZoom
  })

  it('should set large and largeThreshold for large datasets', () => {
    const largeDataset = Array.from({ length: 150 }, (_, i) => ({
      ts: Date.now() + i * 1000,
      value: 6.5 + Math.random()
    }))

    const wrapper = mount(ZoneTelemetryChart, {
      props: {
        data: largeDataset,
        seriesName: 'pH',
        title: 'pH Chart'
      }
    })

    const option = wrapper.vm.option
    const series = option.series[0]
    
    expect(series.large).toBe(true)
    expect(series.largeThreshold).toBe(100)
  })

  it('should not set large flag for small datasets', () => {
    const smallDataset = Array.from({ length: 50 }, (_, i) => ({
      ts: Date.now() + i * 1000,
      value: 6.5 + Math.random()
    }))

    const wrapper = mount(ZoneTelemetryChart, {
      props: {
        data: smallDataset,
        seriesName: 'pH',
        title: 'pH Chart'
      }
    })

    const option = wrapper.vm.option
    const series = option.series[0]
    
    expect(series.large).toBe(false)
  })
})


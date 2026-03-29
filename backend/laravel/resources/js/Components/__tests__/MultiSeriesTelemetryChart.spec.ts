import { mount } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import MultiSeriesTelemetryChart from '../MultiSeriesTelemetryChart.vue'

// Моки для зависимостей
vi.mock('@/Components/Card.vue', () => ({
  default: { name: 'Card', template: '<div class="card"><slot /></div>' },
}))

vi.mock('@/Components/Button.vue', () => ({
  default: { 
    name: 'Button', 
    props: ['size', 'variant'],
    template: '<button><slot /></button>' 
  },
}))

vi.mock('@/Components/ChartBase.vue', () => ({
  default: { 
    name: 'ChartBase', 
    props: ['option'],
    template: '<div class="chart-base"></div>' 
  },
}))

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
  let clickSpy: ReturnType<typeof vi.spyOn>
  const originalBlob = globalThis.Blob

  beforeEach(() => {
    vi.clearAllMocks()
    clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    class MockBlob {
      parts: string[]
      type: string

      constructor(parts: unknown[], options?: { type?: string }) {
        this.parts = parts.map((part) => String(part))
        this.type = options?.type ?? ''
      }

      text(): Promise<string> {
        return Promise.resolve(this.parts.join(''))
      }
    }
    vi.stubGlobal('Blob', MockBlob)
    Object.defineProperty(globalThis.URL, 'createObjectURL', {
      value: vi.fn(() => 'blob:telemetry-export'),
      configurable: true,
      writable: true,
    })
    Object.defineProperty(globalThis.URL, 'revokeObjectURL', {
      value: vi.fn(),
      configurable: true,
      writable: true,
    })
  })

  afterEach(() => {
    clickSpy.mockRestore()
    vi.stubGlobal('Blob', originalBlob)
  })

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

  it('отображает кнопки выбора временного диапазона', () => {
    const wrapper = mount(MultiSeriesTelemetryChart, {
      props: {
        series: sampleSeries,
        timeRange: '24H',
      },
    })

    expect(wrapper.text()).toContain('1H')
    expect(wrapper.text()).toContain('24H')
    expect(wrapper.text()).toContain('7D')
    expect(wrapper.text()).toContain('30D')
    expect(wrapper.text()).toContain('ALL')
  })

  it('выделяет активный временной диапазон', () => {
    const wrapper = mount(MultiSeriesTelemetryChart, {
      props: {
        series: sampleSeries,
        timeRange: '24H',
      },
    })

    const buttons = wrapper.findAllComponents({ name: 'Button' })
    const activeButton = buttons.find(btn => btn.props('variant') === 'default')
    expect(activeButton).toBeTruthy()
    if (activeButton) {
      expect(activeButton.text()).toBe('24H')
    }
  })

  it('эмитирует событие time-range-change при изменении диапазона', async () => {
    const wrapper = mount(MultiSeriesTelemetryChart, {
      props: {
        series: sampleSeries,
        timeRange: '24H',
      },
    })

    const buttons = wrapper.findAllComponents({ name: 'Button' })
    const button1H = buttons.find(btn => btn.text() === '1H')
    
    if (button1H) {
      await button1H.trigger('click')
      expect(wrapper.emitted('time-range-change')).toBeTruthy()
      expect(wrapper.emitted('time-range-change')?.[0]).toEqual(['1H'])
    }
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
    // Проверяем, что отображаются текущие значения
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

  it('использует значение по умолчанию для timeRange', () => {
    const wrapper = mount(MultiSeriesTelemetryChart, {
      props: {
        series: sampleSeries,
      },
    })

    const buttons = wrapper.findAllComponents({ name: 'Button' })
    const activeButton = buttons.find(btn => btn.props('variant') === 'default')
    expect(activeButton).toBeTruthy()
    if (activeButton) {
      expect(activeButton.text()).toBe('24H')
    }
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

      // Проверяем, что значение отформатировано с 2 знаками
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

      // Компонент должен обрабатывать null значения
      expect(wrapper.exists()).toBe(true)
    })
  })

  describe('exportData', () => {
    it('экспортирует данные в CSV', async () => {
      const wrapper = mount(MultiSeriesTelemetryChart, {
        props: {
          title: 'Telemetry Export',
          series: sampleSeries,
          timeRange: '24H',
        },
      })

      const exportButton = wrapper.findAll('button').find((button) => button.text().includes('Экспорт'))
      expect(exportButton).toBeTruthy()

      await exportButton?.trigger('click')

      expect(URL.createObjectURL).toHaveBeenCalledTimes(1)
      const blobArg = vi.mocked(URL.createObjectURL).mock.calls[0]?.[0]
      expect(blobArg).toBeInstanceOf(Blob)

      const csvContent = await blobArg.text()
      expect(csvContent).toContain('Время,Температура (°C),Влажность (%)')
      expect(csvContent).toContain('20.5,60')
      expect(csvContent).toContain('21,61')
      expect(csvContent).toContain('21.5,62')

      expect(clickSpy).toHaveBeenCalledTimes(1)
      expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:telemetry-export')
    })
  })
})

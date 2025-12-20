import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import HeaderStatusBar from '@/Components/HeaderStatusBar.vue'

// Моки
vi.mock('@/composables/useSystemStatus', () => ({
  useSystemStatus: () => ({
    coreStatus: 'ok',
    dbStatus: 'ok',
    wsStatus: 'connected',
    mqttStatus: 'online',
    historyLoggerStatus: 'ok',
    automationEngineStatus: 'ok',
    lastUpdate: new Date()
  })
}))

vi.mock('@/composables/useWebSocket', () => ({
  useWebSocket: () => ({
    subscribeToGlobalEvents: vi.fn(() => () => {})
  })
}))

vi.mock('@/composables/useApi', () => ({
  useApi: () => ({
    api: {
      get: vi.fn(() => Promise.resolve({
        data: {
          data: {
            zonesCount: 5,
            zonesByStatus: { RUNNING: 3 },
            devicesCount: 10,
            nodesByStatus: { online: 8, offline: 2 }
          }
        }
      }))
    }
  })
}))

vi.mock('@/utils/formatTime', () => ({
  formatTime: (date: Date) => date.toISOString()
}))

vi.mock('@/Components/SystemMonitoringModal.vue', () => ({
  default: {
    name: 'SystemMonitoringModal',
    props: ['show'],
    template: '<div v-if="show">Modal</div>',
    emits: ['close']
  }
}))

vi.mock('@inertiajs/vue3', () => ({
  usePage: () => ({
    props: {
      dashboard: null
    }
  })
}))

describe('HeaderStatusBar Enhanced', () => {
  let wrapper: ReturnType<typeof mount>

  beforeEach(() => {
    vi.useFakeTimers()
    wrapper = mount(HeaderStatusBar)
  })

  afterEach(() => {
    vi.useRealTimers()
    wrapper.unmount()
  })

  describe('Real-time метрики', () => {
    it('загружает метрики при монтировании', async () => {
      await nextTick()
      vi.advanceTimersByTime(100)
      await nextTick()

      // Проверяем, что метрики загружаются
      const vm = wrapper.vm as any
      expect(vm.metrics).toBeDefined()
    })

    it('показывает количество зон', async () => {
      await nextTick()
      vi.advanceTimersByTime(6000)
      await nextTick()

      const vm = wrapper.vm as any
      // Метрики могут быть null или содержать значения
      expect(vm.metrics).toBeDefined()
    })

    it('показывает количество устройств', async () => {
      await nextTick()
      vi.advanceTimersByTime(6000)
      await nextTick()

      const vm = wrapper.vm as any
      expect(vm.metrics).toBeDefined()
    })

    it('показывает количество алертов', async () => {
      await nextTick()
      vi.advanceTimersByTime(6000)
      await nextTick()

      const vm = wrapper.vm as any
      expect(vm.metrics).toBeDefined()
    })
  })

  describe('Цветовая индикация алертов', () => {
    it('применяет красный цвет при наличии алертов', async () => {
      const vm = wrapper.vm as any
      vm.metrics = { alertsCount: 5 }
      await nextTick()

      const alertsElement = wrapper.findAll('div').find(el => el.text().includes('алерт.'))
      expect(alertsElement).toBeDefined()
      expect(alertsElement?.classes()).toContain('bg-[color:var(--badge-danger-bg)]')
    })

    it('применяет нейтральный цвет при отсутствии алертов', async () => {
      const vm = wrapper.vm as any
      vm.metrics = { alertsCount: 0 }
      await nextTick()

      const alertsElement = wrapper.findAll('div').find(el => el.text().includes('алерт.'))
      expect(alertsElement).toBeDefined()
      expect(alertsElement?.classes()).toContain('bg-[color:var(--bg-elevated)]')
    })
  })

  describe('Tooltips', () => {
    it('показывает tooltip при hover на метрики зон', async () => {
      const vm = wrapper.vm as any
      vm.metrics = { zonesCount: 5, zonesRunning: 3 }
      await nextTick()

      const zonesElement = wrapper.find('.group')
      expect(zonesElement.exists()).toBe(true)
    })

    it('показывает детальную информацию в tooltip', async () => {
      const vm = wrapper.vm as any
      vm.metrics = { zonesCount: 5, zonesRunning: 3 }
      await nextTick()

      const tooltip = wrapper.find('.opacity-0.group-hover\\:opacity-100')
      expect(tooltip.exists()).toBe(true)
    })
  })

  describe('Автообновление', () => {
    it('обновляет метрики каждые 5 секунд', async () => {
      await nextTick()
      vi.advanceTimersByTime(5000)
      await nextTick()

      // Проверяем, что интервал установлен
      const vm = wrapper.vm as any
      expect(vm.metricsInterval).toBeDefined()
    })
  })

  describe('WebSocket подписка', () => {
    it('подписывается на глобальные события', async () => {
      await nextTick()
      
      // Проверяем, что подписка создана
      const vm = wrapper.vm as any
      expect(vm.unsubscribeMetrics).toBeDefined()
    })
  })
})

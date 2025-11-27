import { mount } from '@vue/test-utils'
import { describe, it, expect, vi } from 'vitest'
import ZonesHeatmap from '../ZonesHeatmap.vue'

// Mock Inertia router
const mockRouter = {
  visit: vi.fn()
}

vi.mock('@inertiajs/vue3', () => ({
  router: mockRouter
}))

// Mock dependencies
vi.mock('@/Components/Card.vue', () => ({
  default: {
    name: 'Card',
    template: '<div class="card"><slot /></div>'
  }
}))

vi.mock('@/utils/i18n', () => ({
  translateStatus: (status: string) => {
    const translations: Record<string, string> = {
      'RUNNING': 'Запущено',
      'PAUSED': 'Приостановлено',
      'WARNING': 'Предупреждение',
      'ALARM': 'Тревога'
    }
    return translations[status] || status
  }
}))

describe('ZonesHeatmap', () => {
  it('renders heatmap with zone statuses', () => {
    const zonesByStatus = {
      RUNNING: 5,
      PAUSED: 2,
      WARNING: 1,
      ALARM: 0
    }

    const wrapper = mount(ZonesHeatmap, {
      props: {
        zonesByStatus
      }
    })

    expect(wrapper.text()).toContain('5')
    expect(wrapper.text()).toContain('2')
    expect(wrapper.text()).toContain('1')
    expect(wrapper.text()).toContain('0')
  })

  it('displays translated status labels', () => {
    const zonesByStatus = {
      RUNNING: 5,
      PAUSED: 2
    }

    const wrapper = mount(ZonesHeatmap, {
      props: {
        zonesByStatus
      }
    })

    expect(wrapper.text()).toContain('Запущено')
    expect(wrapper.text()).toContain('Приостановлено')
  })

  it('applies correct CSS classes for RUNNING status', () => {
    const zonesByStatus = {
      RUNNING: 5
    }

    const wrapper = mount(ZonesHeatmap, {
      props: {
        zonesByStatus
      }
    })

    const runningElement = wrapper.find('.bg-emerald-500\\/10')
    expect(runningElement.exists()).toBe(true)
  })

  it('applies correct CSS classes for PAUSED status', () => {
    const zonesByStatus = {
      PAUSED: 2
    }

    const wrapper = mount(ZonesHeatmap, {
      props: {
        zonesByStatus
      }
    })

    const pausedElement = wrapper.find('.bg-neutral-500\\/10')
    expect(pausedElement.exists()).toBe(true)
  })

  it('applies correct CSS classes for WARNING status', () => {
    const zonesByStatus = {
      WARNING: 1
    }

    const wrapper = mount(ZonesHeatmap, {
      props: {
        zonesByStatus
      }
    })

    const warningElement = wrapper.find('.bg-amber-500\\/10')
    expect(warningElement.exists()).toBe(true)
  })

  it('applies correct CSS classes for ALARM status', () => {
    const zonesByStatus = {
      ALARM: 3
    }

    const wrapper = mount(ZonesHeatmap, {
      props: {
        zonesByStatus
      }
    })

    const alarmElement = wrapper.find('.bg-red-500\\/10')
    expect(alarmElement.exists()).toBe(true)
  })

  it('emits filter event when status item is clicked', async () => {
    const zonesByStatus = {
      RUNNING: 5
    }

    const wrapper = mount(ZonesHeatmap, {
      props: {
        zonesByStatus
      }
    })

    const statusItem = wrapper.find('.cursor-pointer')
    await statusItem.trigger('click')

    // ZonesHeatmap использует router.visit вместо emit('filter')
    expect(mockRouter.visit).toHaveBeenCalledWith('/zones?status=RUNNING', expect.any(Object))
  })

  it('displays legend with all status types', () => {
    const zonesByStatus = {
      RUNNING: 5,
      PAUSED: 2,
      WARNING: 1,
      ALARM: 0
    }

    const wrapper = mount(ZonesHeatmap, {
      props: {
        zonesByStatus
      }
    })

    expect(wrapper.text()).toContain('Запущено')
    expect(wrapper.text()).toContain('Приостановлено')
    expect(wrapper.text()).toContain('Предупреждение')
    expect(wrapper.text()).toContain('Тревога')
  })

  it('handles empty zonesByStatus', () => {
    const wrapper = mount(ZonesHeatmap, {
      props: {
        zonesByStatus: {}
      }
    })

    // Should still render the component
    expect(wrapper.find('.card').exists()).toBe(true)
  })

  it('displays zero count correctly', () => {
    const zonesByStatus = {
      RUNNING: 0,
      PAUSED: 0
    }

    const wrapper = mount(ZonesHeatmap, {
      props: {
        zonesByStatus
      }
    })

    // Should show 0 or handle it gracefully
    const text = wrapper.text()
    expect(text).toContain('0')
  })

  it('handles unknown status gracefully', () => {
    const zonesByStatus = {
      UNKNOWN: 1
    } as any

    const wrapper = mount(ZonesHeatmap, {
      props: {
        zonesByStatus
      }
    })

    // Should not throw and should render
    expect(wrapper.find('.card').exists()).toBe(true)
  })
})


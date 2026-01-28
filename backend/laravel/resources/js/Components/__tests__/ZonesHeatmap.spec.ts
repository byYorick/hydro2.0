import { mount } from '@vue/test-utils'
import { describe, it, expect, vi } from 'vitest'
import ZonesHeatmap from '../ZonesHeatmap.vue'

// Mock Inertia router (hoisted to avoid initialization errors)
const mockRouter = vi.hoisted(() => ({
  visit: vi.fn(),
}))

vi.mock('@inertiajs/vue3', () => ({
  router: mockRouter,
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
  beforeEach(() => {
    vi.clearAllMocks()
    mockRouter.visit.mockReset()
  })
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

    const runningElement = wrapper.findAll('.cursor-pointer').find((entry) => entry.text().includes('Запущено'))
    expect(runningElement).toBeDefined()
    expect(runningElement?.classes()).toContain('bg-[color:var(--badge-success-bg)]')
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

    const pausedElement = wrapper.findAll('.cursor-pointer').find((entry) => entry.text().includes('Приостановлено'))
    expect(pausedElement).toBeDefined()
    expect(pausedElement?.classes()).toContain('bg-[color:var(--bg-elevated)]')
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

    const warningElement = wrapper.findAll('.cursor-pointer').find((entry) => entry.text().includes('Предупреждение'))
    expect(warningElement).toBeDefined()
    expect(warningElement?.classes()).toContain('bg-[color:var(--badge-warning-bg)]')
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

    const alarmElement = wrapper.findAll('.cursor-pointer').find((entry) => entry.text().includes('Тревога'))
    expect(alarmElement).toBeDefined()
    expect(alarmElement?.classes()).toContain('bg-[color:var(--badge-danger-bg)]')
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

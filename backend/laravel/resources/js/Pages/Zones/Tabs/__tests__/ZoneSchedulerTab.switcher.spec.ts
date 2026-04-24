import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

const pageState = vi.hoisted(() => ({ features: { scheduler_cockpit_ui: false } }))

vi.mock('@inertiajs/vue3', () => ({
  usePage: () => ({ props: pageState }),
}))

vi.mock('@/Pages/Zones/Tabs/CockpitSchedulerTab.vue', () => ({
  default: {
    name: 'CockpitSchedulerTab',
    template: '<div data-testid="cockpit-stub">cockpit</div>',
  },
}))

vi.mock('@/Pages/Zones/Tabs/LegacySchedulerTab.vue', () => ({
  default: {
    name: 'LegacySchedulerTab',
    template: '<div data-testid="legacy-stub">legacy</div>',
  },
}))

import ZoneSchedulerTab from '../ZoneSchedulerTab.vue'

describe('ZoneSchedulerTab.vue (switcher)', () => {
  it('монтирует legacy-реализацию, если флаг выключен', () => {
    pageState.features.scheduler_cockpit_ui = false
    const wrapper = mount(ZoneSchedulerTab, { props: { zoneId: 42, targets: {} } as any })
    expect(wrapper.find('[data-testid="legacy-stub"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="cockpit-stub"]').exists()).toBe(false)
  })

  it('монтирует cockpit, если флаг включён', () => {
    pageState.features.scheduler_cockpit_ui = true
    const wrapper = mount(ZoneSchedulerTab, { props: { zoneId: 42, targets: {} } as any })
    expect(wrapper.find('[data-testid="cockpit-stub"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="legacy-stub"]').exists()).toBe(false)
  })
})

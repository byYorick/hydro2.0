import { mount } from '@vue/test-utils'
import { describe, it, expect, vi } from 'vitest'

vi.mock('@/Layouts/AppLayout.vue', () => ({
  default: { name: 'AppLayout', template: '<div><slot /></div>' },
}))

// Mock RecycleScroller для тестов
vi.mock('vue-virtual-scroller', () => ({
  RecycleScroller: {
    name: 'RecycleScroller',
    template: `
      <div>
        <template v-for="(item, index) in items" :key="index">
          <slot :item="item" :index="index" />
        </template>
      </div>
    `,
    props: {
      items: { type: Array, required: true },
      'item-size': { type: Number },
      'key-field': { type: String }
    }
  }
}))

const sampleDevices = [
  { id: 'dev-1', uid: 'dev-1', zone: { name: 'Z1' }, type: 'sensor', status: 'OK', fw_version: '1.0' },
  { id: 'dev-2', uid: 'dev-2', zone: { name: 'Z2' }, type: 'sensor', status: 'OK', fw_version: '1.1' },
  { id: 'dev-3', uid: 'dev-3', zone: { name: 'Z1' }, type: 'actuator', status: 'OK', fw_version: '2.0' },
]

vi.mock('@/stores/devices', () => ({
  useDevicesStore: () => ({
    items: sampleDevices,
    initFromProps: () => {},
  }),
}))

vi.mock('@inertiajs/vue3', () => ({
  Link: { name: 'Link', props: ['href'], template: '<a><slot /></a>' },
  usePage: () => ({ props: { devices: sampleDevices } }),
}))

import DevicesIndex from '../Index.vue'

describe('Devices/Index.vue', () => {
  it('фильтрует по типу', async () => {
    const wrapper = mount(DevicesIndex)
    await wrapper.vm.$nextTick()
    expect(wrapper.findAll('tbody tr').length).toBeGreaterThanOrEqual(3)
    await wrapper.find('select').setValue('actuator')
    await wrapper.vm.$nextTick()
    const rows = wrapper.findAll('tbody tr')
    expect(rows.length).toBeGreaterThanOrEqual(1)
    expect(wrapper.text()).toContain('dev-3')
  })

  it('фильтр по query', async () => {
    const wrapper = mount(DevicesIndex)
    await wrapper.vm.$nextTick()
    const input = wrapper.find('input[placeholder*="ID"]')
    await input.setValue('dev-3')
    await wrapper.vm.$nextTick()
    const rows = wrapper.findAll('tbody tr')
    expect(rows.length).toBeGreaterThanOrEqual(1)
    expect(wrapper.text()).toContain('dev-3')
  })

  it('показывает пустое состояние', async () => {
    const wrapper = mount(DevicesIndex)
    await wrapper.find('input').setValue('no-match')
    expect(wrapper.text()).toContain('Нет устройств по текущим фильтрам')
  })
})



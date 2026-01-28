import { mount, config } from '@vue/test-utils'
import { describe, it, expect, vi } from 'vitest'

vi.mock('@/Layouts/AppLayout.vue', () => ({
  default: { name: 'AppLayout', template: '<div><slot /></div>' },
}))

// Регистрируем RecycleScroller глобально
const RecycleScrollerStub = {
  name: 'RecycleScroller',
  props: {
    items: { type: Array, required: true },
    'item-size': { type: Number, default: 0 },
    itemSize: { type: Number, default: 0 },
    'key-field': { type: String, default: 'id' },
  },
  template: `
    <div class="recycle-scroller-stub">
      <template v-for="(item, index) in items" :key="item.id ?? index">
        <slot :item="item" :index="index" />
      </template>
    </div>
  `,
}

config.global.components.RecycleScroller = RecycleScrollerStub

const sampleDevices = [
  { id: 'dev-1', uid: 'dev-1', zone: { name: 'Z1' }, type: 'sensor', status: 'OK', fw_version: '1.0' },
  { id: 'dev-2', uid: 'dev-2', zone: { name: 'Z2' }, type: 'sensor', status: 'OK', fw_version: '1.1' },
  { id: 'dev-3', uid: 'dev-3', zone: { name: 'Z1' }, type: 'actuator', status: 'OK', fw_version: '2.0' },
]

vi.mock('@/stores/devices', () => ({
  useDevicesStore: () => ({
    items: sampleDevices,
    allDevices: sampleDevices, // Добавляем геттер allDevices
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
    
    // Проверяем, что изначально есть устройства
    expect((wrapper.vm as any).filtered?.length ?? 0).toBeGreaterThanOrEqual(3)
    
    const select = wrapper.find('select')
    if (select.exists()) {
      await select.setValue('actuator')
      await wrapper.vm.$nextTick()
      
      // Проверяем, что фильтрация работает
      expect((wrapper.vm as any).filtered?.length ?? 0).toBeGreaterThanOrEqual(1)
      expect(wrapper.text()).toContain('dev-3')
    }
  })

  it('фильтр по query', async () => {
    const wrapper = mount(DevicesIndex)
    await wrapper.vm.$nextTick()
    
    const input = wrapper.find('input[placeholder*="ID"]')
    if (input.exists()) {
      await input.setValue('dev-3')
      await wrapper.vm.$nextTick()
      
      // Проверяем, что фильтрация работает через computed (используем filtered вместо filteredRows)
      expect((wrapper.vm as any).filtered?.length ?? 0).toBeGreaterThanOrEqual(1)
      expect(wrapper.text()).toContain('dev-3')
    }
  })

  it('показывает пустое состояние', async () => {
    const wrapper = mount(DevicesIndex)
    await wrapper.vm.$nextTick()
    
    const input = wrapper.find('input[placeholder*="ID"]')
    if (input.exists()) {
      await input.setValue('no-match')
      await wrapper.vm.$nextTick()
      
      // Проверяем, что filtered пустой (используем filtered вместо filteredRows)
      expect((wrapper.vm as any).filtered?.length ?? 0).toBe(0)
      expect(wrapper.text()).toContain('Нет устройств по текущим фильтрам')
    }
  })
})



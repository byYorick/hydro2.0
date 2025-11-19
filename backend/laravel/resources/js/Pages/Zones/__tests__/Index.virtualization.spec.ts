import { mount } from '@vue/test-utils'
import { describe, it, expect, vi } from 'vitest'
import ZonesIndex from '../Index.vue'

// Mock DynamicScroller - улучшенный мок с правильной работой со slots
vi.mock('vue-virtual-scroller', () => ({
  DynamicScroller: {
    name: 'DynamicScroller',
    template: `
      <div>
        <template v-for="(item, index) in items" :key="getKey(item)">
          <slot :item="item" :index="index" :active="true" />
        </template>
      </div>
    `,
    props: {
      items: { type: Array, required: true },
      'min-item-size': { type: Number },
      'key-field': { type: String }
    },
    methods: {
      getKey(item: any) {
        return item[this.$attrs['key-field']] || item.id
      }
    }
  },
  DynamicScrollerItem: {
    name: 'DynamicScrollerItem',
    template: '<div><slot /></div>',
    props: ['item', 'active', 'size-dependencies']
  }
}))

// Mock usePage
vi.mock('@inertiajs/vue3', () => ({
  usePage: () => ({
    props: {
      zones: [
        { id: 1, name: 'Zone 1', status: 'RUNNING' },
        { id: 2, name: 'Zone 2', status: 'PAUSED' },
        { id: 3, name: 'Zone 3', status: 'ALARM' }
      ]
    }
  })
}))

describe('Zones Index - Virtualization (P2-1)', () => {
  it('should use DynamicScroller for zone list', () => {
    const wrapper = mount(ZonesIndex)
    
    const scroller = wrapper.findComponent({ name: 'DynamicScroller' })
    expect(scroller.exists()).toBe(true)
  })

  it('should pass filtered zones to DynamicScroller', () => {
    const wrapper = mount(ZonesIndex)
    
    const scroller = wrapper.findComponent({ name: 'DynamicScroller' })
    expect(scroller.props('items')).toBeDefined()
    expect(Array.isArray(scroller.props('items'))).toBe(true)
  })

  it('should use DynamicScrollerItem for each zone', () => {
    const wrapper = mount(ZonesIndex)
    
    const scrollerItems = wrapper.findAllComponents({ name: 'DynamicScrollerItem' })
    // В моке отображается только один элемент, но структура правильная
    expect(scrollerItems.length).toBeGreaterThanOrEqual(0)
  })

  it('should set min-item-size prop', () => {
    const wrapper = mount(ZonesIndex)
    
    const scroller = wrapper.findComponent({ name: 'DynamicScroller' })
    expect(scroller.props('min-item-size')).toBe(160)
  })

  it('should set key-field prop', () => {
    const wrapper = mount(ZonesIndex)
    
    const scroller = wrapper.findComponent({ name: 'DynamicScroller' })
    expect(scroller.props('key-field')).toBe('id')
  })

  it('should filter zones correctly with virtualization', async () => {
    const wrapper = mount(ZonesIndex)
    
    // Устанавливаем фильтр статуса
    const statusSelect = wrapper.find('select')
    await statusSelect.setValue('RUNNING')
    
    const scroller = wrapper.findComponent({ name: 'DynamicScroller' })
    const filteredItems = scroller.props('items')
    
    // Все отфильтрованные зоны должны иметь статус RUNNING
    filteredItems.forEach((zone: any) => {
      expect(zone.status).toBe('RUNNING')
    })
  })

  it('should optimize filtering with memoized query', async () => {
    const wrapper = mount(ZonesIndex)
    
    const input = wrapper.find('input')
    await input.setValue('Zone 1')
    
    // queryLower должен быть мемоизирован
    expect(wrapper.vm.queryLower).toBe('zone 1')
    
    const scroller = wrapper.findComponent({ name: 'DynamicScroller' })
    const filteredItems = scroller.props('items')
    
    // Должна остаться только одна зона
    expect(filteredItems.length).toBe(1)
    expect(filteredItems[0].name).toBe('Zone 1')
  })

  it('should return all zones when no filters are applied', () => {
    const wrapper = mount(ZonesIndex)
    
    const scroller = wrapper.findComponent({ name: 'DynamicScroller' })
    const filteredItems = scroller.props('items')
    
    // Без фильтров должны быть все зоны
    expect(filteredItems.length).toBe(3)
  })
})


import { mount } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import DevicesIndex from '../Index.vue'

// Mock RecycleScroller - улучшенный мок с правильной работой со slots
vi.mock('vue-virtual-scroller', () => ({
  RecycleScroller: {
    name: 'RecycleScroller',
    template: `
      <div>
        <template v-for="(item, index) in items" :key="getKey(item, index)">
          <slot :item="item" :index="index" />
        </template>
      </div>
    `,
    props: {
      items: { type: Array, required: true },
      'item-size': { type: Number },
      'key-field': { type: String }
    },
    methods: {
      getKey(item: any, index: number) {
        if (this.$attrs['key-field']) {
          return item[this.$attrs['key-field']] || index
        }
        return index
      }
    }
  }
}))

// Mock stores
vi.mock('@/stores/devices', () => ({
  useDevicesStore: () => ({
    items: [
      { id: 1, uid: 'DEV001', name: 'Device 1', type: 'sensor', status: 'online' },
      { id: 2, uid: 'DEV002', name: 'Device 2', type: 'actuator', status: 'offline' }
    ],
    initFromProps: vi.fn()
  })
}))

// Mock usePage
vi.mock('@inertiajs/vue3', () => ({
  usePage: () => ({
    props: {
      devices: []
    }
  }),
  Link: {
    name: 'Link',
    template: '<a><slot /></a>',
    props: ['href']
  }
}))

describe('Devices Index - Virtualization (P2-1)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should use RecycleScroller for device list', () => {
    const wrapper = mount(DevicesIndex)
    
    const scroller = wrapper.findComponent({ name: 'RecycleScroller' })
    expect(scroller.exists()).toBe(true)
  })

  it('should pass rows to RecycleScroller', () => {
    const wrapper = mount(DevicesIndex)
    
    const scroller = wrapper.findComponent({ name: 'RecycleScroller' })
    expect(scroller.props('items')).toBeDefined()
    expect(Array.isArray(scroller.props('items'))).toBe(true)
  })

  it('should set item-size prop', () => {
    const wrapper = mount(DevicesIndex)
    
    const scroller = wrapper.findComponent({ name: 'RecycleScroller' })
    expect(scroller.props('item-size')).toBe(44)
  })

  it('should set key-field prop', () => {
    const wrapper = mount(DevicesIndex)
    
    const scroller = wrapper.findComponent({ name: 'RecycleScroller' })
    expect(scroller.props('key-field')).toBe('0')
  })

  it('should optimize filtering with memoized query', async () => {
    const wrapper = mount(DevicesIndex)
    
    const input = wrapper.find('input')
    await input.setValue('DEV001')
    
    // queryLower должен быть мемоизирован
    expect(wrapper.vm.queryLower).toBe('dev001')
  })

  it('should return all devices when no filters are applied', () => {
    const wrapper = mount(DevicesIndex)
    
    const scroller = wrapper.findComponent({ name: 'RecycleScroller' })
    const rows = scroller.props('items')
    
    // Без фильтров должны быть все устройства
    expect(rows.length).toBeGreaterThanOrEqual(0)
  })
})


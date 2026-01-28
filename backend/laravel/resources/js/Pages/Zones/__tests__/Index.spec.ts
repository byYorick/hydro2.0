import { mount } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach, beforeAll } from 'vitest'

vi.mock('@/Layouts/AppLayout.vue', () => ({
  default: { name: 'AppLayout', template: '<div><slot /></div>' },
}))
vi.mock('@/Pages/Zones/ZoneCard.vue', () => ({
  default: { name: 'ZoneCard', props: ['zone'], template: '<div class="zone-card">{{ zone.name }}</div>' },
}))

// Mock DynamicScroller для тестов
vi.mock('vue-virtual-scroller', () => ({
  DynamicScroller: {
    name: 'DynamicScroller',
    template: `
      <div>
        <template v-for="(item, index) in items" :key="item.id || index">
          <slot :item="item" :index="index" :active="true" />
        </template>
      </div>
    `,
    props: {
      items: { type: Array, required: true },
      'min-item-size': { type: Number },
      'key-field': { type: String }
    }
  },
  DynamicScrollerItem: {
    name: 'DynamicScrollerItem',
    template: '<div><slot /></div>',
    props: ['item', 'active', 'size-dependencies']
  },
  RecycleScroller: {
    name: 'RecycleScroller',
    props: {
      items: { type: Array, required: true },
      'key-field': { type: String, default: 'id' }
    },
    template: `
      <div class="recycle-scroller">
        <template v-for="(item, index) in items" :key="item[$attrs['key-field']] || item.id || index">
          <slot :item="item" :index="index" />
        </template>
      </div>
    `
  }
}))

const sampleZones = [
  { id: 1, name: 'Alpha', status: 'RUNNING' },
  { id: 2, name: 'Beta', status: 'PAUSED' },
  { id: 3, name: 'Gamma', status: 'WARNING' },
  { id: 4, name: 'Delta', status: 'RUNNING' },
]

const initFromPropsMock = vi.fn()
const subscribeWithCleanupMock = vi.fn(() => vi.fn())
const batchUpdatesMock = {
  add: vi.fn(),
  flush: vi.fn(),
  getBatchSize: vi.fn(() => 0),
}
const favoritesMock = {
  isZoneFavorite: vi.fn().mockReturnValue(false),
  toggleZoneFavorite: vi.fn(),
}

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

vi.mock('@/stores/zones', () => ({
  useZonesStore: () => ({
    items: sampleZones,
    allZones: sampleZones,
    cacheVersion: 0,
    initFromProps: initFromPropsMock,
    upsert: vi.fn(),
    remove: vi.fn(),
    invalidateCache: vi.fn(),
  }),
}))

vi.mock('@inertiajs/vue3', () => ({
  usePage: () => ({ props: { zones: sampleZones } }),
  router: {
    reload: vi.fn(),
  },
  Link: {
    name: 'Link',
    props: ['href'],
    template: '<a :href="href"><slot /></a>',
  },
}))

vi.mock('@/composables/useOptimizedUpdates', () => ({
  useBatchUpdates: () => batchUpdatesMock,
}))

vi.mock('@/composables/useStoreEvents', () => ({
  useStoreEvents: () => ({
    subscribeWithCleanup: subscribeWithCleanupMock,
  }),
  storeEvents: { emit: vi.fn(), subscribe: vi.fn() },
  zoneEvents: { emit: vi.fn(), subscribe: vi.fn() },
  deviceEvents: { emit: vi.fn(), subscribe: vi.fn() },
  recipeEvents: { emit: vi.fn(), subscribe: vi.fn() },
}))

vi.mock('@/composables/useFavorites', () => ({
  useFavorites: () => favoritesMock,
}))

let ZonesIndex: any
beforeAll(async () => {
  ZonesIndex = (await import('../Index.vue')).default
})

const mountZones = () =>
  mount(ZonesIndex, {
    global: {
      components: {
        RecycleScroller: RecycleScrollerStub,
      },
    },
  })

describe('Zones/Index.vue', () => {
  beforeEach(() => {
    initFromPropsMock.mockClear()
    if (typeof window !== 'undefined') {
      window.history.replaceState({}, '', '/')
    }
  })

  it('фильтрует по статусу', async () => {
    const wrapper = mountZones()
    await wrapper.vm.$nextTick()
    expect(wrapper.vm.filteredZones.length).toBe(sampleZones.length)
    // set status = RUNNING
    const select = wrapper.find('select')
    await select.setValue('RUNNING')
    await wrapper.vm.$nextTick()
    expect(wrapper.vm.filteredZones.map((z) => z.name)).toEqual(['Alpha', 'Delta'])
  })

  it('фильтрует по строке поиска', async () => {
    const wrapper = mountZones()
    const input = wrapper.find('input')
    await input.setValue('ga')
    await wrapper.vm.$nextTick()
    await wrapper.vm.$nextTick()
    expect(wrapper.vm.filteredZones.map((z) => z.name)).toEqual(['Gamma'])
  })

  it('показывает пустое состояние при отсутствии результатов', async () => {
    const wrapper = mountZones()
    await wrapper.find('input').setValue('no-match-here')
    expect(wrapper.text()).toContain('Нет зон по текущим фильтрам')
  })
})

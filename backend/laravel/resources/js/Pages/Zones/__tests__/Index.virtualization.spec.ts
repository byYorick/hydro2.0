import { mount, config } from '@vue/test-utils'
import { ref } from 'vue'
import { describe, it, expect, vi, beforeAll } from 'vitest'

vi.mock('@/Layouts/AppLayout.vue', () => ({
  default: { name: 'AppLayout', template: '<div><slot /></div>' },
}))
vi.mock('@/Components/Button.vue', () => ({
  default: { name: 'Button', props: ['variant', 'size'], template: '<button><slot /></button>' },
}))
vi.mock('@/Components/Badge.vue', () => ({
  default: { name: 'Badge', props: ['variant'], template: '<span><slot /></span>' },
}))
vi.mock('@/Components/ZoneComparisonModal.vue', () => ({
  default: { name: 'ZoneComparisonModal', props: ['open', 'zones'], template: '<div v-if="open"><slot /></div>' },
}))
vi.mock('@/Components/DataTableV2.vue', () => ({
  default: {
    name: 'DataTableV2',
    props: ['columns', 'rows', 'emptyTitle', 'emptyDescription', 'containerClass'],
    template: '<div class="data-table-v2-stub"><slot /></div>',
  },
}))
vi.mock('@/Components/Pagination.vue', () => ({
  default: {
    name: 'Pagination',
    props: ['currentPage', 'perPage', 'total'],
    template: '<div class="pagination-stub"></div>',
  },
}))
vi.mock('@/composables/useUrlState', () => ({
  useUrlState: ({ defaultValue }: { defaultValue: string | number | boolean }) => ref(defaultValue),
}))

const sampleZones = [
  { id: 1, name: 'Zone 1', status: 'RUNNING' },
  { id: 2, name: 'Zone 2', status: 'PAUSED' },
  { id: 3, name: 'Zone 3', status: 'ALARM' },
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
    'min-item-size': { type: Number, default: 0 },
    minItemSize: { type: Number, default: 0 },
  },
  template: `
    <div class="recycle-scroller-stub">
      <template v-for="(item, index) in items" :key="item.id ?? index">
        <slot :item="item" :index="index" />
      </template>
    </div>
  `,
}

vi.mock('vue-virtual-scroller', () => ({
  RecycleScroller: RecycleScrollerStub,
  DynamicScroller: RecycleScrollerStub,
  DynamicScrollerItem: {
    name: 'DynamicScrollerItem',
    props: ['item'],
    template: '<div><slot :item="item" /></div>',
  },
}))

vi.mock('@inertiajs/vue3', () => ({
  usePage: () => ({
    props: {
      zones: sampleZones
    }
  }),
  router: {
    reload: vi.fn(),
  },
  Link: {
    name: 'Link',
    props: ['href'],
    template: '<a :href="href"><slot /></a>',
  },
}))

vi.mock('@/stores/zones', () => ({
  useZonesStore: () => ({
    allZones: sampleZones,
    cacheVersion: 0,
    initFromProps: initFromPropsMock,
    upsert: vi.fn(),
    remove: vi.fn(),
    invalidateCache: vi.fn(),
  }),
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

// Регистрируем глобально для всех тестов
config.global.components.RecycleScroller = RecycleScrollerStub
config.global.components.DynamicScroller = RecycleScrollerStub
config.global.components.DynamicScrollerItem = {
  name: 'DynamicScrollerItem',
  props: ['item'],
  template: '<div><slot :item="item" /></div>',
}

let ZonesIndex: any
beforeAll(async () => {
  ZonesIndex = (await import('../Index.vue')).default
})

const mountZones = () => mount(ZonesIndex)

describe('Zones Index - Table Contract', () => {
  it('should render DataTableV2 for table body', () => {
    const wrapper = mountZones()
    
    const table = wrapper.findComponent({ name: 'DataTableV2' })
    expect(table.exists()).toBe(true)
  })

  it('should pass paginated rows to DataTableV2', () => {
    const wrapper = mountZones()
    
    const table = wrapper.findComponent({ name: 'DataTableV2' })
    expect(table.props('rows')).toEqual(sampleZones)
  })

  it('should expose canonical columns configuration', () => {
    const wrapper = mountZones()
    
    const table = wrapper.findComponent({ name: 'DataTableV2' })
    const columns = table.props('columns')

    expect(columns).toBeDefined()
    expect(Array.isArray(columns)).toBe(true)
    expect(columns.map((column: { key: string }) => column.key)).toEqual([
      'name',
      'status',
      'greenhouse',
      'ph',
      'ec',
      'temperature',
      'actions',
    ])
  })

  it('should keep default pagination state', () => {
    const wrapper = mountZones()
    
    const pagination = wrapper.findComponent({ name: 'Pagination' })
    expect(pagination.exists()).toBe(true)
    expect(pagination.props('currentPage')).toBe(1)
    expect(pagination.props('perPage')).toBe(25)
    expect(pagination.props('total')).toBe(3)
  })

  it('should filter zones correctly with virtualization', async () => {
    const wrapper = mountZones()
    
    // Устанавливаем фильтр статуса
    const statusSelect = wrapper.find('select')
    await statusSelect.setValue('RUNNING')
    await wrapper.vm.$nextTick()

    expect(wrapper.vm.filteredZones.every((zone: any) => zone.status === 'RUNNING')).toBe(true)
  })

  it('should optimize filtering with memoized query', async () => {
    const wrapper = mountZones()
    
    const input = wrapper.find('input')
    await input.setValue('Zone 1')
    await wrapper.vm.$nextTick()
    
    // queryLower должен быть мемоизирован
    expect(wrapper.vm.queryLower).toBe('zone 1')
    
    // Должна остаться только одна зона
    expect(wrapper.vm.filteredZones.length).toBe(1)
    expect(wrapper.vm.filteredZones[0].name).toBe('Zone 1')
  })

  it('should return all zones when no filters are applied', () => {
    const wrapper = mountZones()
    
    expect(wrapper.vm.filteredZones).toHaveLength(3)
    expect(wrapper.vm.paginatedZones).toHaveLength(3)
  })
})

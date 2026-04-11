import { nextTick, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { useCommandPaletteSearch } from '../useCommandPaletteSearch'
import { api } from '@/services/api'

// useCommandPaletteSearch теперь импортирует api.zones/nodes/recipes.list
// напрямую — мокаем services/api, а не старый useApi.
vi.mock('@/services/api', () => ({
  api: {
    zones: { list: vi.fn().mockResolvedValue([]) },
    nodes: { list: vi.fn().mockResolvedValue([]) },
    recipes: { list: vi.fn().mockResolvedValue([]) },
  },
}))

function createDeps() {
  const handlers = {
    navigate: vi.fn(),
    zoneAction: vi.fn(),
    zoneCycle: vi.fn(),
    openGrowCycleWizard: vi.fn(),
  }

  return {
    handlers,
    role: ref('admin'),
    history: ref([]),
  }
}

describe('useCommandPaletteSearch', () => {
  it('highlightMatch корректно сегментирует совпадения', () => {
    const deps = createDeps()
    const state = useCommandPaletteSearch(deps as never)

    const segments = state.highlightMatch('Test Zone', 'zone')
    const matched = segments.find((segment) => segment.match)

    expect(matched?.text.toLowerCase()).toBe('zone')
  })

  it('выполняет debounce-поиск и заполняет searchResults', async () => {
    vi.useFakeTimers()
    vi.mocked(api.zones.list).mockResolvedValue([{ id: 1, name: 'Zone A' }] as never)
    vi.mocked(api.nodes.list).mockResolvedValue([{ id: 11, name: 'Node A' }] as never)
    vi.mocked(api.recipes.list).mockResolvedValue([{ id: 21, name: 'Recipe A' }] as never)

    const deps = createDeps()
    const state = useCommandPaletteSearch(deps as never)
    state.q.value = 'zo'
    await nextTick()

    vi.advanceTimersByTime(350)
    await Promise.resolve()
    await Promise.resolve()

    expect(api.zones.list).toHaveBeenCalledWith({ search: 'zo' })
    expect(api.nodes.list).toHaveBeenCalledWith({ search: 'zo' })
    expect(api.recipes.list).toHaveBeenCalledWith({ search: 'zo' })
    expect(state.searchResults.value.zones).toHaveLength(1)
    expect(state.searchResults.value.nodes).toHaveLength(1)
    expect(state.searchResults.value.recipes).toHaveLength(1)

    vi.useRealTimers()
  })

  it('строит groupedResults и учитывает навигационный минимум', () => {
    const deps = createDeps()
    const state = useCommandPaletteSearch(deps as never)
    state.q.value = ''

    expect(state.commandItems.value.length).toBeGreaterThan(0)
    expect(state.groupedResults.value.length).toBeGreaterThan(0)
    expect(state.totalItemsCount.value).toBeGreaterThan(0)
  })
})

import { nextTick, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { useCommandPaletteSearch } from '../useCommandPaletteSearch'

function createDeps() {
  const api = {
    get: vi.fn().mockResolvedValue({ data: { data: [] } }),
  }

  const handlers = {
    navigate: vi.fn(),
    zoneAction: vi.fn(),
    zoneCycle: vi.fn(),
    openGrowCycleWizard: vi.fn(),
  }

  return {
    api,
    handlers,
    role: ref('admin'),
    history: ref([]),
  }
}

describe('useCommandPaletteSearch', () => {
  it('highlightMatch корректно сегментирует совпадения', () => {
    const deps = createDeps()
    const state = useCommandPaletteSearch(deps)

    const segments = state.highlightMatch('Test Zone', 'zone')
    const matched = segments.find((segment) => segment.match)

    expect(matched?.text.toLowerCase()).toBe('zone')
  })

  it('выполняет debounce-поиск и заполняет searchResults', async () => {
    vi.useFakeTimers()
    const deps = createDeps()
    deps.api.get
      .mockResolvedValueOnce({ data: { data: [{ id: 1, name: 'Zone A' }] } })
      .mockResolvedValueOnce({ data: { data: [{ id: 11, name: 'Node A' }] } })
      .mockResolvedValueOnce({ data: { data: [{ id: 21, name: 'Recipe A' }] } })

    const state = useCommandPaletteSearch(deps)
    state.q.value = 'zo'
    await nextTick()

    vi.advanceTimersByTime(350)
    await Promise.resolve()
    await Promise.resolve()

    expect(deps.api.get).toHaveBeenCalledTimes(3)
    expect(state.searchResults.value.zones).toHaveLength(1)
    expect(state.searchResults.value.nodes).toHaveLength(1)
    expect(state.searchResults.value.recipes).toHaveLength(1)

    vi.useRealTimers()
  })

  it('строит groupedResults и учитывает навигационный минимум', () => {
    const deps = createDeps()
    const state = useCommandPaletteSearch(deps)
    state.q.value = ''

    expect(state.commandItems.value.length).toBeGreaterThan(0)
    expect(state.groupedResults.value.length).toBeGreaterThan(0)
    expect(state.totalItemsCount.value).toBeGreaterThan(0)
  })
})

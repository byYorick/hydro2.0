import { computed, getCurrentInstance, onUnmounted, ref, watch, type Ref } from 'vue'
import {
  buildCommandItems,
  groupCommandItems,
  type CommandHandlers,
  type CommandHistoryItem,
  type CommandItem,
  type CommandSearchResults,
} from '@/commands/registry'
import type { UserRole } from '@/types/User'
import { logger } from '@/utils/logger'

export interface TextSegment {
  text: string
  match: boolean
}

interface ApiLike {
  get: (url: string, config?: { params?: Record<string, unknown> }) => Promise<{ data?: unknown }>
}

interface UseCommandPaletteSearchOptions {
  api: ApiLike
  role: Ref<UserRole | undefined>
  history: Ref<CommandHistoryItem[]>
  handlers: CommandHandlers
}

function extractResponseArray(data: unknown): unknown[] {
  if (Array.isArray(data)) {
    return data
  }
  if (data && typeof data === 'object') {
    const record = data as Record<string, unknown>
    if (Array.isArray(record.data)) {
      return record.data
    }
  }
  return []
}

export function useCommandPaletteSearch({
  api,
  role,
  history,
  handlers,
}: UseCommandPaletteSearchOptions) {
  const allowedRoles: UserRole[] = ['admin', 'agronomist', 'operator', 'engineer', 'viewer']

  const q = ref<string>('')
  const selectedIndex = ref<number>(0)
  const loading = ref<boolean>(false)
  const searchResults = ref<CommandSearchResults>({
    zones: [],
    nodes: [],
    recipes: [],
  })

  async function searchAPI(query: string): Promise<void> {
    if (!query || query.length < 2) {
      searchResults.value = { zones: [], nodes: [], recipes: [] }
      return
    }

    loading.value = true
    try {
      const [zonesRes, nodesRes, recipesRes] = await Promise.allSettled([
        api.get('/api/zones', { params: { search: query } }),
        api.get('/api/nodes', { params: { search: query } }),
        api.get('/api/recipes', { params: { search: query } }),
      ])

      searchResults.value = {
        zones: zonesRes.status === 'fulfilled' ? extractResponseArray(zonesRes.value.data) : [],
        nodes: nodesRes.status === 'fulfilled' ? extractResponseArray(nodesRes.value.data) : [],
        recipes: recipesRes.status === 'fulfilled' ? extractResponseArray(recipesRes.value.data) : [],
      } as CommandSearchResults
    } catch (err) {
      logger.error('[CommandPalette] Search error:', err)
      searchResults.value = { zones: [], nodes: [], recipes: [] }
    } finally {
      loading.value = false
    }
  }

  let searchTimeout: ReturnType<typeof setTimeout> | null = null
  watch(q, (newQuery: string) => {
    selectedIndex.value = 0
    if (searchTimeout) {
      clearTimeout(searchTimeout)
    }
    searchTimeout = setTimeout(() => {
      searchAPI(newQuery)
    }, 300)
  })

  if (getCurrentInstance()) {
    onUnmounted(() => {
      if (searchTimeout) {
        clearTimeout(searchTimeout)
      }
    })
  }

  const commandItems = computed<CommandItem[]>(() => buildCommandItems({
    query: q.value,
    role: allowedRoles.includes(role.value as UserRole) ? role.value : undefined,
    searchResults: searchResults.value,
    history: history.value,
    handlers,
  }))

  const groupedResults = computed(() => groupCommandItems(commandItems.value))

  function getItemIndex(groupIndex: number, itemIndex: number): number {
    let index = 0
    for (let i = 0; i < groupIndex; i++) {
      index += groupedResults.value[i].items.length
    }
    return index + itemIndex
  }

  const selectedItem = computed<CommandItem | null>(() => {
    let currentIndex = 0
    for (const group of groupedResults.value) {
      if (selectedIndex.value >= currentIndex && selectedIndex.value < currentIndex + group.items.length) {
        return group.items[selectedIndex.value - currentIndex]
      }
      currentIndex += group.items.length
    }
    return null
  })

  const totalItemsCount = computed(() => groupedResults.value.reduce((sum, group) => sum + group.items.length, 0))

  function highlightMatch(text: string, query: string): TextSegment[] {
    if (!query) {
      return [{ text, match: false }]
    }

    const escapedQuery = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    const regex = new RegExp(`(${escapedQuery})`, 'gi')
    const segments: TextSegment[] = []
    let lastIndex = 0
    let match: RegExpExecArray | null

    while ((match = regex.exec(text)) !== null) {
      if (match.index > lastIndex) {
        segments.push({
          text: text.substring(lastIndex, match.index),
          match: false,
        })
      }

      segments.push({
        text: match[0],
        match: true,
      })

      lastIndex = regex.lastIndex

      if (match[0].length === 0) {
        regex.lastIndex++
      }
    }

    if (lastIndex < text.length) {
      segments.push({
        text: text.substring(lastIndex),
        match: false,
      })
    }

    if (segments.length === 0) {
      return [{ text, match: false }]
    }

    return segments
  }

  return {
    q,
    selectedIndex,
    loading,
    searchResults,
    commandItems,
    groupedResults,
    getItemIndex,
    selectedItem,
    totalItemsCount,
    highlightMatch,
  }
}

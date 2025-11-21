<template>
  <div>
    <div v-if="open" class="fixed inset-0 z-50">
      <div class="absolute inset-0 bg-black/70" @click="close"></div>
      <div class="relative mx-auto mt-24 w-full max-w-xl rounded-xl border border-neutral-800 bg-neutral-925 p-3">
        <input 
          v-model="q" 
          ref="inputRef"
          placeholder="Команда или поиск..." 
          class="h-10 w-full rounded-md border border-neutral-800 bg-neutral-900 px-3 text-sm"
          @keydown.down.prevent="selectedIndex = Math.min(selectedIndex + 1, filteredResults.length - 1)"
          @keydown.up.prevent="selectedIndex = Math.max(selectedIndex - 1, 0)"
          @keydown.enter.prevent="run(filteredResults[selectedIndex])"
        />
        <div class="mt-2 max-h-72 overflow-y-auto">
          <div 
            v-for="(item, i) in filteredResults" 
            :key="`${item.type}-${item.id || i}`"
            class="px-3 py-2 text-sm hover:bg-neutral-850 cursor-pointer rounded-md flex items-center gap-2"
            :class="{ 'bg-neutral-850': i === selectedIndex }"
            @click="run(item)"
            @mouseenter="selectedIndex = i"
          >
            <span v-if="item.icon" class="text-neutral-400">{{ item.icon }}</span>
            <span v-html="highlightMatch(item.label, q)"></span>
            <span v-if="item.category" class="ml-auto text-xs text-neutral-500">{{ item.category }}</span>
          </div>
          <div v-if="loading" class="px-3 py-2 text-sm text-neutral-400">Загрузка...</div>
          <div v-if="!loading && filteredResults.length === 0 && q" class="px-3 py-2 text-sm text-neutral-400">
            Ничего не найдено
          </div>
        </div>
      </div>
    </div>
    
    <!-- Модальное окно подтверждения -->
    <ConfirmModal
      :open="confirmModal.open"
      :title="confirmModal.title"
      :message="confirmModal.message"
      @close="confirmModal.open = false"
      @confirm="confirmAction"
    />
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref, computed, watch, nextTick } from 'vue'
import { router } from '@inertiajs/vue3'
import { logger } from '@/utils/logger'
import { useApi } from '@/composables/useApi'
import { useCommands } from '@/composables/useCommands'
import ConfirmModal from '@/Components/ConfirmModal.vue'
import type { Zone, Device, Recipe } from '@/types'

interface CommandItem {
  type: 'nav' | 'zone' | 'node' | 'recipe' | 'action'
  id?: number | string
  label: string
  icon?: string
  category?: string
  action?: () => void
  actionFn?: () => void | Promise<void>
  requiresConfirm?: boolean
  zoneId?: number
  zoneName?: string
  recipeId?: number
  recipeName?: string
  actionType?: string
  cycleType?: string
}

interface ConfirmModalState {
  open: boolean
  title: string
  message: string
  action: (() => void | Promise<void>) | null
}

interface SearchResults {
  zones: Zone[]
  nodes: Device[]
  recipes: Recipe[]
}

const open = ref<boolean>(false)
const q = ref<string>('')
const selectedIndex = ref<number>(0)
const inputRef = ref<HTMLInputElement | null>(null)
const loading = ref<boolean>(false)

const { api } = useApi()
const { sendZoneCommand } = useCommands()

// Модальное окно подтверждения
const confirmModal = ref<ConfirmModalState>({
  open: false,
  title: '',
  message: '',
  action: null
})

// Статические команды навигации
const staticCommands: CommandItem[] = [
  { type: 'nav', label: 'Открыть Zones', icon: '📁', action: () => router.visit('/zones') },
  { type: 'nav', label: 'Открыть Devices', icon: '📱', action: () => router.visit('/devices') },
  { type: 'nav', label: 'Открыть Recipes', icon: '📋', action: () => router.visit('/recipes') },
  { type: 'nav', label: 'Открыть Alerts', icon: '⚠️', action: () => router.visit('/alerts') },
  { type: 'nav', label: 'Открыть Dashboard', icon: '📊', action: () => router.visit('/') },
  { type: 'nav', label: 'Мастер настройки системы', icon: '⚙️', action: () => router.visit('/setup/wizard'), category: 'Настройка' },
  { type: 'nav', label: 'Создать теплицу', icon: '🏠', action: () => router.visit('/greenhouses/create'), category: 'Создание' },
  { type: 'nav', label: 'Создать рецепт', icon: '➕', action: () => router.visit('/recipes/create'), category: 'Создание' },
]

// Результаты поиска
const searchResults = ref<SearchResults>({
  zones: [],
  nodes: [],
  recipes: []
})

// Fuzzy search функция
function fuzzyMatch(text: string, query: string): boolean {
  if (!query) return true
  const textLower = text.toLowerCase()
  const queryLower = query.toLowerCase()
  let textIndex = 0
  let queryIndex = 0
  
  while (textIndex < textLower.length && queryIndex < queryLower.length) {
    if (textLower[textIndex] === queryLower[queryIndex]) {
      queryIndex++
    }
    textIndex++
  }
  
  return queryIndex === queryLower.length
}

// Подсветка совпадений
function highlightMatch(text: string, query: string): string {
  if (!query) return text
  const regex = new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi')
  return text.replace(regex, '<mark class="bg-amber-500/30">$1</mark>')
}

// Поиск через API
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
      api.get('/api/recipes', { params: { search: query } })
    ])

    searchResults.value = {
      zones: zonesRes.status === 'fulfilled' ? (zonesRes.value.data?.data || zonesRes.value.data || []) : [],
      nodes: nodesRes.status === 'fulfilled' ? (nodesRes.value.data?.data || nodesRes.value.data || []) : [],
      recipes: recipesRes.status === 'fulfilled' ? (recipesRes.value.data?.data || recipesRes.value.data || []) : []
    }
  } catch (err) {
    logger.error('[CommandPalette] Search error:', err)
    searchResults.value = { zones: [], nodes: [], recipes: [] }
  } finally {
    loading.value = false
  }
}

// Debounce для поиска
let searchTimeout: ReturnType<typeof setTimeout> | null = null
watch(q, (newQuery: string) => {
  selectedIndex.value = 0
  if (searchTimeout) clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => {
    searchAPI(newQuery)
  }, 300)
})

// Формируем результаты
const filteredResults = computed<CommandItem[]>(() => {
  const query = q.value.toLowerCase()
  
  // Если запрос пустой, показываем только статические команды
  if (!query) {
    return staticCommands
  }

  const results = []
  
  // Фильтруем статические команды
  staticCommands.forEach(cmd => {
    if (fuzzyMatch(cmd.label, query)) {
      results.push(cmd)
    }
  })

  // Добавляем зоны с быстрыми действиями
  searchResults.value.zones.forEach(zone => {
    if (fuzzyMatch(zone.name, query)) {
      // Переход к зоне
      results.push({
        type: 'zone',
        id: zone.id,
        label: zone.name,
        icon: '🌱',
        category: 'Зона',
        action: () => router.visit(`/zones/${zone.id}`)
      })
      
      // Быстрые действия для зоны
      if (zone.status === 'PAUSED') {
        results.push({
          type: 'action',
          id: `zone-${zone.id}-resume`,
          label: `Возобновить зону "${zone.name}"`,
          icon: '▶️',
          category: 'Действие',
          zoneId: zone.id,
          zoneName: zone.name,
          actionType: 'resume',
          requiresConfirm: false,
          actionFn: () => executeZoneAction(zone.id, 'resume', zone.name)
        })
      } else if (zone.status === 'RUNNING') {
        results.push({
          type: 'action',
          id: `zone-${zone.id}-pause`,
          label: `Приостановить зону "${zone.name}"`,
          icon: '⏸️',
          category: 'Действие',
          zoneId: zone.id,
          zoneName: zone.name,
          actionType: 'pause',
          requiresConfirm: true,
          actionFn: () => executeZoneAction(zone.id, 'pause', zone.name)
        })
        
        // Быстрые действия для циклов
        results.push({
          type: 'action',
          id: `zone-${zone.id}-irrigate`,
          label: `Полить зону "${zone.name}"`,
          icon: '💧',
          category: 'Цикл: Полив',
          zoneId: zone.id,
          zoneName: zone.name,
          actionType: 'irrigate',
          requiresConfirm: true,
          actionFn: () => executeZoneCycle(zone.id, 'IRRIGATION', zone.name)
        })
        results.push({
          type: 'action',
          id: `zone-${zone.id}-ph-control`,
          label: `Коррекция pH в зоне "${zone.name}"`,
          icon: '🧪',
          category: 'Цикл: pH',
          zoneId: zone.id,
          zoneName: zone.name,
          actionType: 'ph-control',
          requiresConfirm: true,
          actionFn: () => executeZoneCycle(zone.id, 'PH_CONTROL', zone.name)
        })
        results.push({
          type: 'action',
          id: `zone-${zone.id}-ec-control`,
          label: `Коррекция EC в зоне "${zone.name}"`,
          icon: '⚡',
          category: 'Цикл: EC',
          zoneId: zone.id,
          zoneName: zone.name,
          actionType: 'ec-control',
          requiresConfirm: true,
          actionFn: () => executeZoneCycle(zone.id, 'EC_CONTROL', zone.name)
        })
        results.push({
          type: 'action',
          id: `zone-${zone.id}-climate`,
          label: `Управление климатом в зоне "${zone.name}"`,
          icon: '🌡️',
          category: 'Цикл: Климат',
          zoneId: zone.id,
          zoneName: zone.name,
          actionType: 'climate',
          requiresConfirm: true,
          actionFn: () => executeZoneCycle(zone.id, 'CLIMATE', zone.name)
        })
        results.push({
          type: 'action',
          id: `zone-${zone.id}-lighting`,
          label: `Управление освещением в зоне "${zone.name}"`,
          icon: '💡',
          category: 'Цикл: Освещение',
          zoneId: zone.id,
          zoneName: zone.name,
          actionType: 'lighting',
          requiresConfirm: true,
          actionFn: () => executeZoneCycle(zone.id, 'LIGHTING', zone.name)
        })
        
        results.push({
          type: 'action',
          id: `zone-${zone.id}-next-phase`,
          label: `Следующая фаза в зоне "${zone.name}"`,
          icon: '⏭️',
          category: 'Рецепт',
          zoneId: zone.id,
          zoneName: zone.name,
          actionType: 'next-phase',
          requiresConfirm: true,
          actionFn: () => executeZoneAction(zone.id, 'next-phase', zone.name)
        })
      }
    }
  })

  // Добавляем узлы
  searchResults.value.nodes.forEach(node => {
    const label = node.name || node.uid || `Node #${node.id}`
    if (fuzzyMatch(label, query)) {
      results.push({
        type: 'node',
        id: node.id,
        label,
        icon: '📱',
        category: 'Устройство',
        action: () => router.visit(`/devices/${node.id}`)
      })
    }
  })

  // Добавляем рецепты с действиями
  searchResults.value.recipes.forEach(recipe => {
    if (fuzzyMatch(recipe.name, query)) {
      // Переход к рецепту
      results.push({
        type: 'recipe',
        id: recipe.id,
        label: recipe.name,
        icon: '📋',
        category: 'Рецепт',
        action: () => router.visit(`/recipes/${recipe.id}`)
      })
      
      // Действие: применить рецепт к зоне (нужно выбрать зону)
      // Это будет работать только если в запросе упомянута зона
      searchResults.value.zones.forEach(zone => {
        if (fuzzyMatch(zone.name, query) || query.includes(zone.name.toLowerCase())) {
          results.push({
            type: 'action',
            id: `recipe-${recipe.id}-apply-zone-${zone.id}`,
            label: `Применить рецепт "${recipe.name}" к зоне "${zone.name}"`,
            icon: '🔄',
            category: 'Рецепт',
            zoneId: zone.id,
            zoneName: zone.name,
            recipeId: recipe.id,
            recipeName: recipe.name,
            actionType: 'apply-recipe',
            requiresConfirm: true,
            actionFn: () => applyRecipeToZone(zone.id, recipe.id, zone.name, recipe.name)
          })
        }
      })
    }
  })

  return results
})

const run = (item: CommandItem | undefined): void => {
  if (!item) return
  
  // Если действие требует подтверждения
  if (item.requiresConfirm && item.actionFn) {
    const actionNames: Record<string, string> = {
      'pause': 'приостановить',
      'irrigate': 'полить',
      'ph-control': 'запустить коррекцию pH',
      'ec-control': 'запустить коррекцию EC',
      'climate': 'запустить управление климатом',
      'lighting': 'запустить управление освещением',
      'next-phase': 'перейти к следующей фазе',
      'resume': 'возобновить',
      'apply-recipe': `применить рецепт "${item.recipeName}"`
    }
    const actionName = actionNames[item.actionType || ''] || 'выполнить это действие'
    const zoneName = item.zoneName ? ` для зоны "${item.zoneName}"` : ''
    confirmModal.value = {
      open: true,
      title: 'Подтверждение действия',
      message: `Вы уверены, что хотите ${actionName}${zoneName}?`,
      action: item.actionFn
    }
    return
  }
  
  // Обычное действие
  if (item.actionFn) {
    item.actionFn()
  } else {
    item.action?.()
  }
  close()
}

async function executeZoneAction(zoneId: number, action: string, zoneName: string): Promise<void> {
  try {
    if (action === 'pause') {
      await api.post(`/api/zones/${zoneId}/pause`, {})
      logger.info(`[CommandPalette] Зона "${zoneName}" приостановлена`)
    } else if (action === 'resume') {
      await api.post(`/api/zones/${zoneId}/resume`, {})
      logger.info(`[CommandPalette] Зона "${zoneName}" возобновлена`)
    } else if (action === 'next-phase') {
      await api.post(`/api/zones/${zoneId}/next-phase`, {})
      logger.info(`[CommandPalette] Переход к следующей фазе в зоне "${zoneName}"`)
    }
    close()
  } catch (err) {
    logger.error(`[CommandPalette] Failed to execute ${action}:`, err)
    close()
  }
}

/**
 * Выполнить цикл в зоне
 */
async function executeZoneCycle(zoneId: number, cycleType: string, zoneName: string): Promise<void> {
  try {
    const commandType = `FORCE_${cycleType}` as any
    const cycleNames: Record<string, string> = {
      'IRRIGATION': 'Полив',
      'PH_CONTROL': 'Коррекция pH',
      'EC_CONTROL': 'Коррекция EC',
      'CLIMATE': 'Управление климатом',
      'LIGHTING': 'Управление освещением'
    }
    const cycleName = cycleNames[cycleType] || cycleType
    
    // Используем параметры по умолчанию из targets/recipe (как в Zone Detail)
    // Для простоты используем базовые значения, в реальности нужно получать из API
    const defaultParams: Record<string, unknown> = {}
    
    switch (cycleType) {
      case 'IRRIGATION':
        defaultParams.duration_sec = 10
        break
      case 'PH_CONTROL':
        defaultParams.target_ph = 6.0
        break
      case 'EC_CONTROL':
        defaultParams.target_ec = 1.5
        break
      case 'CLIMATE':
        defaultParams.target_temp = 22
        defaultParams.target_humidity = 60
        break
      case 'LIGHTING':
        defaultParams.duration_hours = 12
        defaultParams.intensity = 80
        break
    }
    
    await sendZoneCommand(zoneId, commandType, defaultParams)
    logger.info(`[CommandPalette] Цикл "${cycleName}" запущен в зоне "${zoneName}"`)
    close()
  } catch (err) {
    logger.error(`[CommandPalette] Failed to execute cycle ${cycleType}:`, err)
    close()
  }
}

/**
 * Применить рецепт к зоне с перекрестной инвалидацией кеша
 */
async function applyRecipeToZone(zoneId: number, recipeId: number, zoneName: string, recipeName: string): Promise<void> {
  try {
    await api.post(`/api/zones/${zoneId}/attach-recipe`, {
      recipe_id: recipeId
    })
    
    // Инвалидируем кеш зон и рецептов через stores
    const { useZonesStore } = await import('@/stores/zones')
    const zonesStore = useZonesStore()
    await zonesStore.attachRecipe(zoneId, recipeId)
    
    logger.info(`[CommandPalette] Рецепт "${recipeName}" применен к зоне "${zoneName}"`)
    close()
  } catch (err) {
    logger.error(`[CommandPalette] Failed to apply recipe:`, err)
    handleError(err, {
      component: 'CommandPalette',
      action: 'applyRecipeToZone',
      zoneId,
      recipeId,
    })
    close()
  }
}

function confirmAction(): void {
  if (confirmModal.value.action) {
    confirmModal.value.action()
  }
  confirmModal.value.open = false
  close()
}

const close = (): void => {
  open.value = false
  q.value = ''
  selectedIndex.value = 0
  searchResults.value = { zones: [], nodes: [], recipes: [] }
}

watch(open, (isOpen: boolean) => {
  if (isOpen) {
    nextTick(() => {
      inputRef.value?.focus()
    })
  }
})

const onKey = (e: KeyboardEvent): void => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    open.value = !open.value
  }
  if (e.key === 'Escape' && open.value) {
    e.preventDefault()
    close()
  }
}

onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>


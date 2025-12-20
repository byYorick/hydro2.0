<template>
  <Transition name="command-palette">
    <div v-if="open" class="fixed inset-0 z-50">
      <div class="absolute inset-0 bg-[color:var(--bg-main)] opacity-80 backdrop-blur-sm" @click="close"></div>
      <div class="relative mx-auto mt-12 sm:mt-24 w-full max-w-xl rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3 shadow-[var(--shadow-card)] mx-4 sm:mx-auto">
        <!-- Заголовок и подсказки -->
        <div class="mb-2 flex items-center justify-between">
          <div class="text-xs text-[color:var(--text-muted)]">Командная палитра</div>
          <div class="hidden sm:flex items-center gap-2 text-xs text-[color:var(--text-dim)]">
            <kbd class="px-1.5 py-0.5 rounded bg-[color:var(--bg-elevated)] border border-[color:var(--border-muted)]">↑↓</kbd>
            <span>навигация</span>
            <kbd class="px-1.5 py-0.5 rounded bg-[color:var(--bg-elevated)] border border-[color:var(--border-muted)]">↵</kbd>
            <span>выбрать</span>
            <kbd class="px-1.5 py-0.5 rounded bg-[color:var(--bg-elevated)] border border-[color:var(--border-muted)]">Esc</kbd>
            <span>закрыть</span>
          </div>
        </div>
        
        <input 
          v-model="q" 
          ref="inputRef"
          placeholder="Команда или поиск..." 
          class="input-field h-12 w-full px-4 text-sm transition-all duration-200"
          @keydown.down.prevent="selectedIndex = Math.min(selectedIndex + 1, totalItemsCount - 1)"
          @keydown.up.prevent="selectedIndex = Math.max(selectedIndex - 1, 0)"
          @keydown.enter.prevent="runSelected()"
        />
        
        <div class="mt-3 max-h-80 overflow-y-auto scrollbar-thin scrollbar-thumb-[color:var(--border-muted)] scrollbar-track-transparent">
          <!-- Группированные результаты -->
          <template v-for="(group, groupIndex) in groupedResults" :key="group.category">
            <div v-if="group.items.length > 0" class="mb-2">
              <div class="px-3 py-1.5 text-xs font-semibold text-[color:var(--text-dim)] uppercase tracking-wider">
                {{ group.category }}
              </div>
              <TransitionGroup name="command-item" tag="div">
                <div 
                  v-for="(item, itemIndex) in group.items" 
                  :key="`${item.type}-${item.id || itemIndex}`"
                  :data-index="getItemIndex(groupIndex, itemIndex)"
                  class="px-3 py-2.5 text-sm hover:bg-[color:var(--bg-elevated)] cursor-pointer rounded-md flex items-center gap-3 transition-all duration-150"
                  :class="{ 
                    'bg-[color:var(--bg-elevated)] border-l-2 border-[color:var(--accent-cyan)]': getItemIndex(groupIndex, itemIndex) === selectedIndex 
                  }"
                  @click="run(item)"
                  @mouseenter="selectedIndex = getItemIndex(groupIndex, itemIndex)"
                >
                  <span v-if="item.icon" class="text-lg flex-shrink-0">{{ item.icon }}</span>
                  <span class="flex-1">
                    <template v-for="(segment, segmentIndex) in highlightMatch(item.label, q)" :key="segmentIndex">
                      <mark v-if="segment.match" class="bg-[color:var(--badge-warning-bg)] text-[color:var(--badge-warning-text)]">{{ segment.text }}</mark>
                      <span v-else>{{ segment.text }}</span>
                    </template>
                  </span>
                  <span v-if="item.shortcut" class="ml-auto text-xs text-[color:var(--text-dim)] flex items-center gap-1">
                    <kbd class="px-1.5 py-0.5 rounded bg-[color:var(--bg-elevated)] border border-[color:var(--border-muted)] text-[10px]">
                      {{ item.shortcut }}
                    </kbd>
                  </span>
                </div>
              </TransitionGroup>
            </div>
          </template>
          
          <div v-if="loading" class="px-3 py-4 text-sm text-[color:var(--text-muted)] flex items-center gap-2">
            <div class="w-4 h-4 border-2 border-[color:var(--border-muted)] border-t-transparent rounded-full animate-spin"></div>
            Загрузка...
          </div>
          <div v-if="!loading && groupedResults.length === 0 && q" class="px-3 py-4 text-sm text-[color:var(--text-muted)] text-center">
            Ничего не найдено
          </div>
          <div v-if="!loading && groupedResults.length === 0 && !q" class="px-3 py-4 text-sm text-[color:var(--text-muted)] text-center">
            Начните вводить для поиска...
          </div>
        </div>
      </div>
    </div>
  </Transition>
  
  <!-- Модальное окно подтверждения -->
  <ConfirmModal
    :open="confirmModal.open"
    :title="confirmModal.title"
    :message="confirmModal.message"
    @close="confirmModal.open = false"
    @confirm="confirmAction"
  />
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref, computed, watch, nextTick } from 'vue'
import { router } from '@inertiajs/vue3'
import { logger } from '@/utils/logger'
import { useApi } from '@/composables/useApi'
import { useCommands } from '@/composables/useCommands'
import { useRole } from '@/composables/useRole'
import ConfirmModal from '@/Components/ConfirmModal.vue'
import type { Zone, Device, Recipe } from '@/types'

// Debounce для предотвращения множественных вызовов router.visit
const visitTimers = new Map<string, ReturnType<typeof setTimeout>>()
const VISIT_DEBOUNCE_MS = 300

/**
 * Безопасный переход с проверкой текущего URL и debounce
 */
function safeVisit(url: string, options: { preserveScroll?: boolean } = {}): void {
  const currentUrl = router.page?.url || window.location.pathname
  const targetUrl = url.startsWith('/') ? url : `/${url}`
  
  // Если уже на целевой странице, не делаем переход
  if (currentUrl === targetUrl) {
    return
  }
  
  const key = targetUrl
  
  // Очищаем предыдущий таймер для этого URL
  if (visitTimers.has(key)) {
    clearTimeout(visitTimers.get(key)!)
  }
  
  // Устанавливаем новый таймер с debounce
  visitTimers.set(key, setTimeout(() => {
    visitTimers.delete(key)
    router.visit(targetUrl, { preserveScroll: options.preserveScroll ?? true })
  }, VISIT_DEBOUNCE_MS))
}

interface CommandItem {
  type: 'nav' | 'zone' | 'node' | 'recipe' | 'action'
  id?: number | string
  label: string
  icon?: string
  category?: string
  shortcut?: string
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

interface GroupedResult {
  category: string
  items: CommandItem[]
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
const { isAdmin, isOperator, isAgronomist, isEngineer } = useRole()

// История команд (хранится в localStorage)
const commandHistory = ref<Array<{ label: string; timestamp: number; action: string }>>([])
const maxHistorySize = 10

// Загрузка истории из localStorage
function loadHistory() {
  try {
    const stored = localStorage.getItem('commandPaletteHistory')
    if (stored) {
      commandHistory.value = JSON.parse(stored).slice(0, maxHistorySize)
    }
  } catch (err) {
    logger.error('[CommandPalette] Failed to load history:', err)
  }
}

// Сохранение команды в историю
function saveToHistory(item: CommandItem) {
  if (item.type === 'nav' || item.type === 'action') {
    const historyItem = {
      label: item.label,
      timestamp: Date.now(),
      action: item.type
    }
    // Удаляем дубликаты
    commandHistory.value = commandHistory.value.filter(h => h.label !== item.label)
    // Добавляем в начало
    commandHistory.value.unshift(historyItem)
    // Ограничиваем размер
    commandHistory.value = commandHistory.value.slice(0, maxHistorySize)
    // Сохраняем в localStorage
    try {
      localStorage.setItem('commandPaletteHistory', JSON.stringify(commandHistory.value))
    } catch (err) {
      logger.error('[CommandPalette] Failed to save history:', err)
    }
  }
}

// Модальное окно подтверждения
const confirmModal = ref<ConfirmModalState>({
  open: false,
  title: '',
  message: '',
  action: null
})

// Статические команды навигации (базовые для всех)
const baseStaticCommands: CommandItem[] = [
  { type: 'nav', label: 'Открыть Dashboard', icon: '📊', category: 'Навигация', action: () => safeVisit('/') },
  { type: 'nav', label: 'Открыть Zones', icon: '🌱', category: 'Навигация', action: () => safeVisit('/zones') },
  { type: 'nav', label: 'Открыть Devices', icon: '📱', category: 'Навигация', action: () => safeVisit('/devices') },
  { type: 'nav', label: 'Открыть Recipes', icon: '📋', category: 'Навигация', action: () => safeVisit('/recipes') },
  { type: 'nav', label: 'Открыть Alerts', icon: '⚠️', category: 'Навигация', action: () => safeVisit('/alerts') },
]

// Ролевые команды
const roleBasedCommands = computed<CommandItem[]>(() => {
  const commands: CommandItem[] = []
  
  // Команды для админа
  if (isAdmin.value) {
    commands.push(
      { type: 'nav', label: 'Управление пользователями', icon: '👥', category: 'Администрирование', action: () => safeVisit('/users') },
      { type: 'nav', label: 'Системные настройки', icon: '⚙️', category: 'Администрирование', action: () => safeVisit('/settings') },
      { type: 'nav', label: 'Аудит', icon: '📝', category: 'Администрирование', action: () => safeVisit('/audit') },
    )
  }
  
  // Команды для агронома
  if (isAgronomist.value) {
    commands.push(
      { type: 'nav', label: 'Аналитика', icon: '📈', category: 'Аналитика', action: () => safeVisit('/analytics') },
      { type: 'nav', label: 'Создать рецепт', icon: '➕', category: 'Создание', action: () => safeVisit('/recipes/create') },
    )
  }
  
  // Команды для инженера
  if (isEngineer.value) {
    commands.push(
      { type: 'nav', label: 'Системные метрики', icon: '📊', category: 'Система', action: () => safeVisit('/system') },
      { type: 'nav', label: 'Логи', icon: '📋', category: 'Система', action: () => safeVisit('/logs') },
    )
  }
  
  // Команды для оператора и админа
  if (isOperator.value || isAdmin.value) {
    commands.push(
      { type: 'nav', label: 'Теплицы', icon: '🏠', category: 'Управление', action: () => safeVisit('/greenhouses') },
    )
  }
  
  return commands
})

// Объединенные статические команды
const staticCommands = computed(() => [...baseStaticCommands, ...roleBasedCommands.value])

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

// Интерфейс для сегмента текста
interface TextSegment {
  text: string
  match: boolean
}

// Подсветка совпадений - возвращает массив сегментов вместо HTML
function highlightMatch(text: string, query: string): TextSegment[] {
  if (!query) {
    return [{ text, match: false }]
  }
  
  // Экранируем спецсимволы regex
  const escapedQuery = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const regex = new RegExp(`(${escapedQuery})`, 'gi')
  const segments: TextSegment[] = []
  let lastIndex = 0
  let match
  
  // Используем цикл для поиска всех совпадений
  while ((match = regex.exec(text)) !== null) {
    // Добавляем текст до совпадения
    if (match.index > lastIndex) {
      segments.push({
        text: text.substring(lastIndex, match.index),
        match: false
      })
    }
    
    // Добавляем совпадение
    segments.push({
      text: match[0],
      match: true
    })
    
    lastIndex = regex.lastIndex
    
    // Предотвращаем бесконечный цикл при пустых совпадениях
    if (match[0].length === 0) {
      regex.lastIndex++
    }
  }
  
  // Добавляем оставшийся текст
  if (lastIndex < text.length) {
    segments.push({
      text: text.substring(lastIndex),
      match: false
    })
  }
  
  // Если совпадений не найдено, возвращаем весь текст как один сегмент
  if (segments.length === 0) {
    return [{ text, match: false }]
  }
  
  return segments
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

// Формируем результаты с группировкой
const groupedResults = computed<GroupedResult[]>(() => {
  const query = q.value.toLowerCase()
  const flatResults: CommandItem[] = []
  
  // Если запрос пустой, показываем историю и статические команды
  if (!query) {
    // Добавляем историю команд
    if (commandHistory.value.length > 0) {
      commandHistory.value.forEach((historyItem, index) => {
        flatResults.push({
          type: 'nav',
          label: historyItem.label,
          icon: '🕐',
          category: 'История',
          shortcut: index === 0 ? 'Недавно' : undefined,
          action: () => {
            // Восстанавливаем действие из истории (упрощенная версия)
            const matchingCommand = staticCommands.value.find(cmd => cmd.label === historyItem.label)
            if (matchingCommand?.action) {
              matchingCommand.action()
            }
          }
        })
      })
    }
    // Добавляем статические команды
    flatResults.push(...staticCommands.value)
  } else {
  
    // Фильтруем статические команды
    staticCommands.value.forEach(cmd => {
      if (fuzzyMatch(cmd.label, query)) {
        flatResults.push(cmd)
      }
    })
    
    // Фильтруем историю
    commandHistory.value.forEach(historyItem => {
      if (fuzzyMatch(historyItem.label, query)) {
        flatResults.push({
          type: 'nav',
          label: historyItem.label,
          icon: '🕐',
          category: 'История',
          action: () => {
            const matchingCommand = staticCommands.value.find(cmd => cmd.label === historyItem.label)
            if (matchingCommand?.action) {
              matchingCommand.action()
            }
          }
        })
      }
    })

    // Добавляем зоны с быстрыми действиями
    searchResults.value.zones.forEach(zone => {
      if (fuzzyMatch(zone.name, query)) {
        // Переход к зоне
        flatResults.push({
          type: 'zone',
          id: zone.id,
          label: zone.name,
          icon: '🌱',
          category: 'Зона',
          action: () => safeVisit(`/zones/${zone.id}`)
        })
      
        // Быстрые действия для зоны
        if (zone.status === 'PAUSED') {
          flatResults.push({
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
          flatResults.push({
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
          flatResults.push({
            type: 'action',
            id: `zone-${zone.id}-irrigate`,
            label: `Полить зону "${zone.name}"`,
            icon: '💧',
            category: 'Цикл',
            zoneId: zone.id,
            zoneName: zone.name,
            actionType: 'irrigate',
            requiresConfirm: true,
            actionFn: () => executeZoneCycle(zone.id, 'IRRIGATION', zone.name)
          })
          flatResults.push({
            type: 'action',
            id: `zone-${zone.id}-ph-control`,
            label: `Коррекция pH в зоне "${zone.name}"`,
            icon: '🧪',
            category: 'Цикл',
            zoneId: zone.id,
            zoneName: zone.name,
            actionType: 'ph-control',
            requiresConfirm: true,
            actionFn: () => executeZoneCycle(zone.id, 'PH_CONTROL', zone.name)
          })
          flatResults.push({
            type: 'action',
            id: `zone-${zone.id}-ec-control`,
            label: `Коррекция EC в зоне "${zone.name}"`,
            icon: '⚡',
            category: 'Цикл',
            zoneId: zone.id,
            zoneName: zone.name,
            actionType: 'ec-control',
            requiresConfirm: true,
            actionFn: () => executeZoneCycle(zone.id, 'EC_CONTROL', zone.name)
          })
          flatResults.push({
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
        flatResults.push({
          type: 'node',
          id: node.id,
          label,
          icon: '📱',
          category: 'Устройство',
          action: () => safeVisit(`/devices/${node.id}`)
        })
      }
    })

    // Добавляем рецепты с действиями
    searchResults.value.recipes.forEach(recipe => {
      if (fuzzyMatch(recipe.name, query)) {
        // Переход к рецепту
        flatResults.push({
          type: 'recipe',
          id: recipe.id,
          label: recipe.name,
          icon: '📋',
          category: 'Рецепт',
          action: () => safeVisit(`/recipes/${recipe.id}`)
        })
        
        // Действие: применить рецепт к зоне (нужно выбрать зону)
        searchResults.value.zones.forEach(zone => {
          if (fuzzyMatch(zone.name, query) || query.includes(zone.name.toLowerCase())) {
            flatResults.push({
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
  }
  
  // Группируем результаты по категориям
  const grouped = new Map<string, CommandItem[]>()
  flatResults.forEach(item => {
    const category = item.category || 'Другое'
    if (!grouped.has(category)) {
      grouped.set(category, [])
    }
    grouped.get(category)!.push(item)
  })
  
  // Преобразуем в массив и сортируем категории
  const categoryOrder = ['История', 'Навигация', 'Зона', 'Устройство', 'Рецепт', 'Действие', 'Цикл', 'Создание', 'Настройка', 'Администрирование', 'Аналитика', 'Система', 'Другое']
  return Array.from(grouped.entries())
    .map(([category, items]) => ({ category, items }))
    .sort((a, b) => {
      const aIndex = categoryOrder.indexOf(a.category)
      const bIndex = categoryOrder.indexOf(b.category)
      return (aIndex === -1 ? 999 : aIndex) - (bIndex === -1 ? 999 : bIndex)
    })
})

// Вычисляем индекс элемента в плоском списке
function getItemIndex(groupIndex: number, itemIndex: number): number {
  let index = 0
  for (let i = 0; i < groupIndex; i++) {
    index += groupedResults.value[i].items.length
  }
  return index + itemIndex
}

// Получаем выбранный элемент
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

function runSelected(): void {
  if (selectedItem.value) {
    run(selectedItem.value)
  }
}

// Плоский список для обратной совместимости
const filteredResults = computed<CommandItem[]>(() => {
  return groupedResults.value.flatMap(group => group.items)
})

// Общее количество элементов для навигации
const totalItemsCount = computed(() => {
  return groupedResults.value.reduce((sum, group) => sum + group.items.length, 0)
})

const run = (item: CommandItem | undefined): void => {
  if (!item) return
  
  // Сохраняем в историю перед выполнением
  saveToHistory(item)
  
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

onMounted(() => {
  loadHistory()
  window.addEventListener('keydown', onKey)
})
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>

<style scoped>
/* Анимации для Command Palette */
.command-palette-enter-active,
.command-palette-leave-active {
  transition: opacity 0.2s ease;
}

.command-palette-enter-from,
.command-palette-leave-to {
  opacity: 0;
}

.command-palette-enter-active > div:last-child,
.command-palette-leave-active > div:last-child {
  transition: transform 0.2s ease, opacity 0.2s ease;
}

.command-palette-enter-from > div:last-child {
  transform: translateY(-10px) scale(0.95);
  opacity: 0;
}

.command-palette-leave-to > div:last-child {
  transform: translateY(-10px) scale(0.95);
  opacity: 0;
}

/* Анимации для элементов списка */
.command-item-enter-active {
  transition: all 0.15s ease;
}

.command-item-enter-from {
  opacity: 0;
  transform: translateX(-10px);
}

.command-item-leave-active {
  transition: all 0.1s ease;
}

.command-item-leave-to {
  opacity: 0;
  transform: translateX(10px);
}

/* Кастомный скроллбар */
.scrollbar-thin::-webkit-scrollbar {
  width: 6px;
}

.scrollbar-thin::-webkit-scrollbar-track {
  background: transparent;
}

.scrollbar-thin::-webkit-scrollbar-thumb {
  background-color: var(--border-muted);
  border-radius: 3px;
}

.scrollbar-thin::-webkit-scrollbar-thumb:hover {
  background-color: var(--border-strong);
}
</style>

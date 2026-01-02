<template>
  <Transition name="command-palette">
    <div
      v-if="open"
      class="fixed inset-0 z-50"
    >
      <div
        class="absolute inset-0 bg-[color:var(--bg-main)] opacity-80 backdrop-blur-sm"
        @click="close"
      ></div>
      <div class="relative mx-auto mt-12 sm:mt-24 w-full max-w-xl rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3 shadow-[var(--shadow-card)] mx-4 sm:mx-auto">
        <!-- Заголовок и подсказки -->
        <div class="mb-2 flex items-center justify-between">
          <div class="text-xs text-[color:var(--text-muted)]">
            Командная палитра
          </div>
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
          ref="inputRef" 
          v-model="q"
          placeholder="Команда или поиск..." 
          class="input-field h-12 w-full px-4 text-sm transition-all duration-200"
          @keydown.down.prevent="selectedIndex = Math.min(selectedIndex + 1, totalItemsCount - 1)"
          @keydown.up.prevent="selectedIndex = Math.max(selectedIndex - 1, 0)"
          @keydown.enter.prevent="runSelected()"
        />
        
        <div class="mt-3 max-h-80 overflow-y-auto scrollbar-thin scrollbar-thumb-[color:var(--border-muted)] scrollbar-track-transparent">
          <!-- Группированные результаты -->
          <template
            v-for="(group, groupIndex) in groupedResults"
            :key="group.category"
          >
            <div
              v-if="group.items.length > 0"
              class="mb-2"
            >
              <div class="px-3 py-1.5 text-xs font-semibold text-[color:var(--text-dim)] uppercase tracking-wider">
                {{ group.category }}
              </div>
              <TransitionGroup
                name="command-item"
                tag="div"
              >
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
                  <span
                    v-if="item.icon"
                    class="text-lg flex-shrink-0"
                  >{{ item.icon }}</span>
                  <span class="flex-1">
                    <template
                      v-for="(segment, segmentIndex) in highlightMatch(item.label, q)"
                      :key="segmentIndex"
                    >
                      <mark
                        v-if="segment.match"
                        class="bg-[color:var(--badge-warning-bg)] text-[color:var(--badge-warning-text)]"
                      >{{ segment.text }}</mark>
                      <span v-else>{{ segment.text }}</span>
                    </template>
                  </span>
                  <span
                    v-if="item.shortcut"
                    class="ml-auto text-xs text-[color:var(--text-dim)] flex items-center gap-1"
                  >
                    <kbd class="px-1.5 py-0.5 rounded bg-[color:var(--bg-elevated)] border border-[color:var(--border-muted)] text-[10px]">
                      {{ item.shortcut }}
                    </kbd>
                  </span>
                </div>
              </TransitionGroup>
            </div>
          </template>
          
          <div
            v-if="loading"
            class="px-3 py-4 text-sm text-[color:var(--text-muted)] flex items-center gap-2"
          >
            <div class="w-4 h-4 border-2 border-[color:var(--border-muted)] border-t-transparent rounded-full animate-spin"></div>
            Загрузка...
          </div>
          <div
            v-if="!loading && groupedResults.length === 0 && q"
            class="px-3 py-4 text-sm text-[color:var(--text-muted)] text-center"
          >
            Ничего не найдено
          </div>
          <div
            v-if="!loading && groupedResults.length === 0 && !q"
            class="px-3 py-4 text-sm text-[color:var(--text-muted)] text-center"
          >
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

  <ZoneActionModal
    v-if="actionModal.open && actionModal.zoneId"
    :show="actionModal.open"
    :action-type="actionModal.actionType"
    :zone-id="actionModal.zoneId"
    :default-params="actionModal.defaultParams"
    @close="closeActionModal"
    @submit="onActionModalSubmit"
  />
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref, computed, watch, nextTick } from 'vue'
import { router, usePage } from '@inertiajs/vue3'
import { logger } from '@/utils/logger'
import { useApi } from '@/composables/useApi'
import { useCommands } from '@/composables/useCommands'
import { useRole } from '@/composables/useRole'
import { buildCommandItems, groupCommandItems, type CommandItem, type CommandHistoryItem, type CommandSearchResults, type CommandActionType, type CommandCycleType } from '@/commands/registry'
import ConfirmModal from '@/Components/ConfirmModal.vue'
import ZoneActionModal from '@/Components/ZoneActionModal.vue'
import type { CommandParams, CommandType } from '@/types'

const page = usePage()

// Debounce для предотвращения множественных вызовов router.visit
const visitTimers = new Map<string, ReturnType<typeof setTimeout>>()
const VISIT_DEBOUNCE_MS = 300

/**
 * Безопасный переход с проверкой текущего URL и debounce
 */
function safeVisit(url: string, options: { preserveUrl?: boolean } = {}): void {
  const currentUrl = page.url || window.location.pathname
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
    router.visit(targetUrl, { preserveUrl: options.preserveUrl ?? true })
  }, VISIT_DEBOUNCE_MS))
}

interface ConfirmModalState {
  open: boolean
  title: string
  message: string
  action: (() => void | Promise<void>) | null
}

const open = ref<boolean>(false)
const q = ref<string>('')
const selectedIndex = ref<number>(0)
const inputRef = ref<HTMLInputElement | null>(null)
const loading = ref<boolean>(false)

const { api } = useApi()
const { sendZoneCommand } = useCommands()
const { role } = useRole()

// История команд (хранится в localStorage)
const commandHistory = ref<CommandHistoryItem[]>([])
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

const actionModal = ref<{
  open: boolean
  zoneId: number | null
  actionType: CommandType
  defaultParams: CommandParams
}>({
  open: false,
  zoneId: null,
  actionType: 'FORCE_IRRIGATION',
  defaultParams: {},
})

// Результаты поиска
const searchResults = ref<CommandSearchResults>({
  zones: [],
  nodes: [],
  recipes: []
})

const targetsCache = new Map<number, unknown>()
const currentZoneId = computed(() => {
  const props = page.props as Record<string, any>
  return props.zone?.id ?? props.zoneId ?? null
})
const currentPhaseTargets = computed(() => {
  const props = page.props as Record<string, any>
  return props.current_phase?.targets ?? null
})
const legacyTargets = computed(() => {
  const props = page.props as Record<string, any>
  return props.targets ?? null
})

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

const commandItems = computed<CommandItem[]>(() => {
  return buildCommandItems({
    query: q.value,
    role: role.value,
    searchResults: searchResults.value,
    history: commandHistory.value,
    handlers: {
      navigate: safeVisit,
      zoneAction: executeZoneAction,
      zoneCycle: executeZoneCycle,
      openGrowCycleWizard: openGrowCycleWizardForZone,
    },
  })
})

// Формируем результаты с группировкой
const groupedResults = computed(() => groupCommandItems(commandItems.value))

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
      'open-cycle-wizard': 'открыть мастер цикла'
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

const normalizeTargets = (payload: unknown): Record<string, any> | null => {
  if (!payload || typeof payload !== 'object') return null
  const raw = payload as Record<string, any>
  if (raw.targets && typeof raw.targets === 'object') {
    return raw.targets as Record<string, any>
  }
  return raw
}

const resolveTargetValue = (target: any): number | null => {
  if (target === null || target === undefined) return null
  if (typeof target === 'number') return target
  if (typeof target.target === 'number') return target.target
  const min = typeof target.min === 'number' ? target.min : null
  const max = typeof target.max === 'number' ? target.max : null
  if (min !== null && max !== null) {
    return (min + max) / 2
  }
  return min ?? max
}

const resolveIrrigationDuration = (targets: Record<string, any> | null): number | null => {
  if (!targets) return null
  const candidates = [
    targets.irrigation?.duration_sec,
    targets.irrigation?.duration_seconds,
    targets.irrigation_duration_sec,
    targets.irrigation_duration_seconds,
  ]
  const match = candidates.find((value) => typeof value === 'number')
  return typeof match === 'number' ? match : null
}

const resolveCycleParams = async (zoneId: number, cycleType: CommandCycleType): Promise<CommandParams | null> => {
  let targets: Record<string, any> | null = null

  if (currentZoneId.value === zoneId) {
    targets = normalizeTargets(currentPhaseTargets.value) || normalizeTargets(legacyTargets.value)
  } else if (targetsCache.has(zoneId)) {
    targets = normalizeTargets(targetsCache.get(zoneId)) as Record<string, any> | null
  } else {
    try {
      const response = await api.get(`/api/zones/${zoneId}/effective-targets`)
      const payload = response?.data?.data ?? null
      targets = normalizeTargets(payload)
      targetsCache.set(zoneId, targets)
    } catch (err) {
      logger.warn('[CommandPalette] Failed to load effective targets', err)
      targetsCache.set(zoneId, null)
    }
  }

  if (!targets) return null

  if (cycleType === 'IRRIGATION') {
    const duration = resolveIrrigationDuration(targets)
    return duration !== null ? { duration_sec: duration } : null
  }

  if (cycleType === 'PH_CONTROL') {
    const phTarget = resolveTargetValue(targets.ph ?? { min: targets.ph_min, max: targets.ph_max })
    return phTarget !== null ? { target_ph: phTarget } : null
  }

  if (cycleType === 'EC_CONTROL') {
    const ecTarget = resolveTargetValue(targets.ec ?? { min: targets.ec_min, max: targets.ec_max })
    return ecTarget !== null ? { target_ec: ecTarget } : null
  }

  return null
}

const openActionModalForCycle = (zoneId: number, cycleType: CommandCycleType): void => {
  const actionMap: Record<CommandCycleType, CommandType> = {
    IRRIGATION: 'FORCE_IRRIGATION',
    PH_CONTROL: 'FORCE_PH_CONTROL',
    EC_CONTROL: 'FORCE_EC_CONTROL',
  }
  actionModal.value = {
    open: true,
    zoneId,
    actionType: actionMap[cycleType],
    defaultParams: {},
  }
}

const closeActionModal = (): void => {
  actionModal.value.open = false
  actionModal.value.zoneId = null
  actionModal.value.defaultParams = {}
}

const onActionModalSubmit = async ({ actionType, params }: { actionType: CommandType; params: CommandParams }): Promise<void> => {
  if (!actionModal.value.zoneId) return

  try {
    await sendZoneCommand(actionModal.value.zoneId, actionType, params)
  } catch (err) {
    logger.error('[CommandPalette] Failed to execute action from modal', err)
  } finally {
    closeActionModal()
  }
}

async function executeZoneAction(zoneId: number, action: CommandActionType, zoneName: string): Promise<void> {
  try {
    const cycleResponse = await api.get(`/api/zones/${zoneId}/grow-cycle`)
    const growCycleId = cycleResponse.data?.data?.id

    if (!growCycleId) {
      logger.warn(`[CommandPalette] No active grow cycle in zone "${zoneName}"`)
      close()
      return
    }

    if (action === 'pause') {
      await api.post(`/api/grow-cycles/${growCycleId}/pause`, {})
      logger.info(`[CommandPalette] Цикл в зоне "${zoneName}" приостановлен`)
    } else if (action === 'resume') {
      await api.post(`/api/grow-cycles/${growCycleId}/resume`, {})
      logger.info(`[CommandPalette] Цикл в зоне "${zoneName}" возобновлен`)
    } else if (action === 'next-phase') {
      await api.post(`/api/grow-cycles/${growCycleId}/advance-phase`, {})
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
 * @deprecated После рефакторинга циклы управляются через GrowCycle API.
 * Эта функция оставлена для обратной совместимости с ручными командами.
 */
async function executeZoneCycle(zoneId: number, cycleType: CommandCycleType, zoneName: string): Promise<void> {
  try {
    const commandType = `FORCE_${cycleType}` as CommandType
    const cycleNames: Record<string, string> = {
      'IRRIGATION': 'Полив',
      'PH_CONTROL': 'Коррекция pH',
      'EC_CONTROL': 'Коррекция EC',
      'CLIMATE': 'Управление климатом',
      'LIGHTING': 'Управление освещением'
    }
    const cycleName = cycleNames[cycleType] || cycleType

    const params = await resolveCycleParams(zoneId, cycleType)
    if (!params) {
      openActionModalForCycle(zoneId, cycleType)
      close()
      return
    }

    await sendZoneCommand(zoneId, commandType, params)
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
function openGrowCycleWizardForZone(zoneId: number, recipeId: number, zoneName: string, recipeName: string): void {
  const query = `?start_cycle=1&recipe_id=${recipeId}`
  logger.info(`[CommandPalette] Open grow cycle wizard for zone "${zoneName}" (recipe: "${recipeName}")`)
  safeVisit(`/zones/${zoneId}${query}`)
  close()
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

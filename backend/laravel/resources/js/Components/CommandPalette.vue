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
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { router, usePage } from '@inertiajs/vue3'
import { logger } from '@/utils/logger'
import { useApi } from '@/composables/useApi'
import { useCommands } from '@/composables/useCommands'
import { useRole } from '@/composables/useRole'
import { type CommandActionType, type CommandCycleType, type CommandHistoryItem, type CommandItem } from '@/commands/registry'
import { useCommandPaletteSearch } from '@/composables/useCommandPaletteSearch'
import ConfirmModal from '@/Components/ConfirmModal.vue'
import ZoneActionModal from '@/Components/ZoneActionModal.vue'
import type { CommandParams, CommandType } from '@/types'

interface ConfirmModalState {
  open: boolean
  title: string
  message: string
  action: (() => void | Promise<void>) | null
}

const page = usePage()
const { api } = useApi()
const { sendZoneCommand } = useCommands()
const { role } = useRole()

const open = ref<boolean>(false)
const inputRef = ref<HTMLInputElement | null>(null)
const commandHistory = ref<CommandHistoryItem[]>([])
const maxHistorySize = 10
const visitTimers = new Map<string, ReturnType<typeof setTimeout>>()
const VISIT_DEBOUNCE_MS = 300

const confirmModal = ref<ConfirmModalState>({
  open: false,
  title: '',
  message: '',
  action: null,
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

const targetsCache = new Map<number, unknown>()
const currentZoneId = computed(() => {
  const props = page.props as Record<string, unknown>
  const zone = props.zone as { id?: number } | undefined
  return zone?.id ?? (props.zoneId as number | null | undefined) ?? null
})
const currentPhaseTargets = computed(() => {
  const props = page.props as Record<string, unknown>
  const currentPhase = props.current_phase as { targets?: unknown } | undefined
  return currentPhase?.targets ?? null
})
const legacyTargets = computed(() => {
  const props = page.props as Record<string, unknown>
  return props.targets ?? null
})

function safeVisit(url: string, options: { preserveUrl?: boolean } = {}): void {
  const currentUrl = page.url || window.location.pathname
  const targetUrl = url.startsWith('/') ? url : `/${url}`
  if (currentUrl === targetUrl) {
    return
  }

  const existingTimer = visitTimers.get(targetUrl)
  if (existingTimer) {
    clearTimeout(existingTimer)
  }

  visitTimers.set(targetUrl, setTimeout(() => {
    visitTimers.delete(targetUrl)
    router.visit(targetUrl, { preserveUrl: options.preserveUrl ?? true })
  }, VISIT_DEBOUNCE_MS))
}

function loadHistory(): void {
  try {
    const stored = localStorage.getItem('commandPaletteHistory')
    if (stored) {
      commandHistory.value = JSON.parse(stored).slice(0, maxHistorySize)
    }
  } catch (err) {
    logger.error('[CommandPalette] Failed to load history:', err)
  }
}

function saveToHistory(item: CommandItem): void {
  if (item.type !== 'nav' && item.type !== 'action') {
    return
  }
  const historyItem = {
    label: item.label,
    timestamp: Date.now(),
    action: item.type,
  }
  commandHistory.value = commandHistory.value.filter(h => h.label !== item.label)
  commandHistory.value.unshift(historyItem)
  commandHistory.value = commandHistory.value.slice(0, maxHistorySize)
  try {
    localStorage.setItem('commandPaletteHistory', JSON.stringify(commandHistory.value))
  } catch (err) {
    logger.error('[CommandPalette] Failed to save history:', err)
  }
}

function normalizeTargets(payload: unknown): Record<string, unknown> | null {
  if (!payload || typeof payload !== 'object') return null
  const raw = payload as Record<string, unknown>
  if (raw.targets && typeof raw.targets === 'object') {
    return raw.targets as Record<string, unknown>
  }
  return raw
}

function resolveTargetValue(target: unknown): number | null {
  if (target === null || target === undefined) return null
  if (typeof target === 'number') return target
  if (typeof target !== 'object') return null
  const targetRecord = target as Record<string, unknown>
  if (typeof targetRecord.target === 'number') return targetRecord.target
  const min = typeof targetRecord.min === 'number' ? targetRecord.min : null
  const max = typeof targetRecord.max === 'number' ? targetRecord.max : null
  if (min !== null && max !== null) return (min + max) / 2
  return min ?? max
}

function resolveIrrigationDuration(targets: Record<string, unknown> | null): number | null {
  if (!targets) return null
  const irrigation = targets.irrigation as Record<string, unknown> | undefined
  const candidates = [
    irrigation?.duration_sec,
    irrigation?.duration_seconds,
    targets.irrigation_duration_sec,
    targets.irrigation_duration_seconds,
  ]
  const match = candidates.find((value) => typeof value === 'number')
  return typeof match === 'number' ? match : null
}

async function resolveCycleParams(zoneId: number, cycleType: CommandCycleType): Promise<CommandParams | null> {
  let targets: Record<string, unknown> | null = null

  if (currentZoneId.value === zoneId) {
    targets = normalizeTargets(currentPhaseTargets.value) || normalizeTargets(legacyTargets.value)
  } else if (targetsCache.has(zoneId)) {
    targets = normalizeTargets(targetsCache.get(zoneId))
  } else {
    try {
      const response = await api.get(`/api/zones/${zoneId}/effective-targets`)
      const responseData = response.data as { data?: unknown } | undefined
      const payload = responseData?.data ?? null
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
    const ph = targets.ph
    const phTarget = resolveTargetValue(typeof ph === 'undefined' ? { min: targets.ph_min, max: targets.ph_max } : ph)
    return phTarget !== null ? { target_ph: phTarget } : null
  }

  if (cycleType === 'EC_CONTROL') {
    const ec = targets.ec
    const ecTarget = resolveTargetValue(typeof ec === 'undefined' ? { min: targets.ec_min, max: targets.ec_max } : ec)
    return ecTarget !== null ? { target_ec: ecTarget } : null
  }

  return null
}

function openActionModalForCycle(zoneId: number, cycleType: CommandCycleType): void {
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

function closeActionModal(): void {
  actionModal.value.open = false
  actionModal.value.zoneId = null
  actionModal.value.defaultParams = {}
}

async function onActionModalSubmit({
  actionType,
  params,
}: { actionType: CommandType; params: CommandParams }): Promise<void> {
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
    const responseData = cycleResponse.data as { data?: { id?: number } } | undefined
    const growCycleId = responseData?.data?.id

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

async function executeZoneCycle(zoneId: number, cycleType: CommandCycleType, zoneName: string): Promise<void> {
  try {
    const commandType = `FORCE_${cycleType}` as CommandType
    const cycleNames: Record<string, string> = {
      IRRIGATION: 'Полив',
      PH_CONTROL: 'Коррекция pH',
      EC_CONTROL: 'Коррекция EC',
      CLIMATE: 'Управление климатом',
      LIGHTING: 'Управление освещением',
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

function openGrowCycleWizardForZone(zoneId: number, recipeId: number, zoneName: string, recipeName: string): void {
  const query = `?start_cycle=1&recipe_id=${recipeId}`
  logger.info(`[CommandPalette] Open grow cycle wizard for zone "${zoneName}" (recipe: "${recipeName}")`)
  safeVisit(`/zones/${zoneId}${query}`)
  close()
}

const {
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
} = useCommandPaletteSearch({
  api,
  role,
  history: commandHistory,
  handlers: {
    navigate: safeVisit,
    zoneAction: executeZoneAction,
    zoneCycle: executeZoneCycle,
    openGrowCycleWizard: openGrowCycleWizardForZone,
  },
})

function run(item: CommandItem | undefined): void {
  if (!item) return
  saveToHistory(item)

  if (item.requiresConfirm && item.actionFn) {
    const actionNames: Record<string, string> = {
      pause: 'приостановить',
      irrigate: 'полить',
      'ph-control': 'запустить коррекцию pH',
      'ec-control': 'запустить коррекцию EC',
      climate: 'запустить управление климатом',
      lighting: 'запустить управление освещением',
      'next-phase': 'перейти к следующей фазе',
      resume: 'возобновить',
      'open-cycle-wizard': 'открыть мастер цикла',
    }
    const actionName = actionNames[item.actionType || ''] || 'выполнить это действие'
    const zoneName = item.zoneName ? ` для зоны "${item.zoneName}"` : ''
    confirmModal.value = {
      open: true,
      title: 'Подтверждение действия',
      message: `Вы уверены, что хотите ${actionName}${zoneName}?`,
      action: item.actionFn,
    }
    return
  }

  if (item.actionFn) {
    item.actionFn()
  } else {
    item.action?.()
  }
  close()
}

function runSelected(): void {
  if (!commandItems.value.length) {
    return
  }
  if (selectedItem.value) {
    run(selectedItem.value)
  }
}

function confirmAction(): void {
  if (confirmModal.value.action) {
    confirmModal.value.action()
  }
  confirmModal.value.open = false
  close()
}

function close(): void {
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

function onKey(e: KeyboardEvent): void {
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

onUnmounted(() => {
  window.removeEventListener('keydown', onKey)
  visitTimers.forEach((timer) => clearTimeout(timer))
  visitTimers.clear()
})
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

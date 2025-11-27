<template>
  <AppLayout>
    <!-- Toast notifications -->
    <Teleport to="body">
      <div 
        class="fixed top-4 right-4 z-[10000] space-y-2 pointer-events-none"
        style="position: fixed !important; top: 1rem !important; right: 1rem !important; z-index: 10000 !important; pointer-events: none;"
      >
        <div
          v-for="toast in toasts"
          :key="toast.id"
          class="pointer-events-auto"
          style="pointer-events: auto;"
        >
          <Toast
            :message="toast.message"
            :variant="toast.variant"
            :duration="toast.duration"
            @close="removeToast(toast.id)"
          />
        </div>
      </div>
    </Teleport>
    
    <div class="flex flex-col gap-3">
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div class="flex-1 min-w-0">
          <div class="text-lg font-semibold truncate">{{ zone.name }}</div>
          <div class="text-xs text-neutral-400 mt-1">
            <span v-if="zone.description" class="block sm:inline">{{ zone.description }}</span>
            <span v-if="zone.recipeInstance?.recipe" class="block sm:inline sm:ml-1">
              <span v-if="zone.description" class="hidden sm:inline">·</span>
              Рецепт: {{ zone.recipeInstance.recipe.name }}
              <span v-if="zone.recipeInstance.current_phase_index !== null">
                (фаза {{ zone.recipeInstance.current_phase_index + 1 }})
              </span>
            </span>
          </div>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <Badge :variant="variant" class="shrink-0">{{ translateStatus(zone.status) }}</Badge>
          <template v-if="page.props.auth?.user?.role === 'admin' || page.props.auth?.user?.role === 'operator'">
            <Button size="sm" variant="secondary" @click="onToggle" :disabled="loading.toggle" class="flex-1 sm:flex-none min-w-[120px]">
              <template v-if="loading.toggle">
                <LoadingState loading size="sm" :container-class="'inline-flex mr-2'" />
              </template>
              <span class="hidden sm:inline">{{ zone.status === 'PAUSED' ? 'Возобновить' : 'Приостановить' }}</span>
              <span class="sm:hidden">{{ zone.status === 'PAUSED' ? '▶' : '⏸' }}</span>
            </Button>
            <Button size="sm" variant="outline" @click="openActionModal('FORCE_IRRIGATION')" :disabled="loading.irrigate" class="flex-1 sm:flex-none">
              <template v-if="loading.irrigate">
                <LoadingState loading size="sm" :container-class="'inline-flex mr-2'" />
              </template>
              <span class="hidden sm:inline">Полить сейчас</span>
              <span class="sm:hidden">💧</span>
            </Button>
            <Button size="sm" @click="onNextPhase" :disabled="loading.nextPhase" class="flex-1 sm:flex-none">
              <template v-if="loading.nextPhase">
                <LoadingState loading size="sm" :container-class="'inline-flex mr-2'" />
              </template>
              <span class="hidden sm:inline">Следующая фаза</span>
              <span class="sm:hidden">⏭</span>
            </Button>
          </template>
          <Button size="sm" variant="outline" @click="showSimulationModal = true" class="flex-1 sm:flex-none">
            <span class="hidden sm:inline">Симуляция</span>
            <span class="sm:hidden">🧪</span>
          </Button>
        </div>
      </div>

      <!-- Target vs Actual (основная метрика зоны) -->
      <ZoneTargets :telemetry="telemetry" :targets="targets" />

      <!-- Прогресс фазы рецепта -->
      <PhaseProgress
        v-if="zone.recipeInstance"
        :recipe-instance="zone.recipeInstance"
        :phase-progress="computedPhaseProgress"
        :phase-days-elapsed="computedPhaseDaysElapsed"
        :phase-days-total="computedPhaseDaysTotal"
      />

      <div class="grid grid-cols-1 xl:grid-cols-3 gap-3">
        <div class="xl:col-span-2 space-y-3">
          <!-- Мульти-серии график pH + EC -->
          <MultiSeriesTelemetryChart
            v-if="chartDataPh.length > 0 || chartDataEc.length > 0"
            title="pH и EC"
            :series="multiSeriesData"
            :time-range="chartTimeRange"
            @time-range-change="onChartTimeRangeChange"
          />
          <!-- Отдельные графики как fallback или опционально -->
          <div v-if="showSeparateCharts" class="space-y-3">
            <ZoneTelemetryChart 
              title="pH" 
              :data="chartDataPh" 
              series-name="pH"
              :time-range="chartTimeRange"
              @time-range-change="onChartTimeRangeChange"
            />
            <ZoneTelemetryChart 
              title="EC" 
              :data="chartDataEc" 
              series-name="EC"
              :time-range="chartTimeRange"
              @time-range-change="onChartTimeRangeChange"
            />
          </div>
        </div>
        <!-- Визуализация устройств зоны -->
        <ZoneDevicesVisualization
          :zone-name="zone.name"
          :zone-status="zone.status"
          :devices="devices"
          :can-manage="page.props.auth?.user?.role === 'admin' || page.props.auth?.user?.role === 'operator'"
          @attach="showAttachNodesModal = true"
          @configure="(device) => openNodeConfig(device.id, device)"
        />
        
        <!-- Рецепт зоны -->
        <Card>
          <div class="flex items-center justify-between mb-2">
            <div class="text-sm font-semibold">Рецепт</div>
            <template v-if="page.props.auth?.user?.role === 'admin' || page.props.auth?.user?.role === 'operator'">
              <Button
                size="sm"
                :variant="zone.recipeInstance?.recipe ? 'secondary' : 'primary'"
                @click="showAttachRecipeModal = true"
              >
                {{ zone.recipeInstance?.recipe ? 'Изменить рецепт' : 'Привязать рецепт' }}
              </Button>
            </template>
          </div>
          <div v-if="zone.recipeInstance?.recipe" class="text-sm text-neutral-300">
            <div class="font-semibold">{{ zone.recipeInstance.recipe.name }}</div>
            <div class="text-xs text-neutral-400">
              Фаза {{ (zone.recipeInstance.current_phase_index || 0) + 1 }} из {{ zone.recipeInstance.recipe.phases?.length || 0 }}
              <span v-if="zone.recipeInstance.current_phase_name">
                — {{ zone.recipeInstance.current_phase_name }}
              </span>
            </div>
          </div>
          <div v-else class="space-y-2">
            <div class="text-sm text-neutral-400">
              Рецепт не привязан
              <span v-if="zone.recipeInstance && !zone.recipeInstance.recipe" class="text-red-400 text-xs block mt-1">
                DEBUG: recipeInstance существует (id={{ zone.recipeInstance.id }}, recipe_id={{ zone.recipeInstance.recipe_id }}), но recipe не загружен!
              </span>
            </div>
            <template v-if="page.props.auth?.user?.role === 'admin' || page.props.auth?.user?.role === 'operator'">
              <div class="text-xs text-neutral-500">
                Привяжите рецепт для автоматического управления фазами выращивания
              </div>
            </template>
          </div>
        </Card>
      </div>

      <!-- Cycles (расписание подсистем) -->
      <Card>
        <div class="text-sm font-semibold mb-3">Циклы</div>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-3">
          <div v-for="cycle in cyclesList" :key="cycle.type" class="text-xs text-neutral-400 p-3 rounded border border-neutral-800 bg-neutral-925 hover:border-neutral-700 transition-colors">
            <div class="font-semibold text-sm mb-2 text-neutral-200">{{ translateCycleType(cycle.type) }}</div>
            <div class="text-xs mb-1">Стратегия: {{ translateStrategy(cycle.strategy || 'periodic') }}</div>
            <div class="text-xs mb-2">Интервал: {{ cycle.interval ? formatInterval(cycle.interval) : 'Не настроено' }}</div>
            
            <!-- Последний запуск с индикатором -->
            <div class="mb-2">
              <div class="text-xs text-neutral-500 mb-1">Последний запуск:</div>
              <div class="flex items-center gap-2">
                <div v-if="cycle.last_run" class="w-2 h-2 rounded-full bg-emerald-400"></div>
                <div v-else class="w-2 h-2 rounded-full bg-neutral-600"></div>
                <span class="text-xs text-neutral-300">{{ formatTimeShort(cycle.last_run) }}</span>
              </div>
            </div>
            
            <!-- Следующий запуск с прогресс-баром -->
            <div class="mb-2">
              <div class="text-xs text-neutral-500 mb-1">Следующий запуск:</div>
              <div v-if="cycle.next_run" class="space-y-1">
                <div class="flex items-center gap-2">
                  <div class="w-2 h-2 rounded-full bg-amber-400 animate-pulse"></div>
                  <span class="text-xs text-neutral-300">{{ formatTimeShort(cycle.next_run) }}</span>
                </div>
                <!-- Прогресс-бар до следующего запуска -->
                <div v-if="cycle.last_run && cycle.interval" class="w-full h-1.5 bg-neutral-800 rounded-full overflow-hidden">
                  <div 
                    class="h-full bg-amber-400 transition-all duration-300"
                    :style="{ width: `${getProgressToNextRun(cycle)}%` }"
                  ></div>
                </div>
                <div v-if="cycle.last_run && cycle.interval" class="text-xs text-neutral-500">
                  {{ getTimeUntilNextRun(cycle) }}
                </div>
              </div>
              <div v-else class="text-xs text-neutral-500">Не запланирован</div>
            </div>
            
            <Button 
              size="sm" 
              variant="secondary" 
              class="mt-2 w-full text-xs" 
              @click="onRunCycle(cycle.type)"
              :disabled="loading.cycles[cycle.type]"
            >
              <template v-if="loading.cycles[cycle.type]">
                <LoadingState loading size="sm" :container-class="'inline-flex mr-2'" />
              </template>
              {{ loading.cycles[cycle.type] ? 'Запуск...' : 'Запустить сейчас' }}
            </Button>
            
            <!-- Индикатор статуса последней команды -->
            <div v-if="getLastCommandStatus(cycle.type)" class="mt-2 text-xs">
              <div class="flex items-center gap-1">
                <div 
                  class="w-1.5 h-1.5 rounded-full"
                  :class="{
                    'bg-amber-400 animate-pulse': getLastCommandStatus(cycle.type) === 'pending' || getLastCommandStatus(cycle.type) === 'executing',
                    'bg-emerald-400': getLastCommandStatus(cycle.type) === 'completed',
                    'bg-red-400': getLastCommandStatus(cycle.type) === 'failed'
                  }"
                ></div>
                <span class="text-neutral-500">
                  {{ getCommandStatusText(getLastCommandStatus(cycle.type)) }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </Card>

      <!-- Automation Engine -->
      <AutomationEngine :zone-id="zoneId" />

      <!-- Events (история событий) -->
      <Card>
        <div class="text-sm font-semibold mb-2">События</div>
        <div v-if="events.length > 0" class="space-y-1 max-h-[400px] overflow-y-auto">
          <div
            v-for="e in events"
            :key="e.id"
            class="text-sm text-neutral-300 flex items-start gap-2 py-1 border-b border-neutral-800 last:border-0"
          >
            <Badge
              :variant="
                e.kind === 'ALERT' ? 'danger' :
                e.kind === 'WARNING' ? 'warning' :
                e.kind === 'INFO' ? 'info' : 'neutral'
              "
              class="text-xs shrink-0"
            >
              {{ translateEventKind(e.kind) }}
            </Badge>
            <div class="flex-1 min-w-0">
              <div class="text-xs text-neutral-400">
                {{ new Date(e.occurred_at).toLocaleString('ru-RU') }}
              </div>
              <div class="text-sm">{{ e.message }}</div>
            </div>
          </div>
        </div>
        <div v-else class="text-sm text-neutral-400">Нет событий</div>
      </Card>
    </div>
    
    <!-- Digital Twin Simulation Modal -->
    <ZoneSimulationModal
      :show="showSimulationModal"
      :zone-id="zoneId"
      :default-recipe-id="zone.recipeInstance?.recipe_id"
      @close="showSimulationModal = false"
    />
    
    <!-- Модальное окно для действий с параметрами -->
    <ZoneActionModal
      v-if="showActionModal"
      :show="showActionModal"
      :action-type="currentActionType"
      :zone-id="zoneId"
      @close="showActionModal = false"
      @submit="onActionSubmit"
    />
    
    <!-- Модальное окно привязки рецепта -->
    <AttachRecipeModal
      v-if="showAttachRecipeModal"
      :show="showAttachRecipeModal"
      :zone-id="zoneId"
      @close="showAttachRecipeModal = false"
      @attached="onRecipeAttached"
    />
    
    <!-- Модальное окно привязки узлов -->
    <AttachNodesModal
      v-if="showAttachNodesModal"
      :show="showAttachNodesModal"
      :zone-id="zoneId"
      @close="showAttachNodesModal = false"
      @attached="onNodesAttached"
    />
    
    <!-- Модальное окно настройки узла -->
    <NodeConfigModal
      v-if="showNodeConfigModal && selectedNodeId"
      :show="showNodeConfigModal"
      :node-id="selectedNodeId"
      :node="selectedNode"
      @close="showNodeConfigModal = false"
      @published="onNodeConfigPublished"
    />
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, onUnmounted, ref, watch } from 'vue'
import { Link, usePage, router } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import Badge from '@/Components/Badge.vue'
import { useHistory } from '@/composables/useHistory'
import ZoneTargets from '@/Components/ZoneTargets.vue'
import PhaseProgress from '@/Components/PhaseProgress.vue'
import ZoneDevicesVisualization from '@/Components/ZoneDevicesVisualization.vue'
import Toast from '@/Components/Toast.vue'
import LoadingState from '@/Components/LoadingState.vue'
import ZoneSimulationModal from '@/Components/ZoneSimulationModal.vue'
import ZoneActionModal from '@/Components/ZoneActionModal.vue'
import AttachRecipeModal from '@/Components/AttachRecipeModal.vue'
import AttachNodesModal from '@/Components/AttachNodesModal.vue'
import NodeConfigModal from '@/Components/NodeConfigModal.vue'
import AutomationEngine from '@/Components/AutomationEngine.vue'
import { translateStatus, translateEventKind, translateCycleType, translateStrategy } from '@/utils/i18n'
import { formatTimeShort, formatInterval } from '@/utils/formatTime'
import { logger } from '@/utils/logger'

// Безопасные обёртки для логирования
const logInfo = logger?.info || ((...args: unknown[]) => console.log('[INFO]', ...args))
const logError = logger?.error || ((...args: unknown[]) => console.error('[ERROR]', ...args))
const logWarn = logger?.warn || ((...args: unknown[]) => console.warn('[WARN]', ...args))
const logLog = logger?.log || ((...args: unknown[]) => console.log('[LOG]', ...args))
import { useCommands } from '@/composables/useCommands'
import { useTelemetry } from '@/composables/useTelemetry'
import { useZones } from '@/composables/useZones'
import { useApi } from '@/composables/useApi'
import { useWebSocket } from '@/composables/useWebSocket'
import { useErrorHandler } from '@/composables/useErrorHandler'
import { useOptimisticUpdate, createOptimisticZoneUpdate } from '@/composables/useOptimisticUpdate'
import { useZonesStore } from '@/stores/zones'
import { useOptimizedUpdates, useTelemetryBatch } from '@/composables/useOptimizedUpdates'
import type { Zone, Device, ZoneTelemetry, ZoneTargets as ZoneTargetsType, Cycle, CommandType } from '@/types'
import type { ZoneEvent } from '@/types/ZoneEvent'
import type { ToastVariant } from '@/composables/useToast'

const ZoneTelemetryChart = defineAsyncComponent(() => import('@/Pages/Zones/ZoneTelemetryChart.vue'))
const MultiSeriesTelemetryChart = defineAsyncComponent(() => import('@/Components/MultiSeriesTelemetryChart.vue'))

interface PageProps {
  zone?: Zone
  zoneId?: number
  telemetry?: ZoneTelemetry
  targets?: ZoneTargetsType
  devices?: Device[]
  events?: ZoneEvent[]
  cycles?: Record<string, Cycle>
  auth?: {
    user?: {
      role?: string
    }
  }
}

const page = usePage<PageProps>()

interface ToastItem {
  id: number
  message: string
  variant: ToastVariant
  duration: number
}

// Toast notifications
const toasts = ref<ToastItem[]>([])
let toastIdCounter = 0

// Simulation modal
const showSimulationModal = ref<boolean>(false)
const showActionModal = ref<boolean>(false)
const currentActionType = ref<CommandType>('FORCE_IRRIGATION')
const showAttachRecipeModal = ref<boolean>(false)
const showAttachNodesModal = ref<boolean>(false)
const showNodeConfigModal = ref<boolean>(false)
const selectedNodeId = ref<number | null>(null)
const selectedNode = ref<any>(null)

// Loading states
interface LoadingState {
  toggle: boolean
  irrigate: boolean
  nextPhase: boolean
  cycles: Record<string, boolean>
}

const loading = ref<LoadingState>({
  toggle: false,
  irrigate: false,
  nextPhase: false,
  cycles: {
    PH_CONTROL: false,
    EC_CONTROL: false,
    IRRIGATION: false,
    LIGHTING: false,
    CLIMATE: false,
  },
})

function showToast(message: string, variant: ToastVariant = 'info', duration: number = 3000): number {
  const id = ++toastIdCounter
  toasts.value.push({ id, message, variant, duration })
  return id
}

// Инициализация composables с Toast (после определения showToast)
const { sendZoneCommand, reloadZoneAfterCommand, updateCommandStatus, pendingCommands } = useCommands(showToast)
const { fetchHistory } = useTelemetry(showToast)
const { reloadZone } = useZones(showToast)
const { api } = useApi(showToast)
const { subscribeToZoneCommands } = useWebSocket(showToast)
const { handleError } = useErrorHandler(showToast)
const { performUpdate } = useOptimisticUpdate()
const zonesStore = useZonesStore()

function removeToast(id: number): void {
  const index = toasts.value.findIndex(t => t.id === id)
  if (index > -1) {
    toasts.value.splice(index, 1)
  }
}
const zone = computed(() => {
  const rawZoneData = (page.props.zone || {}) as any
  
  // Нормализуем snake_case в camelCase для recipe_instance
  // Laravel/Inertia может отправлять данные в snake_case, а фронтенд ожидает camelCase
  const zoneData = { ...rawZoneData }
  if (zoneData.recipe_instance && !zoneData.recipeInstance) {
    zoneData.recipeInstance = zoneData.recipe_instance
  }
  
  return zoneData as Zone
})
const zoneId = computed(() => {
  const id = zone.value.id || page.props.zoneId
  return typeof id === 'string' ? parseInt(id) : id
})

// История просмотров
const { addToHistory } = useHistory()

// Добавляем зону в историю просмотров
watch(zone, (newZone) => {
  if (newZone?.id) {
    addToHistory({
      id: newZone.id,
      type: 'zone',
      name: newZone.name || `Зона ${newZone.id}`,
      url: `/zones/${newZone.id}`
    })
  }
}, { immediate: true })

// Телеметрия, цели и устройства из props
// Оптимизированное обновление телеметрии
const telemetryRef = ref<ZoneTelemetry>(page.props.telemetry || { ph: null, ec: null, temperature: null, humidity: null } as ZoneTelemetry)

// Используем batch updates для оптимизации частых обновлений телеметрии
const { addUpdate, flush } = useTelemetryBatch((updates) => {
  // Применяем обновления пакетом
  const currentZoneId = zoneId.value
  updates.forEach((metrics, zoneIdStr) => {
    if (zoneIdStr === String(currentZoneId)) {
      const current = { ...telemetryRef.value }
      metrics.forEach((value, metric) => {
        switch (metric) {
          case 'ph':
            current.ph = value
            break
          case 'ec':
            current.ec = value
            break
          case 'temperature':
            current.temperature = value
            break
          case 'humidity':
            current.humidity = value
            break
        }
      })
      telemetryRef.value = current
    }
  })
}, 200) // Debounce 200ms для телеметрии

const telemetry = computed(() => telemetryRef.value)
const targets = computed(() => (page.props.targets || {}) as ZoneTargetsType)
const devices = computed(() => (page.props.devices || []) as Device[])
const events = computed(() => (page.props.events || []) as ZoneEvent[])
const cycles = computed(() => (page.props.cycles || {}) as Record<string, Cycle>)

// Вычисление прогресса фазы рецепта
const computedPhaseProgress = computed(() => {
  const instance = zone.value.recipeInstance
  if (!instance || !instance.recipe?.phases || instance.current_phase_index === null) return null
  
  const currentPhase = instance.recipe.phases.find(p => p.phase_index === instance.current_phase_index)
  if (!currentPhase || !currentPhase.duration_hours || !instance.started_at) return null
  
  // Вычисляем кумулятивное время начала текущей фазы
  let phaseStartCumulative = 0
  for (const phase of instance.recipe.phases) {
    if (phase.phase_index < instance.current_phase_index) {
      phaseStartCumulative += phase.duration_hours || 0
    } else {
      break
    }
  }
  
  // Вычисляем прошедшее время с начала рецепта
  const startedAt = new Date(instance.started_at)
  const now = new Date()
  const elapsedHours = (now.getTime() - startedAt.getTime()) / (1000 * 60 * 60)
  if (elapsedHours < 0) return 0
  
  // Вычисляем время в текущей фазе
  const timeInPhaseHours = elapsedHours - phaseStartCumulative
  if (timeInPhaseHours < 0) return 0
  
  // Вычисляем прогресс (0-100%)
  const progress = (timeInPhaseHours / currentPhase.duration_hours) * 100
  return Math.min(100, Math.max(0, progress))
})

const computedPhaseDaysElapsed = computed(() => {
  const instance = zone.value.recipeInstance
  if (!instance || !instance.recipe?.phases || instance.current_phase_index === null) return null
  
  const currentPhase = instance.recipe.phases.find(p => p.phase_index === instance.current_phase_index)
  if (!currentPhase || !currentPhase.duration_hours || !instance.started_at) return null
  
  // Вычисляем кумулятивное время начала текущей фазы
  let phaseStartCumulative = 0
  for (const phase of instance.recipe.phases) {
    if (phase.phase_index < instance.current_phase_index) {
      phaseStartCumulative += phase.duration_hours || 0
    } else {
      break
    }
  }
  
  const startedAt = new Date(instance.started_at)
  const now = new Date()
  const elapsedHours = (now.getTime() - startedAt.getTime()) / (1000 * 60 * 60)
  const timeInPhaseHours = Math.max(0, elapsedHours - phaseStartCumulative)
  
  return Math.floor(timeInPhaseHours / 24)
})

const computedPhaseDaysTotal = computed(() => {
  const instance = zone.value.recipeInstance
  if (!instance || !instance.recipe?.phases || instance.current_phase_index === null) return null
  
  const currentPhase = instance.recipe.phases.find(p => p.phase_index === instance.current_phase_index)
  if (!currentPhase || !currentPhase.duration_hours) return null
  
  return Math.ceil(currentPhase.duration_hours / 24)
})

// Список циклов для отображения
const cyclesList = computed(() => {
  const defaultCycles = [
    { type: 'PH_CONTROL', strategy: 'periodic', interval: 300 },
    { type: 'EC_CONTROL', strategy: 'periodic', interval: 300 },
    { type: 'IRRIGATION', strategy: 'periodic', interval: targets.value.irrigation_interval_sec || null },
    { type: 'LIGHTING', strategy: 'periodic', interval: targets.value.light_hours ? targets.value.light_hours * 3600 : null },
    { type: 'CLIMATE', strategy: 'periodic', interval: 300 },
  ]
  
  return defaultCycles.map(cycle => ({
    ...cycle,
    ...(cycles.value[cycle.type] || {}),
    last_run: cycles.value[cycle.type]?.last_run || null,
    next_run: cycles.value[cycle.type]?.next_run || null,
  }))
})

// Функции для вычисления прогресса до следующего запуска
function getProgressToNextRun(cycle: Cycle & { last_run?: string | null; next_run?: string | null; interval?: number | null }): number {
  if (!cycle.last_run || !cycle.next_run || !cycle.interval) return 0
  
  const now = new Date().getTime()
  const lastRun = new Date(cycle.last_run).getTime()
  const nextRun = new Date(cycle.next_run).getTime()
  
  if (now >= nextRun) return 100
  if (now <= lastRun) return 0
  
  const total = nextRun - lastRun
  const elapsed = now - lastRun
  return Math.min(100, Math.max(0, (elapsed / total) * 100))
}

function getTimeUntilNextRun(cycle: Cycle & { next_run?: string | null }): string {
  if (!cycle.next_run) return ''
  
  const now = new Date().getTime()
  const nextRun = new Date(cycle.next_run).getTime()
  const diff = nextRun - now
  
  if (diff <= 0) return 'Просрочено'
  
  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(minutes / 60)
  const days = Math.floor(hours / 24)
  
  if (days > 0) return `Через ${days} дн.`
  if (hours > 0) return `Через ${hours} ч.`
  if (minutes > 0) return `Через ${minutes} мин.`
  return 'Скоро'
}

// Функции для отображения статуса команд
function getLastCommandStatus(cycleType: string): string | null {
  const commandType = `FORCE_${cycleType}` as CommandType
  const command = pendingCommands.value.find(cmd => 
    cmd.type === commandType && 
    cmd.zoneId === zoneId.value &&
    (cmd.status === 'pending' || cmd.status === 'executing' || cmd.status === 'completed' || cmd.status === 'failed')
  )
  return command?.status || null
}

function getCommandStatusText(status: string | null): string {
  if (!status) return ''
  const texts: Record<string, string> = {
    'pending': 'Ожидание...',
    'executing': 'Выполняется...',
    'completed': 'Выполнено',
    'failed': 'Ошибка'
  }
  return texts[status] || status
}

// Графики: загрузка данных истории
const chartTimeRange = ref<'1H' | '24H' | '7D' | '30D' | 'ALL'>('24H')
const chartDataPh = ref<Array<{ ts: number; value: number }>>([])
const chartDataEc = ref<Array<{ ts: number; value: number }>>([])
const showSeparateCharts = ref(false) // Опция для показа отдельных графиков

// Мульти-серии данные для комбинированного графика
const multiSeriesData = computed(() => {
  return [
    {
      name: 'ph',
      label: 'pH',
      color: '#3b82f6', // blue-500
      data: chartDataPh.value,
      currentValue: telemetry.value.ph,
      yAxisIndex: 0,
    },
    {
      name: 'ec',
      label: 'EC',
      color: '#10b981', // emerald-500
      data: chartDataEc.value,
      currentValue: telemetry.value.ec,
      yAxisIndex: 1, // Используем правую ось Y для EC
    },
  ]
})

// Загрузка данных истории для графиков через useTelemetry
async function loadChartData(metric: 'PH' | 'EC', timeRange: string): Promise<Array<{ ts: number; value: number }>> {
  if (!zoneId.value) return []
  
  const now = new Date()
  let from: Date | null = null
  switch (timeRange) {
    case '1H':
      from = new Date(now.getTime() - 60 * 60 * 1000)
      break
    case '24H':
      from = new Date(now.getTime() - 24 * 60 * 60 * 1000)
      break
    case '7D':
      from = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)
      break
    case '30D':
      from = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000)
      break
    case 'ALL':
      from = null
      break
  }
  
  try {
    const params: { from?: string; to: string } = { to: now.toISOString() }
    if (from) params.from = from.toISOString()
    
    return await fetchHistory(zoneId.value, metric, params)
  } catch (err) {
    logError(`Failed to load ${metric} history:`, err)
    return []
  }
}

async function onChartTimeRangeChange(newRange: string): Promise<void> {
  chartTimeRange.value = newRange as '1H' | '24H' | '7D' | '30D' | 'ALL'
  chartDataPh.value = await loadChartData('PH', newRange)
  chartDataEc.value = await loadChartData('EC', newRange)
}

// Watch для отслеживания изменений zone props (отключен для производительности)
// watch(() => page.props.zone, (newZone: any, oldZone: any) => {
//   logInfo('[Zones/Show] Zone props changed')
// }, { deep: true, immediate: true })

onMounted(async () => {
  logLog('[Show.vue] Компонент смонтирован', { zoneId: zoneId.value })
  
  // Загрузить данные для графиков
  chartDataPh.value = await loadChartData('PH', chartTimeRange.value)
  chartDataEc.value = await loadChartData('EC', chartTimeRange.value)
  
  // Подписаться на WebSocket канал команд зоны
  if (zoneId.value) {
    subscribeToZoneCommands(zoneId.value, (commandEvent) => {
      // Обновляем статус команды через useCommands
      updateCommandStatus(commandEvent.commandId, commandEvent.status, commandEvent.message)
      
      // Если команда завершена, обновляем зону
      if (commandEvent.status === 'completed' || commandEvent.status === 'failed') {
        reloadZoneAfterCommand(zoneId.value, ['zone', 'cycles'])
      }
    })
  }
  
  // Автоматическая синхронизация через события stores
  const { useStoreEvents } = await import('@/composables/useStoreEvents')
  const { subscribeWithCleanup } = useStoreEvents()
  
  // Слушаем события обновления зоны для автоматического обновления
  subscribeWithCleanup('zone:updated', (updatedZone: any) => {
    if (updatedZone.id === zoneId.value) {
      // Если есть обновление телеметрии, применяем его оптимизированно
      if (updatedZone.telemetry) {
        const tel = updatedZone.telemetry
        if (tel.ph !== null && tel.ph !== undefined) {
          addUpdate(String(zoneId.value), 'ph', tel.ph)
        }
        if (tel.ec !== null && tel.ec !== undefined) {
          addUpdate(String(zoneId.value), 'ec', tel.ec)
        }
        if (tel.temperature !== null && tel.temperature !== undefined) {
          addUpdate(String(zoneId.value), 'temperature', tel.temperature)
        }
        if (tel.humidity !== null && tel.humidity !== undefined) {
          addUpdate(String(zoneId.value), 'humidity', tel.humidity)
        }
      } else {
        // Обновляем зону через Inertia partial reload только если нет телеметрии
        reloadZone(zoneId.value, ['zone'])
      }
    }
  })
  
  // Слушаем события присвоения рецепта к зоне
  subscribeWithCleanup('zone:recipe:attached', ({ zoneId: eventZoneId }: { zoneId: number; recipeId: number }) => {
    if (eventZoneId === zoneId.value) {
      // Обновляем зону при присвоении рецепта
      reloadZone(zoneId.value, ['zone'])
    }
  })
  
  // При размонтировании применяем все накопленные обновления телеметрии
  onUnmounted(() => {
    flush()
  })
})

/**
 * Получить параметры по умолчанию для команды цикла на основе targets/recipe
 */
function getDefaultCycleParams(cycleType: string): Record<string, unknown> {
  const params: Record<string, unknown> = {}
  
  switch (cycleType) {
    case 'IRRIGATION':
      // Используем длительность полива из targets или рецепта
      if (targets.value.irrigation_duration_sec) {
        params.duration_sec = targets.value.irrigation_duration_sec
      } else if (zone.value.recipeInstance?.recipe?.phases) {
        // Ищем текущую фазу рецепта
        const currentPhaseIndex = zone.value.recipeInstance.current_phase_index ?? 0
        const currentPhase = zone.value.recipeInstance.recipe.phases?.find(
          (p: { phase_index: number }) => p.phase_index === currentPhaseIndex
        )
        if (currentPhase?.targets?.irrigation_duration_sec) {
          params.duration_sec = currentPhase.targets.irrigation_duration_sec
        } else {
          // Значение по умолчанию, если не найдено
          params.duration_sec = 10
        }
      } else {
        params.duration_sec = 10
      }
      break
      
    case 'PH_CONTROL':
      // Используем целевой pH из targets или рецепта
      if (targets.value.ph?.min && targets.value.ph?.max) {
        params.target_ph = (targets.value.ph.min + targets.value.ph.max) / 2
      } else if (targets.value.ph) {
        params.target_ph = targets.value.ph
      } else if (zone.value.recipeInstance?.recipe?.phases) {
        const currentPhaseIndex = zone.value.recipeInstance.current_phase_index ?? 0
        const currentPhase = zone.value.recipeInstance.recipe.phases?.find(
          (p: { phase_index: number }) => p.phase_index === currentPhaseIndex
        )
        if (currentPhase?.targets?.ph?.min && currentPhase?.targets?.ph?.max) {
          params.target_ph = (currentPhase.targets.ph.min + currentPhase.targets.ph.max) / 2
        } else if (currentPhase?.targets?.ph) {
          params.target_ph = currentPhase.targets.ph
        } else {
          params.target_ph = 6.0
        }
      } else {
        params.target_ph = 6.0
      }
      break
      
    case 'EC_CONTROL':
      // Используем целевой EC из targets или рецепта
      if (targets.value.ec?.min && targets.value.ec?.max) {
        params.target_ec = (targets.value.ec.min + targets.value.ec.max) / 2
      } else if (targets.value.ec) {
        params.target_ec = targets.value.ec
      } else if (zone.value.recipeInstance?.recipe?.phases) {
        const currentPhaseIndex = zone.value.recipeInstance.current_phase_index ?? 0
        const currentPhase = zone.value.recipeInstance.recipe.phases?.find(
          (p: { phase_index: number }) => p.phase_index === currentPhaseIndex
        )
        if (currentPhase?.targets?.ec?.min && currentPhase?.targets?.ec?.max) {
          params.target_ec = (currentPhase.targets.ec.min + currentPhase.targets.ec.max) / 2
        } else if (currentPhase?.targets?.ec) {
          params.target_ec = currentPhase.targets.ec
        } else {
          params.target_ec = 1.5
        }
      } else {
        params.target_ec = 1.5
      }
      break
      
    case 'CLIMATE':
      // Используем целевые параметры климата из targets или рецепта
      if (targets.value.temp_air) {
        params.target_temp = targets.value.temp_air
      } else if (zone.value.recipeInstance?.recipe?.phases) {
        const currentPhaseIndex = zone.value.recipeInstance.current_phase_index ?? 0
        const currentPhase = zone.value.recipeInstance.recipe.phases?.find(
          (p: { phase_index: number }) => p.phase_index === currentPhaseIndex
        )
        if (currentPhase?.targets?.temp_air) {
          params.target_temp = currentPhase.targets.temp_air
        } else {
          params.target_temp = 22
        }
      } else {
        params.target_temp = 22
      }
      
      if (targets.value.humidity_air) {
        params.target_humidity = targets.value.humidity_air
      } else if (zone.value.recipeInstance?.recipe?.phases) {
        const currentPhaseIndex = zone.value.recipeInstance.current_phase_index ?? 0
        const currentPhase = zone.value.recipeInstance.recipe.phases?.find(
          (p: { phase_index: number }) => p.phase_index === currentPhaseIndex
        )
        if (currentPhase?.targets?.humidity_air) {
          params.target_humidity = currentPhase.targets.humidity_air
        } else {
          params.target_humidity = 60
        }
      } else {
        params.target_humidity = 60
      }
      break
      
    case 'LIGHTING':
      // Используем параметры освещения из targets или рецепта
      if (targets.value.light_hours) {
        params.duration_hours = targets.value.light_hours
      } else if (zone.value.recipeInstance?.recipe?.phases) {
        const currentPhaseIndex = zone.value.recipeInstance.current_phase_index ?? 0
        const currentPhase = zone.value.recipeInstance.recipe.phases?.find(
          (p: { phase_index: number }) => p.phase_index === currentPhaseIndex
        )
        if (currentPhase?.targets?.light_hours) {
          params.duration_hours = currentPhase.targets.light_hours
        } else {
          params.duration_hours = 12
        }
      } else {
        params.duration_hours = 12
      }
      
      params.intensity = 80 // Интенсивность по умолчанию
      break
  }
  
  return params
}

async function onRunCycle(cycleType: string): Promise<void> {
  if (!zoneId.value) {
    logWarn('[onRunCycle] zoneId is missing')
    showToast('Ошибка: зона не найдена', 'error', 3000)
    return
  }
  
  loading.value.cycles[cycleType] = true
  const cycleName = translateCycleType(cycleType)
  const commandType = `FORCE_${cycleType}` as CommandType
  
  // Получаем параметры по умолчанию из targets/recipe
  const defaultParams = getDefaultCycleParams(cycleType)
  
  logInfo(`[onRunCycle] Отправка команды ${commandType} для зоны ${zoneId.value} с параметрами:`, defaultParams)
  
  try {
    await sendZoneCommand(zoneId.value, commandType, defaultParams)
    logInfo(`✓ [onRunCycle] Команда "${cycleName}" отправлена успешно`)
    showToast(`Команда "${cycleName}" отправлена успешно`, 'success', 3000)
    // Обновляем зону и cycles через Inertia partial reload (не window.location.reload!)
    reloadZoneAfterCommand(zoneId.value, ['zone', 'cycles'])
  } catch (err) {
    logError(`✗ [onRunCycle] Ошибка при отправке команды ${cycleType}:`, err)
    handleError(err, {
      component: 'Zones/Show',
      action: 'onRunCycle',
      cycleType,
      zoneId: zoneId.value,
    })
  } finally {
    loading.value.cycles[cycleType] = false
  }
}

const variant = computed<'success' | 'neutral' | 'warning' | 'danger'>(() => {
  switch (zone.value.status) {
    case 'RUNNING': return 'success'
    case 'PAUSED': return 'neutral'
    case 'WARNING': return 'warning'
    case 'ALARM': return 'danger'
    default: return 'neutral'
  }
})

async function onToggle(): Promise<void> {
  if (!zoneId.value) return
  
  loading.value.toggle = true
  
  // Оптимистично обновляем статус зоны в store
  const newStatus = zone.value.status === 'PAUSED' ? 'RUNNING' : 'PAUSED'
  const action = zone.value.status === 'PAUSED' ? 'resume' : 'pause'
  const actionText = zone.value.status === 'PAUSED' ? 'возобновлена' : 'приостановлена'
  
  // Создаем оптимистичное обновление
  const optimisticUpdate = createOptimisticZoneUpdate(
    zonesStore,
    zoneId.value,
    { status: newStatus }
  )
  
  try {
    // Применяем оптимистичное обновление и выполняем операцию на сервере
    await performUpdate(
      `zone-toggle-${zoneId.value}-${Date.now()}`,
      {
        applyUpdate: optimisticUpdate.applyUpdate,
        rollback: optimisticUpdate.rollback,
        syncWithServer: async () => {
          // Выполняем операцию на сервере
          const response = await api.post(`/api/zones/${zoneId.value}/${action}`, {})
          
          // Обновляем зону в store с данными с сервера
          const updatedZone = (response.data as { data?: Zone })?.data || 
                            (response.data as Zone) || 
                            zone.value
          
          if (updatedZone.id) {
            zonesStore.upsert(updatedZone)
          }
          
          return updatedZone
        },
        onSuccess: () => {
          showToast(`Зона успешно ${actionText}`, 'success', 3000)
          // Обновляем зону через Inertia partial reload для синхронизации всех данных
          reloadZone(zoneId.value, ['zone'])
        },
        onError: (error) => {
          logError('Failed to toggle zone:', error)
          let errorMessage = 'Неизвестная ошибка'
          if (error && typeof error === 'object' && 'message' in error) {
            errorMessage = String(error.message)
          }
          showToast(`Ошибка при изменении статуса зоны: ${errorMessage}`, 'error', 5000)
        },
        showLoading: false, // Управляем loading вручную
        timeout: 10000, // 10 секунд таймаут
      }
    )
  } catch (err) {
    // Ошибка уже обработана в onError callback
    logError('Failed to toggle zone (unhandled):', err)
  } finally {
    loading.value.toggle = false
  }
}

function openActionModal(actionType: CommandType): void {
  currentActionType.value = actionType
  showActionModal.value = true
}

async function onActionSubmit({ actionType, params }: { actionType: CommandType; params: Record<string, unknown> }): Promise<void> {
  if (!zoneId.value) return
  
  loading.value.irrigate = true
  
  try {
    await sendZoneCommand(zoneId.value, actionType, params)
    const actionNames: Record<CommandType, string> = {
      'FORCE_IRRIGATION': 'Полив',
      'FORCE_PH_CONTROL': 'Коррекция pH',
      'FORCE_EC_CONTROL': 'Коррекция EC',
      'FORCE_CLIMATE': 'Управление климатом',
      'FORCE_LIGHTING': 'Управление освещением'
    } as Record<CommandType, string>
    const actionName = actionNames[actionType] || 'Действие'
    showToast(`${actionName} запущено успешно`, 'success', 3000)
    // Обновляем зону и cycles через Inertia partial reload
    reloadZoneAfterCommand(zoneId.value, ['zone', 'cycles'])
  } catch (err) {
    logError(`Failed to execute ${actionType}:`, err)
    let errorMessage = 'Неизвестная ошибка'
    if (err && typeof err === 'object' && 'message' in err) errorMessage = String(err.message)
    const actionName = actionNames[actionType] || 'Действие'
    showToast(`Ошибка при выполнении "${actionName}": ${errorMessage}`, 'error', 5000)
  } finally {
    loading.value.irrigate = false
  }
}

function openNodeConfig(nodeId: number, node: any): void {
  selectedNodeId.value = nodeId
  selectedNode.value = node
  showNodeConfigModal.value = true
}

async function onRecipeAttached(recipeId: number): Promise<void> {
  logInfo('[Zones/Show] Recipe attached event received:', recipeId)
  
  // Показываем уведомление
  showToast('Рецепт успешно привязан к зоне', 'success', 3000)
  
  // Даем время для отображения toast перед обновлением
  await new Promise(resolve => setTimeout(resolve, 300))
  
  // Делаем полный reload страницы через Inertia для получения обновленных данных
  // Используем router.reload() для гарантированного обновления всех данных
  // preserveState: false чтобы обновить все props, включая zone с recipeInstance
  logInfo('[Zones/Show] Starting zone reload after recipe attachment')
  
  router.reload({ 
    only: ['zone'],
    preserveScroll: true,
    preserveState: false, // Важно! Это гарантирует обновление всех props
    onSuccess: (page) => {
      logInfo('[Zones/Show] Zone reloaded successfully after recipe attachment', {
        zone: page.props.zone,
        hasRecipeInstance: !!page.props.zone?.recipeInstance,
        recipeId: page.props.zone?.recipeInstance?.recipe_id,
        recipeName: page.props.zone?.recipeInstance?.recipe?.name
      })
    },
    onError: (error) => {
      logError('[Zones/Show] Failed to reload zone:', error)
    },
    onFinish: () => {
      logInfo('[Zones/Show] Zone reload finished')
    }
  })
}

function onNodesAttached(nodeIds: number[]): void {
  showToast(`Успешно привязано узлов: ${nodeIds.length}`, 'success', 3000)
  reloadZone(zoneId.value, ['zone', 'devices'])
}

function onNodeConfigPublished(): void {
  showToast('Конфигурация узла успешно отправлена', 'success', 3000)
  reloadZone(zoneId.value, ['devices'])
}

async function onNextPhase(): Promise<void> {
  if (!zoneId.value || !zone.value.recipeInstance) return
  
  loading.value.nextPhase = true
  
  // Оптимистично обновляем фазу в store
  const nextPhaseIndex = (zone.value.recipeInstance.current_phase_index || 0) + 1
  
  // Создаем оптимистичное обновление
  const optimisticUpdate = createOptimisticZoneUpdate(
    zonesStore,
    zoneId.value,
    {
      recipeInstance: {
        ...zone.value.recipeInstance,
        current_phase_index: nextPhaseIndex,
      },
    }
  )
  
  try {
    // Применяем оптимистичное обновление и выполняем операцию на сервере
    await performUpdate(
      `zone-phase-${zoneId.value}-${Date.now()}`,
      {
        applyUpdate: optimisticUpdate.applyUpdate,
        rollback: optimisticUpdate.rollback,
        syncWithServer: async () => {
          // Выполняем операцию на сервере
          const response = await api.post(`/api/zones/${zoneId.value}/change-phase`, {
            phase_index: nextPhaseIndex,
          })
          
          // Обновляем зону в store с данными с сервера
          const updatedZone = (response.data as { data?: Zone })?.data || 
                            (response.data as Zone) || 
                            zone.value
          
          if (updatedZone.id) {
            zonesStore.upsert(updatedZone)
          }
          
          return updatedZone
        },
        onSuccess: () => {
          showToast('Фаза успешно изменена', 'success', 3000)
          // Обновляем зону через Inertia partial reload для синхронизации всех данных
          reloadZone(zoneId.value, ['zone'])
        },
        onError: (error) => {
          logError('Failed to change phase:', error)
          let errorMessage = 'Неизвестная ошибка'
          if (error && typeof error === 'object' && 'message' in error) {
            errorMessage = String(error.message)
          }
          showToast(`Ошибка при изменении фазы: ${errorMessage}`, 'error', 5000)
        },
        showLoading: false, // Управляем loading вручную
        timeout: 10000, // 10 секунд таймаут
      }
    )
  } catch (err) {
    // Ошибка уже обработана в onError callback
    logError('Failed to change phase (unhandled):', err)
  } finally {
    loading.value.nextPhase = false
  }
}
</script>

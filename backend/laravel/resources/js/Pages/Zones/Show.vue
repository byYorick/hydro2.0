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
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div class="text-lg font-semibold">{{ zone.name }}</div>
          <div class="text-xs text-neutral-400">
            <span v-if="zone.description">{{ zone.description }}</span>
            <span v-if="zone.recipeInstance?.recipe">
              · Рецепт: {{ zone.recipeInstance.recipe.name }}
              <span v-if="zone.recipeInstance.current_phase_index !== null">
                (фаза {{ zone.recipeInstance.current_phase_index + 1 }})
              </span>
            </span>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <Badge :variant="variant">{{ translateStatus(zone.status) }}</Badge>
          <template v-if="page.props.auth?.user?.role === 'admin' || page.props.auth?.user?.role === 'operator'">
            <Button size="sm" variant="secondary" @click="onToggle" :disabled="loading.toggle">
              {{ zone.status === 'PAUSED' ? 'Возобновить' : 'Приостановить' }}
            </Button>
            <Button size="sm" variant="outline" @click="showIrrigationModal = true" :disabled="loading.irrigate">
              Полить сейчас
            </Button>
            <Button size="sm" @click="onNextPhase" :disabled="loading.nextPhase">
              Следующая фаза
            </Button>
          </template>
          <Button size="sm" variant="outline" @click="showSimulationModal = true">
            Симуляция
          </Button>
        </div>
      </div>

      <!-- Target vs Actual (основная метрика зоны) -->
      <ZoneTargets :telemetry="telemetry" :targets="targets" />

      <div class="grid grid-cols-1 xl:grid-cols-3 gap-3">
        <div class="xl:col-span-2 space-y-3">
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
        <Card>
          <div class="text-sm font-semibold mb-2">Устройства</div>
          <ul v-if="devices.length > 0" class="text-sm text-neutral-300 space-y-1">
            <li v-for="d in devices" :key="d.id">
              <Link :href="`/devices/${d.id}`" class="text-sky-400 hover:underline">{{ d.uid || d.name }}</Link>
              — {{ translateStatus(d.status) }}
            </li>
          </ul>
          <div v-else class="text-sm text-neutral-400">Нет устройств</div>
        </Card>
      </div>

      <!-- Cycles (расписание подсистем) -->
      <Card>
        <div class="text-sm font-semibold mb-3">Циклы</div>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-3">
          <div v-for="cycle in cyclesList" :key="cycle.type" class="text-xs text-neutral-400 p-2 rounded border border-neutral-800">
            <div class="font-semibold text-sm mb-1">{{ translateCycleType(cycle.type) }}</div>
            <div class="text-xs">Стратегия: {{ translateStrategy(cycle.strategy || 'periodic') }}</div>
            <div class="text-xs mt-1">Интервал: {{ cycle.interval ? formatInterval(cycle.interval) : 'Не настроено' }}</div>
            <div class="text-xs mt-1">Последний запуск: {{ formatTimeShort(cycle.last_run) }}</div>
            <div class="text-xs mt-1">Следующий запуск: {{ formatTimeShort(cycle.next_run) }}</div>
            <Button 
              size="sm" 
              variant="secondary" 
              class="mt-2 w-full text-xs" 
              @click="onRunCycle(cycle.type)"
              :disabled="loading.cycles[cycle.type]"
            >
              {{ loading.cycles[cycle.type] ? 'Запуск...' : 'Запустить сейчас' }}
            </Button>
          </div>
        </div>
      </Card>

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
    
    <!-- Irrigation Modal -->
    <Modal :open="showIrrigationModal" title="Полив зоны" @close="showIrrigationModal = false">
      <div class="space-y-3">
        <div>
          <label class="text-sm text-neutral-300">Длительность полива (секунды)</label>
          <input
            v-model.number="irrigationDuration"
            type="number"
            min="1"
            max="3600"
            class="mt-1 w-full h-9 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm"
            placeholder="10"
          />
        </div>
      </div>
      <template #footer>
        <Button size="sm" variant="secondary" @click="showIrrigationModal = false">Отмена</Button>
        <Button size="sm" @click="onIrrigate(irrigationDuration)" :disabled="loading.irrigate">
          {{ loading.irrigate ? 'Запуск...' : 'Полить' }}
        </Button>
      </template>
    </Modal>
  </AppLayout>
</template>

<script setup>
import { computed, defineAsyncComponent, onMounted, ref } from 'vue'
import { Link, usePage, router } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import Badge from '@/Components/Badge.vue'
import ZoneTargets from '@/Components/ZoneTargets.vue'
import Toast from '@/Components/Toast.vue'
import ZoneSimulationModal from '@/Components/ZoneSimulationModal.vue'
import Modal from '@/Components/Modal.vue'
import { translateStatus, translateEventKind, translateCycleType, translateStrategy } from '@/utils/i18n'
import { formatTimeShort, formatInterval } from '@/utils/formatTime'
import { logger } from '@/utils/logger'
import { useApi } from '@/composables/useApi'

const ZoneTelemetryChart = defineAsyncComponent(() => import('@/Pages/Zones/ZoneTelemetryChart.vue'))

const page = usePage()

// Toast notifications
const toasts = ref([])
let toastIdCounter = 0

// Simulation modal
const showSimulationModal = ref(false)
const showIrrigationModal = ref(false)
const irrigationDuration = ref(10)

// Loading states
const loading = ref({
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

function showToast(message, variant = 'info', duration = 3000) {
  const id = ++toastIdCounter
  toasts.value.push({ id, message, variant, duration })
  return id
}

// Инициализация API с Toast (после определения showToast)
const { api } = useApi(showToast)

function removeToast(id) {
  const index = toasts.value.findIndex(t => t.id === id)
  if (index > -1) {
    toasts.value.splice(index, 1)
  }
}
const zone = computed(() => page.props.zone || {})
const zoneId = computed(() => {
  const id = zone.value.id || page.props.zoneId
  return typeof id === 'string' ? parseInt(id) : id
})

// Телеметрия, цели и устройства из props
const telemetry = computed(() => page.props.telemetry || { ph: null, ec: null, temperature: null, humidity: null })
const targets = computed(() => page.props.targets || {})
const devices = computed(() => page.props.devices || [])
const events = computed(() => page.props.events || [])
const cycles = computed(() => page.props.cycles || {})

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

// Графики: загрузка данных истории
const chartTimeRange = ref('24H') // 1H, 24H, 7D, 30D, ALL
const chartDataPh = ref([])
const chartDataEc = ref([])

// Загрузка данных истории для графиков
async function loadChartData(metric, timeRange) {
  if (!zoneId.value) return
  
  const now = new Date()
  let from = null
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
    const params = { metric }
    if (from) params.from = from.toISOString()
    params.to = now.toISOString()
    
    const res = await api.get(`/api/zones/${zoneId.value}/telemetry/history`, { params })
    
    const data = res.data?.data || []
    return data.map(item => ({
      ts: new Date(item.ts).getTime(),
      value: item.value,
    }))
  } catch (err) {
    logger.error(`Failed to load ${metric} history:`, err)
    return []
  }
}

async function onChartTimeRangeChange(newRange) {
  chartTimeRange.value = newRange
  chartDataPh.value = await loadChartData('PH', newRange)
  chartDataEc.value = await loadChartData('EC', newRange)
}

onMounted(async () => {
  logger.log('[Show.vue] Компонент смонтирован', { zoneId: zoneId.value })
  
  // Загрузить данные для графиков
  chartDataPh.value = await loadChartData('PH', chartTimeRange.value)
  chartDataEc.value = await loadChartData('EC', chartTimeRange.value)
})

async function onRunCycle(cycleType) {
  if (!zoneId.value) {
    logger.warn('[onRunCycle] zoneId is missing')
    showToast('Ошибка: зона не найдена', 'error', 3000)
    return
  }
  
  loading.value.cycles[cycleType] = true
  const cycleName = translateCycleType(cycleType)
  
  logger.log(`[onRunCycle] Отправка команды ${cycleType} для зоны ${zoneId.value}`)
  
  try {
    const url = `/api/zones/${zoneId.value}/commands`
    const payload = {
      type: `FORCE_${cycleType}`,
      params: {},
    }
    
    const response = await api.post(url, payload)
    
    if (response.data?.status === 'ok') {
      logger.log(`✓ [onRunCycle] Команда "${cycleName}" отправлена успешно`)
      showToast(`Команда "${cycleName}" отправлена успешно`, 'success', 3000)
    } else {
      logger.warn(`[onRunCycle] Неожиданный ответ:`, response.data)
      showToast('Неожиданный ответ сервера', 'error', 5000)
    }
  } catch (err) {
    logger.error(`✗ [onRunCycle] Ошибка при отправке команды ${cycleType}:`, err)
    const errorMsg = err.response?.data?.message || err.message || 'Неизвестная ошибка'
    showToast(`Ошибка: ${errorMsg}`, 'error', 5000)
  } finally {
    loading.value.cycles[cycleType] = false
  }
}

const variant = computed(() => {
  switch (zone.value.status) {
    case 'RUNNING': return 'success'
    case 'PAUSED': return 'neutral'
    case 'WARNING': return 'warning'
    case 'ALARM': return 'danger'
    default: return 'neutral'
  }
})

async function onToggle() {
  if (!zoneId.value) return
  
  loading.value.toggle = true
  const url = `/api/zones/${zoneId.value}/${zone.value.status === 'PAUSED' ? 'resume' : 'pause'}`
  const action = zone.value.status === 'PAUSED' ? 'возобновлена' : 'приостановлена'
  
  try {
    await api.post(url, {})
    showToast(`Зона успешно ${action}`, 'success', 3000)
    router.reload({ only: ['zone'] })
  } catch (err) {
    logger.error('Failed to toggle zone:', err)
    const errorMsg = err.response?.data?.message || err.message || 'Неизвестная ошибка'
    showToast(`Ошибка: ${errorMsg}`, 'error', 5000)
  } finally {
    loading.value.toggle = false
  }
}

async function onIrrigate(durationSec = 10) {
  if (!zoneId.value) return
  
  loading.value.irrigate = true
  
  try {
    await api.post(`/api/zones/${zoneId.value}/commands`, {
      type: 'FORCE_IRRIGATION',
      params: { duration_sec: durationSec },
    })
    showToast(`Полив запущен на ${durationSec} секунд`, 'success', 3000)
    showIrrigationModal.value = false
  } catch (err) {
    logger.error('Failed to irrigate:', err)
    const errorMsg = err.response?.data?.message || err.message || 'Неизвестная ошибка'
    showToast(`Ошибка: ${errorMsg}`, 'error', 5000)
  } finally {
    loading.value.irrigate = false
  }
}

async function onNextPhase() {
  if (!zoneId.value) return
  
  loading.value.nextPhase = true
  
  try {
    await api.post(`/api/zones/${zoneId.value}/change-phase`, {
      phase_index: (zone.value.recipeInstance?.current_phase_index || 0) + 1,
    })
    showToast('Фаза успешно изменена', 'success', 3000)
    router.reload({ only: ['zone'] })
  } catch (err) {
    logger.error('Failed to change phase:', err)
    const errorMsg = err.response?.data?.message || err.message || 'Неизвестная ошибка'
    showToast(`Ошибка: ${errorMsg}`, 'error', 5000)
  } finally {
    loading.value.nextPhase = false
  }
}
</script>

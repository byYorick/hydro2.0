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
          <Badge :variant="variant">{{ zone.status }}</Badge>
          <template v-if="page.props.auth?.user?.role === 'admin' || page.props.auth?.user?.role === 'operator'">
            <Button size="sm" variant="secondary" @click="onToggle">{{ zone.status === 'PAUSED' ? 'Resume' : 'Pause' }}</Button>
            <Button size="sm" variant="outline" @click="onIrrigate">Irrigate Now</Button>
            <Button size="sm" @click="onNextPhase">Next Phase</Button>
          </template>
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
          <div class="text-sm font-semibold mb-2">Devices</div>
          <ul v-if="devices.length > 0" class="text-sm text-neutral-300 space-y-1">
            <li v-for="d in devices" :key="d.id">
              <Link :href="`/devices/${d.id}`" class="text-sky-400 hover:underline">{{ d.uid || d.name }}</Link>
              — {{ d.status }}
            </li>
          </ul>
          <div v-else class="text-sm text-neutral-400">Нет устройств</div>
        </Card>
      </div>

      <!-- Cycles (расписание подсистем) -->
      <Card>
        <div class="text-sm font-semibold mb-3">Cycles</div>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-3">
          <div class="text-xs text-neutral-400 p-2 rounded border border-neutral-800">
            <div class="font-semibold text-sm mb-1">PH_CONTROL</div>
            <div class="text-xs">Strategy: periodic</div>
            <div class="text-xs mt-1">Interval: 5 min</div>
            <div class="text-xs mt-1">Last: {{ formatTime(null) }}</div>
            <div class="text-xs mt-1">Next: {{ formatTime(null) }}</div>
            <Button size="sm" variant="secondary" class="mt-2 w-full text-xs" @click="onRunCycle('PH_CONTROL')">
              Запустить сейчас
            </Button>
          </div>
          <div class="text-xs text-neutral-400 p-2 rounded border border-neutral-800">
            <div class="font-semibold text-sm mb-1">EC_CONTROL</div>
            <div class="text-xs">Strategy: periodic</div>
            <div class="text-xs mt-1">Interval: 5 min</div>
            <div class="text-xs mt-1">Last: {{ formatTime(null) }}</div>
            <div class="text-xs mt-1">Next: {{ formatTime(null) }}</div>
            <Button size="sm" variant="secondary" class="mt-2 w-full text-xs" @click="onRunCycle('EC_CONTROL')">
              Запустить сейчас
            </Button>
          </div>
          <div class="text-xs text-neutral-400 p-2 rounded border border-neutral-800">
            <div class="font-semibold text-sm mb-1">IRRIGATION</div>
            <div class="text-xs">Strategy: periodic</div>
            <div class="text-xs mt-1">Interval: {{ targets.irrigation_interval_sec ? `${Math.floor(targets.irrigation_interval_sec / 60)} min` : '-' }}</div>
            <div class="text-xs mt-1">Last: {{ formatTime(null) }}</div>
            <div class="text-xs mt-1">Next: {{ formatTime(null) }}</div>
            <Button size="sm" variant="secondary" class="mt-2 w-full text-xs" @click="onRunCycle('IRRIGATION')">
              Запустить сейчас
            </Button>
          </div>
          <div class="text-xs text-neutral-400 p-2 rounded border border-neutral-800">
            <div class="font-semibold text-sm mb-1">LIGHTING</div>
            <div class="text-xs">Strategy: periodic</div>
            <div class="text-xs mt-1">Interval: {{ targets.light_hours ? `${targets.light_hours} hours` : '-' }}</div>
            <div class="text-xs mt-1">Last: {{ formatTime(null) }}</div>
            <div class="text-xs mt-1">Next: {{ formatTime(null) }}</div>
            <Button size="sm" variant="secondary" class="mt-2 w-full text-xs" @click="onRunCycle('LIGHTING')">
              Запустить сейчас
            </Button>
          </div>
          <div class="text-xs text-neutral-400 p-2 rounded border border-neutral-800">
            <div class="font-semibold text-sm mb-1">CLIMATE</div>
            <div class="text-xs">Strategy: periodic</div>
            <div class="text-xs mt-1">Interval: 5 min</div>
            <div class="text-xs mt-1">Last: {{ formatTime(null) }}</div>
            <div class="text-xs mt-1">Next: {{ formatTime(null) }}</div>
            <Button size="sm" variant="secondary" class="mt-2 w-full text-xs" @click="onRunCycle('CLIMATE')">
              Запустить сейчас
            </Button>
          </div>
        </div>
      </Card>

      <!-- Events (история событий) -->
      <Card>
        <div class="text-sm font-semibold mb-2">Events</div>
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
              {{ e.kind }}
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
  </AppLayout>
</template>

<script setup>
import { computed, defineAsyncComponent, onMounted, ref } from 'vue'
import { Link, usePage } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import Badge from '@/Components/Badge.vue'
import ZoneTargets from '@/Components/ZoneTargets.vue'
import Toast from '@/Components/Toast.vue'
import axios from 'axios'

const ZoneTelemetryChart = defineAsyncComponent(() => import('@/Pages/Zones/ZoneTelemetryChart.vue'))

const page = usePage()

// Toast notifications
const toasts = ref([])
let toastIdCounter = 0

function showToast(message, variant = 'info', duration = 3000) {
  console.log('=== showToast ВЫЗВАНА ===', { message, variant, duration, timestamp: new Date().toISOString() })
  const id = ++toastIdCounter
  toasts.value.push({ id, message, variant, duration })
  console.log(`[showToast] Уведомление добавлено, ID: ${id}`)
  console.log(`[showToast] Всего уведомлений: ${toasts.value.length}`)
  console.log(`[showToast] Массив toasts:`, JSON.stringify(toasts.value, null, 2))
  console.log('=== showToast ЗАВЕРШЕНА ===')
  return id
}

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
    
    const res = await axios.get(`/api/zones/${zoneId.value}/telemetry/history`, {
      params,
      headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
    })
    
    const data = res.data?.data || []
    return data.map(item => ({
      ts: new Date(item.ts).getTime(),
      value: item.value,
    }))
  } catch (err) {
    console.error(`Failed to load ${metric} history:`, err)
    return []
  }
}

async function onChartTimeRangeChange(newRange) {
  chartTimeRange.value = newRange
  chartDataPh.value = await loadChartData('PH', newRange)
  chartDataEc.value = await loadChartData('EC', newRange)
}

onMounted(async () => {
  console.log('========================================')
  console.log('[Show.vue] ===== КОМПОНЕНТ СМОНТИРОВАН =====')
  console.log('[Show.vue] zoneId:', zoneId.value)
  console.log('[Show.vue] zone:', zone.value)
  console.log('[Show.vue] Функция onRunCycle доступна:', typeof onRunCycle)
  console.log('[Show.vue] Функция showToast доступна:', typeof showToast)
  console.log('[Show.vue] Массив toasts:', toasts.value)
  console.log('[Show.vue] window.console:', typeof window.console)
  console.log('========================================')
  
  // Загрузить данные для графиков
  chartDataPh.value = await loadChartData('PH', chartTimeRange.value)
  chartDataEc.value = await loadChartData('EC', chartTimeRange.value)
})

function formatTime(timestamp) {
  if (!timestamp) return '-'
  return new Date(timestamp).toLocaleString('ru-RU', { 
    hour: '2-digit', 
    minute: '2-digit',
    day: '2-digit',
    month: '2-digit',
  })
}

async function onRunCycle(cycleType) {
  // Принудительный лог в начале функции
  console.log('=== onRunCycle ВЫЗВАНА ===', { cycleType, zoneId: zoneId.value, timestamp: new Date().toISOString() })
  
  if (!zoneId.value) {
    console.warn('[onRunCycle] zoneId is missing')
    showToast('Ошибка: зона не найдена', 'error', 3000)
    return
  }
  
  // Show loading state (optional - can add button disabled state)
  const cycleNames = {
    'PH_CONTROL': 'Контроль pH',
    'EC_CONTROL': 'Контроль EC',
    'IRRIGATION': 'Полив',
    'LIGHTING': 'Освещение',
    'CLIMATE': 'Климат',
  }
  const cycleName = cycleNames[cycleType] || cycleType
  
  console.log(`[onRunCycle] Отправка команды ${cycleType} для зоны ${zoneId.value}`)
  console.log(`[onRunCycle] Имя цикла: ${cycleName}`)
  
  try {
    const url = `/api/zones/${zoneId.value}/commands`
    const payload = {
      type: `FORCE_${cycleType}`,
      params: {},
    }
    console.log(`[onRunCycle] POST запрос:`, { url, payload })
    
    const response = await axios.post(url, payload, {
      headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
    })
    
    console.log(`[onRunCycle] Ответ сервера получен:`, response.data)
    console.log(`[onRunCycle] Статус ответа:`, response.data?.status)
    
    // Show success message
    if (response.data?.status === 'ok') {
      console.log(`✓ [onRunCycle] Команда "${cycleName}" отправлена успешно`, response.data)
      showToast(`Команда "${cycleName}" отправлена успешно`, 'success', 3000)
    } else {
      console.warn(`[onRunCycle] Неожиданный ответ:`, response.data)
      showToast(`Неизвестный ответ сервера: ${JSON.stringify(response.data)}`, 'error', 5000)
    }
  } catch (err) {
    console.error(`✗ [onRunCycle] Ошибка при отправке команды ${cycleType}:`, err)
    console.error(`[onRunCycle] Детали ошибки:`, {
      message: err.message,
      response: err.response?.data,
      status: err.response?.status,
      config: err.config,
    })
    const errorMsg = err.response?.data?.message || err.message || 'Неизвестная ошибка'
    console.error(`[onRunCycle] Показываю toast с ошибкой:`, errorMsg)
    showToast(`Ошибка: ${errorMsg}`, 'error', 5000)
  }
  
  console.log('=== onRunCycle ЗАВЕРШЕНА ===')
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
  const url = `/api/zones/${zoneId.value}/${zone.value.status === 'PAUSED' ? 'resume' : 'pause'}`
  try {
    await axios.post(url, {}, {
      headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
    })
    window.location.reload()
  } catch (err) {
    console.error('Failed to toggle zone:', err)
  }
}

async function onIrrigate() {
  if (!zoneId.value) return
  try {
    await axios.post(`/api/zones/${zoneId.value}/commands`, {
      type: 'FORCE_IRRIGATION',
      params: { duration_sec: 10 },
    }, {
      headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
    })
  } catch (err) {
    console.error('Failed to irrigate:', err)
  }
}

async function onNextPhase() {
  if (!zoneId.value) return
  try {
    await axios.post(`/api/zones/${zoneId.value}/change-phase`, {
      phase_index: (zone.value.recipeInstance?.current_phase_index || 0) + 1,
    }, {
      headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
    })
    window.location.reload()
  } catch (err) {
    console.error('Failed to change phase:', err)
  }
}
</script>

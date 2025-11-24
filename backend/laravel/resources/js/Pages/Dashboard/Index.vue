<template>
  <AppLayout>
    <template #default>
      <!-- Ролевые Dashboard -->
      <AgronomistDashboard 
        v-if="isAgronomist"
        :dashboard="dashboard"
      />
      <AdminDashboard 
        v-else-if="isAdmin"
        :dashboard="dashboard"
      />
      <EngineerDashboard 
        v-else-if="isEngineer"
        :dashboard="dashboard"
      />
      <OperatorDashboard 
        v-else-if="isOperator"
        :dashboard="dashboard"
      />
      <ViewerDashboard 
        v-else-if="isViewer"
        :dashboard="dashboard"
      />
      <!-- Дефолтный Dashboard для остальных случаев -->
      <div v-else>
        <div class="flex items-center justify-between mb-4">
          <h1 class="text-lg font-semibold">Панель управления</h1>
        <div class="flex gap-2">
          <Link href="/setup/wizard">
            <Button size="sm" variant="secondary">Мастер настройки</Button>
          </Link>
          <Link href="/greenhouses/create">
            <Button size="sm" variant="outline">Создать теплицу</Button>
          </Link>
        </div>
      </div>
      
      <!-- Основные статистики -->
      <div class="grid grid-cols-2 sm:grid-cols-2 md:grid-cols-2 xl:grid-cols-4 gap-3 sm:gap-4 mb-6">
        <Card class="hover:border-neutral-700 transition-all duration-200 hover:shadow-lg">
          <div class="flex items-start justify-between mb-2">
            <div class="text-neutral-400 text-xs font-medium uppercase tracking-wide">Теплицы</div>
            <div class="w-8 h-8 rounded-lg bg-sky-900/30 border border-sky-700/50 flex items-center justify-center">
              <svg class="w-4 h-4 text-sky-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
              </svg>
            </div>
          </div>
          <div class="text-3xl font-bold text-neutral-100">{{ dashboard.greenhousesCount }}</div>
        </Card>
        <Card class="hover:border-neutral-700 transition-all duration-200 hover:shadow-lg">
          <div class="flex items-start justify-between mb-2">
            <div class="text-neutral-400 text-xs font-medium uppercase tracking-wide">Зоны</div>
            <div class="w-8 h-8 rounded-lg bg-emerald-900/30 border border-emerald-700/50 flex items-center justify-center">
              <svg class="w-4 h-4 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
              </svg>
            </div>
          </div>
          <div class="text-3xl font-bold text-neutral-100 mb-2">{{ dashboard.zonesCount }}</div>
          <div v-if="zonesStatusSummary" class="flex flex-wrap gap-1.5 text-xs">
            <span v-if="zonesStatusSummary.RUNNING" class="px-1.5 py-0.5 rounded bg-emerald-900/30 text-emerald-400 border border-emerald-700/50">
              Запущено: {{ zonesStatusSummary.RUNNING }}
            </span>
            <span v-if="zonesStatusSummary.PAUSED" class="px-1.5 py-0.5 rounded bg-neutral-800 text-neutral-400 border border-neutral-700">
              Пауза: {{ zonesStatusSummary.PAUSED }}
            </span>
            <span v-if="zonesStatusSummary.ALARM" class="px-1.5 py-0.5 rounded bg-red-900/30 text-red-400 border border-red-700/50">
              Тревога: {{ zonesStatusSummary.ALARM }}
            </span>
            <span v-if="zonesStatusSummary.WARNING" class="px-1.5 py-0.5 rounded bg-amber-900/30 text-amber-400 border border-amber-700/50">
              Предупреждение: {{ zonesStatusSummary.WARNING }}
            </span>
          </div>
        </Card>
        <Card class="hover:border-neutral-700 transition-all duration-200 hover:shadow-lg">
          <div class="flex items-start justify-between mb-2">
            <div class="text-neutral-400 text-xs font-medium uppercase tracking-wide">Устройства</div>
            <div class="w-8 h-8 rounded-lg bg-purple-900/30 border border-purple-700/50 flex items-center justify-center">
              <svg class="w-4 h-4 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m-2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
              </svg>
            </div>
          </div>
          <div class="text-3xl font-bold text-neutral-100 mb-2">{{ dashboard.devicesCount }}</div>
          <div v-if="nodesStatusSummary" class="flex flex-wrap gap-1.5 text-xs">
            <span v-if="nodesStatusSummary.online" class="px-1.5 py-0.5 rounded bg-emerald-900/30 text-emerald-400 border border-emerald-700/50">
              Онлайн: {{ nodesStatusSummary.online }}
            </span>
            <span v-if="nodesStatusSummary.offline" class="px-1.5 py-0.5 rounded bg-red-900/30 text-red-400 border border-red-700/50">
              Офлайн: {{ nodesStatusSummary.offline }}
            </span>
          </div>
        </Card>
        <Card class="hover:border-neutral-700 transition-all duration-200 hover:shadow-lg" :class="dashboard.alertsCount > 0 ? 'border-red-800/50' : ''">
          <div class="flex items-start justify-between mb-2">
            <div class="text-neutral-400 text-xs font-medium uppercase tracking-wide">Активные алерты</div>
            <div class="w-8 h-8 rounded-lg flex items-center justify-center" :class="dashboard.alertsCount > 0 ? 'bg-red-900/30 border border-red-700/50' : 'bg-emerald-900/30 border border-emerald-700/50'">
              <svg class="w-4 h-4" :class="dashboard.alertsCount > 0 ? 'text-red-400' : 'text-emerald-400'" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
          </div>
          <div class="text-3xl font-bold" :class="dashboard.alertsCount > 0 ? 'text-red-400' : 'text-emerald-400'">
            {{ dashboard.alertsCount }}
          </div>
        </Card>
      </div>

      <!-- Быстрые действия -->
      <div v-if="!hasGreenhouses || dashboard.greenhousesCount === 0" class="mb-6">
        <Card class="bg-sky-900/20 border-sky-700">
          <div class="flex items-center justify-between">
            <div>
              <div class="text-sm font-semibold mb-1">Начать работу</div>
              <div class="text-xs text-neutral-400">
                Создайте теплицу и зоны для начала работы с системой
              </div>
            </div>
            <div class="flex gap-2">
              <Link href="/setup/wizard">
                <Button size="sm">Мастер настройки</Button>
              </Link>
              <Link href="/greenhouses/create">
                <Button size="sm" variant="secondary">Создать теплицу</Button>
              </Link>
            </div>
          </div>
        </Card>
      </div>

      <!-- Теплицы -->
      <div v-if="hasGreenhouses" class="mb-6">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-base font-semibold text-neutral-100">Теплицы</h2>
          <Link href="/greenhouses/create">
            <Button size="sm" variant="outline">Создать теплицу</Button>
          </Link>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          <Card 
            v-for="gh in dashboard.greenhouses" 
            :key="gh.id" 
            v-memo="[gh.id, gh.name, gh.zones_count, gh.zones_running]"
            class="hover:border-neutral-700 hover:shadow-lg transition-all duration-200"
          >
            <div class="flex items-start justify-between">
              <div>
                <div class="text-sm font-semibold">{{ gh.name }}</div>
                <div class="text-xs text-neutral-400 mt-1">
                  <span v-if="gh.type">{{ gh.type }}</span>
                  <span v-if="gh.uid" class="ml-2">UID: {{ gh.uid }}</span>
                </div>
              </div>
            </div>
            <div class="mt-3 text-xs text-neutral-400">
              <div>Зон: {{ gh.zones_count || 0 }}</div>
              <div class="text-emerald-400">Запущено: {{ gh.zones_running || 0 }}</div>
            </div>
          </Card>
        </div>
      </div>

      <!-- Проблемные зоны -->
      <div v-if="hasProblematicZones" class="mb-6">
        <h2 class="text-base font-semibold text-neutral-100 mb-4">Проблемные зоны</h2>
        <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          <Card 
            v-for="zone in dashboard.problematicZones" 
            :key="zone.id" 
            v-memo="[zone.id, zone.status, zone.alerts_count]"
            class="hover:border-red-800/50 hover:shadow-lg transition-all duration-200 border-red-900/30"
          >
            <div class="flex items-start justify-between mb-2">
              <div>
                <div class="text-sm font-semibold">{{ zone.name }}</div>
                <div v-if="zone.greenhouse" class="text-xs text-neutral-400 mt-1">
                  {{ zone.greenhouse.name }}
                </div>
              </div>
              <Badge :variant="zone.status === 'ALARM' ? 'danger' : 'warning'">
                {{ translateStatus(zone.status) }}
              </Badge>
            </div>
            <div v-if="zone.description" class="text-xs text-neutral-400 mb-2">{{ zone.description }}</div>
            <div v-if="zone.alerts_count > 0" class="text-xs text-red-400 mb-2">
              Активных алертов: {{ zone.alerts_count }}
            </div>
            <!-- Быстрые действия -->
            <div class="mt-3 flex items-center gap-2 flex-wrap">
              <Link :href="`/zones/${zone.id}`">
                <Button size="sm" variant="secondary">Подробнее</Button>
              </Link>
              <Button
                v-if="zone.status === 'RUNNING'"
                size="sm"
                variant="outline"
                @click="handleQuickAction(zone, 'PAUSE')"
                class="text-xs"
              >
                ⏸ Пауза
              </Button>
              <Button
                v-if="zone.status === 'PAUSED'"
                size="sm"
                variant="outline"
                @click="handleQuickAction(zone, 'RESUME')"
                class="text-xs"
              >
                ▶ Запустить
              </Button>
              <Button
                v-if="zone.status === 'ALARM' || zone.status === 'WARNING'"
                size="sm"
                variant="outline"
                @click="handleQuickAction(zone, 'FORCE_IRRIGATION')"
                class="text-xs text-emerald-400 border-emerald-700 hover:bg-emerald-950/20"
              >
                💧 Полив
              </Button>
            </div>
          </Card>
        </div>
      </div>
      <div v-else class="mb-6">
        <Card>
          <div class="text-sm text-neutral-400">Нет проблемных зон</div>
        </Card>
      </div>

      <!-- Мини-графики телеметрии (если есть зоны) -->
      <div v-if="hasZonesForTelemetry" class="mb-6">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-base font-semibold text-neutral-100">Телеметрия за 24 часа</h2>
          <div class="flex items-center gap-2 text-xs text-neutral-500">
            <div class="flex items-center gap-1.5">
              <div class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></div>
              <span>Обновляется в реальном времени</span>
            </div>
          </div>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
          <MiniTelemetryChart
            v-for="metric in telemetryMetrics"
            :key="metric.key"
            v-memo="[metric.data, metric.currentValue, metric.loading]"
            :label="metric.label"
            :data="metric.data"
            :current-value="metric.currentValue"
            :unit="metric.unit"
            :loading="metric.loading"
            :color="metric.color"
            :zone-id="firstZoneId"
            :metric="metric.key"
            @open-detail="handleOpenDetail"
          />
        </div>
      </div>

      <!-- Heatmap зон по статусам -->
      <div v-if="hasZones" class="mb-6">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-base font-semibold text-neutral-100">Статусы зон</h2>
          <Link href="/zones" class="text-xs text-sky-400 hover:text-sky-300 transition-colors">
            Все зоны →
          </Link>
        </div>
        <ZonesHeatmap :zones-by-status="zonesStatusSummary" />
      </div>
      </div>
    </template>
    <template #context>
      <div class="h-full flex flex-col">
        <div class="flex items-center justify-between mb-3">
          <div class="text-neutral-300 font-medium">Последние события</div>
          <div class="flex items-center gap-1.5 text-xs text-neutral-500">
            <div class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></div>
            <span>Live</span>
          </div>
        </div>
        
        <!-- Фильтр по типу событий -->
        <div class="mb-3 flex gap-1 flex-wrap">
          <button
            v-for="kind in ['ALL', 'ALERT', 'WARNING', 'INFO']"
            :key="kind"
            @click="eventFilter = kind"
            class="px-2.5 py-1 text-xs rounded-md border transition-all duration-200"
            :class="eventFilter === kind 
              ? 'border-neutral-600 bg-neutral-800 text-neutral-100' 
              : 'border-neutral-800 bg-neutral-900 text-neutral-400 hover:border-neutral-700'"
          >
            {{ kind === 'ALL' ? 'Все' : kind }}
          </button>
        </div>
        
        <div v-if="filteredEvents.length > 0" class="space-y-2 flex-1 overflow-y-auto scrollbar-thin scrollbar-thumb-neutral-800 scrollbar-track-transparent">
          <div 
            v-for="e in filteredEvents" 
            :key="e.id" 
            v-memo="[e.id, e.kind, e.message, e.occurred_at]"
            class="rounded-lg border p-2.5 transition-all duration-200 hover:shadow-md"
            :class="e.kind === 'ALERT' 
              ? 'border-red-800/50 bg-red-950/20' 
              : e.kind === 'WARNING' 
              ? 'border-amber-800/50 bg-amber-950/20' 
              : 'border-neutral-800 bg-neutral-925'"
          >
            <div class="flex items-start justify-between mb-1.5">
              <Badge 
                :variant="e.kind === 'ALERT' ? 'danger' : e.kind === 'WARNING' ? 'warning' : 'info'" 
                class="text-xs"
              >
                {{ e.kind }}
              </Badge>
              <span class="text-xs text-neutral-500">{{ formatTime(e.occurred_at || e.created_at) }}</span>
            </div>
            <div v-if="e.zone_id" class="text-xs text-neutral-400 mb-1.5">
              <Link :href="`/zones/${e.zone_id}`" class="text-sky-400 hover:text-sky-300 transition-colors">
                Зона #{{ e.zone_id }} →
              </Link>
            </div>
            <div class="text-sm text-neutral-200 leading-relaxed">
              {{ e.message }}
            </div>
          </div>
        </div>
        <div v-else class="text-neutral-500 text-sm text-center py-4">Нет событий</div>
      </div>
    </template>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, shallowRef } from 'vue'
import { Link, router } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import MiniTelemetryChart from '@/Components/MiniTelemetryChart.vue'
import ZonesHeatmap from '@/Components/ZonesHeatmap.vue'
import AgronomistDashboard from './Dashboards/AgronomistDashboard.vue'
import AdminDashboard from './Dashboards/AdminDashboard.vue'
import EngineerDashboard from './Dashboards/EngineerDashboard.vue'
import OperatorDashboard from './Dashboards/OperatorDashboard.vue'
import ViewerDashboard from './Dashboards/ViewerDashboard.vue'
import { translateStatus } from '@/utils/i18n'
import { formatTime } from '@/utils/formatTime'
import { logger } from '@/utils/logger'
import { useTelemetry } from '@/composables/useTelemetry'
import { useWebSocket } from '@/composables/useWebSocket'
import { useRole } from '@/composables/useRole'
import { useCommands } from '@/composables/useCommands'
import type { Zone, Greenhouse, Alert, ZoneEvent, EventKind } from '@/types'

interface DashboardData {
  greenhousesCount: number
  zonesCount: number
  devicesCount: number
  alertsCount: number
  zonesByStatus?: Record<string, number>
  nodesByStatus?: Record<string, number>
  greenhouses?: Greenhouse[]
  problematicZones?: Zone[]
  latestAlerts?: Alert[]
}

interface Props {
  dashboard: DashboardData
}

const props = defineProps<Props>()

const { isAgronomist, isAdmin, isEngineer, isOperator, isViewer } = useRole()

const zonesStatusSummary = computed(() => props.dashboard.zonesByStatus || {})
const nodesStatusSummary = computed(() => props.dashboard.nodesByStatus || {})
const hasAlerts = computed(() => {
  const alerts = props.dashboard.latestAlerts
  return alerts && Array.isArray(alerts) && alerts.length > 0
})
const hasGreenhouses = computed(() => {
  const gh = props.dashboard.greenhouses
  return gh && Array.isArray(gh) && gh.length > 0
})
const hasProblematicZones = computed(() => {
  const zones = props.dashboard.problematicZones
  return zones && Array.isArray(zones) && zones.length > 0
})

const hasZones = computed(() => {
  return props.dashboard.zonesCount > 0
})

const hasZonesForTelemetry = computed(() => {
  return props.dashboard.zonesCount > 0
})

// Телеметрия для мини-графиков
const { fetchAggregates } = useTelemetry()
const { subscribeToGlobalEvents } = useWebSocket()
// Используем shallowRef для больших объектов телеметрии
const telemetryData = shallowRef({
  ph: { data: [], currentValue: null, loading: false },
  ec: { data: [], currentValue: null, loading: false },
  temp: { data: [], currentValue: null, loading: false },
  humidity: { data: [], currentValue: null, loading: false },
})

// События для боковой панели - используем shallowRef для массива
const events = shallowRef<Array<ZoneEvent & { created_at?: string }>>([])
const eventFilter = ref<'ALL' | EventKind>('ALL')

// Объединяем события из props и WebSocket
// Мемоизируем propsEvents для избежания пересоздания при каждом рендере
const propsEvents = computed(() => {
  return (props.dashboard.latestAlerts || []).map(a => ({
    id: a.id,
    kind: 'ALERT' as const,
    message: a.details?.message || a.type,
    zone_id: a.zone_id,
    occurred_at: a.created_at,
    created_at: a.created_at
  }))
})

const allEvents = computed(() => {
  return [...events.value, ...propsEvents.value].sort((a, b) => {
    const timeA = new Date(a.occurred_at || a.created_at || 0).getTime()
    const timeB = new Date(b.occurred_at || b.created_at || 0).getTime()
    return timeB - timeA
  }).slice(0, 20)
})

const filteredEvents = computed(() => {
  if (eventFilter.value === 'ALL') {
    return allEvents.value
  }
  return allEvents.value.filter(e => e.kind === eventFilter.value)
})

// Получаем первую зону для отображения телеметрии (можно расширить для всех зон)
const firstZoneId = computed(() => {
  if (props.dashboard.problematicZones && props.dashboard.problematicZones.length > 0) {
    return props.dashboard.problematicZones[0].id
  }
  // Если нет проблемных зон, берем первую зону из списка
  if (props.dashboard.zones && props.dashboard.zones.length > 0) {
    return props.dashboard.zones[0].id
  }
  return null
})

// Обработчик клика на мини-график для перехода к детальному графику
function handleOpenDetail(zoneId: number, metric: string): void {
  if (zoneId) {
    router.visit(`/zones/${zoneId}`, {
      preserveScroll: false,
    })
  }
}

// Toast notifications для быстрых действий
function showToast(message: string, variant: 'success' | 'error' | 'warning' | 'info' = 'info', duration: number = 3000): void {
  // Используем простой console.log для Dashboard, так как здесь нет глобального toast
  console.log(`[Dashboard] ${variant.toUpperCase()}: ${message}`)
}

// Инициализация useCommands для быстрых действий
const { sendZoneCommand } = useCommands(showToast)

// Обработчик быстрых действий для проблемных зон
async function handleQuickAction(zone: Zone, action: 'PAUSE' | 'RESUME' | 'FORCE_IRRIGATION'): Promise<void> {
  try {
    if (action === 'PAUSE') {
      await sendZoneCommand(zone.id, 'PAUSE', {})
      showToast(`Зона "${zone.name}" приостановлена`, 'success')
    } else if (action === 'RESUME') {
      await sendZoneCommand(zone.id, 'RESUME', {})
      showToast(`Зона "${zone.name}" запущена`, 'success')
    } else if (action === 'FORCE_IRRIGATION') {
      await sendZoneCommand(zone.id, 'FORCE_IRRIGATION', {})
      showToast(`Запущен полив для зоны "${zone.name}"`, 'success')
    }
  } catch (error) {
    logger.error('[Dashboard] Failed to execute quick action:', error)
    showToast(`Ошибка выполнения действия для зоны "${zone.name}"`, 'error')
  }
}

// Мемоизируем метрики телеметрии для избежания пересоздания массива
const telemetryMetrics = computed(() => {
  const data = telemetryData.value
  return [
    {
      key: 'ph',
      label: 'pH',
      data: data.ph.data,
      currentValue: data.ph.currentValue,
      unit: '',
      loading: data.ph.loading,
      color: '#3b82f6'
    },
    {
      key: 'ec',
      label: 'EC',
      data: data.ec.data,
      currentValue: data.ec.currentValue,
      unit: 'мСм/см',
      loading: data.ec.loading,
      color: '#10b981'
    },
    {
      key: 'temp',
      label: 'Температура',
      data: data.temp.data,
      currentValue: data.temp.currentValue,
      unit: '°C',
      loading: data.temp.loading,
      color: '#f59e0b'
    },
    {
      key: 'humidity',
      label: 'Влажность',
      data: data.humidity.data,
      currentValue: data.humidity.currentValue,
      unit: '%',
      loading: data.humidity.loading,
      color: '#8b5cf6'
    }
  ]
})

async function loadTelemetryMetrics() {
  if (!firstZoneId.value) return

  const metrics = ['ph', 'ec', 'temp', 'humidity']
  
  for (const metric of metrics) {
    telemetryData.value[metric].loading = true
    try {
      const data = await fetchAggregates(firstZoneId.value, metric, '24h')
      telemetryData.value[metric].data = data.map(item => ({
        ts: new Date(item.ts).getTime(),
        value: item.value,
        avg: item.avg,
        min: item.min,
        max: item.max
      }))
      // Текущее значение - последнее значение из данных
      if (data.length > 0) {
        telemetryData.value[metric].currentValue = data[data.length - 1].value || data[data.length - 1].avg
      }
    } catch (err) {
      logger.error(`[Dashboard] Failed to load ${metric} telemetry:`, err)
    } finally {
      telemetryData.value[metric].loading = false
    }
  }
}

onMounted(async () => {
  if (hasZonesForTelemetry.value) {
    loadTelemetryMetrics()
  }
  
  // Подписаться на глобальные события с оптимизацией
  const { useBatchUpdates } = await import('@/composables/useOptimizedUpdates')
  const { add: addEvent, flush: flushEvents } = useBatchUpdates<any>(
    (eventBatch) => {
      // Применяем события пакетом
      eventBatch.forEach(event => {
        events.value.unshift({
          id: event.id,
          kind: event.kind,
          message: event.message,
          zone_id: event.zoneId,
          occurred_at: event.occurredAt,
          created_at: event.occurredAt
        })
      })
      
      // Ограничиваем список 20 событиями
      if (events.value.length > 20) {
        events.value = events.value.slice(0, 20)
      }
    },
    { debounceMs: 200, maxBatchSize: 5, maxWaitMs: 1000 }
  )
  
  subscribeToGlobalEvents((event) => {
    // Используем batch updates для оптимизации
    addEvent({
      id: event.id,
      kind: event.kind,
      message: event.message,
      zoneId: event.zoneId,
      occurredAt: event.occurredAt
    })
  })
})

</script>


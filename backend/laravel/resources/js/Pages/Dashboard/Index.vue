<template>
  <AppLayout>
    <template #default>
      <h1 class="text-lg font-semibold mb-4">Панель управления</h1>
      
      <!-- Основные статистики -->
      <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 mb-6">
        <Card>
          <div class="text-neutral-400 text-sm mb-1">Теплицы</div>
          <div class="text-3xl font-bold">{{ dashboard.greenhousesCount }}</div>
        </Card>
        <Card>
          <div class="text-neutral-400 text-sm mb-1">Зоны</div>
          <div class="text-3xl font-bold">{{ dashboard.zonesCount }}</div>
          <div v-if="zonesStatusSummary" class="text-xs text-neutral-500 mt-1">
            <span v-if="zonesStatusSummary.RUNNING">Запущено: {{ zonesStatusSummary.RUNNING }}</span>
            <span v-if="zonesStatusSummary.PAUSED" class="ml-2">Приостановлено: {{ zonesStatusSummary.PAUSED }}</span>
            <span v-if="zonesStatusSummary.ALARM" class="ml-2 text-red-400">Тревога: {{ zonesStatusSummary.ALARM }}</span>
            <span v-if="zonesStatusSummary.WARNING" class="ml-2 text-amber-400">Предупреждение: {{ zonesStatusSummary.WARNING }}</span>
          </div>
        </Card>
        <Card>
          <div class="text-neutral-400 text-sm mb-1">Устройства</div>
          <div class="text-3xl font-bold">{{ dashboard.devicesCount }}</div>
          <div v-if="nodesStatusSummary" class="text-xs text-neutral-500 mt-1">
            <span v-if="nodesStatusSummary.online" class="text-emerald-400">Онлайн: {{ nodesStatusSummary.online }}</span>
            <span v-if="nodesStatusSummary.offline" class="ml-2 text-red-400">Офлайн: {{ nodesStatusSummary.offline }}</span>
          </div>
        </Card>
        <Card>
          <div class="text-neutral-400 text-sm mb-1">Активные алерты</div>
          <div class="text-3xl font-bold" :class="dashboard.alertsCount > 0 ? 'text-red-400' : 'text-emerald-400'">
            {{ dashboard.alertsCount }}
          </div>
        </Card>
      </div>

      <!-- Теплицы -->
      <div v-if="hasGreenhouses" class="mb-6">
        <h2 class="text-md font-semibold mb-3">Теплицы</h2>
        <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          <Card 
            v-for="gh in dashboard.greenhouses" 
            :key="gh.id" 
            v-memo="[gh.id, gh.name, gh.zones_count, gh.zones_running]"
            class="hover:border-neutral-700 transition-colors"
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
        <h2 class="text-md font-semibold mb-3">Проблемные зоны</h2>
        <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          <Card 
            v-for="zone in dashboard.problematicZones" 
            :key="zone.id" 
            v-memo="[zone.id, zone.status, zone.alerts_count]"
            class="hover:border-neutral-700 transition-colors"
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
            <div v-if="zone.alerts_count > 0" class="text-xs text-red-400">
              Активных алертов: {{ zone.alerts_count }}
            </div>
            <div class="mt-3">
              <Link :href="`/zones/${zone.id}`">
                <Button size="sm" variant="secondary">Подробнее</Button>
              </Link>
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
        <h2 class="text-md font-semibold mb-3">Телеметрия за 24 часа</h2>
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
          />
        </div>
      </div>

      <!-- Heatmap зон по статусам -->
      <div v-if="hasZones" class="mb-6">
        <h2 class="text-md font-semibold mb-3">Статусы зон</h2>
        <ZonesHeatmap :zones-by-status="zonesStatusSummary" />
      </div>
    </template>
    <template #context>
      <div class="h-full flex flex-col">
        <div class="text-neutral-300 font-medium mb-3">Последние события</div>
        
        <!-- Фильтр по типу событий -->
        <div class="mb-2 flex gap-1">
          <button
            v-for="kind in ['ALL', 'ALERT', 'WARNING', 'INFO']"
            :key="kind"
            @click="eventFilter = kind"
            class="px-2 py-1 text-xs rounded border"
            :class="eventFilter === kind ? 'border-neutral-600 bg-neutral-800' : 'border-neutral-800 bg-neutral-900'"
          >
            {{ kind === 'ALL' ? 'Все' : kind }}
          </button>
        </div>
        
        <div v-if="filteredEvents.length > 0" class="space-y-2 flex-1 overflow-y-auto">
          <div 
            v-for="e in filteredEvents" 
            :key="e.id" 
            v-memo="[e.id, e.kind, e.message, e.occurred_at]"
            class="rounded-lg border border-neutral-800 bg-neutral-925 p-2"
          >
            <div class="flex items-start justify-between mb-1">
              <Badge 
                :variant="e.kind === 'ALERT' ? 'danger' : e.kind === 'WARNING' ? 'warning' : 'info'" 
                class="text-xs"
              >
                {{ e.kind }}
              </Badge>
              <span class="text-xs text-neutral-500">{{ formatTime(e.occurred_at || e.created_at) }}</span>
            </div>
            <div v-if="e.zone_id" class="text-xs text-neutral-500 mb-1">
              Зона ID: {{ e.zone_id }}
            </div>
            <div class="text-sm text-neutral-300 mt-1">
              {{ e.message }}
            </div>
          </div>
        </div>
        <div v-else class="text-neutral-500 text-sm">Нет событий</div>
      </div>
    </template>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, shallowRef } from 'vue'
import { Link } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import MiniTelemetryChart from '@/Components/MiniTelemetryChart.vue'
import ZonesHeatmap from '@/Components/ZonesHeatmap.vue'
import { translateStatus } from '@/utils/i18n'
import { formatTime } from '@/utils/formatTime'
import { useTelemetry } from '@/composables/useTelemetry'
import { useWebSocket } from '@/composables/useWebSocket'
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
  return null
})

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
      console.error(`Failed to load ${metric} telemetry:`, err)
    } finally {
      telemetryData.value[metric].loading = false
    }
  }
}

onMounted(() => {
  if (hasZonesForTelemetry.value) {
    loadTelemetryMetrics()
  }
  
  // Подписаться на глобальные события
  subscribeToGlobalEvents((event) => {
    // Добавляем событие в начало списка
    events.value.unshift({
      id: event.id,
      kind: event.kind,
      message: event.message,
      zone_id: event.zoneId,
      occurred_at: event.occurredAt,
      created_at: event.occurredAt
    })
    
    // Ограничиваем список 20 событиями
    if (events.value.length > 20) {
      events.value = events.value.slice(0, 20)
    }
  })
})

</script>


<template>
  <div
    v-if="open"
    class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[color:var(--bg-main)]/80 backdrop-blur-sm"
    @click.self="$emit('close')"
  >
    <div class="bg-[color:var(--bg-surface-strong)] border border-[color:var(--border-muted)] rounded-lg shadow-[var(--shadow-card)] w-full max-w-7xl max-h-[90vh] flex flex-col">
      <!-- Header -->
      <div class="flex items-center justify-between p-4 border-b border-[color:var(--border-muted)]">
        <h2 class="text-lg font-semibold">Сравнение зон</h2>
        <button
          @click="$emit('close')"
          class="p-1.5 rounded hover:bg-[color:var(--bg-elevated)] transition-colors"
        >
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <!-- Content -->
      <div class="flex-1 overflow-y-auto p-4">
        <!-- Выбор зон -->
        <div class="mb-4">
          <label class="text-sm font-medium mb-2 block">Выберите зоны для сравнения (2-5 зон):</label>
          <div class="flex flex-wrap gap-2">
            <button
              v-for="zone in availableZones"
              :key="zone.id"
              @click="toggleZone(zone.id)"
              class="px-3 py-1.5 rounded border text-sm transition-colors"
              :class="selectedZoneIds.includes(zone.id)
                ? 'border-[color:var(--accent-cyan)] bg-[color:var(--badge-info-bg)] text-[color:var(--badge-info-text)]'
                : 'border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] text-[color:var(--text-muted)] hover:border-[color:var(--border-strong)]'"
            >
              {{ zone.name }}
              <span v-if="selectedZoneIds.includes(zone.id)" class="ml-1">✓</span>
            </button>
          </div>
          <div v-if="selectedZoneIds.length < 2" class="text-xs text-[color:var(--accent-amber)] mt-2">
            Выберите минимум 2 зоны для сравнения
          </div>
        </div>

        <!-- Сравнительная таблица метрик -->
        <div v-if="selectedZoneIds.length >= 2" class="mb-6">
          <h3 class="text-sm font-semibold mb-3">Текущие метрики</h3>
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="border-b border-[color:var(--border-muted)]">
                  <th class="text-left p-2 text-[color:var(--text-muted)]">Метрика</th>
                  <th
                    v-for="zoneId in selectedZoneIds"
                    :key="zoneId"
                    class="text-left p-2 text-[color:var(--text-muted)]"
                  >
                    {{ getZoneName(zoneId) }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="metric in metrics" :key="metric.key" class="border-b border-[color:var(--border-muted)]">
                  <td class="p-2 font-medium">{{ metric.label }}</td>
                  <td
                    v-for="zoneId in selectedZoneIds"
                    :key="zoneId"
                    class="p-2"
                  >
                    <div class="flex items-center gap-2">
                      <span>{{ formatMetricValue(zoneId, metric.key) }}</span>
                      <span v-if="metric.unit" class="text-xs text-[color:var(--text-dim)]">{{ metric.unit }}</span>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Графики сравнения -->
        <div v-if="selectedZoneIds.length >= 2 && !loading" class="space-y-4">
          <div v-for="metric in chartMetrics" :key="metric.key">
            <h3 class="text-sm font-semibold mb-2">{{ metric.label }}</h3>
            <Card>
              <MultiSeriesTelemetryChart
                :title="metric.label"
                :series="getChartSeries(metric.key)"
                :time-range="timeRange"
                @time-range-change="onTimeRangeChange"
              />
            </Card>
          </div>
        </div>

        <!-- Loading state -->
        <div v-if="loading" class="flex items-center justify-center py-12">
          <LoadingState loading size="lg" />
        </div>
      </div>

      <!-- Footer -->
      <div class="flex items-center justify-between p-4 border-t border-[color:var(--border-muted)]">
        <div class="text-xs text-[color:var(--text-muted)]">
          Выбрано зон: {{ selectedZoneIds.length }}
        </div>
        <div class="flex gap-2">
          <Button
            size="sm"
            variant="outline"
            @click="exportComparison"
            :disabled="selectedZoneIds.length < 2 || loading"
          >
            📥 Экспорт данных
          </Button>
          <Button
            size="sm"
            variant="secondary"
            @click="$emit('close')"
          >
            Закрыть
          </Button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import LoadingState from '@/Components/LoadingState.vue'
import MultiSeriesTelemetryChart from '@/Components/MultiSeriesTelemetryChart.vue'
import { useTelemetry } from '@/composables/useTelemetry'
import { useTheme } from '@/composables/useTheme'
import type { Zone, TelemetrySample } from '@/types'

type TimeRange = '1H' | '24H' | '7D' | '30D' | 'ALL'

interface Props {
  open: boolean
  zones: Zone[]
}

const props = defineProps<Props>()
const emit = defineEmits<{
  close: []
}>()

const { fetchAggregates } = useTelemetry()
const { theme } = useTheme()

const selectedZoneIds = ref<number[]>([])
const timeRange = ref<TimeRange>('24H')
const loading = ref(false)
const telemetryData = ref<Map<number, Map<string, TelemetrySample[]>>>(new Map())
const requestVersion = ref(0)

const availableZones = computed(() => props.zones)
const hasMinimumSelection = computed(() => selectedZoneIds.value.length >= 2)

const metrics = [
  { key: 'ph', label: 'pH', unit: '' },
  { key: 'ec', label: 'EC', unit: 'мСм/см' },
  { key: 'temperature', label: 'Температура', unit: '°C' },
  { key: 'humidity', label: 'Влажность', unit: '%' },
]

const chartMetrics = [
  { key: 'ph', label: 'pH' },
  { key: 'ec', label: 'EC' },
]

const resolveCssColor = (variable: string, fallback: string): string => {
  if (typeof window === 'undefined') {
    return fallback
  }
  const value = getComputedStyle(document.documentElement).getPropertyValue(variable).trim()
  return value || fallback
}

const chartPalette = computed(() => {
  theme.value
  return [
    resolveCssColor('--accent-cyan', '#3b82f6'),
    resolveCssColor('--accent-green', '#10b981'),
    resolveCssColor('--accent-amber', '#f59e0b'),
    resolveCssColor('--accent-red', '#ef4444'),
    resolveCssColor('--accent-lime', '#8b5cf6'),
  ]
})

function toggleZone(zoneId: number): void {
  const index = selectedZoneIds.value.indexOf(zoneId)
  if (index > -1) {
    selectedZoneIds.value.splice(index, 1)
  } else {
    if (selectedZoneIds.value.length < 5) {
      selectedZoneIds.value.push(zoneId)
    }
  }
}

function getZoneName(zoneId: number): string {
  const zone = props.zones.find(z => z.id === zoneId)
  return zone?.name || `Зона ${zoneId}`
}

function formatMetricValue(zoneId: number, metricKey: string): string {
  const zone = props.zones.find(z => z.id === zoneId)
  if (!zone?.telemetry) return '-'
  
  const value = (zone.telemetry as any)[metricKey]
  if (value === null || value === undefined) return '-'
  
  if (metricKey === 'ph') {
    return value.toFixed(2)
  }
  return value.toFixed(1)
}

function getChartSeries(metricKey: string) {
  return selectedZoneIds.value.map((zoneId, index) => {
    const zone = props.zones.find(z => z.id === zoneId)
    const data = telemetryData.value.get(zoneId)?.get(metricKey) || []
    
    return {
      name: getZoneName(zoneId),
      label: getZoneName(zoneId),
      color: chartPalette.value[index % chartPalette.value.length],
      data: data.map(d => ({
        ts: d.ts,
        value: d.value !== undefined ? d.value : d.avg || 0,
      })),
      currentValue: formatMetricValue(zoneId, metricKey),
    }
  })
}

async function loadTelemetryData(): Promise<void> {
  if (!hasMinimumSelection.value) return

  const currentRequest = ++requestVersion.value
  loading.value = true
  telemetryData.value.clear()

  const period = timeRange.value === '1H' ? '1h' :
                 timeRange.value === '24H' ? '24h' :
                 timeRange.value === '7D' ? '7d' :
                 timeRange.value === '30D' ? '30d' : '30d'

  const zoneSnapshot = [...selectedZoneIds.value]

  try {
    const promises = zoneSnapshot.flatMap(zoneId =>
      chartMetrics.map(async (metric) => {
        try {
          const data = await fetchAggregates(zoneId, metric.key, period, true)
          if (requestVersion.value !== currentRequest) return
          if (!telemetryData.value.has(zoneId)) {
            telemetryData.value.set(zoneId, new Map())
          }
          telemetryData.value.get(zoneId)?.set(metric.key, data)
        } catch (err) {
          import('@/utils/logger').then(({ logger }) => {
            logger.error(`[ZoneComparisonModal] Failed to load ${metric.key} for zone ${zoneId}:`, err)
          })
        }
      })
    )

    await Promise.all(promises)
  } finally {
    if (requestVersion.value === currentRequest) {
      loading.value = false
    }
  }
}

function onTimeRangeChange(range: TimeRange): void {
  timeRange.value = range
}

function exportComparison(): void {
  if (selectedZoneIds.value.length < 2) return
  
  const csvRows: string[] = []
  
  // Заголовки
  const headers = ['Timestamp', ...selectedZoneIds.value.map(id => `${getZoneName(id)} pH`), ...selectedZoneIds.value.map(id => `${getZoneName(id)} EC`)]
  csvRows.push(headers.join(','))
  
  // Объединяем данные по временным меткам
  const allTimestamps = new Set<number>()
  selectedZoneIds.value.forEach(zoneId => {
    chartMetrics.forEach(metric => {
      const data = telemetryData.value.get(zoneId)?.get(metric.key) || []
      data.forEach(d => allTimestamps.add(d.ts))
    })
  })
  
  const sortedTimestamps = Array.from(allTimestamps).sort((a, b) => a - b)
  
  sortedTimestamps.forEach(ts => {
    const row: (string | number)[] = [new Date(ts).toISOString()]
    
    // pH значения
    selectedZoneIds.value.forEach(zoneId => {
      const data = telemetryData.value.get(zoneId)?.get('ph') || []
      const point = data.find(d => d.ts === ts)
      const value = point?.value !== undefined ? point.value : point?.avg
      row.push(value !== undefined ? value.toFixed(2) : '')
    })
    
    // EC значения
    selectedZoneIds.value.forEach(zoneId => {
      const data = telemetryData.value.get(zoneId)?.get('ec') || []
      const point = data.find(d => d.ts === ts)
      const value = point?.value !== undefined ? point.value : point?.avg
      row.push(value !== undefined ? value.toFixed(1) : '')
    })
    
    csvRows.push(row.join(','))
  })
  
  const csvString = csvRows.join('\n')
  const blob = new Blob([csvString], { type: 'text/csv;charset=utf-8;' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.setAttribute('download', `zones_comparison_${new Date().toISOString().slice(0, 10)}.csv`)
  link.click()
}

function resetComparisonState() {
  if (selectedZoneIds.value.length > 0) {
    selectedZoneIds.value = []
  }
  telemetryData.value.clear()
  loading.value = false
  requestVersion.value += 1
}

watch(
  () => [selectedZoneIds.value.slice(), timeRange.value, props.open],
  ([zones, , isOpen]) => {
    if (!isOpen) {
      resetComparisonState()
      return
    }

    if (zones.length < 2) {
      telemetryData.value.clear()
      return
    }

    loadTelemetryData()
  },
  { immediate: true }
)
</script>

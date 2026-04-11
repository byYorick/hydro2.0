<template>
  <AppLayout>
    <div class="flex items-center justify-between mb-3">
      <div>
        <div class="text-lg font-semibold">
          {{ device.uid || device.name || device.id }}
        </div>
        <div class="text-xs text-[color:var(--text-muted)]">
          <span v-if="linkedZoneId">
            <Link
              :href="`/zones/${linkedZoneId}`"
              class="text-[color:var(--accent-cyan)] hover:underline"
            >Zone: {{ linkedZoneName }}</Link>
          </span>
          <span v-else>Zone: -</span>
          · Type: {{ device.type || '-' }}
          <span v-if="device.fw_version"> · FW: {{ device.fw_version }}</span>
        </div>
      </div>
      <div class="flex items-center gap-2">
        <Badge :variant="device.status === 'online' ? 'success' : device.status === 'offline' ? 'danger' : 'neutral'">
          {{ device.status?.toUpperCase() || 'UNKNOWN' }}
        </Badge>
        <NodeLifecycleBadge
          v-if="device.lifecycle_state"
          :lifecycle-state="device.lifecycle_state"
        />
        <Button
          size="sm"
          variant="secondary"
          @click="onRestart"
        >
          Перезапустить
        </Button>
      </div>
    </div>

    <!-- Визуализация связи с зоной -->
    <Card
      v-if="hasZoneAssignment"
      class="mb-3"
    >
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-3">
          <div class="w-12 h-12 rounded-lg border-2 border-[color:var(--border-strong)] bg-[color:var(--bg-elevated)] flex items-center justify-center">
            <span class="text-2xl">🌱</span>
          </div>
          <div>
            <div class="text-sm font-semibold text-[color:var(--text-primary)]">
              {{ zoneAssignmentTitle }}
            </div>
            <template v-if="linkedZoneId">
              <Link
                :href="`/zones/${linkedZoneId}`"
                class="text-[color:var(--accent-cyan)] hover:underline text-sm"
              >
                {{ linkedZoneName }}
              </Link>
            </template>
            <div
              v-else
              class="text-sm text-[color:var(--text-muted)]"
            >
              Зона ещё не определена
            </div>
            <div
              v-if="device.zone?.status"
              class="text-xs text-[color:var(--text-muted)] mt-1"
            >
              Статус: {{ device.zone.status }}
            </div>
            <div
              v-else-if="device.pending_zone_id && !device.zone_id"
              class="text-xs text-[color:var(--text-muted)] mt-1"
            >
              Ожидается подтверждение привязки от ноды
            </div>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <Link
            v-if="linkedZoneId"
            :href="`/zones/${linkedZoneId}`"
          >
            <Button
              size="sm"
              variant="outline"
            >
              Перейти к зоне →
            </Button>
          </Link>
          <button 
            v-if="device.zone_id"
            :disabled="detaching"
            class="inline-flex items-center justify-center rounded-md font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-[color:var(--accent-red)]/50 h-8 px-3 text-xs bg-[color:var(--badge-danger-bg)] text-[color:var(--badge-danger-text)] border border-[color:var(--badge-danger-border)] hover:border-[color:var(--accent-red)] disabled:opacity-50 disabled:cursor-not-allowed"
            @click="detachNode"
          >
            <svg
              v-if="!detaching"
              class="w-4 h-4 mr-2"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
            <span v-if="detaching">Отвязка...</span>
            <span v-else>Отвязать от зоны</span>
          </button>
        </div>
      </div>
    </Card>
    <Card
      v-else
      class="mb-3 border-[color:var(--badge-warning-border)] bg-[color:var(--badge-warning-bg)]"
    >
      <div class="flex items-center gap-2 text-[color:var(--badge-warning-text)]">
        <svg
          class="w-5 h-5"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
          />
        </svg>
        <span class="text-sm">Устройство не привязано к зоне</span>
      </div>
    </Card>

    <!-- Графики телеметрии для сенсорных каналов (раздельно) -->
    <div
      v-if="sensorChannels.length > 0"
      class="mb-3 space-y-3"
    >
      <template
        v-for="(channel, index) in sensorChannels"
        :key="channel?.channel || index"
      >
        <MultiSeriesTelemetryChart
          v-if="channel && getChartSeriesForChannel(channel).length > 0"
          :title="getChartTitleForChannel(channel)"
          :series="getChartSeriesForChannel(channel)"
          :time-range="chartTimeRange"
          @time-range-change="onChartTimeRangeChange"
        />
      </template>
      <Card
        v-if="sensorChannels.length > 0 && !hasChartData"
        class="text-center text-sm text-[color:var(--text-dim)] py-8"
      >
        <div>Загрузка данных телеметрии...</div>
      </Card>
    </div>

    <div class="grid grid-cols-1 xl:grid-cols-3 gap-3">
      <Card class="xl:col-span-2">
        <div class="flex items-center justify-between gap-2 mb-2">
          <div>
            <div class="text-sm font-semibold">
              Channels
            </div>
            <div class="text-xs text-[color:var(--text-dim)]">
              <span v-if="configLoading">Обновляем конфиг...</span>
              <span v-else>Текущий конфиг ноды (read-only)</span>
              <span
                v-if="configError"
                class="text-[color:var(--accent-amber)] ml-2"
              >{{ configError }}</span>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              :disabled="configLoading"
              @click="loadNodeConfig"
            >
              {{ configLoading ? 'Обновление...' : 'Обновить' }}
            </Button>
          </div>
        </div>
        <DeviceChannelsTable 
          :channels="displayChannels" 
          :node-type="device.type"
          :testing-channels="testingChannels"
          @test="onTestPump" 
        />
      </Card>
      <Card>
        <div class="flex items-center justify-between mb-2">
          <div class="text-sm font-semibold">
            NodeConfig
          </div>
          <div
            v-if="configLoading"
            class="text-[11px] text-[color:var(--text-dim)]"
          >
            Загрузка...
          </div>
        </div>
        <div class="text-[11px] text-[color:var(--text-dim)] mb-2">
          Конфиг присылается нодой через config_report и хранится на сервере.
        </div>
        <pre class="text-xs text-[color:var(--text-muted)] overflow-auto">{{ nodeConfig }}</pre>
      </Card>
    </div>

    <ConfirmModal
      :open="detachModalOpen"
      title="Отвязать ноду"
      message="Отвязать ноду от зоны? Нода будет сброшена в состояние «Зарегистрирована»."
      confirm-text="Отвязать"
      confirm-variant="danger"
      :loading="detaching"
      @close="detachModalOpen = false"
      @confirm="confirmDetachNode"
    />
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, ref, watch, onMounted, onUnmounted } from 'vue'
import { Link, usePage } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import ConfirmModal from '@/Components/ConfirmModal.vue'
import NodeLifecycleBadge from '@/Components/NodeLifecycleBadge.vue'
// @ts-ignore
import DeviceChannelsTable from '@/Pages/Devices/DeviceChannelsTable.vue'
import MultiSeriesTelemetryChart from '@/Components/MultiSeriesTelemetryChart.vue'
import { logger } from '@/utils/logger'
import { useHistory } from '@/composables/useHistory'
import { useToast } from '@/composables/useToast'
import { api } from '@/services/api'
import { useDevicesStore } from '@/stores/devices'
import { useNodeTelemetry } from '@/composables/useNodeTelemetry'
import { useTheme } from '@/composables/useTheme'
import { useDeviceCommandActions } from '@/composables/useDeviceCommandActions'
import type { Device, DeviceChannel } from '@/types'

interface PageProps {
  device?: Device
  [key: string]: any
}

const page = usePage<PageProps>()
const device = computed(() => (page.props.device || {}) as Device)
const channels = computed(() => (device.value.channels || []) as DeviceChannel[])
const linkedZoneId = computed<number | null>(() => {
  return device.value.zone?.id ?? device.value.zone_id ?? device.value.pending_zone_id ?? null
})
const linkedZoneName = computed(() => {
  if (device.value.zone?.name) {
    return device.value.zone.name
  }

  if (device.value.zone_id) {
    return `Zone #${device.value.zone_id}`
  }

  if (device.value.pending_zone_id) {
    return `Zone #${device.value.pending_zone_id}`
  }

  return '-'
})
const hasZoneAssignment = computed(() => linkedZoneId.value !== null)
const zoneAssignmentTitle = computed(() => {
  if (device.value.zone_id) {
    return 'Привязано к зоне'
  }

  if (device.value.pending_zone_id) {
    return 'Привязка к зоне в процессе'
  }

  return 'Устройство не привязано к зоне'
})
const nodeConfigData = ref<any | null>(null)
const configLoading = ref(false)
const configError = ref('')
const { showToast } = useToast()
const devicesStore = useDevicesStore()
const { theme } = useTheme()
const {
  testingChannels,
  detaching,
  detachModalOpen,
  onRestart,
  detachNode,
  confirmDetachNode,
  onTestPump,
} = useDeviceCommandActions({
  device,
  showToast,
  upsertDevice: (updatedDevice) => devicesStore.upsert(updatedDevice),
})

// Графики телеметрии
const chartTimeRange = ref<'1H' | '24H' | '7D' | '30D' | 'ALL'>('24H')
const chartDataByChannel = ref<Record<string, Array<{ ts: number; value: number }>>>({})

// Приоритеты метрик для сортировки (меньше = выше приоритет)
const METRIC_PRIORITY: Record<string, number> = {
  'TEMPERATURE': 1,
  'HUMIDITY': 2,
}

const getMetricPriority = (metric: string): number => {
  return METRIC_PRIORITY[metric] ?? 999
}

// Определяем сенсорные каналы (для которых нужны графики)
// Сортируем так, чтобы температура была первой, влажность второй
const sensorChannels = computed(() => {
  const sensors = channels.value.filter(ch => (ch.type || '').toString().toLowerCase() === 'sensor')
  
  return sensors.sort((a, b) => {
    const aMetric = getMetricFromChannel(a)
    const bMetric = getMetricFromChannel(b)
    return getMetricPriority(aMetric) - getMetricPriority(bMetric)
  })
})

// Каналы из NodeConfig (приоритетнее данных из БД)
const configChannels = computed(() => {
  const cfg = nodeConfigData.value
  if (cfg?.channels && Array.isArray(cfg.channels) && cfg.channels.length > 0) {
    return cfg.channels.map((ch: any) => ({
      channel: ch.name || ch.channel,
      name: ch.name || ch.channel,
      type: ch.type || ch.channel_type,
      metric: ch.metric || ch.metrics || null,
      unit: ch.unit || null,
      actuator_type: ch.actuator_type || ch.config?.actuator_type,
      description: ch.description || ch.config?.description || null,
      config: ch,
    }))
  }
  return []
})

const displayChannels = computed(() => {
  if (configChannels.value.length > 0) {
    return configChannels.value
  }
  return channels.value
})

const resolveCssColor = (variable: string, fallback: string): string => {
  if (typeof window === 'undefined') {
    return fallback
  }
  const value = getComputedStyle(document.documentElement).getPropertyValue(variable).trim()
  return value || fallback
}

// Константы для метрик
const METRIC_COLORS = computed<Record<string, string>>(() => {
  theme.value
  return {
    TEMPERATURE: resolveCssColor('--accent-amber', '#f59e0b'),
    HUMIDITY: resolveCssColor('--accent-cyan', '#3b82f6'),
    CO2: resolveCssColor('--accent-green', '#10b981'),
    PH: resolveCssColor('--accent-lime', '#8b5cf6'),
    EC: resolveCssColor('--accent-cyan', '#06b6d4'),
    DEFAULT: resolveCssColor('--accent-cyan', '#3b82f6'),
  }
})

const METRIC_LABELS: Record<string, string> = {
  'TEMPERATURE': 'Температура',
  'HUMIDITY': 'Влажность',
  'CO2': 'CO₂',
  'PH': 'pH',
  'EC': 'EC',
}

const METRIC_NORMALIZATION: Record<string, string> = {
  'TEMPERATURE': 'TEMPERATURE',
  'HUMIDITY': 'HUMIDITY',
  'CO2': 'CO2',
  'PH': 'PH',
  'EC': 'EC',
}

// Утилиты для работы с метриками
const getMetricFromChannel = (channel: DeviceChannel): string => {
  return String(channel.metric || channel.channel.toUpperCase())
}

const getMetricColor = (metric: string, fallback?: string): string => {
  return METRIC_COLORS.value[metric] || fallback || METRIC_COLORS.value.DEFAULT
}

const getMetricLabel = (metric: string, fallback?: string): string => {
  return METRIC_LABELS[metric] || fallback || metric
}

const normalizeMetricForQuery = (metric: string): string => {
  return METRIC_NORMALIZATION[metric] || metric
}

const getCurrentValue = (data: Array<{ ts: number; value: number }>): number | undefined => {
  if (data.length === 0) return undefined
  const lastValue = data[data.length - 1].value
  return typeof lastValue === 'number' && !isNaN(lastValue) ? lastValue : undefined
}

// Константы для временных диапазонов (в миллисекундах)
const TIME_RANGE_MS: Record<string, number> = {
  '1H': 60 * 60 * 1000,
  '24H': 24 * 60 * 60 * 1000,
  '7D': 7 * 24 * 60 * 60 * 1000,
  '30D': 30 * 24 * 60 * 60 * 1000,
}

// Получить дату "от" для временного диапазона
const getTimeRangeFrom = (timeRange: string): Date | undefined => {
  if (timeRange === 'ALL') return undefined
  const ms = TIME_RANGE_MS[timeRange]
  return ms ? new Date(Date.now() - ms) : undefined
}

// Проверка наличия данных для графиков
const hasChartData = computed(() => {
  return sensorChannels.value.some(channel => {
    const data = chartDataByChannel.value[channel.channel]
    return data && data.length > 0
  })
})

// Получить серию для конкретного канала (для раздельных графиков)
function getChartSeriesForChannel(channel: DeviceChannel | undefined) {
  if (!channel || !channel.channel) {
    return []
  }
  
  const metric = getMetricFromChannel(channel)
  const data = chartDataByChannel.value[channel.channel] || []
  const color = getMetricColor(metric)
  const label = getMetricLabel(metric, channel.channel)
  const currentValue = getCurrentValue(data)
  
  return [{
    name: channel.channel,
    label: `${label} (${channel.unit || ''})`,
    color,
    data,
    currentValue,
    yAxisIndex: 0,
  }]
}

// Получить заголовок для графика канала
function getChartTitleForChannel(channel: DeviceChannel | undefined): string {
  if (!channel) {
    return 'Телеметрия'
  }
  
  const metric = getMetricFromChannel(channel)
  const label = getMetricLabel(metric, channel.channel)
  return `${label}${channel.unit ? ` (${channel.unit})` : ''}`
}

// История просмотров
const { addToHistory } = useHistory()

// Добавляем устройство в историю просмотров
watch(device, (newDevice) => {
  if (newDevice?.id) {
    addToHistory({
      id: newDevice.id,
      type: 'device',
      name: newDevice.name || newDevice.uid || `Устройство ${newDevice.id}`,
      url: `/devices/${newDevice.id}`
    })
  }
}, { immediate: true })

const nodeConfig = computed(() => {
  if (nodeConfigData.value) {
    return JSON.stringify(nodeConfigData.value, null, 2)
  }

  const fallback = {
    id: device.value.uid || device.value.id,
    name: device.value.name,
    type: device.value.type,
    status: device.value.status,
    fw_version: device.value.fw_version,
    config: device.value.config,
    channels: displayChannels.value.map((c: any) => ({
      channel: c.channel,
      type: c.type,
      metric: c.metric,
      unit: c.unit,
    })),
  }
  return JSON.stringify(fallback, null, 2)
})

const loadNodeConfig = async (): Promise<void> => {
  if (!device.value.id) return

  configLoading.value = true
  configError.value = ''
  try {
    const payload = await api.nodes.getConfig(device.value.id)
    nodeConfigData.value = payload && typeof payload === 'object' && !Array.isArray(payload) ? payload : null
  } catch (error) {
    configError.value = 'Не удалось загрузить конфиг'
    logger.error('[Devices/Show] Failed to load node config', error)
  } finally {
    configLoading.value = false
  }
}

// Загрузка данных телеметрии для графиков
async function loadChartData(channel: string, metric: string, timeRange: string): Promise<Array<{ ts: number; value: number }>> {
  if (!device.value.id) {
    return []
  }

  try {
    const normalizedMetric = normalizeMetricForQuery(metric)
    const from = getTimeRangeFrom(timeRange)
    
    logger.debug(`[Devices/Show] Loading telemetry: channel=${channel}, metric=${metric}, normalized=${normalizedMetric}`)
    
    const rows = await api.nodes.getTelemetryHistory(device.value.id, {
      metric: normalizedMetric,
      channel,
      from: from?.toISOString(),
    })

    if (Array.isArray(rows) && rows.length > 0) {
      logger.debug(`[Devices/Show] Loaded ${rows.length} telemetry records for ${channel}`)
      return rows.map((item) => ({
        ts: new Date(item.ts).getTime(),
        value: item.value,
      }))
    }

    logger.warn(`[Devices/Show] No data received for channel ${channel}`)
    return []
  } catch (err) {
    logger.error(`[Devices/Show] Failed to load telemetry for channel ${channel}:`, err)
    return []
  }
}

// Загрузка всех графиков
async function loadAllCharts(): Promise<void> {
  if (sensorChannels.value.length === 0) {
    return
  }
  
  for (const channel of sensorChannels.value) {
    const metric = String(channel.metric || channel.channel.toUpperCase())
    const data = await loadChartData(channel.channel, metric, chartTimeRange.value)
    chartDataByChannel.value[channel.channel] = data
  }
}

// Обработчик изменения временного диапазона
function onChartTimeRangeChange(newRange: '1H' | '24H' | '7D' | '30D' | 'ALL'): void {
  chartTimeRange.value = newRange
  loadAllCharts()
}

// WebSocket подписка на телеметрию
const nodeId = computed(() => device.value.id)
const zoneId = computed(() => device.value.zone?.id ?? null)
const { subscribe: subscribeTelemetry, unsubscribe: unsubscribeTelemetry } = useNodeTelemetry(nodeId, zoneId)
let unsubscribeTelemetryFn: (() => void) | null = null

// Обработчик обновления телеметрии через WebSocket
const handleTelemetryUpdate = (data: { node_id: number; channel: string | null; metric_type: string; value: number; ts: number }) => {
  try {
    // Пропускаем данные с null channel
    if (!data.channel) {
      return
    }

    const channelName = data.channel
    const channel = sensorChannels.value.find(ch => ch.channel === channelName)
    if (!channel) {
      return
    }

    // Получаем или создаем массив данных для канала
    if (!chartDataByChannel.value[channelName]) {
      chartDataByChannel.value[channelName] = []
    }

    const existingData = chartDataByChannel.value[channelName]

    // Проверяем, не дублируется ли точка (по timestamp)
    const isDuplicate = existingData.length > 0 && 
      existingData[existingData.length - 1].ts === data.ts

    if (!isDuplicate) {
      // Добавляем новую точку напрямую в массив (мутация вместо создания нового массива)
      existingData.push({
        ts: data.ts,
        value: data.value,
      })
      
      // Ограничиваем количество точек в зависимости от временного диапазона
      const maxPoints = getMaxPointsForTimeRange(chartTimeRange.value)
      if (existingData.length > maxPoints) {
        // Удаляем самые старые точки
        existingData.splice(0, existingData.length - maxPoints)
      }

      logger.debug('[Devices/Show] Updated chart data via WebSocket', {
        channel: channelName,
        value: data.value,
        pointsCount: existingData.length,
      })
    }
  } catch (error) {
    // Обрабатываем ошибки, чтобы они не вызывали перезагрузку страницы
    logger.error('[Devices/Show] Error updating chart data via WebSocket:', error)
  }
}

// Константы для максимального количества точек в зависимости от временного диапазона
const MAX_POINTS_BY_RANGE: Record<string, number> = {
  '1H': 60,    // 1 точка в минуту
  '24H': 288,  // 1 точка в 5 минут
  '7D': 336,   // 1 точка в 30 минут
  '30D': 720,  // 1 точка в час
  'ALL': 1000, // Максимум 1000 точек
}

const getMaxPointsForTimeRange = (timeRange: string): number => {
  return MAX_POINTS_BY_RANGE[timeRange] ?? 288
}

// Загружаем данные при монтировании компонента
onMounted(() => {
  loadNodeConfig().catch((error) => {
    logger.error('[Devices/Show] Error loading node config on mount:', error)
  })
  loadAllCharts().catch((error) => {
    logger.error('[Devices/Show] Error loading charts on mount:', error)
  })
  
  // Подписываемся на WebSocket обновления телеметрии
  try {
    unsubscribeTelemetryFn = subscribeTelemetry(handleTelemetryUpdate)
  } catch (error) {
    logger.error('[Devices/Show] Error subscribing to telemetry:', error)
  }
})

// Отписываемся при размонтировании
onUnmounted(() => {
  if (unsubscribeTelemetryFn) {
    unsubscribeTelemetryFn()
    unsubscribeTelemetryFn = null
  }
  unsubscribeTelemetry()
})

// Перезагружаем графики и переподписываемся при изменении устройства
watch(device, (newDevice, oldDevice) => {
  const oldZoneId = oldDevice?.zone?.id ?? null
  const newZoneId = newDevice?.zone?.id ?? null
  const nodeChanged = newDevice?.id !== oldDevice?.id
  const zoneChanged = newZoneId !== oldZoneId

  if (nodeChanged || zoneChanged) {
    loadNodeConfig().catch((error) => {
      logger.error('[Devices/Show] Error reloading config on device change:', error)
    })
    // Отписываемся от старого устройства
    if (unsubscribeTelemetryFn) {
      unsubscribeTelemetryFn()
      unsubscribeTelemetryFn = null
    }
    unsubscribeTelemetry()
    
    // Очищаем данные графиков при смене устройства
    chartDataByChannel.value = {}
    
    // Подписываемся на новое устройство
    if (newDevice?.id) {
      try {
        unsubscribeTelemetryFn = subscribeTelemetry(handleTelemetryUpdate)
      } catch (error) {
        logger.error('[Devices/Show] Error subscribing to telemetry on device change:', error)
      }
    }
    
    // Загружаем данные только при смене устройства
    loadAllCharts().catch((error) => {
      logger.error('[Devices/Show] Error loading charts on device change:', error)
    })
  }
  // Не перезагружаем графики при других изменениях устройства (например, статус)
})

</script>

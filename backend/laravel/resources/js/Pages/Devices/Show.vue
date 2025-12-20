<template>
  <AppLayout>
    <div class="flex items-center justify-between mb-3">
      <div>
        <div class="text-lg font-semibold">{{ device.uid || device.name || device.id }}</div>
        <div class="text-xs text-[color:var(--text-muted)]">
          <span v-if="device.zone">
            <Link :href="`/zones/${device.zone.id}`" class="text-[color:var(--accent-cyan)] hover:underline">Zone: {{ device.zone.name }}</Link>
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
        <NodeLifecycleBadge v-if="device.lifecycle_state" :lifecycle-state="device.lifecycle_state" />
        <Button size="sm" variant="secondary" @click="onRestart">Restart</Button>
      </div>
    </div>

    <!-- Визуализация связи с зоной -->
    <Card v-if="device.zone" class="mb-3">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-3">
          <div class="w-12 h-12 rounded-lg border-2 border-[color:var(--border-strong)] bg-[color:var(--bg-elevated)] flex items-center justify-center">
            <span class="text-2xl">🌱</span>
          </div>
          <div>
            <div class="text-sm font-semibold text-[color:var(--text-primary)]">Привязано к зоне</div>
            <Link :href="`/zones/${device.zone.id}`" class="text-[color:var(--accent-cyan)] hover:underline text-sm">
              {{ device.zone.name }}
            </Link>
            <div v-if="device.zone.status" class="text-xs text-[color:var(--text-muted)] mt-1">
              Статус: {{ device.zone.status }}
            </div>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <Link :href="`/zones/${device.zone.id}`">
            <Button size="sm" variant="outline">
              Перейти к зоне →
            </Button>
          </Link>
          <button 
            @click="detachNode"
            :disabled="detaching"
            class="inline-flex items-center justify-center rounded-md font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-[color:var(--accent-red)]/50 h-8 px-3 text-xs bg-[color:var(--badge-danger-bg)] text-[color:var(--badge-danger-text)] border border-[color:var(--badge-danger-border)] hover:border-[color:var(--accent-red)] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <svg v-if="!detaching" class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
            <span v-if="detaching">Отвязка...</span>
            <span v-else>Отвязать от зоны</span>
          </button>
        </div>
      </div>
    </Card>
    <Card v-else class="mb-3 border-[color:var(--badge-warning-border)] bg-[color:var(--badge-warning-bg)]">
      <div class="flex items-center gap-2 text-[color:var(--badge-warning-text)]">
        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
        <span class="text-sm">Устройство не привязано к зоне</span>
      </div>
    </Card>

    <!-- Графики телеметрии для сенсорных каналов (раздельно) -->
    <div v-if="sensorChannels.length > 0" class="mb-3 space-y-3">
      <template v-for="(channel, index) in sensorChannels" :key="channel?.channel || index">
        <MultiSeriesTelemetryChart
          v-if="channel && getChartSeriesForChannel(channel).length > 0"
          :title="getChartTitleForChannel(channel)"
          :series="getChartSeriesForChannel(channel)"
          :time-range="chartTimeRange"
          @time-range-change="onChartTimeRangeChange"
        />
      </template>
      <Card v-if="sensorChannels.length > 0 && !hasChartData" class="text-center text-sm text-[color:var(--text-dim)] py-8">
        <div>Загрузка данных телеметрии...</div>
      </Card>
    </div>

    <div class="grid grid-cols-1 xl:grid-cols-3 gap-3">
      <Card class="xl:col-span-2">
        <div class="flex items-center justify-between gap-2 mb-2">
          <div>
            <div class="text-sm font-semibold">Channels</div>
            <div class="text-xs text-[color:var(--text-dim)]">
              <span v-if="configLoading">Обновляем конфиг...</span>
              <span v-else>Текущий конфиг ноды</span>
              <span v-if="configError" class="text-[color:var(--accent-amber)] ml-2">{{ configError }}</span>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <Button size="sm" variant="outline" :disabled="configLoading" @click="loadNodeConfig">
              {{ configLoading ? 'Обновление...' : 'Обновить' }}
            </Button>
            <Button size="sm" @click="showConfigWizard = true">
              Редактировать конфиг
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
          <div class="text-sm font-semibold">NodeConfig</div>
          <div class="text-[11px] text-[color:var(--text-dim)]" v-if="configLoading">Загрузка...</div>
        </div>
        <pre class="text-xs text-[color:var(--text-muted)] overflow-auto">{{ nodeConfig }}</pre>
      </Card>
    </div>

    <RelayConfigWizard
      :show="showConfigWizard"
      :node-id="device.id"
      :initial-channels="wizardInitialChannels"
      @close="showConfigWizard = false"
      @published="onConfigPublished"
    />

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
import DeviceChannelsTable from '@/Pages/Devices/DeviceChannelsTable.vue'
import RelayConfigWizard from '@/Pages/Devices/RelayConfigWizard.vue'
import MultiSeriesTelemetryChart from '@/Components/MultiSeriesTelemetryChart.vue'
import { logger } from '@/utils/logger'
import { useHistory } from '@/composables/useHistory'
import { useToast } from '@/composables/useToast'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import { useApi } from '@/composables/useApi'
import { normalizeStatus } from '@/composables/useCommands'
import { useDevicesStore } from '@/stores/devices'
import { useNodeTelemetry } from '@/composables/useNodeTelemetry'
import { useTheme } from '@/composables/useTheme'
import type { Device, DeviceChannel } from '@/types'

interface PageProps {
  device?: Device
}

const page = usePage<PageProps>()
const device = computed(() => (page.props.device || {}) as Device)
const channels = computed(() => (device.value.channels || []) as DeviceChannel[])
const testingChannels = ref<Set<string>>(new Set())
const nodeConfigData = ref<any | null>(null)
const configLoading = ref(false)
const configError = ref('')
const showConfigWizard = ref(false)
const detaching = ref(false)
const detachModalOpen = ref(false)
const { showToast } = useToast()
const { api } = useApi(showToast)
const devicesStore = useDevicesStore()
const { theme } = useTheme()

// Графики телеметрии
const chartTimeRange = ref<'1H' | '24H' | '7D' | '30D' | 'ALL'>('24H')
const chartDataByChannel = ref<Record<string, Array<{ ts: number; value: number }>>>({})

// Приоритеты метрик для сортировки (меньше = выше приоритет)
const METRIC_PRIORITY: Record<string, number> = {
  'TEMPERATURE': 1,
  'TEMP_AIR': 1,
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
    return cfg.channels.map((ch) => ({
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
    TEMP_AIR: resolveCssColor('--accent-amber', '#f59e0b'),
    TEMPERATURE: resolveCssColor('--accent-amber', '#f59e0b'),
    HUMIDITY: resolveCssColor('--accent-cyan', '#3b82f6'),
    CO2: resolveCssColor('--accent-green', '#10b981'),
    PH: resolveCssColor('--accent-lime', '#8b5cf6'),
    EC: resolveCssColor('--accent-cyan', '#06b6d4'),
    DEFAULT: resolveCssColor('--accent-cyan', '#3b82f6'),
  }
})

const METRIC_LABELS: Record<string, string> = {
  'TEMP_AIR': 'Температура',
  'TEMPERATURE': 'Температура',
  'HUMIDITY': 'Влажность',
  'CO2': 'CO₂',
  'PH': 'pH',
  'EC': 'EC',
}

const METRIC_NORMALIZATION: Record<string, string> = {
  'TEMP_AIR': 'TEMPERATURE',
  'TEMPERATURE': 'TEMPERATURE',
  'HUMIDITY': 'HUMIDITY',
  'CO2': 'CO2',
  'PH': 'PH',
  'EC': 'EC',
}

const COMMAND_ERROR_MESSAGES: Record<string, string> = {
  relay_not_initialized: 'Релейный драйвер не инициализирован',
  relay_invalid_channel: 'Неверное имя канала реле',
  relay_channel_not_found: 'Канал реле не найден',
  relay_mutex_timeout: 'Таймаут выполнения команды реле',
  relay_gpio_error: 'Ошибка управления GPIO реле',
  relay_error: 'Ошибка управления реле',
  invalid_params: 'Неверные параметры команды',
  set_time_failed: 'Не удалось установить время на ноде',
}

// Утилиты для работы с метриками
const getMetricFromChannel = (channel: DeviceChannel): string => {
  return channel.metric || channel.channel.toUpperCase()
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

const formatCommandError = (status: string, errorMessage?: string, errorCode?: string): string => {
  if (errorCode && COMMAND_ERROR_MESSAGES[errorCode]) {
    return COMMAND_ERROR_MESSAGES[errorCode]
  }

  if (errorMessage) {
    return errorMessage
  }

  if (errorCode) {
    return `Код ошибки: ${errorCode}`
  }

  return status
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
    channels: displayChannels.value.map(c => ({
      channel: c.channel,
      type: c.type,
      metric: c.metric,
      unit: c.unit,
    })),
  }
  return JSON.stringify(fallback, null, 2)
})

const wizardInitialChannels = computed(() => {
  if (nodeConfigData.value?.channels) {
    return nodeConfigData.value.channels
  }

  if (channels.value.length > 0) {
    return channels.value.map(ch => ({
      name: ch.channel,
      channel: ch.channel,
      type: ch.type,
      metric: ch.metric,
      unit: ch.unit,
      config: ch.config,
    }))
  }

  return []
})

const loadNodeConfig = async (): Promise<void> => {
  if (!device.value.id) return

  configLoading.value = true
  configError.value = ''
  try {
    const response = await api.get<{ status: string; data?: Record<string, unknown> }>(
      `/nodes/${device.value.id}/config`
    )
    nodeConfigData.value = response.data?.data || null
  } catch (error) {
    configError.value = 'Не удалось загрузить конфиг'
    logger.error('[Devices/Show] Failed to load node config', error)
  } finally {
    configLoading.value = false
  }
}

const onConfigPublished = async (): Promise<void> => {
  await loadNodeConfig()
  showConfigWizard.value = false
}

const onRestart = async (): Promise<void> => {
  try {
    const response = await api.post<{ status: string }>(
      `/nodes/${device.value.id}/commands`,
      {
        type: 'restart',
        params: {},
      }
    )
    
    if (response.data?.status === 'ok') {
      logger.debug('[Devices/Show] Device restart command sent successfully', response.data)
      showToast('Команда перезапуска отправлена', 'success', TOAST_TIMEOUT.NORMAL)
    }
  } catch (err) {
    // Ошибка уже обработана в useApi через showToast
    logger.error('[Devices/Show] Failed to restart device:', err)
  }
}

const detachNode = async (): Promise<void> => {
  if (!device.value.zone_id) {
    showToast('Нода уже отвязана от зоны', 'warning', TOAST_TIMEOUT.NORMAL)
    return
  }

  detachModalOpen.value = true
}

const confirmDetachNode = async (): Promise<void> => {
  if (!device.value.zone_id) {
    detachModalOpen.value = false
    return
  }

  detaching.value = true
  try {
    const response = await api.post<{ status: string; data?: Device }>(
      `/nodes/${device.value.id}/detach`,
      {}
    )
    
    if (response.data?.status === 'ok') {
      logger.debug('[Devices/Show] Node detached successfully', response.data)
      showToast(`Нода "${device.value.uid || device.value.name}" успешно отвязана от зоны`, 'success', TOAST_TIMEOUT.NORMAL)
      
      // Обновляем device локально, убирая zone_id, вместо полного reload
      const updatedDevice = response.data?.data || {
        ...device.value,
        zone_id: null,
        zone: null,
      }
      
      // Обновляем device в store для мгновенного отображения
      if (updatedDevice?.id) {
        devicesStore.upsert(updatedDevice)
        logger.debug('[Devices/Show] Device updated in store after detach', { deviceId: updatedDevice.id })
      }
      
      // Опционально: можно перенаправить на список устройств, если нужно
      // router.visit('/devices')
    }
  } catch (err) {
    // Ошибка уже обработана в useApi через showToast
    logger.error('[Devices/Show] Failed to detach node:', err)
  } finally {
    detaching.value = false
    detachModalOpen.value = false
  }
}

// Функция для теста конкретного насоса/клапана
const onTestPump = async (channelName: string, channelType: string): Promise<void> => {
  if (testingChannels.value.has(channelName)) return
  
  testingChannels.value.add(channelName)
  const channelLabel = getChannelLabel(channelName, channelType)
  showToast(`Команда отправлена: ${channelLabel}`, 'info', TOAST_TIMEOUT.SHORT)
  
  try {
    let commandType = 'run_pump'
    let params: Record<string, any> = { duration_ms: 3000 } // 3 секунды по умолчанию

    const nodeTypeLower = (device.value.type || '').toLowerCase()
    const channelNameLower = (channelName || '').toLowerCase()
    const channelTypeLower = (channelType || '').toLowerCase()

    const isRelayNode = nodeTypeLower.includes('relay')
    const isSensor = channelTypeLower === 'sensor'
    const isValve = channelType === 'valve' || channelNameLower.includes('valve')
    
    if (isSensor) {
      commandType = 'test_sensor'
      params = {}
    } else if (isRelayNode) {
      commandType = 'set_state'
      params = { state: 1, duration_ms: 3000 }
    } else if (isValve) {
      commandType = 'set_relay'
      params = { state: true, duration_ms: 3000 }
    }
    
    const response = await api.post<{ status: string; data?: { command_id: number } }>(
      `/nodes/${device.value.id}/commands`,
      {
        type: commandType,
        channel: channelName,
        params: params,
      }
    )
    
    if (response.data?.status === 'ok' && response.data?.data?.command_id) {
      const cmdId = response.data.data.command_id
      // Ожидаем ответа от ноды
      let executionNotified = false
      const result = await checkCommandStatus(cmdId, 30, (status) => {
        if (status === 'ACCEPTED' && !executionNotified) {
          executionNotified = true
          showToast(`Выполнение: ${channelLabel}...`, 'info', TOAST_TIMEOUT.NORMAL)
        }
      }) // Максимум 30 секунд
      
      if (result.success) {
        showToast(`Выполнено: ${channelLabel}`, 'success', TOAST_TIMEOUT.LONG)
      } else {
        const detail = formatCommandError(result.status, result.errorMessage, result.errorCode)
        showToast(`Ошибка теста ${channelLabel}: ${detail}`, 'error', TOAST_TIMEOUT.LONG)
      }
    } else {
      showToast(`Не удалось отправить команду для ${channelLabel}`, 'error', TOAST_TIMEOUT.LONG)
    }
  } catch (err) {
    const apiMessage = (err as { response?: { data?: { message?: string; error?: string } } })?.response?.data
    const detail = apiMessage?.message || apiMessage?.error
    if (detail) {
      showToast(`Ошибка теста ${channelLabel}: ${detail}`, 'error', TOAST_TIMEOUT.LONG)
    }
    logger.error(`[Devices/Show] Failed to test ${channelName}:`, err)
  } finally {
    testingChannels.value.delete(channelName)
  }
}

// Функция для получения читаемого названия канала
function getChannelLabel(channelName, channelType) {
  const name = (channelName || '').toLowerCase()
  const nodeType = (device.value.type || '').toLowerCase()
  const type = (channelType || '').toLowerCase()
  const isSensor = type === 'sensor'
  
  // PH нода
  if (nodeType.includes('ph')) {
    if (isSensor && name.includes('ph_sensor')) return 'Тест pH сенсора'
    if (isSensor && (name.includes('solution_temp') || name.includes('temp'))) return 'Тест температуры раствора'
    if (name.includes('acid') || name.includes('up')) return 'PH UP тест'
    if (name.includes('base') || name.includes('down')) return 'PH DOWN тест'
  }
  
  // EC нода
  if (nodeType.includes('ec')) {
    if (name.includes('nutrient_a') || name.includes('pump_a')) return 'Тест насоса A'
    if (name.includes('nutrient_b') || name.includes('pump_b')) return 'Тест насоса B'
    if (name.includes('nutrient_c') || name.includes('pump_c')) return 'Тест насоса C'
    if (name.includes('nutrient')) return 'Тест насоса питательного раствора'
  }
  
  // Pump нода
  if (nodeType.includes('pump')) {
    if (name.includes('main') || name.includes('primary')) return 'Тест главного насоса'
    if (name.includes('backup') || name.includes('reserve') || name.includes('reserve')) return 'Тест резервного насоса'
    if (name.includes('transfer') || name.includes('перекач')) return 'Тест перекачивающего насоса'
    if (name.includes('valve') || channelType === 'valve') return 'Тест клапана'
  }
  
  // Общий случай
  if (isSensor) return `Тест сенсора ${channelName || 'канал'}`
  return channelName || 'Канал'
}

// Функция для проверки статуса команды
async function checkCommandStatus(
  cmdId: number,
  maxAttempts = 30,
  onStatusChange?: (status: string) => void
): Promise<{
  success: boolean
  status: string
  error?: string
  errorCode?: string
  errorMessage?: string
}> {
  let lastStatus: string | null = null
  for (let i = 0; i < maxAttempts; i++) {
    try {
      const response = await api.get<{
        status: string
        data?: {
          status: string
          error_message?: string | null
          error_code?: string | null
          result_code?: number | null
          duration_ms?: number | null
        }
      }>(
        `/commands/${cmdId}/status`
      )
      
      if (response.data?.status === 'ok' && response.data?.data) {
        const cmdStatus = response.data.data.status
        // Используем новые статусы из единого контракта
        const normalizedStatus = normalizeStatus(cmdStatus)
        if (normalizedStatus !== lastStatus) {
          lastStatus = normalizedStatus
          if (onStatusChange) {
            onStatusChange(normalizedStatus)
          }
        }
        if (normalizedStatus === 'DONE') {
          return { success: true, status: 'DONE' }
        } else if (['FAILED', 'TIMEOUT', 'SEND_FAILED'].includes(normalizedStatus)) {
          const errorMessage = response.data.data.error_message || undefined
          const errorCode = response.data.data.error_code || undefined
          const errorDetail = errorMessage || errorCode || null
          return {
            success: false,
            status: normalizedStatus,
            error: errorDetail || undefined,
            errorCode,
            errorMessage,
          }
        } else if (normalizedStatus === 'QUEUED' || normalizedStatus === 'SENT' || normalizedStatus === 'ACCEPTED') {
          // Продолжаем ожидание
          await new Promise(resolve => setTimeout(resolve, 500))
          continue
        }
      }
    } catch (err) {
      logger.error('[Devices/Show] Failed to check command status:', err)
      // Если команда не найдена, возможно она еще не создана, продолжаем ожидание
      const errorStatus = (err as { response?: { status?: number } })?.response?.status
      if (errorStatus === 404 && i < maxAttempts - 1) {
        await new Promise(resolve => setTimeout(resolve, 500))
        continue
      }
      const errorMessage = err instanceof Error ? err.message : 'Unknown error'
      return { success: false, status: 'error', error: errorMessage }
    }
  }
  return { success: false, status: 'timeout' }
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
    
    const response = await api.get<{ status: string; data?: Array<{ ts: string; value: number; channel: string }> }>(
      `/nodes/${device.value.id}/telemetry/history`,
      {
        params: {
          metric: normalizedMetric,
          channel,
          from: from?.toISOString(),
        }
      }
    )
    
    if (response.data?.status === 'ok' && response.data?.data) {
      logger.debug(`[Devices/Show] Loaded ${response.data.data.length} telemetry records for ${channel}`)
      return response.data.data.map(item => ({
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
    const metric = channel.metric || channel.channel.toUpperCase()
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
const { subscribe: subscribeTelemetry, unsubscribe: unsubscribeTelemetry } = useNodeTelemetry(nodeId)
let unsubscribeTelemetryFn: (() => void) | null = null

// Обработчик обновления телеметрии через WebSocket
const handleTelemetryUpdate = (data: { node_id: number; channel: string; metric_type: string; value: number; ts: number }) => {
  try {
    const channel = sensorChannels.value.find(ch => ch.channel === data.channel)
    if (!channel) {
      return
    }

    // Получаем или создаем массив данных для канала
    if (!chartDataByChannel.value[data.channel]) {
      chartDataByChannel.value[data.channel] = []
    }
    
    const existingData = chartDataByChannel.value[data.channel]

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
        channel: data.channel,
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
  // Если изменился nodeId, нужно переподписаться
  if (newDevice?.id !== oldDevice?.id) {
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

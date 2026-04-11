<template>
  <div class="flex items-center gap-2 sm:gap-4 px-2 sm:px-4 py-2 bg-[color:var(--bg-surface-strong)] border-b border-[color:var(--border-muted)] overflow-x-auto">
    <div class="flex items-center gap-2 sm:gap-4 text-xs shrink-0">
      <!-- Core Status -->
      <div class="flex items-center gap-2 group relative">
        <div class="relative">
          <div
            class="w-2.5 h-2.5 rounded-full transition-all duration-300"
            :class="[getStatusDotClass(coreStatus), coreStatus === 'ok' ? 'animate-pulse' : '']"
          ></div>
          <div
            v-if="coreStatus === 'ok'"
            class="absolute inset-0 w-2.5 h-2.5 rounded-full animate-ping opacity-75"
            :class="getStatusDotClass(coreStatus)"
          ></div>
        </div>
        <div class="flex flex-col">
          <span class="text-[color:var(--text-dim)] text-[10px] leading-tight">Core</span>
          <span
            class="text-[11px] font-medium leading-tight transition-colors"
            :class="getStatusTextClass(coreStatus)"
          >
            {{ getStatusText(coreStatus) }}
          </span>
        </div>
        <div
          class="absolute left-0 top-full mt-2 px-2 py-1.5 bg-[color:var(--bg-surface-strong)] rounded text-xs text-[color:var(--text-primary)] opacity-0 group-hover:opacity-100 pointer-events-none whitespace-nowrap z-50 shadow-[var(--shadow-card)] border border-[color:var(--border-muted)]"
        >
          <div class="font-medium">
            Core Service
          </div>
          <div class="text-[10px] text-[color:var(--text-dim)] mt-0.5">
            Статус: {{ getStatusText(coreStatus) }}
          </div>
          <div
            v-if="lastUpdate"
            class="text-[10px] text-[color:var(--text-dim)] mt-1"
          >
            Обновлено: {{ formatTime(lastUpdate) }}
          </div>
        </div>
      </div>

      <!-- Database Status -->
      <div class="flex items-center gap-2 group relative">
        <div class="relative">
          <div
            class="w-2.5 h-2.5 rounded-full transition-all duration-300"
            :class="[getStatusDotClass(dbStatus), dbStatus === 'ok' ? 'animate-pulse' : '']"
          ></div>
          <div
            v-if="dbStatus === 'ok'"
            class="absolute inset-0 w-2.5 h-2.5 rounded-full animate-ping opacity-75"
            :class="getStatusDotClass(dbStatus)"
          ></div>
        </div>
        <div class="flex flex-col">
          <span class="text-[color:var(--text-dim)] text-[10px] leading-tight">Database</span>
          <span
            class="text-[11px] font-medium leading-tight transition-colors"
            :class="getStatusTextClass(dbStatus)"
          >
            {{ getStatusText(dbStatus) }}
          </span>
        </div>
        <div
          class="absolute left-0 top-full mt-2 px-2 py-1.5 bg-[color:var(--bg-surface-strong)] rounded text-xs text-[color:var(--text-primary)] opacity-0 group-hover:opacity-100 pointer-events-none whitespace-nowrap z-50 shadow-[var(--shadow-card)] border border-[color:var(--border-muted)]"
        >
          <div class="font-medium">
            Database
          </div>
          <div class="text-[10px] text-[color:var(--text-dim)] mt-0.5">
            Статус: {{ getStatusText(dbStatus) }}
          </div>
          <div
            v-if="lastUpdate"
            class="text-[10px] text-[color:var(--text-dim)] mt-1"
          >
            Обновлено: {{ formatTime(lastUpdate) }}
          </div>
        </div>
      </div>

      <!-- WebSocket Status -->
      <div
        class="flex items-center gap-2 group relative"
        data-testid="ws-status-indicator"
      >
        <div class="relative">
          <div
            class="w-2.5 h-2.5 rounded-full transition-all duration-300"
            :class="[getWsStatusDotClass(wsStatus), wsStatus === 'connected' ? 'animate-pulse' : '']"
            :data-testid="wsStatus === 'connected' ? 'ws-status-connected' : 'ws-status-disconnected'"
          ></div>
          <div
            v-if="wsStatus === 'connected'"
            class="absolute inset-0 w-2.5 h-2.5 rounded-full animate-ping opacity-75"
            :class="getWsStatusDotClass(wsStatus)"
          ></div>
        </div>
        <div class="flex flex-col">
          <span class="text-[color:var(--text-dim)] text-[10px] leading-tight">WebSocket</span>
          <span
            class="text-[11px] font-medium leading-tight transition-colors"
            :class="getWsStatusTextClass(wsStatus)"
          >
            {{ getWsStatusText(wsStatus) }}
          </span>
        </div>
        <div
          class="absolute left-0 top-full mt-2 px-2 py-1.5 bg-[color:var(--bg-surface-strong)] rounded text-xs text-[color:var(--text-primary)] opacity-0 group-hover:opacity-100 pointer-events-none whitespace-nowrap z-50 shadow-[var(--shadow-card)] border border-[color:var(--border-muted)] max-w-xs"
        >
          <div class="font-medium">
            WebSocket Connection
          </div>
          <div class="text-[10px] text-[color:var(--text-dim)] mt-0.5">
            Статус: {{ getWsStatusText(wsStatus) }}
          </div>
          <div
            v-if="wsStatus === 'connected'"
            class="text-[10px] text-[color:var(--accent-green)] mt-1"
          >
            ✓ Соединение активно
            <div
              v-if="wsConnectionDetails?.socketId"
              class="text-[color:var(--text-dim)] mt-0.5 text-[9px]"
            >
              Socket ID: {{ wsConnectionDetails.socketId.substring(0, 8) }}...
            </div>
          </div>
          <div
            v-else-if="wsStatus === 'disconnected' || wsStatus === 'connecting'"
            class="text-[10px] text-[color:var(--accent-red)] mt-1"
          >
            <div>✗ Соединение разорвано</div>
            <div
              v-if="wsReconnectAttempts > 0"
              class="text-[color:var(--accent-amber)] mt-1 text-[9px]"
            >
              Попыток переподключения: {{ wsReconnectAttempts }}
            </div>
            <div
              v-if="wsLastError"
              class="text-[color:var(--badge-danger-text)] mt-1 text-[9px]"
            >
              <div class="font-medium">
                Последняя ошибка:
              </div>
              <div class="break-words">
                {{ wsLastError.message }}
              </div>
              <div
                v-if="wsLastError.code"
                class="text-[color:var(--text-dim)] mt-0.5"
              >
                Код: {{ wsLastError.code }}
              </div>
              <div
                v-if="wsLastError.timestamp"
                class="text-[color:var(--text-dim)] mt-0.5"
              >
                {{ formatTime(new Date(wsLastError.timestamp)) }}
              </div>
            </div>
            <div class="text-[color:var(--text-dim)] mt-1 text-[9px]">
              Проверьте настройки WebSocket
            </div>
          </div>
          <div
            v-else
            class="text-[10px] text-[color:var(--text-dim)] mt-1"
          >
            ? Инициализация...
            <div class="text-[9px] text-[color:var(--text-dim)] mt-0.5">
              Ожидание подключения
            </div>
            <div
              v-if="wsStatus === 'unknown'"
              class="text-[9px] text-[color:var(--accent-amber)] mt-1"
            >
              WebSocket клиент не инициализирован
            </div>
            <div
              v-if="wsStatus === 'unknown' && wsConnectionDetails?.reconnectAttempts > 0"
              class="text-[9px] text-[color:var(--accent-amber)] mt-1"
            >
              Попыток переподключения: {{ wsConnectionDetails.reconnectAttempts }}
            </div>
          </div>
        </div>
      </div>

      <!-- MQTT Status -->
      <div class="flex items-center gap-2 group relative">
        <div class="relative">
          <div
            class="w-2.5 h-2.5 rounded-full transition-all duration-300"
            :class="[getMqttStatusDotClass(mqttStatus), mqttStatus === 'online' ? 'animate-pulse' : '']"
          ></div>
          <div
            v-if="mqttStatus === 'online'"
            class="absolute inset-0 w-2.5 h-2.5 rounded-full animate-ping opacity-75"
            :class="getMqttStatusDotClass(mqttStatus)"
          ></div>
        </div>
        <div class="flex flex-col">
          <span class="text-[color:var(--text-dim)] text-[10px] leading-tight">MQTT</span>
          <span
            class="text-[11px] font-medium leading-tight transition-colors"
            :class="getMqttStatusTextClass(mqttStatus)"
          >
            {{ getMqttStatusText(mqttStatus) }}
          </span>
        </div>
        <div
          class="absolute left-0 top-full mt-2 px-2 py-1.5 bg-[color:var(--bg-surface-strong)] rounded text-xs text-[color:var(--text-primary)] opacity-0 group-hover:opacity-100 pointer-events-none whitespace-nowrap z-50 shadow-[var(--shadow-card)] border border-[color:var(--border-muted)]"
        >
          <div class="font-medium">
            MQTT Broker
          </div>
          <div class="text-[10px] text-[color:var(--text-dim)] mt-0.5">
            Статус: {{ getMqttStatusText(mqttStatus) }}
          </div>
          <div
            v-if="mqttStatus === 'online'"
            class="text-[10px] text-[color:var(--accent-green)] mt-1"
          >
            ✓ Брокер доступен
          </div>
          <div
            v-else-if="mqttStatus === 'offline'"
            class="text-[10px] text-[color:var(--accent-red)] mt-1"
          >
            ✗ Брокер недоступен
          </div>
          <div
            v-else-if="mqttStatus === 'degraded'"
            class="text-[10px] text-[color:var(--accent-amber)] mt-1"
          >
            ⚠ Частичная доступность
          </div>
          <div
            v-else
            class="text-[10px] text-[color:var(--text-dim)] mt-1"
          >
            ? Статус неизвестен
          </div>
        </div>
      </div>

      <!-- Real-time метрики -->
      <div class="flex items-center gap-3 ml-auto text-xs">
        <!-- Активные зоны -->
        <div 
          v-if="metrics.zonesCount !== null"
          class="flex items-center gap-1.5 px-2 py-1 rounded-md bg-[color:var(--bg-elevated)] hover:bg-[color:var(--bg-surface-strong)] transition-colors group relative"
        >
          <span class="text-[color:var(--text-dim)]">🌱</span>
          <span class="font-medium text-[color:var(--text-primary)]">{{ metrics.zonesCount }}</span>
          <span class="text-[color:var(--text-dim)] hidden sm:inline">зон</span>
          <div
            class="absolute left-0 top-full mt-2 px-2 py-1.5 bg-[color:var(--bg-surface-strong)] rounded text-xs text-[color:var(--text-primary)] opacity-0 group-hover:opacity-100 pointer-events-none whitespace-nowrap z-50 shadow-[var(--shadow-card)] border border-[color:var(--border-muted)]"
          >
            <div class="font-medium">
              Активные зоны
            </div>
            <div class="text-[10px] text-[color:var(--text-dim)] mt-0.5">
              Всего: {{ metrics.zonesCount }}
            </div>
            <div
              v-if="metrics.zonesRunning !== null"
              class="text-[10px] text-[color:var(--accent-green)] mt-1"
            >
              Запущено: {{ metrics.zonesRunning }}
            </div>
          </div>
        </div>
        
        <!-- Устройства -->
        <div 
          v-if="metrics.devicesCount !== null"
          class="flex items-center gap-1.5 px-2 py-1 rounded-md bg-[color:var(--bg-elevated)] hover:bg-[color:var(--bg-surface-strong)] transition-colors group relative"
        >
          <span class="text-[color:var(--text-dim)]">📱</span>
          <span class="font-medium text-[color:var(--text-primary)]">{{ metrics.devicesCount }}</span>
          <span class="text-[color:var(--text-dim)] hidden sm:inline">устр.</span>
          <div
            class="absolute left-0 top-full mt-2 px-2 py-1.5 bg-[color:var(--bg-surface-strong)] rounded text-xs text-[color:var(--text-primary)] opacity-0 group-hover:opacity-100 pointer-events-none whitespace-nowrap z-50 shadow-[var(--shadow-card)] border border-[color:var(--border-muted)]"
          >
            <div class="font-medium">
              Устройства
            </div>
            <div class="text-[10px] text-[color:var(--text-dim)] mt-0.5">
              Всего: {{ metrics.devicesCount }}
            </div>
            <div
              v-if="metrics.devicesOnline !== null"
              class="text-[10px] text-[color:var(--accent-green)] mt-1"
            >
              Онлайн: {{ metrics.devicesOnline }}
            </div>
            <div
              v-if="metrics.devicesOffline !== null && metrics.devicesOffline > 0"
              class="text-[10px] text-[color:var(--accent-red)] mt-1"
            >
              Офлайн: {{ metrics.devicesOffline }}
            </div>
          </div>
        </div>
        
        <!-- Алерты -->
        <div 
          v-if="metrics.alertsCount !== null"
          class="flex items-center gap-1.5 px-2 py-1 rounded-md transition-colors group relative"
          data-testid="alerts-metric"
          :class="metrics.alertsCount > 0 
            ? 'bg-[color:var(--badge-danger-bg)] hover:bg-[color:var(--badge-danger-bg)] border border-[color:var(--badge-danger-border)]' 
            : 'bg-[color:var(--bg-elevated)] hover:bg-[color:var(--bg-surface-strong)]'"
        >
          <span :class="metrics.alertsCount > 0 ? 'text-[color:var(--accent-red)]' : 'text-[color:var(--text-dim)]'">⚠️</span>
          <span 
            class="font-medium transition-colors"
            :class="metrics.alertsCount > 0 ? 'text-[color:var(--accent-red)]' : 'text-[color:var(--text-primary)]'"
          >
            {{ metrics.alertsCount }}
          </span>
          <span class="text-[color:var(--text-dim)] hidden sm:inline">алерт.</span>
          <div
            class="absolute left-0 top-full mt-2 px-2 py-1.5 bg-[color:var(--bg-surface-strong)] rounded text-xs text-[color:var(--text-primary)] opacity-0 group-hover:opacity-100 pointer-events-none whitespace-nowrap z-50 shadow-[var(--shadow-card)] border border-[color:var(--border-muted)]"
          >
            <div class="font-medium">
              Активные алерты
            </div>
            <div class="text-[10px] text-[color:var(--text-dim)] mt-0.5">
              Всего: {{ metrics.alertsCount }}
            </div>
            <div
              v-if="metrics.alertsCount > 0"
              class="text-[10px] text-[color:var(--accent-red)] mt-1"
            >
              ⚠️ Требуют внимания
            </div>
            <div
              v-else
              class="text-[10px] text-[color:var(--accent-green)] mt-1"
            >
              ✓ Нет активных алертов
            </div>
          </div>
        </div>
        
        <!-- Кнопка мониторинга сервисов -->
        <button
          class="flex items-center gap-2 px-2 py-1 rounded-md hover:bg-[color:var(--bg-surface-strong)] transition-colors text-xs text-[color:var(--text-dim)] hover:text-[color:var(--text-primary)]"
          title="Мониторинг сервисов"
          @click="openMonitoringModal()"
        >
          <span>📊</span>
          <span class="hidden sm:inline">Сервисы</span>
        </button>
        <ThemeToggle />
      </div>
    </div>
    
    <!-- Модальное окно мониторинга сервисов -->
    <SystemMonitoringModal
      :show="showMonitoringModal"
      @close="closeMonitoringModal()"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { usePage } from '@inertiajs/vue3'
import { useSystemStatus } from '@/composables/useSystemStatus'
import { useWebSocket } from '@/composables/useWebSocket'
import { formatTime } from '@/utils/formatTime'
import SystemMonitoringModal from '@/Components/SystemMonitoringModal.vue'
import ThemeToggle from '@/Components/ThemeToggle.vue'
import { api } from '@/services/api'
import { useSimpleModal } from '@/composables/useModal'
import { logger } from '@/utils/logger'
import type { User } from '@/types'

interface DashboardData {
  alertsCount?: number
  zonesCount?: number
  devicesCount?: number
  zonesByStatus?: Record<string, number>
  nodesByStatus?: Record<string, number>
  [key: string]: unknown
}

interface PageProps {
  auth?: { user?: User }
  dashboard?: DashboardData
  [key: string]: unknown
}

const { isOpen: showMonitoringModal, open: openMonitoringModal, close: closeMonitoringModal } = useSimpleModal()

const {
  coreStatus,
  dbStatus,
  wsStatus,
  mqttStatus,
  lastUpdate,
  wsReconnectAttempts,
  wsLastError,
  wsConnectionDetails
} = useSystemStatus()

const page = usePage<PageProps>()

// Real-time метрики
const metrics = ref<{
  zonesCount: number | null
  zonesRunning: number | null
  devicesCount: number | null
  devicesOnline: number | null
  devicesOffline: number | null
  alertsCount: number | null
}>({
  zonesCount: null,
  zonesRunning: null,
  devicesCount: null,
  devicesOnline: null,
  devicesOffline: null,
  alertsCount: null,
})

// Флаг для предотвращения повторных запросов при 401
let isUnauthenticated = false
// Объявляем metricsInterval до watch, чтобы он был доступен в immediate: true
let metricsInterval: ReturnType<typeof setInterval> | null = null

// Загрузка метрик (только алерты, данные dashboard приходят через props)
async function loadMetrics() {
  // Проверяем, авторизован ли пользователь
  const user = page.props.auth?.user
  if (!user) {
    // Если пользователь не авторизован, не делаем запросы
    isUnauthenticated = true
    if (metricsInterval) {
      clearInterval(metricsInterval)
      metricsInterval = null
    }
    return
  }
  
  // Если уже была ошибка 401, не повторяем запросы
  if (isUnauthenticated) {
    return
  }
  
  // Используем данные из props, если они доступны (предпочтительно)
  const dashboardData = page.props.dashboard
  if (dashboardData?.alertsCount !== undefined) {
    metrics.value.alertsCount = dashboardData.alertsCount
    return
  }
  
  // Проверяем аутентификацию перед запросом
  const currentUser = page.props.auth?.user
  if (!currentUser || isUnauthenticated) {
    return
  }

  try {
    // Загружаем только активные алерты, данные dashboard уже в props
    const alertsRes = await Promise.allSettled([
      api.alerts.list({ status: 'active' })
    ])

    if (alertsRes[0]?.status === 'fulfilled') {
      const alerts = alertsRes[0].value
      metrics.value.alertsCount = Array.isArray(alerts) ? alerts.length : 0
      isUnauthenticated = false // Сбрасываем флаг при успешном запросе
    } else if (alertsRes[0]?.status === 'rejected') {
      const error = alertsRes[0].reason
      // Игнорируем отмененные запросы (Inertia.js при навигации)
      if (error?.code === 'ERR_CANCELED' || 
          error?.name === 'CanceledError' || 
          error?.message === 'canceled' ||
          error?.message === 'Request aborted') {
        // Не логируем отмененные запросы - это нормальное поведение
        return
      }
      // Если ошибка 401, прекращаем повторные запросы
      if (error?.response?.status === 401) {
        isUnauthenticated = true
        if (metricsInterval) {
          clearInterval(metricsInterval)
          metricsInterval = null
        }
      }
    }
  } catch (err: any) {
    // Если ошибка 401, прекращаем повторные запросы
    if (err?.response?.status === 401) {
      isUnauthenticated = true
      if (metricsInterval) {
        clearInterval(metricsInterval)
        metricsInterval = null
      }
    }
    // Игнорируем отмененные запросы и другие некритичные ошибки
    if (err?.code === 'ERR_CANCELED' || 
        err?.name === 'CanceledError' || 
        err?.message === 'canceled' ||
        err?.message === 'Request aborted') {
      // Не логируем отмененные запросы - это нормальное поведение Inertia.js
      return
    }
    logger.debug('[HeaderStatusBar] Failed to load alerts:', err)
  }
}

// Обновление метрик из props (если доступны)
const dashboardData = computed(() => page.props.dashboard)
watch(dashboardData, (data) => {
  if (data) {
    metrics.value.zonesCount = data.zonesCount || null
    metrics.value.zonesRunning = data.zonesByStatus?.RUNNING || null
    metrics.value.devicesCount = data.devicesCount || null
    metrics.value.devicesOnline = data.nodesByStatus?.online || null
    metrics.value.devicesOffline = data.nodesByStatus?.offline || null
    // Если данные алертов доступны из props, используем их и не делаем API запросы
    if (data.alertsCount !== undefined) {
      metrics.value.alertsCount = data.alertsCount
      // Останавливаем интервал, так как данные обновляются через props
      if (metricsInterval) {
        clearInterval(metricsInterval)
        metricsInterval = null
      }
      isUnauthenticated = false // Сбрасываем флаг, так как данные есть
    }
  }
}, { immediate: true })

// Подписка на WebSocket обновления
const { subscribeToGlobalEvents } = useWebSocket()
let unsubscribeMetrics: (() => void) | null = null

onMounted(() => {
  // Проверяем аутентификацию перед началом загрузки метрик
  const user = page.props.auth?.user
  if (!user) {
    // Если пользователь не авторизован, не запускаем загрузку метрик
    isUnauthenticated = true
    logger.debug('[HeaderStatusBar] User not authenticated, skipping metrics loading')
    return
  }
  
  // Загружаем метрики только один раз при монтировании
  // Dashboard данные обновляются через props, алерты обновляются реже
  loadMetrics()
  
  // Обновляем только алерты каждые 30 секунд (не критично часто)
  // Только если пользователь авторизован И не было ошибки 401
  // Запускаем интервал только после успешной загрузки метрик
  metricsInterval = setInterval(() => {
      // Проверяем аутентификацию перед каждым запросом
      const currentUser = page.props.auth?.user
      if (!currentUser || isUnauthenticated) {
        if (metricsInterval) {
          clearInterval(metricsInterval)
          metricsInterval = null
        }
        logger.debug('[HeaderStatusBar] Stopping metrics interval - user not authenticated')
        return
      }
      // Вызываем loadMetrics только если пользователь авторизован
      loadMetrics()
    }, 30000)
  
  // Подписываемся на глобальные события для обновления метрик
  unsubscribeMetrics = subscribeToGlobalEvents(() => {
    // Обновляем метрики при получении событий только если авторизован
    const currentUser = page.props.auth?.user
    if (currentUser && !isUnauthenticated) {
      loadMetrics()
    }
  })
})

onUnmounted(() => {
  if (metricsInterval) {
    clearInterval(metricsInterval)
  }
  if (unsubscribeMetrics) {
    unsubscribeMetrics()
  }
})

function getStatusDotClass(status: string | undefined) {
  switch (status) {
    case 'ok':
      return 'bg-[color:var(--accent-green)]'
    case 'fail':
      return 'bg-[color:var(--accent-red)]'
    default:
      return 'bg-[color:var(--text-dim)]'
  }
}

function getStatusText(status: string | undefined) {
  switch (status) {
    case 'ok':
      return 'Онлайн'
    case 'fail':
      return 'Офлайн'
    default:
      return 'Неизвестно'
  }
}

function getStatusTextClass(status: string | undefined) {
  switch (status) {
    case 'ok':
      return 'text-[color:var(--accent-green)]'
    case 'fail':
      return 'text-[color:var(--accent-red)]'
    default:
      return 'text-[color:var(--text-dim)]'
  }
}

function getWsStatusDotClass(status: string | undefined) {
  switch (status) {
    case 'connected':
      return 'bg-[color:var(--accent-green)]'
    case 'disconnected':
      return 'bg-[color:var(--accent-red)]'
    default:
      return 'bg-[color:var(--text-dim)]'
  }
}

function getWsStatusText(status: string | undefined) {
  switch (status) {
    case 'connected':
      return 'Подключено'
    case 'disconnected':
      return 'Отключено'
    default:
      return 'Неизвестно'
  }
}

function getWsStatusTextClass(status: string | undefined) {
  switch (status) {
    case 'connected':
      return 'text-[color:var(--accent-green)]'
    case 'disconnected':
      return 'text-[color:var(--accent-red)]'
    default:
      return 'text-[color:var(--text-dim)]'
  }
}

function getMqttStatusDotClass(status: string | undefined) {
  switch (status) {
    case 'online':
      return 'bg-[color:var(--accent-green)]'
    case 'offline':
      return 'bg-[color:var(--accent-red)]'
    case 'degraded':
      return 'bg-[color:var(--accent-amber)]'
    default:
      return 'bg-[color:var(--text-dim)]'
  }
}

function getMqttStatusText(status: string | undefined) {
  switch (status) {
    case 'online': {
      return 'Онлайн'
    }
    case 'offline': {
      return 'Офлайн'
    }
    case 'degraded': {
      return 'Частично'
    }
    default: {
      return 'Неизвестно'
    }
  }
}

function getMqttStatusTextClass(status: string | undefined) {
  switch (status) {
    case 'online':
      return 'text-[color:var(--accent-green)]'
    case 'offline':
      return 'text-[color:var(--accent-red)]'
    case 'degraded':
      return 'text-[color:var(--accent-amber)]'
    default:
      return 'text-[color:var(--text-dim)]'
  }
}
</script>

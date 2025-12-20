<template>
  <AppLayout>
    <div class="space-y-4">
      <div class="flex items-center justify-between">
        <h1 class="text-lg font-semibold">Мониторинг системы</h1>
        <Button
          size="sm"
          variant="secondary"
          @click="refreshStatus"
          :disabled="refreshing"
        >
          {{ refreshing ? 'Обновление...' : 'Обновить' }}
        </Button>
      </div>

      <!-- Основные компоненты -->
      <div>
        <h3 class="text-sm font-semibold mb-3 text-[color:var(--text-primary)]">Основные компоненты</h3>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
          <ServiceStatusCard
            name="Core API"
            :status="coreStatus"
            icon="⚙️"
            description="Основной API сервис"
          />
          <ServiceStatusCard
            name="Database"
            :status="dbStatus"
            icon="💾"
            description="PostgreSQL база данных"
          />
          <ServiceStatusCard
            name="WebSocket"
            :status="wsStatus"
            icon="🔌"
            description="WebSocket соединение"
            status-type="ws"
          />
          <ServiceStatusCard
            name="MQTT Broker"
            :status="mqttStatus"
            icon="📡"
            description="MQTT брокер"
            status-type="mqtt"
          />
        </div>
      </div>

      <!-- Python сервисы -->
      <div>
        <h3 class="text-sm font-semibold mb-3 text-[color:var(--text-primary)]">Python сервисы</h3>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
          <ServiceStatusCard
            name="History Logger"
            :status="historyLoggerStatus"
            icon="📝"
            description="Логирование телеметрии в БД"
            :endpoint="historyLoggerEndpoint"
          />
          <ServiceStatusCard
            name="Automation Engine"
            :status="automationEngineStatus"
            icon="🤖"
            description="Автоматизация управления зонами"
            :endpoint="automationEngineEndpoint"
          />
        </div>
      </div>

      <!-- Цепочка состояния -->
      <div>
        <h3 class="text-sm font-semibold mb-3 text-[color:var(--text-primary)]">Цепочка состояния</h3>
        <div class="bg-[color:var(--bg-elevated)] rounded-lg p-4 border border-[color:var(--border-muted)]">
          <div class="flex items-center justify-between gap-4 text-xs">
            <div class="flex items-center gap-2">
              <div
                class="w-3 h-3 rounded-full"
                :class="getChainStatusClass('db')"
              ></div>
              <span class="text-[color:var(--text-muted)]">БД</span>
            </div>
            <span class="text-[color:var(--text-dim)]">→</span>
            <div class="flex items-center gap-2">
              <div
                class="w-3 h-3 rounded-full"
                :class="getChainStatusClass('mqtt')"
              ></div>
              <span class="text-[color:var(--text-muted)]">MQTT</span>
            </div>
            <span class="text-[color:var(--text-dim)]">→</span>
            <div class="flex items-center gap-2">
              <div
                class="w-3 h-3 rounded-full"
                :class="getChainStatusClass('ws')"
              ></div>
              <span class="text-[color:var(--text-muted)]">WebSocket</span>
            </div>
            <span class="text-[color:var(--text-dim)]">→</span>
            <div class="flex items-center gap-2">
              <div
                class="w-3 h-3 rounded-full"
                :class="getChainStatusClass('ui')"
              ></div>
              <span class="text-[color:var(--text-muted)]">UI</span>
            </div>
          </div>
          <div class="mt-3 text-xs">
            <div 
              v-if="chainStatus.type === 'success'" 
              class="text-[color:var(--accent-green)] flex items-center gap-2"
            >
              <span class="text-base">✓</span>
              <span>Все компоненты работают нормально</span>
            </div>
            <div 
              v-else-if="chainStatus.type === 'warning'" 
              class="text-[color:var(--accent-amber)] flex items-center gap-2"
            >
              <span class="text-base">⚠</span>
              <span>{{ chainStatus.message }}</span>
            </div>
            <div 
              v-else 
              class="text-[color:var(--accent-red)] flex items-center gap-2"
            >
              <span class="text-base">✗</span>
              <span>{{ chainStatus.message }}</span>
            </div>
          </div>
          <!-- Легенда цветов -->
          <div class="mt-3 pt-3 border-t border-[color:var(--border-muted)] text-xs text-[color:var(--text-dim)]">
            <div class="flex items-center gap-4 flex-wrap">
              <div class="flex items-center gap-1">
                <div class="w-2 h-2 rounded-full bg-[color:var(--accent-green)]"></div>
                <span>Работает</span>
              </div>
              <div class="flex items-center gap-1">
                <div class="w-2 h-2 rounded-full bg-[color:var(--accent-amber)]"></div>
                <span>Деградировано</span>
              </div>
              <div class="flex items-center gap-1">
                <div class="w-2 h-2 rounded-full bg-[color:var(--text-dim)]"></div>
                <span>Проверяется</span>
              </div>
              <div class="flex items-center gap-1">
                <div class="w-2 h-2 rounded-full bg-[color:var(--accent-red)]"></div>
                <span>Недоступно</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Последнее обновление -->
      <div class="text-xs text-[color:var(--text-dim)] text-center">
        Последнее обновление: {{ lastUpdate ? formatTime(lastUpdate) : 'Никогда' }}
      </div>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import AppLayout from '@/Layouts/AppLayout.vue'
import Button from '@/Components/Button.vue'
import ServiceStatusCard from '@/Components/ServiceStatusCard.vue'
import { useSystemStatus } from '@/composables/useSystemStatus'
import { formatTime } from '@/utils/formatTime'

const refreshing = ref(false)
let autoRefreshInterval: ReturnType<typeof setInterval> | null = null

const {
  coreStatus,
  dbStatus,
  wsStatus,
  mqttStatus,
  historyLoggerStatus,
  automationEngineStatus,
  lastUpdate,
  checkHealth,
  checkWebSocketStatus,
} = useSystemStatus()

const historyLoggerEndpoint = 'http://history-logger:9300/health'
const automationEngineEndpoint = 'http://automation-engine:9401/metrics'

// Вычисляем состояние цепочки
const isChainHealthy = computed(() => {
  const criticalStatuses = ['fail', 'offline', 'disconnected']
  return !criticalStatuses.includes(dbStatus.value) &&
         !criticalStatuses.includes(mqttStatus.value) &&
         !criticalStatuses.includes(wsStatus.value)
})

const chainStatus = computed(() => {
  if (isChainHealthy.value) {
    return { type: 'success', message: 'Все компоненты работают нормально' }
  }
  
  const issues: string[] = []
  if (['fail', 'offline', 'disconnected'].includes(dbStatus.value)) {
    issues.push('БД недоступна')
  }
  if (['fail', 'offline', 'disconnected'].includes(mqttStatus.value)) {
    issues.push('MQTT недоступен')
  }
  if (['fail', 'offline', 'disconnected'].includes(wsStatus.value)) {
    issues.push('WebSocket недоступен')
  }
  
  if (issues.length > 0) {
    return { type: 'error', message: issues.join(', ') }
  }
  
  return { type: 'warning', message: 'Некоторые компоненты в состоянии деградации' }
})

function getChainStatusClass(component: 'db' | 'mqtt' | 'ws' | 'ui'): string {
  let status: string
  switch (component) {
    case 'db':
      status = dbStatus.value
      break
    case 'mqtt':
      status = mqttStatus.value
      break
    case 'ws':
      status = wsStatus.value
      break
    case 'ui':
      status = 'success' // UI всегда доступен, если страница загрузилась
      break
    default:
      status = 'unknown'
  }
  
  switch (status) {
    case 'success':
    case 'connected':
      return 'bg-[color:var(--accent-green)]'
    case 'degraded':
    case 'warning':
      return 'bg-[color:var(--accent-amber)]'
    case 'fail':
    case 'offline':
    case 'disconnected':
      return 'bg-[color:var(--accent-red)]'
    default:
      return 'bg-[color:var(--text-dim)]'
  }
}

async function refreshStatus(): Promise<void> {
  refreshing.value = true
  try {
    await Promise.all([
      checkHealth(),
      checkWebSocketStatus(),
    ])
  } finally {
    refreshing.value = false
  }
}

// Автообновление каждые 30 секунд
onMounted(() => {
  refreshStatus()
  autoRefreshInterval = setInterval(() => {
    refreshStatus()
  }, 30000)
})

onUnmounted(() => {
  if (autoRefreshInterval) {
    clearInterval(autoRefreshInterval)
    autoRefreshInterval = null
  }
})
</script>

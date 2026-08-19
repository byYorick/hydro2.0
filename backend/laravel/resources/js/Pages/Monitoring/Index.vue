<template>
  <AppLayout>
    <div class="space-y-4">
      <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h1 class="text-lg font-semibold">
          Здоровье системы
        </h1>
        <div class="flex flex-wrap items-center gap-2">
          <a
            href="http://localhost:3000"
            target="_blank"
            rel="noopener noreferrer"
            class="btn btn-outline h-9 px-3 text-xs"
          >Grafana</a>
          <a
            href="http://localhost:9090"
            target="_blank"
            rel="noopener noreferrer"
            class="btn btn-outline h-9 px-3 text-xs"
          >Prometheus</a>
          <Button
            size="sm"
            variant="secondary"
            :disabled="refreshing"
            @click="refreshStatus"
          >
            {{ refreshing ? 'Обновление...' : 'Обновить' }}
          </Button>
        </div>
      </div>

      <button
        v-if="!isEngineer"
        type="button"
        data-testid="health-summary"
        class="w-full flex items-center justify-between gap-3 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] px-4 py-3 text-left"
        :aria-expanded="detailsOpen"
        @click="detailsOpen = !detailsOpen"
      >
        <span class="flex items-center gap-3">
          <span
            class="w-3 h-3 rounded-full shrink-0"
            :class="summaryDotClass"
          />
          <span class="text-sm font-medium text-[color:var(--text-primary)]">
            {{ healthyCount }} из {{ totalCount }} в норме
          </span>
        </span>
        <span class="text-xs text-[color:var(--text-muted)]">
          {{ detailsOpen ? 'Скрыть детали' : 'Показать детали' }}
        </span>
      </button>

      <div
        v-if="isEngineer || detailsOpen"
        class="space-y-4"
      >
        <div>
          <h3 class="text-sm font-semibold mb-3 text-[color:var(--text-primary)]">
            Основные компоненты
          </h3>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div
              v-for="service in coreServices"
              :key="service.key"
              class="space-y-1"
            >
              <ServiceStatusCard
                :name="service.name"
                :status="service.status"
                :icon="service.icon"
                :description="service.description"
                :status-type="service.statusType"
                :endpoint="service.endpoint"
              />
              <div
                v-if="isEngineer && extraText(service.healthKey)"
                class="px-3 text-xs text-[color:var(--text-muted)]"
              >
                {{ extraText(service.healthKey) }}
              </div>
            </div>
          </div>
        </div>

        <div>
          <h3 class="text-sm font-semibold mb-3 text-[color:var(--text-primary)]">
            Python сервисы
          </h3>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div
              v-for="service in pythonServices"
              :key="service.key"
              class="space-y-1"
            >
              <ServiceStatusCard
                :name="service.name"
                :status="service.status"
                :icon="service.icon"
                :description="service.description"
                :endpoint="service.endpoint"
              />
              <div
                v-if="isEngineer && extraText(service.healthKey)"
                class="px-3 text-xs text-[color:var(--text-muted)]"
              >
                {{ extraText(service.healthKey) }}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div>
        <h3 class="text-sm font-semibold mb-3 text-[color:var(--text-primary)]">
          Пайплайны
        </h3>
        <div class="bg-[color:var(--bg-elevated)] rounded-lg p-4 border border-[color:var(--border-muted)] space-y-3 text-xs">
          <div>
            <div class="font-medium text-[color:var(--text-primary)] mb-1">
              Телеметрия
            </div>
            <div class="text-[color:var(--text-muted)]">
              узел → MQTT → history-logger → PostgreSQL
            </div>
          </div>
          <div>
            <div class="font-medium text-[color:var(--text-primary)] mb-1">
              Команды
            </div>
            <div class="text-[color:var(--text-muted)]">
              Laravel → automation-engine → history-logger → MQTT → узел
            </div>
          </div>
          <div>
            <div class="font-medium text-[color:var(--text-primary)] mb-1">
              UI live
            </div>
            <div class="text-[color:var(--text-muted)]">
              WebSocket (Reverb) — отдельный канал обновления UI, не звено телеметрии
            </div>
          </div>
        </div>
      </div>

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
import { useRole } from '@/composables/useRole'
import { api } from '@/services/api'
import type { SystemHealthPayload } from '@/services/api/system'
import { formatTime } from '@/utils/formatTime'

type StatusType = 'service' | 'ws' | 'mqtt'

interface MonitoredService {
  key: string
  name: string
  status: string
  icon: string
  description: string
  healthKey: string
  statusType?: StatusType
  endpoint?: string
}

const { isEngineer } = useRole()

const refreshing = ref(false)
const detailsOpen = ref(false)
const healthPayload = ref<SystemHealthPayload | null>(null)
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

const historyLoggerEndpoint = '/api/system/health (data.history_logger)'
const automationEngineEndpoint = '/api/system/health (data.automation_engine)'

const coreServices = computed<MonitoredService[]>(() => [
  {
    key: 'core',
    name: 'Core API',
    status: coreStatus.value ?? 'unknown',
    icon: '⚙️',
    description: 'Основной API сервис',
    healthKey: 'app',
  },
  {
    key: 'db',
    name: 'Database',
    status: dbStatus.value ?? 'unknown',
    icon: '💾',
    description: 'PostgreSQL база данных',
    healthKey: 'db',
  },
  {
    key: 'ws',
    name: 'WebSocket',
    status: wsStatus.value ?? 'unknown',
    icon: '🔌',
    description: 'WebSocket соединение',
    healthKey: 'websocket',
    statusType: 'ws',
  },
  {
    key: 'mqtt',
    name: 'MQTT Broker',
    status: mqttStatus.value ?? 'unknown',
    icon: '📡',
    description: 'MQTT брокер',
    healthKey: 'mqtt',
    statusType: 'mqtt',
  },
])

const pythonServices = computed<MonitoredService[]>(() => [
  {
    key: 'history_logger',
    name: 'History Logger',
    status: historyLoggerStatus.value,
    icon: '📝',
    description: 'Логирование телеметрии в БД',
    healthKey: 'history_logger',
    endpoint: historyLoggerEndpoint,
  },
  {
    key: 'automation_engine',
    name: 'Automation Engine',
    status: automationEngineStatus.value,
    icon: '🤖',
    description: 'Автоматизация управления зонами',
    healthKey: 'automation_engine',
    endpoint: automationEngineEndpoint,
  },
])

const allServices = computed(() => [...coreServices.value, ...pythonServices.value])

function isHealthyStatus(status: string): boolean {
  return status === 'ok' || status === 'connected' || status === 'online' || status === 'success'
}

function isFailStatus(status: string): boolean {
  return status === 'fail' || status === 'offline' || status === 'disconnected'
}

const healthyCount = computed(() => allServices.value.filter((service) => isHealthyStatus(service.status)).length)
const totalCount = computed(() => allServices.value.length)

const summaryDotClass = computed(() => {
  if (allServices.value.some((service) => isFailStatus(service.status))) {
    return 'bg-[color:var(--accent-red)]'
  }
  if (healthyCount.value === totalCount.value) {
    return 'bg-[color:var(--accent-green)]'
  }
  return 'bg-[color:var(--accent-amber)]'
})

function extraText(healthKey: string): string {
  if (!isEngineer.value) {
    return ''
  }
  const payload = healthPayload.value
  if (!payload) {
    return ''
  }

  const parts: string[] = []
  const pick = (value: unknown) => {
    if (!value || typeof value !== 'object') {
      return
    }
    const rec = value as Record<string, unknown>
    if (typeof rec.version === 'string' && rec.version.trim()) {
      parts.push(`версия ${rec.version}`)
    }
    if (typeof rec.error === 'string' && rec.error.trim()) {
      parts.push(rec.error)
    }
  }

  pick(payload[healthKey])
  const checks = payload.checks
  if (checks && typeof checks === 'object') {
    pick((checks as Record<string, unknown>)[healthKey])
  }

  return parts.join(' · ')
}

async function loadHealthDetails(): Promise<void> {
  try {
    healthPayload.value = await api.system.health()
  } catch {
    healthPayload.value = null
  }
}

async function refreshStatus(): Promise<void> {
  refreshing.value = true
  try {
    await Promise.all([
      checkHealth(),
      Promise.resolve(checkWebSocketStatus()),
      loadHealthDetails(),
    ])
  } finally {
    refreshing.value = false
  }
}

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

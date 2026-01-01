<template>
  <Modal :open="show" :title="'Мониторинг системы'" @close="$emit('close')">
    <div class="space-y-4">
      <!-- Основные компоненты -->
      <div>
        <h3 class="text-sm font-semibold mb-3 text-[color:var(--text-primary)]">Основные компоненты</h3>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
          <ServiceStatusCard
            name="Core API"
            :status="coreStatus ?? 'unknown'"
            icon="⚙️"
            description="Основной API сервис"
          />
          <ServiceStatusCard
            name="Database"
            :status="dbStatus ?? 'unknown'"
            icon="💾"
            description="PostgreSQL база данных"
          />
          <ServiceStatusCard
            name="WebSocket"
            :status="wsStatus ?? 'unknown'"
            icon="🔌"
            description="WebSocket соединение"
            status-type="ws"
          />
          <ServiceStatusCard
            name="MQTT Broker"
            :status="mqttStatus ?? 'unknown'"
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
            :status="historyLoggerStatus ?? 'unknown'"
            icon="📝"
            description="Логирование телеметрии в БД"
            :endpoint="historyLoggerEndpoint"
          />
          <ServiceStatusCard
            name="Automation Engine"
            :status="automationEngineStatus ?? 'unknown'"
            icon="🤖"
            description="Автоматизация управления зонами"
            :endpoint="automationEngineEndpoint"
          />
        </div>
      </div>

      <!-- Цепочка состояния -->
      <div>
        <h3 class="text-sm font-semibold mb-3 text-[color:var(--text-primary)]">Цепочка состояния</h3>
        <div class="bg-[color:var(--bg-surface-strong)] rounded-lg p-4 border border-[color:var(--border-muted)]">
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
              <span>{{ chainStatus.message }}</span>
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
              <span class="text-base">❌</span>
              <span>{{ chainStatus.message }}</span>
            </div>
            
            <!-- Детальный список проблем -->
            <ul 
              v-if="chainIssues.length > 0" 
              class="mt-2 ml-6 list-disc space-y-1"
              :class="{
                'text-[color:var(--badge-danger-text)]': chainStatus.type === 'error',
                'text-[color:var(--badge-warning-text)]': chainStatus.type === 'warning',
              }"
            >
              <li v-for="issue in chainIssues" :key="issue" class="text-xs">
                {{ issue.replace(/^[❌⚠️]\s*/, '') }}
              </li>
            </ul>
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
        <button
          @click="refreshStatus"
          class="ml-2 px-2 py-1 rounded bg-[color:var(--bg-elevated)] hover:bg-[color:var(--bg-surface-strong)] transition-colors"
          :disabled="refreshing"
        >
          {{ refreshing ? 'Обновление...' : 'Обновить' }}
        </button>
      </div>
    </div>
    
    <template #footer>
      <Button
        variant="secondary"
        size="sm"
        @click="openInNewWindow"
      >
        Открыть в новом окне
      </Button>
      <Button
        variant="secondary"
        size="sm"
        @click="$emit('close')"
      >
        Закрыть
      </Button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue'
import Modal from '@/Components/Modal.vue'
import Button from '@/Components/Button.vue'
import ServiceStatusCard from '@/Components/ServiceStatusCard.vue'
import { useSystemStatus } from '@/composables/useSystemStatus'
import { formatTime } from '@/utils/formatTime'

interface Props {
  show?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  show: false
})

const emit = defineEmits<{
  close: []
}>()

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
// Цепочка считается здоровой, если нет критических проблем (fail/offline/disconnected)
// unknown и degraded считаются допустимыми состояниями (еще инициализируются)
// @ts-ignore - не используется сейчас, но может понадобиться
const isChainHealthy = computed(() => {
  // Критические проблемы блокируют работу системы
  const hasCriticalIssues = 
    dbStatus.value === 'fail' ||
    mqttStatus.value === 'offline' ||
    wsStatus.value === 'disconnected' ||
    historyLoggerStatus.value === 'fail' ||
    automationEngineStatus.value === 'fail'
  
  // Предупреждения - система работает, но может работать неоптимально
  // @ts-ignore - не используется сейчас, но может понадобиться
  const hasWarnings = 
    dbStatus.value === 'unknown' ||
    mqttStatus.value === 'degraded' ||
    mqttStatus.value === 'unknown' ||
    wsStatus.value === 'unknown' ||
    historyLoggerStatus.value === 'unknown' ||
    automationEngineStatus.value === 'unknown'
  
  // Цепочка здорова, если нет критических проблем
  return !hasCriticalIssues
})

// Вычисляем список проблемных компонентов для детального отображения
const chainIssues = computed(() => {
  const issues: string[] = []
  
  // Критические проблемы (блокируют работу)
  if (dbStatus.value === 'fail') {
    issues.push('❌ База данных недоступна - критическая проблема')
  } else if (dbStatus.value === 'unknown') {
    issues.push('⚠️ Статус БД неизвестен - проверка не завершена')
  }
  
  if (mqttStatus.value === 'offline') {
    issues.push('❌ MQTT брокер недоступен - критическая проблема')
  } else if (mqttStatus.value === 'degraded') {
    issues.push('⚠️ MQTT брокер работает в деградированном режиме')
  } else if (mqttStatus.value === 'unknown') {
    issues.push('⚠️ Статус MQTT неизвестен - проверка не завершена')
  }
  
  if (wsStatus.value === 'disconnected') {
    issues.push('❌ WebSocket соединение разорвано - критическая проблема')
  } else if (wsStatus.value === 'unknown') {
    issues.push('⚠️ Статус WebSocket неизвестен - проверка не завершена')
  }
  
  // Проблемы сервисов (не блокируют, но влияют на функциональность)
  if (historyLoggerStatus.value === 'fail') {
    issues.push('❌ History Logger недоступен - телеметрия не логируется')
  } else if (historyLoggerStatus.value === 'unknown') {
    issues.push('⚠️ Статус History Logger неизвестен - проверка не завершена или требуется аутентификация')
  }
  
  if (automationEngineStatus.value === 'fail') {
    issues.push('❌ Automation Engine недоступен - автоматизация не работает')
  } else if (automationEngineStatus.value === 'unknown') {
    issues.push('⚠️ Статус Automation Engine неизвестен - проверка не завершена или требуется аутентификация')
  }
  
  return issues
})

// Вычисляем общий статус цепочки для отображения
const chainStatus = computed(() => {
  const criticalCount = chainIssues.value.filter(issue => issue.startsWith('❌')).length
  const warningCount = chainIssues.value.filter(issue => issue.startsWith('⚠️')).length
  
  if (criticalCount > 0) {
    return { type: 'error', message: `Обнаружены ${criticalCount} критических проблем` }
  } else if (warningCount > 0) {
    return { type: 'warning', message: `Обнаружены ${warningCount} предупреждений` }
  } else {
    return { type: 'success', message: 'Все компоненты цепочки работают корректно' }
  }
})

function getChainStatusClass(component: 'db' | 'mqtt' | 'ws' | 'ui'): string {
  switch (component) {
    case 'db':
      if (dbStatus.value === 'ok') return 'bg-[color:var(--accent-green)]'
      if (dbStatus.value === 'unknown') return 'bg-[color:var(--text-dim)]'
      return 'bg-[color:var(--accent-red)]'
    case 'mqtt':
      if (mqttStatus.value === 'online') return 'bg-[color:var(--accent-green)]'
      if (mqttStatus.value === 'degraded') return 'bg-[color:var(--accent-amber)]'
      if (mqttStatus.value === 'unknown') return 'bg-[color:var(--text-dim)]'
      return 'bg-[color:var(--accent-red)]'
    case 'ws':
      if (wsStatus.value === 'connected') return 'bg-[color:var(--accent-green)]'
      if (wsStatus.value === 'unknown') return 'bg-[color:var(--text-dim)]'
      return 'bg-[color:var(--accent-red)]'
    case 'ui':
      // UI всегда доступен, если модальное окно открыто
      return 'bg-[color:var(--accent-green)]'
    default:
      return 'bg-[color:var(--text-dim)]'
  }
}

async function refreshStatus(): Promise<void> {
  refreshing.value = true
  try {
    // checkHealth() теперь получает все статусы, включая MQTT
    // checkWebSocketStatus() не требует API запросов
    await Promise.all([
      checkHealth(),
      checkWebSocketStatus(),
    ])
  } finally {
    refreshing.value = false
  }
}

function openInNewWindow(): void {
  const url = window.location.origin + '/monitoring'
  window.open(url, 'system-monitoring', 'width=1200,height=800,menubar=no,toolbar=no')
}

// Автообновление при открытии модального окна
// Используем более длинный интервал, чтобы не конфликтовать с основным мониторингом
watch(() => props.show, (isOpen: boolean) => {
  if (isOpen) {
    refreshStatus()
    // Устанавливаем автообновление каждые 30 секунд (совпадает с основным интервалом)
    // Это предотвращает дублирование запросов
    if (autoRefreshInterval) {
      clearInterval(autoRefreshInterval)
    }
    autoRefreshInterval = setInterval(() => {
      if (props.show) {
        refreshStatus()
      }
    }, 30000) // Увеличено с 10 до 30 секунд для соответствия основному интервалу
  } else {
    // Очистка при закрытии
    if (autoRefreshInterval) {
      clearInterval(autoRefreshInterval)
      autoRefreshInterval = null
    }
  }
})

onUnmounted(() => {
  if (autoRefreshInterval) {
    clearInterval(autoRefreshInterval)
    autoRefreshInterval = null
  }
})
</script>

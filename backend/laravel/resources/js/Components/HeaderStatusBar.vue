<template>
  <div class="flex items-center gap-4 px-4 py-2 bg-neutral-900 border-b border-neutral-800">
    <div class="flex items-center gap-4 text-xs">
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
          <span class="text-neutral-400 text-[10px] leading-tight">Core</span>
          <span
            class="text-[11px] font-medium leading-tight transition-colors"
            :class="getStatusTextClass(coreStatus)"
          >
            {{ getStatusText(coreStatus) }}
          </span>
        </div>
        <div
          class="absolute left-0 top-full mt-2 px-2 py-1.5 bg-neutral-800 rounded text-xs text-neutral-200 opacity-0 group-hover:opacity-100 pointer-events-none whitespace-nowrap z-50 shadow-lg border border-neutral-700"
        >
          <div class="font-medium">Core Service</div>
          <div class="text-[10px] text-neutral-400 mt-0.5">
            Статус: {{ getStatusText(coreStatus) }}
          </div>
          <div v-if="lastUpdate" class="text-[10px] text-neutral-400 mt-1">
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
          <span class="text-neutral-400 text-[10px] leading-tight">Database</span>
          <span
            class="text-[11px] font-medium leading-tight transition-colors"
            :class="getStatusTextClass(dbStatus)"
          >
            {{ getStatusText(dbStatus) }}
          </span>
        </div>
        <div
          class="absolute left-0 top-full mt-2 px-2 py-1.5 bg-neutral-800 rounded text-xs text-neutral-200 opacity-0 group-hover:opacity-100 pointer-events-none whitespace-nowrap z-50 shadow-lg border border-neutral-700"
        >
          <div class="font-medium">Database</div>
          <div class="text-[10px] text-neutral-400 mt-0.5">
            Статус: {{ getStatusText(dbStatus) }}
          </div>
          <div v-if="lastUpdate" class="text-[10px] text-neutral-400 mt-1">
            Обновлено: {{ formatTime(lastUpdate) }}
          </div>
        </div>
      </div>

      <!-- WebSocket Status -->
      <div class="flex items-center gap-2 group relative">
        <div class="relative">
          <div
            class="w-2.5 h-2.5 rounded-full transition-all duration-300"
            :class="[getWsStatusDotClass(wsStatus), wsStatus === 'connected' ? 'animate-pulse' : '']"
          ></div>
          <div
            v-if="wsStatus === 'connected'"
            class="absolute inset-0 w-2.5 h-2.5 rounded-full animate-ping opacity-75"
            :class="getWsStatusDotClass(wsStatus)"
          ></div>
        </div>
        <div class="flex flex-col">
          <span class="text-neutral-400 text-[10px] leading-tight">WebSocket</span>
          <span
            class="text-[11px] font-medium leading-tight transition-colors"
            :class="getWsStatusTextClass(wsStatus)"
          >
            {{ getWsStatusText(wsStatus) }}
          </span>
        </div>
        <div
          class="absolute left-0 top-full mt-2 px-2 py-1.5 bg-neutral-800 rounded text-xs text-neutral-200 opacity-0 group-hover:opacity-100 pointer-events-none whitespace-nowrap z-50 shadow-lg border border-neutral-700"
        >
          <div class="font-medium">WebSocket Connection</div>
          <div class="text-[10px] text-neutral-400 mt-0.5">
            Статус: {{ getWsStatusText(wsStatus) }}
          </div>
          <div v-if="wsStatus === 'connected'" class="text-[10px] text-emerald-400 mt-1">
            ✓ Соединение активно
          </div>
          <div v-else-if="wsStatus === 'disconnected'" class="text-[10px] text-red-400 mt-1">
            ✗ Соединение разорвано
            <div class="text-[9px] text-neutral-500 mt-0.5">
              Проверьте настройки WebSocket
            </div>
          </div>
          <div v-else class="text-[10px] text-neutral-500 mt-1">
            ? Инициализация...
            <div class="text-[9px] text-neutral-500 mt-0.5">
              Ожидание подключения
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
          <span class="text-neutral-400 text-[10px] leading-tight">MQTT</span>
          <span
            class="text-[11px] font-medium leading-tight transition-colors"
            :class="getMqttStatusTextClass(mqttStatus)"
          >
            {{ getMqttStatusText(mqttStatus) }}
          </span>
        </div>
        <div
          class="absolute left-0 top-full mt-2 px-2 py-1.5 bg-neutral-800 rounded text-xs text-neutral-200 opacity-0 group-hover:opacity-100 pointer-events-none whitespace-nowrap z-50 shadow-lg border border-neutral-700"
        >
          <div class="font-medium">MQTT Broker</div>
          <div class="text-[10px] text-neutral-400 mt-0.5">
            Статус: {{ getMqttStatusText(mqttStatus) }}
          </div>
          <div v-if="mqttStatus === 'online'" class="text-[10px] text-emerald-400 mt-1">
            ✓ Брокер доступен
          </div>
          <div v-else-if="mqttStatus === 'offline'" class="text-[10px] text-red-400 mt-1">
            ✗ Брокер недоступен
          </div>
          <div v-else-if="mqttStatus === 'degraded'" class="text-[10px] text-amber-400 mt-1">
            ⚠ Частичная доступность
          </div>
          <div v-else class="text-[10px] text-neutral-500 mt-1">
            ? Статус неизвестен
          </div>
        </div>
      </div>

      <!-- Services Status (компактный вид с возможностью открыть модальное окно) -->
      <div class="flex items-center gap-2 ml-auto">
        <button
          @click="showMonitoringModal = true"
          class="flex items-center gap-2 px-2 py-1 rounded-md hover:bg-neutral-800 transition-colors text-xs text-neutral-400 hover:text-neutral-200"
          title="Мониторинг сервисов"
        >
          <span>📊</span>
          <span class="hidden sm:inline">Сервисы</span>
        </button>
      </div>
    </div>
    
    <!-- Модальное окно мониторинга сервисов -->
    <SystemMonitoringModal
      :show="showMonitoringModal"
      @close="showMonitoringModal = false"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useSystemStatus } from '@/composables/useSystemStatus'
import { formatTime } from '@/utils/formatTime'
import SystemMonitoringModal from '@/Components/SystemMonitoringModal.vue'

const { 
  coreStatus, 
  dbStatus, 
  wsStatus, 
  mqttStatus, 
  historyLoggerStatus,
  automationEngineStatus,
  lastUpdate 
} = useSystemStatus()
const showMonitoringModal = ref(false)

function getStatusDotClass(status) {
  switch (status) {
    case 'ok':
      return 'bg-emerald-400'
    case 'fail':
      return 'bg-red-400'
    default:
      return 'bg-neutral-500'
  }
}

function getStatusText(status) {
  switch (status) {
    case 'ok':
      return 'Онлайн'
    case 'fail':
      return 'Офлайн'
    default:
      return 'Неизвестно'
  }
}

function getStatusTextClass(status) {
  switch (status) {
    case 'ok':
      return 'text-emerald-400'
    case 'fail':
      return 'text-red-400'
    default:
      return 'text-neutral-500'
  }
}

function getWsStatusDotClass(status) {
  switch (status) {
    case 'connected':
      return 'bg-emerald-400'
    case 'disconnected':
      return 'bg-red-400'
    default:
      return 'bg-neutral-500'
  }
}

function getWsStatusText(status) {
  switch (status) {
    case 'connected':
      return 'Подключено'
    case 'disconnected':
      return 'Отключено'
    default:
      return 'Неизвестно'
  }
}

function getWsStatusTextClass(status) {
  switch (status) {
    case 'connected':
      return 'text-emerald-400'
    case 'disconnected':
      return 'text-red-400'
    default:
      return 'text-neutral-500'
  }
}

function getMqttStatusDotClass(status) {
  switch (status) {
    case 'online':
      return 'bg-emerald-400'
    case 'offline':
      return 'bg-red-400'
    case 'degraded':
      return 'bg-amber-400'
    default:
      return 'bg-neutral-500'
  }
}

function getMqttStatusText(status) {
  switch (status) {
    case 'online':
      return 'Онлайн'
    case 'offline':
      return 'Офлайн'
    case 'degraded':
      return 'Частично'
    default:
      return 'Неизвестно'
  }
}

function getMqttStatusTextClass(status) {
  switch (status) {
    case 'online':
      return 'text-emerald-400'
    case 'offline':
      return 'text-red-400'
    case 'degraded':
      return 'text-amber-400'
    default:
      return 'text-neutral-500'
  }
}
</script>


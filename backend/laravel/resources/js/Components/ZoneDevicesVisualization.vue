<template>
  <div class="relative overflow-hidden">
    <div class="flex items-center justify-between mb-2">
      <div class="text-xs font-semibold text-[color:var(--text-primary)]">
        Устройства зоны
      </div>
      <div class="flex items-center gap-1.5">
        <button
          class="p-1.5 rounded border transition-colors"
          :class="viewMode === 'grid' 
            ? 'border-[color:var(--border-strong)] bg-[color:var(--bg-elevated)] text-[color:var(--text-primary)]' 
            : 'border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] text-[color:var(--text-muted)] hover:bg-[color:var(--bg-elevated)]'"
          title="Сетка"
          @click="viewMode = 'grid'"
        >
          <svg
            class="w-4 h-4"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"
            />
          </svg>
        </button>
        <button
          class="p-1.5 rounded border transition-colors"
          :class="viewMode === 'graph' 
            ? 'border-[color:var(--border-strong)] bg-[color:var(--bg-elevated)] text-[color:var(--text-primary)]' 
            : 'border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] text-[color:var(--text-muted)] hover:bg-[color:var(--bg-elevated)]'"
          title="Граф"
          @click="viewMode = 'graph'"
        >
          <svg
            class="w-4 h-4"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M13 10V3L4 14h7v7l9-11h-7z"
            />
          </svg>
        </button>
      </div>
      <template v-if="canManage">
        <Button
          size="sm"
          variant="secondary"
          @click="$emit('attach')"
        >
          Привязать узлы
        </Button>
      </template>
    </div>

    <!-- Граф визуализация -->
    <div
      v-if="viewMode === 'graph' && devices.length > 0"
      class="relative min-h-[300px] sm:min-h-[400px]"
    >
      <div class="absolute inset-0 flex items-center justify-center">
        <!-- Центральная зона (SCADA стиль) -->
        <div
          class="relative z-10 flex flex-col items-center justify-center w-36 h-36 sm:w-44 sm:h-44 rounded-full border-3 transition-all duration-300 hover:scale-105 shadow-lg"
          :class="zoneStatusClass"
        >
          <!-- SCADA индикатор статуса зоны -->
          <div class="absolute top-2 right-2">
            <StatusIndicator
              :status="zoneStatus || 'NEUTRAL'"
              :pulse="zoneStatus === 'RUNNING'"
              size="medium"
            />
          </div>
          
          <div class="text-sm sm:text-base font-bold text-center px-3">
            {{ zoneName }}
          </div>
          <div class="text-xs text-[color:var(--text-muted)] mt-1 font-medium">
            {{ devices.length }} {{ devices.length === 1 ? 'устройство' : devices.length < 5 ? 'устройства' : 'устройств' }}
          </div>
          
          <!-- Статистика устройств -->
          <div class="mt-2 flex items-center gap-2 text-[10px]">
            <div class="flex items-center gap-1">
              <div class="w-1.5 h-1.5 rounded-full bg-[color:var(--accent-green)]"></div>
              <span>{{ getOnlineDevicesCount() }}</span>
            </div>
            <div class="flex items-center gap-1">
              <div class="w-1.5 h-1.5 rounded-full bg-[color:var(--accent-red)]"></div>
              <span>{{ getOfflineDevicesCount() }}</span>
            </div>
          </div>
        </div>

        <!-- Устройства вокруг зоны -->
        <div
          v-for="(device, index) in devices"
          :key="device.id"
          class="absolute z-20 transition-all duration-300 hover:scale-110"
          :style="getDevicePosition(index, devices.length)"
        >
          <!-- Линия связи (SCADA стиль) -->
          <svg
            class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 pointer-events-none z-0"
            :style="getConnectionLineStyle(index, devices.length)"
          >
            <line
              x1="50%"
              y1="50%"
              :x2="getConnectionX(index, devices.length)"
              :y2="getConnectionY(index, devices.length)"
              stroke="currentColor"
              stroke-width="2"
              stroke-dasharray="6,4"
              :class="device.status === 'online' ? 'text-[color:var(--accent-green)] opacity-60' : 'text-[color:var(--text-dim)] opacity-40'"
            />
          </svg>

          <!-- Устройство -->
          <Link
            :href="`/devices/${device.id}`"
            class="group relative block w-20 h-20 sm:w-24 sm:h-24 rounded-lg border-2 transition-all duration-300 hover:shadow-[var(--shadow-card)] hover:scale-110"
            :class="getDeviceCardClass(device)"
            :title="device.uid || device.name || `Device ${device.id}`"
          >
            <div class="flex flex-col items-center justify-center h-full p-2 bg-[color:var(--bg-surface-strong)] rounded-lg">
              <!-- SCADA индикатор статуса -->
              <div class="absolute top-1 right-1 z-10">
                <StatusIndicator
                  :status="getDeviceStatus(device)"
                  :pulse="device.status === 'online'"
                  size="small"
                />
              </div>
              
              <!-- Иконка устройства -->
              <div class="w-8 h-8 sm:w-10 sm:h-10 mb-1 text-[color:var(--text-dim)]" v-html="getDeviceIconSvg(device.type)"></div>
              
              <!-- Название устройства -->
              <div class="text-[9px] sm:text-xs font-semibold text-center truncate w-full px-1">
                {{ getDeviceShortName(device) }}
              </div>
              
              <!-- Тип устройства -->
              <div class="text-[7px] sm:text-[9px] text-[color:var(--text-dim)] text-center mt-0.5">
                {{ translateDeviceType(device.type) }}
              </div>
            </div>
          </Link>
        </div>
      </div>
    </div>

    <!-- Сетка визуализация -->
    <div
      v-else-if="viewMode === 'grid' && devices.length > 0"
      class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-2"
    >
      <div
        v-for="device in devices"
        :key="device.id"
        class="group relative rounded-lg border bg-[color:var(--bg-surface-strong)] flex flex-col overflow-hidden"
        :class="getDeviceCardClass(device)"
      >
        <!-- Шапка карточки: иконка + имя + статус -->
        <Link
          :href="`/devices/${device.id}`"
          class="flex items-center gap-1.5 px-2 py-1.5 hover:bg-[color:var(--bg-elevated)]/40 transition-colors"
        >
          <span class="w-5 h-5 shrink-0 text-[color:var(--text-dim)]" v-html="getDeviceIconSvg(device.type)"></span>
          <div class="min-w-0 flex-1">
            <div class="text-[11px] font-semibold truncate text-[color:var(--text-primary)]">
              {{ device.uid || device.name || `#${device.id}` }}
            </div>
            <div class="text-[10px] text-[color:var(--text-dim)] uppercase tracking-wide">
              {{ translateDeviceType(device.type) }}
            </div>
          </div>
          <Badge
            :variant="device.status === 'online' ? 'success' : device.status === 'offline' ? 'danger' : 'neutral'"
            size="sm"
            class="shrink-0"
          >
            {{ device.status === 'online' ? '●' : device.status === 'offline' ? '○' : '◑' }}
          </Badge>
        </Link>

        <!-- Связь и память -->
        <div
          v-if="device.rssi != null || device.free_heap_bytes != null || device.uptime_seconds != null"
          class="border-t border-[color:var(--border-muted)] px-2 py-1 space-y-0.5"
        >
          <div v-if="device.rssi != null" class="flex items-center justify-between font-mono text-[10px]">
            <span class="text-[color:var(--text-dim)]">Wi-Fi</span>
            <span :class="rssiClass(device.rssi)">{{ device.rssi }} dBm</span>
          </div>
          <div v-if="device.free_heap_bytes != null" class="flex items-center justify-between font-mono text-[10px]">
            <span class="text-[color:var(--text-dim)]">Heap</span>
            <span class="text-[color:var(--text-primary)]">{{ formatHeap(device.free_heap_bytes) }}</span>
          </div>
          <div v-if="device.uptime_seconds != null" class="flex items-center justify-between font-mono text-[10px]">
            <span class="text-[color:var(--text-dim)]">Uptime</span>
            <span class="text-[color:var(--text-primary)]">{{ formatUptime(device.uptime_seconds) }}</span>
          </div>
        </div>

        <!-- Футер: FW + last_seen + кнопка -->
        <div class="mt-auto border-t border-[color:var(--border-muted)] px-2 py-1 flex items-center gap-2 text-[10px] text-[color:var(--text-dim)]">
          <span v-if="device.fw_version" class="font-mono">v{{ device.fw_version }}</span>
          <span v-if="device.last_seen_at" class="truncate">{{ formatLastSeen(device.last_seen_at) }}</span>
          <div v-if="canManage" class="ml-auto shrink-0" @click.stop>
            <button
              type="button"
              class="h-5 px-1.5 text-[10px] rounded border border-[color:var(--border-muted)] text-[color:var(--text-dim)] hover:text-[color:var(--text-primary)] hover:border-[color:var(--border-strong)] transition-colors"
              @click.stop="$emit('configure', device)"
            >
              Конфиг
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Пустое состояние -->
    <div
      v-else
      class="text-center py-8 text-[color:var(--text-muted)]"
    >
      <div class="text-4xl mb-2">
        📱
      </div>
      <div class="text-sm mb-3">
        Нет устройств в зоне
      </div>
      <template v-if="canManage">
        <Button
          size="sm"
          variant="secondary"
          @click="$emit('attach')"
        >
          Привязать узлы
        </Button>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Link } from '@inertiajs/vue3'
import Button from '@/Components/Button.vue'
import Badge from '@/Components/Badge.vue'
import StatusIndicator from '@/Components/StatusIndicator.vue'
import type { Device } from '@/types'
import { useRole } from '@/composables/useRole'

type ViewMode = 'grid' | 'graph'

interface Props {
  zoneName: string
  zoneStatus?: string
  devices: Device[]
  canManage?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  zoneStatus: 'RUNNING',
  canManage: false
})

defineEmits<{
  attach: []
  configure: [device: Device]
}>()

useRole()
const viewMode = ref<ViewMode>('grid')

const zoneStatusClass = computed(() => {
  switch (props.zoneStatus) {
    case 'RUNNING':
      return 'border-[color:var(--badge-success-border)] bg-[color:var(--badge-success-bg)] text-[color:var(--badge-success-text)]'
    case 'PAUSED':
      return 'border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] text-[color:var(--text-primary)]'
    case 'ALARM':
      return 'border-[color:var(--badge-danger-border)] bg-[color:var(--badge-danger-bg)] text-[color:var(--badge-danger-text)]'
    case 'WARNING':
      return 'border-[color:var(--badge-warning-border)] bg-[color:var(--badge-warning-bg)] text-[color:var(--badge-warning-text)]'
    default:
      return 'border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] text-[color:var(--text-primary)]'
  }
})

function getDeviceIconSvg(type: string | undefined): string {
  const a = `xmlns="http://www.w3.org/2000/svg" width="100%" height="100%" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"`
  const icons: Record<string, string> = {
    // Колба — pH сенсор
    ph: `<svg ${a}><path d="M8 3h8"/><path d="M9 3v6L5 17a1 1 0 00.9 1.5h12.2A1 1 0 0019 17l-4-8V3"/><line x1="8" y1="14" x2="16" y2="14"/></svg>`,
    // Синусоида — EC/проводимость
    ec: `<svg ${a}><path d="M2 12c2-6 4-6 6 0s4 6 6 0 4-6 6 0"/></svg>`,
    // Концентрические окружности — датчик
    sensor: `<svg ${a}><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r="1" fill="currentColor" stroke="none"/></svg>`,
    // Шестерня — актуатор
    actuator: `<svg ${a}><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/></svg>`,
    // Чип CPU — контроллер
    controller: `<svg ${a}><rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/></svg>`,
    // Капля воды — полив/насос
    irrig: `<svg ${a}><path d="M12 2C6.5 9 4 13 4 16a8 8 0 0016 0c0-3-2.5-7-8-14z"/></svg>`,
    // Термометр — климат
    climate: `<svg ${a}><path d="M14 14.76V3.5a2.5 2.5 0 00-5 0v11.26a4.5 4.5 0 105 0z"/></svg>`,
    // Лампочка — освещение
    light: `<svg ${a}><path d="M9 18h6"/><path d="M10 22h4"/><path d="M12 2a7 7 0 014.95 11.95A5 5 0 0115 18H9a5 5 0 01-1.95-4.05A7 7 0 0112 2z"/></svg>`,
    // Тумблер — реле
    relay: `<svg ${a}><rect x="1" y="8" width="22" height="8" rx="4"/><circle cx="16" cy="12" r="3" fill="currentColor" stroke="none"/></svg>`,
    // Волны — датчик уровня воды
    water_sensor: `<svg ${a}><path d="M2 12c1.5-2 3-2 4.5 0s3 2 4.5 0 3-2 4.5 0 1.5 2 3 2"/><path d="M2 17c1.5-2 3-2 4.5 0s3 2 4.5 0 3-2 4.5 0 1.5 2 3 2"/><line x1="12" y1="3" x2="12" y2="9"/></svg>`,
    // Стрелки цикла — рециркуляция
    recirculation: `<svg ${a}><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/></svg>`,
  }
  // Крест в прямоугольнике — неизвестный тип
  const fallback = `<svg ${a}><rect x="3" y="3" width="18" height="18" rx="3"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>`
  return icons[type ?? ''] ?? fallback
}

function translateDeviceType(type: string | undefined): string {
  const types: Record<string, string> = {
    ph: 'pH сенсор',
    ec: 'EC сенсор',
    sensor: 'Сенсор',
    actuator: 'Актуатор',
    controller: 'Контроллер',
    irrig: 'Насос',
    climate: 'Климат',
    light: 'Освещение',
    relay: 'Реле',
    water_sensor: 'Уровень воды',
    recirculation: 'Рециркуляция',
    unknown: 'Устройство',
  }
  return types[type ?? ''] ?? 'Устройство'
}

function getDeviceShortName(device: Device): string {
  const name = device.uid || device.name || `Device ${device.id}`
  return name.length > 8 ? name.substring(0, 8) + '...' : name
}

function getDeviceCardClass(device: Device): string {
  const base = 'bg-[color:var(--bg-surface-strong)]'
  if (device.status === 'online') {
    return `${base} border-[color:var(--badge-success-border)] hover:border-[color:var(--accent-green)]`
  } else if (device.status === 'offline') {
    return `${base} border-[color:var(--badge-danger-border)] hover:border-[color:var(--accent-red)]`
  } else if (device.status === 'degraded') {
    return `${base} border-[color:var(--badge-warning-border)] hover:border-[color:var(--accent-amber)]`
  }
  return `${base} border-[color:var(--border-muted)] hover:border-[color:var(--border-strong)]`
}

function getDeviceStatus(device: Device): string {
  // Преобразуем статус устройства в формат для StatusIndicator
  if (device.status === 'online') return 'ONLINE'
  if (device.status === 'offline') return 'OFFLINE'
  if (device.status === 'degraded') return 'WARNING'
  return 'NEUTRAL'
}

function getDevicePosition(index: number, total: number): Record<string, string> {
  const radius = 140 // Радиус в пикселях
  const angle = (index / total) * 2 * Math.PI - Math.PI / 2 // Начинаем сверху
  const x = Math.cos(angle) * radius
  const y = Math.sin(angle) * radius

  return {
    left: `calc(50% + ${x}px)`,
    top: `calc(50% + ${y}px)`,
    transform: 'translate(-50%, -50%)',
  }
}

function getConnectionLineStyle(index: number, total: number): Record<string, string> {
  const radius = 140
  const angle = (index / total) * 2 * Math.PI - Math.PI / 2
  const x = Math.cos(angle) * radius
  const y = Math.sin(angle) * radius

  const centerX = 50 // 50% от центра
  const centerY = 50
  const deviceX = 50 + (x / radius) * 20 // Примерно 20% от центра
  const deviceY = 50 + (y / radius) * 20

  const length = Math.sqrt(Math.pow(deviceX - centerX, 2) + Math.pow(deviceY - centerY, 2))
  const angleDeg = (Math.atan2(deviceY - centerY, deviceX - centerX) * 180) / Math.PI

  return {
    width: `${length}%`,
    height: '2px',
    transform: `rotate(${angleDeg}deg)`,
    transformOrigin: '0 0',
  }
}

function getConnectionX(index: number, total: number): string {
  const radius = 140
  const angle = (index / total) * 2 * Math.PI - Math.PI / 2
  const x = Math.cos(angle) * radius
  return `${50 + (x / radius) * 20}%`
}

function getConnectionY(index: number, total: number): string {
  const radius = 140
  const angle = (index / total) * 2 * Math.PI - Math.PI / 2
  const y = Math.sin(angle) * radius
  return `${50 + (y / radius) * 20}%`
}

function getOnlineDevicesCount(): number {
  return props.devices.filter(d => d.status === 'online').length
}

function getOfflineDevicesCount(): number {
  return props.devices.filter(d => d.status === 'offline').length
}

function formatLastSeen(timestamp: string | undefined): string {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)

  if (diffMins < 1) return 'Только что'
  if (diffMins < 60) return `${diffMins} мин назад`
  const diffHours = Math.floor(diffMins / 60)
  if (diffHours < 24) return `${diffHours} ч назад`
  const diffDays = Math.floor(diffHours / 24)
  return `${diffDays} дн назад`
}

function rssiClass(rssi: number): string {
  if (rssi >= -60) return 'text-[color:var(--accent-green)]'
  if (rssi >= -75) return 'text-[color:var(--accent-amber)]'
  return 'text-[color:var(--accent-red)]'
}

function formatHeap(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`
  return `${bytes} B`
}

function formatUptime(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`
  return `${Math.floor(seconds / 86400)}d`
}
</script>

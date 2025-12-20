<template>
  <Card class="relative overflow-hidden">
    <div class="flex items-center justify-between mb-3">
      <div class="text-sm font-semibold">Устройства зоны</div>
      <div class="flex items-center gap-2">
        <button
          @click="viewMode = 'grid'"
          class="p-1.5 rounded border transition-colors"
          :class="viewMode === 'grid' 
            ? 'border-[color:var(--border-strong)] bg-[color:var(--bg-elevated)] text-[color:var(--text-primary)]' 
            : 'border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] text-[color:var(--text-muted)] hover:bg-[color:var(--bg-elevated)]'"
          title="Сетка"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
          </svg>
        </button>
        <button
          @click="viewMode = 'graph'"
          class="p-1.5 rounded border transition-colors"
          :class="viewMode === 'graph' 
            ? 'border-[color:var(--border-strong)] bg-[color:var(--bg-elevated)] text-[color:var(--text-primary)]' 
            : 'border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] text-[color:var(--text-muted)] hover:bg-[color:var(--bg-elevated)]'"
          title="Граф"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
        </button>
      </div>
      <template v-if="canManage">
        <Button size="sm" variant="secondary" @click="$emit('attach')">
          Привязать узлы
        </Button>
      </template>
    </div>

    <!-- Граф визуализация -->
    <div v-if="viewMode === 'graph' && devices.length > 0" class="relative min-h-[300px] sm:min-h-[400px]">
      <div class="absolute inset-0 flex items-center justify-center">
        <!-- Центральная зона -->
        <div
          class="relative z-10 flex flex-col items-center justify-center w-32 h-32 sm:w-40 sm:h-40 rounded-full border-2 transition-all duration-300 hover:scale-105"
          :class="zoneStatusClass"
        >
          <div class="text-xs sm:text-sm font-semibold text-center px-2">{{ zoneName }}</div>
          <div class="text-xs text-[color:var(--text-muted)] mt-1">{{ devices.length }} устройств</div>
        </div>

        <!-- Устройства вокруг зоны -->
        <div
          v-for="(device, index) in devices"
          :key="device.id"
          class="absolute z-20 transition-all duration-300 hover:scale-110"
          :style="getDevicePosition(index, devices.length)"
        >
          <!-- Линия связи -->
          <svg
            class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 pointer-events-none"
            :style="getConnectionLineStyle(index, devices.length)"
          >
            <line
              x1="50%"
              y1="50%"
              :x2="getConnectionX(index, devices.length)"
              :y2="getConnectionY(index, devices.length)"
              stroke="currentColor"
              stroke-width="1.5"
              stroke-dasharray="4,4"
              class="text-[color:var(--text-dim)]"
            />
          </svg>

          <!-- Устройство -->
          <Link
            :href="`/devices/${device.id}`"
            class="block w-16 h-16 sm:w-20 sm:h-20 rounded-lg border-2 transition-all duration-300 hover:shadow-[var(--shadow-card)]"
            :class="getDeviceCardClass(device)"
            :title="device.uid || device.name || `Device ${device.id}`"
          >
            <div class="flex flex-col items-center justify-center h-full p-2">
              <div class="text-lg sm:text-xl mb-1">{{ getDeviceIcon(device.type) }}</div>
              <div class="text-[8px] sm:text-xs font-medium text-center truncate w-full">
                {{ getDeviceShortName(device) }}
              </div>
              <div
                class="absolute top-1 right-1 w-2 h-2 rounded-full"
                :class="getStatusDotClass(device.status)"
              ></div>
            </div>
          </Link>
        </div>
      </div>
    </div>

    <!-- Сетка визуализация -->
    <div v-else-if="viewMode === 'grid' && devices.length > 0" class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
      <Link
        v-for="device in devices"
        :key="device.id"
        :href="`/devices/${device.id}`"
        class="group relative rounded-lg border-2 p-3 transition-all duration-200 hover:shadow-[var(--shadow-card)] hover:scale-105"
        :class="getDeviceCardClass(device)"
      >
        <!-- Статус индикатор -->
        <div class="absolute top-2 right-2 flex items-center gap-1.5">
          <div
            class="w-2 h-2 rounded-full animate-pulse"
            :class="getStatusDotClass(device.status)"
          ></div>
          <Badge
            :variant="device.status === 'online' ? 'success' : device.status === 'offline' ? 'danger' : 'neutral'"
            class="text-[10px] px-1.5 py-0.5"
          >
            {{ device.status?.toUpperCase() || 'UNKNOWN' }}
          </Badge>
        </div>

        <!-- Иконка устройства -->
        <div class="flex items-center justify-center mb-2">
          <div class="text-3xl">{{ getDeviceIcon(device.type) }}</div>
        </div>

        <!-- Название -->
        <div class="text-sm font-semibold text-center mb-1 truncate">
          {{ device.uid || device.name || `Device ${device.id}` }}
        </div>

        <!-- Тип -->
        <div class="text-xs text-[color:var(--text-muted)] text-center mb-2">
          {{ translateDeviceType(device.type) }}
        </div>

        <!-- Дополнительная информация -->
        <div class="text-xs text-[color:var(--text-dim)] space-y-0.5">
          <div v-if="device.fw_version" class="flex items-center justify-center gap-1">
            <span>FW:</span>
            <span class="font-medium">{{ device.fw_version }}</span>
          </div>
          <div v-if="device.last_seen_at" class="text-center">
            {{ formatLastSeen(device.last_seen_at) }}
          </div>
        </div>

        <!-- Кнопка настройки (для управляющих ролей) -->
        <div
          v-if="canManage"
          class="mt-2 flex justify-center"
          @click.stop
        >
          <Button
            size="sm"
            variant="outline"
            @click.stop="$emit('configure', device)"
            class="text-xs w-full"
          >
            Настроить
          </Button>
        </div>
      </Link>
    </div>

    <!-- Пустое состояние -->
    <div v-else class="text-center py-8 text-[color:var(--text-muted)]">
      <div class="text-4xl mb-2">📱</div>
      <div class="text-sm mb-3">Нет устройств в зоне</div>
      <template v-if="canManage">
        <Button size="sm" variant="secondary" @click="$emit('attach')">
          Привязать узлы
        </Button>
      </template>
    </div>
  </Card>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Link } from '@inertiajs/vue3'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import Badge from '@/Components/Badge.vue'
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

const emit = defineEmits<{
  attach: []
  configure: [device: Device]
}>()

const { isAdmin, isOperator } = useRole()
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

function getDeviceIcon(type: string | undefined): string {
  const icons: Record<string, string> = {
    ph: '🧪',
    ec: '⚡',
    sensor: '📊',
    actuator: '🔧',
    controller: '🎛️',
    pump: '💧',
    climate: '🌡️',
  }
  return icons[type || 'sensor'] || '📱'
}

function translateDeviceType(type: string | undefined): string {
  const types: Record<string, string> = {
    ph: 'pH сенсор',
    ec: 'EC сенсор',
    sensor: 'Сенсор',
    actuator: 'Актуатор',
    controller: 'Контроллер',
    pump: 'Насос',
    climate: 'Климат',
  }
  return types[type || 'sensor'] || 'Устройство'
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

function getStatusDotClass(status: string | undefined): string {
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
</script>

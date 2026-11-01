<template>
  <div 
    class="bg-[color:var(--bg-surface-strong)] rounded-lg p-3 border border-[color:var(--border-muted)] hover:border-[color:var(--border-strong)] transition-colors relative group"
    :class="status === 'fail' || status === 'offline' || status === 'disconnected' ? 'border-[color:var(--badge-danger-border)]' : ''"
  >
    <div class="flex items-start justify-between gap-2">
      <div class="flex items-center gap-2 flex-1">
        <div class="relative">
          <div
            class="w-3 h-3 rounded-full transition-all duration-300"
            :class="[getStatusDotClass(status, statusType), status === 'ok' || status === 'connected' || status === 'online' ? 'animate-pulse' : '']"
          ></div>
          <div
            v-if="status === 'ok' || status === 'connected' || status === 'online'"
            class="absolute inset-0 w-3 h-3 rounded-full animate-ping opacity-75"
            :class="getStatusDotClass(status, statusType)"
          ></div>
        </div>
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2">
            <span class="text-sm">{{ icon }}</span>
            <span class="text-sm font-medium text-[color:var(--text-primary)]">{{ name }}</span>
          </div>
          <div class="text-xs text-[color:var(--text-muted)] mt-0.5">
            {{ description }}
          </div>
        </div>
      </div>
      <div class="flex flex-col items-end">
        <span
          class="text-xs font-medium transition-colors"
          :class="getStatusTextClass(status, statusType)"
        >
          {{ getStatusText(status, statusType) }}
        </span>
        <div
          v-if="endpointPreview"
          class="text-[10px] text-[color:var(--text-dim)] mt-0.5 truncate max-w-[120px]"
        >
          {{ endpointPreview }}
        </div>
      </div>
    </div>
    <!-- Tooltip с дополнительной информацией при ошибке -->
    <div 
      v-if="(status === 'fail' || status === 'offline' || status === 'disconnected') && endpoint"
      class="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-3 py-2 bg-[color:var(--bg-surface-strong)] border border-[color:var(--border-muted)] rounded-lg text-xs text-[color:var(--text-muted)] opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10 whitespace-nowrap shadow-[var(--shadow-card)]"
    >
      <div class="font-medium mb-1">
        Проблема с подключением
      </div>
      <div class="text-[color:var(--text-dim)]">
        Endpoint: {{ endpoint }}
      </div>
      <div class="text-[color:var(--text-dim)] mt-1">
        Проверьте, запущен ли сервис
      </div>
      <div class="absolute top-full left-1/2 transform -translate-x-1/2 -mt-1">
        <div class="w-2 h-2 bg-[color:var(--bg-surface-strong)] border-r border-b border-[color:var(--border-muted)] transform rotate-45"></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  name: string
  status: string
  icon?: string
  description?: string
  statusType?: 'service' | 'ws' | 'mqtt'
  endpoint?: string
}

const props = withDefaults(defineProps<Props>(), {
  icon: '📦',
  description: '',
  statusType: 'service',
  endpoint: undefined
})

const endpointPreview = computed(() => {
  if (!props.endpoint) return ''

  if (/^https?:\/\//.test(props.endpoint)) {
    try {
      return new URL(props.endpoint).host
    } catch {
      return props.endpoint
    }
  }

  return props.endpoint
})

function getStatusDotClass(status: string, statusType: string): string {
  if (statusType === 'ws') {
    switch (status) {
      case 'connected':
        return 'bg-[color:var(--status-ok)]'
      case 'disconnected':
        return 'bg-[color:var(--status-critical)]'
      default:
        return 'bg-[color:var(--text-dim)]'
    }
  }
  
  if (statusType === 'mqtt') {
    switch (status) {
      case 'online':
        return 'bg-[color:var(--status-ok)]'
      case 'offline':
        return 'bg-[color:var(--status-critical)]'
      case 'degraded':
        return 'bg-[color:var(--status-warning)]'
      default:
        return 'bg-[color:var(--text-dim)]'
    }
  }
  
  // service status
  switch (status) {
    case 'ok':
      return 'bg-[color:var(--status-ok)]'
    case 'fail':
      return 'bg-[color:var(--status-critical)]'
    default:
      return 'bg-[color:var(--text-dim)]'
  }
}

function getStatusText(status: string, statusType: string): string {
  if (statusType === 'ws') {
    switch (status) {
      case 'connected':
        return 'Подключено'
      case 'disconnected':
        return 'Отключено'
      default:
        return 'Неизвестно'
    }
  }
  
  if (statusType === 'mqtt') {
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
  
  // service status
  switch (status) {
    case 'ok':
      return 'Работает'
    case 'fail':
      return 'Ошибка'
    default:
      return 'Неизвестно'
  }
}

function getStatusTextClass(status: string, statusType: string): string {
  if (statusType === 'ws') {
    switch (status) {
      case 'connected':
        return 'text-[color:var(--status-ok)]'
      case 'disconnected':
        return 'text-[color:var(--status-critical)]'
      default:
        return 'text-[color:var(--text-dim)]'
    }
  }
  
  if (statusType === 'mqtt') {
    switch (status) {
      case 'online':
        return 'text-[color:var(--status-ok)]'
      case 'offline':
        return 'text-[color:var(--status-critical)]'
      case 'degraded':
        return 'text-[color:var(--status-warning)]'
      default:
        return 'text-[color:var(--text-dim)]'
    }
  }
  
  // service status
  switch (status) {
    case 'ok':
      return 'text-[color:var(--status-ok)]'
    case 'fail':
      return 'text-[color:var(--status-critical)]'
    default:
      return 'text-[color:var(--text-dim)]'
}
}
</script>

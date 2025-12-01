<template>
  <div 
    class="bg-neutral-900 rounded-lg p-3 border border-neutral-800 hover:border-neutral-700 transition-colors relative group"
    :class="status === 'fail' || status === 'offline' || status === 'disconnected' ? 'border-red-500/50' : ''"
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
            <span class="text-sm font-medium text-neutral-200">{{ name }}</span>
          </div>
          <div class="text-xs text-neutral-400 mt-0.5">{{ description }}</div>
        </div>
      </div>
      <div class="flex flex-col items-end">
        <span
          class="text-xs font-medium transition-colors"
          :class="getStatusTextClass(status, statusType)"
        >
          {{ getStatusText(status, statusType) }}
        </span>
        <div v-if="endpoint" class="text-[10px] text-neutral-500 mt-0.5 truncate max-w-[120px]">
          {{ endpoint.replace(/^https?:\/\//, '').split('/')[0] }}
        </div>
      </div>
    </div>
    <!-- Tooltip с дополнительной информацией при ошибке -->
    <div 
      v-if="(status === 'fail' || status === 'offline' || status === 'disconnected') && endpoint"
      class="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-3 py-2 bg-neutral-800 border border-neutral-700 rounded-lg text-xs text-neutral-300 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10 whitespace-nowrap shadow-lg"
    >
      <div class="font-medium mb-1">Проблема с подключением</div>
      <div class="text-neutral-400">Endpoint: {{ endpoint }}</div>
      <div class="text-neutral-400 mt-1">Проверьте, запущен ли сервис</div>
      <div class="absolute top-full left-1/2 transform -translate-x-1/2 -mt-1">
        <div class="w-2 h-2 bg-neutral-800 border-r border-b border-neutral-700 transform rotate-45"></div>
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

function getStatusDotClass(status: string, statusType: string): string {
  if (statusType === 'ws') {
    switch (status) {
      case 'connected':
        return 'bg-emerald-400'
      case 'disconnected':
        return 'bg-red-400'
      default:
        return 'bg-neutral-500'
    }
  }
  
  if (statusType === 'mqtt') {
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
  
  // service status
  switch (status) {
    case 'ok':
      return 'bg-emerald-400'
    case 'fail':
      return 'bg-red-400'
    default:
      return 'bg-neutral-500'
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
        return 'text-emerald-400'
      case 'disconnected':
        return 'text-red-400'
      default:
        return 'text-neutral-500'
    }
  }
  
  if (statusType === 'mqtt') {
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
  
  // service status
  switch (status) {
    case 'ok':
      return 'text-emerald-400'
    case 'fail':
      return 'text-red-400'
    default:
      return 'text-neutral-500'
  }
}
</script>


<template>
  <Card class="hover:border-neutral-700 transition-all duration-200">
    <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
      <div
        v-for="(count, status) in zonesByStatus"
        :key="status"
        class="p-4 rounded-lg border-2 transition-all duration-200 hover:scale-105 hover:shadow-lg cursor-pointer group relative"
        :class="getStatusClasses(status)"
        @click="handleStatusClick(status)"
        @mouseenter="hoveredStatus = status"
        @mouseleave="hoveredStatus = null"
      >
        <div class="flex items-center justify-between mb-2">
          <div class="text-xs font-medium uppercase tracking-wide opacity-70 group-hover:opacity-100 transition-opacity">
            {{ translateStatus(status) }}
          </div>
          <div 
            class="w-2 h-2 rounded-full transition-all duration-200"
            :class="getStatusDotClass(status)"
          ></div>
        </div>
        <div class="text-3xl font-bold" :class="getStatusTextClass(status)">{{ count || 0 }}</div>
        <div v-if="count > 0" class="text-xs opacity-60 mt-1">
          {{ getStatusPercentage(status) }}% от всех
        </div>
        <!-- Tooltip при hover -->
        <div 
          v-if="hoveredStatus === status && count > 0"
          class="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-3 py-2 bg-neutral-900 border border-neutral-700 rounded-lg shadow-xl text-xs z-50 whitespace-nowrap pointer-events-none"
        >
          <div class="text-neutral-200 font-medium mb-1">{{ translateStatus(status) }}</div>
          <div class="text-neutral-400">
            {{ count }} {{ count === 1 ? 'зона' : count < 5 ? 'зоны' : 'зон' }}
          </div>
          <div class="text-neutral-500 mt-1">Клик для просмотра →</div>
          <!-- Стрелка вниз -->
          <div class="absolute top-full left-1/2 transform -translate-x-1/2 -mt-px">
            <div class="w-2 h-2 bg-neutral-900 border-r border-b border-neutral-700 transform rotate-45"></div>
          </div>
        </div>
      </div>
    </div>
    
    <!-- Легенда -->
    <div class="mt-4 pt-4 border-t border-neutral-800 flex flex-wrap gap-4 text-xs text-neutral-400">
      <div class="flex items-center gap-2">
        <div class="w-3 h-3 rounded bg-emerald-500"></div>
        <span>Запущено</span>
      </div>
      <div class="flex items-center gap-2">
        <div class="w-3 h-3 rounded bg-neutral-500"></div>
        <span>Приостановлено</span>
      </div>
      <div class="flex items-center gap-2">
        <div class="w-3 h-3 rounded bg-amber-500"></div>
        <span>Предупреждение</span>
      </div>
      <div class="flex items-center gap-2">
        <div class="w-3 h-3 rounded bg-red-500"></div>
        <span>Тревога</span>
      </div>
    </div>
  </Card>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { router } from '@inertiajs/vue3'
import Card from '@/Components/Card.vue'
import { translateStatus } from '@/utils/i18n'
import type { ZoneStatus } from '@/types'

interface Props {
  zonesByStatus?: Record<ZoneStatus | string, number>
}

const props = withDefaults(defineProps<Props>(), {
  zonesByStatus: () => ({})
})

const emit = defineEmits<{
  filter: [status: ZoneStatus | string]
}>()

const hoveredStatus = ref<string | null>(null)

function handleStatusClick(status: ZoneStatus | string): void {
  emit('filter', status)
  // Переход к списку зон с фильтром по статусу
  const statusParam = status === 'ALL' ? '' : `?status=${status}`
  router.visit(`/zones${statusParam}`, {
    preserveScroll: false,
  })
}

const totalZones = computed(() => {
  return Object.values(props.zonesByStatus || {}).reduce((sum, count) => sum + (count || 0), 0)
})

function getStatusClasses(status: string): string {
  const classes: Record<string, string> = {
    'RUNNING': 'bg-emerald-500/10 border-emerald-500/50 hover:border-emerald-500 hover:bg-emerald-500/20',
    'PAUSED': 'bg-neutral-500/10 border-neutral-500/50 hover:border-neutral-500 hover:bg-neutral-500/20',
    'WARNING': 'bg-amber-500/10 border-amber-500/50 hover:border-amber-500 hover:bg-amber-500/20',
    'ALARM': 'bg-red-500/10 border-red-500/50 hover:border-red-500 hover:bg-red-500/20',
  }
  return classes[status] || 'bg-neutral-800/10 border-neutral-700/50'
}

function getStatusDotClass(status: string): string {
  const classes: Record<string, string> = {
    'RUNNING': 'bg-emerald-400 animate-pulse',
    'PAUSED': 'bg-neutral-400',
    'WARNING': 'bg-amber-400',
    'ALARM': 'bg-red-400',
  }
  return classes[status] || 'bg-neutral-500'
}

function getStatusTextClass(status: string): string {
  const classes: Record<string, string> = {
    'RUNNING': 'text-emerald-400',
    'PAUSED': 'text-neutral-300',
    'WARNING': 'text-amber-400',
    'ALARM': 'text-red-400',
  }
  return classes[status] || 'text-neutral-200'
}

function getStatusPercentage(status: string): number {
  const count = props.zonesByStatus?.[status] || 0
  if (totalZones.value === 0) return 0
  return Math.round((count / totalZones.value) * 100)
}
</script>


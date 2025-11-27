<template>
  <Card class="hover:border-neutral-700 transition-all duration-200">
    <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
      <div
        v-for="entry in statusEntries"
        :key="entry.status"
        class="p-4 rounded-lg border-2 transition-all duration-200 hover:scale-105 hover:shadow-lg cursor-pointer group relative"
        :class="entry.cardClass"
        @click="handleStatusClick(entry.status)"
        @mouseenter="hoveredStatus = entry.status"
        @mouseleave="hoveredStatus = null"
      >
        <div class="flex items-center justify-between mb-2">
          <div class="text-xs font-medium uppercase tracking-wide opacity-70 group-hover:opacity-100 transition-opacity">
            {{ entry.label }}
          </div>
          <div class="w-2 h-2 rounded-full transition-all duration-200" :class="entry.dotClass"></div>
        </div>
        <div class="text-3xl font-bold" :class="entry.textClass">{{ entry.count }}</div>
        <div v-if="entry.count > 0" class="text-xs opacity-60 mt-1">
          {{ entry.percentage }}% от всех
        </div>
        <div
          v-if="hoveredStatus === entry.status && entry.count > 0"
          class="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-3 py-2 bg-neutral-900 border border-neutral-700 rounded-lg shadow-xl text-xs z-50 whitespace-nowrap pointer-events-none"
        >
          <div class="text-neutral-200 font-medium mb-1">{{ entry.label }}</div>
          <div class="text-neutral-400">
            {{ entry.count }} {{ entry.countLabel }}
          </div>
          <div class="text-neutral-500 mt-1">Клик для просмотра →</div>
          <div class="absolute top-full left-1/2 transform -translate-x-1/2 -mt-px">
            <div class="w-2 h-2 bg-neutral-900 border-r border-b border-neutral-700 transform rotate-45"></div>
          </div>
        </div>
      </div>
    </div>

    <div class="mt-4 pt-4 border-t border-neutral-800 flex flex-wrap gap-4 text-xs text-neutral-400">
      <div v-for="legend in legendItems" :key="legend.text" class="flex items-center gap-2">
        <div :class="legend.dot" class="w-3 h-3 rounded"></div>
        <span>{{ legend.text }}</span>
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

type StatusKey = ZoneStatus | string

const props = withDefaults(defineProps<Props>(), {
  zonesByStatus: () => ({}),
})

const emit = defineEmits<{
  filter: [status: StatusKey]
}>()

const hoveredStatus = ref<StatusKey | null>(null)

const statusPalette: Record<StatusKey, { label: string; cardClass: string; dotClass: string; textClass: string }> = {
  RUNNING: {
    label: 'Запущено',
    cardClass: 'bg-emerald-500/10 border-emerald-500/50 hover:border-emerald-500 hover:bg-emerald-500/20',
    dotClass: 'bg-emerald-400 animate-pulse',
    textClass: 'text-emerald-400',
  },
  PAUSED: {
    label: 'Приостановлено',
    cardClass: 'bg-neutral-500/10 border-neutral-500/50 hover:border-neutral-500 hover:bg-neutral-500/20',
    dotClass: 'bg-neutral-400',
    textClass: 'text-neutral-300',
  },
  WARNING: {
    label: 'Предупреждение',
    cardClass: 'bg-amber-500/10 border-amber-500/50 hover:border-amber-500 hover:bg-amber-500/20',
    dotClass: 'bg-amber-400',
    textClass: 'text-amber-400',
  },
  ALARM: {
    label: 'Тревога',
    cardClass: 'bg-red-500/10 border-red-500/50 hover:border-red-500 hover:bg-red-500/20',
    dotClass: 'bg-red-400',
    textClass: 'text-red-400',
  },
}

const totalZones = computed(() => {
  return Object.values(props.zonesByStatus || {}).reduce((sum, current) => sum + (current || 0), 0)
})

const fallbackClass = 'bg-neutral-800/10 border-neutral-700/50 hover:border-neutral-500 hover:bg-neutral-700/20'
const fallbackDot = 'bg-neutral-500'
const fallbackText = 'text-neutral-200'

const statusEntries = computed(() => {
  const entries: Array<{
    status: StatusKey
    label: string
    count: number
    percentage: number
    countLabel: string
    cardClass: string
    dotClass: string
    textClass: string
  }> = []

  const statuses = ['RUNNING', 'PAUSED', 'WARNING', 'ALARM']

  const addEntry = (status: StatusKey) => {
    const count = props.zonesByStatus?.[status] ?? 0
    const palette = statusPalette[status as ZoneStatus]
    entries.push({
      status,
      label: palette?.label || translateStatus(status),
      count,
      percentage: totalZones.value === 0 ? 0 : Math.round((count / totalZones.value) * 100),
      countLabel: count === 1 ? 'зона' : count < 5 ? 'зоны' : 'зон',
      cardClass: palette?.cardClass || fallbackClass,
      dotClass: palette?.dotClass || fallbackDot,
      textClass: palette?.textClass || fallbackText,
    })
  }

  statuses.forEach(addEntry)

  const unknownStatuses = Object.keys(props.zonesByStatus || {}).filter(
    (status) => !statuses.includes(status)
  )
  unknownStatuses.forEach((status) => addEntry(status))

  return entries
})

const legendItems = [
  { text: 'Запущено', dot: 'bg-emerald-500' },
  { text: 'Приостановлено', dot: 'bg-neutral-500' },
  { text: 'Предупреждение', dot: 'bg-amber-500' },
  { text: 'Тревога', dot: 'bg-red-500' },
]

const isRouterAvailable = typeof router !== 'undefined' && typeof router.visit === 'function'

function handleStatusClick(status: StatusKey): void {
  emit('filter', status)
  if (!isRouterAvailable) return
  const statusParam = status === 'ALL' ? '' : `?status=${status}`
  router.visit(`/zones${statusParam}`, {
    preserveScroll: false,
  })
}
</script>

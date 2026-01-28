<template>
  <Card class="hover:border-[color:var(--border-strong)] transition-all duration-200">
    <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
      <div
        v-for="entry in statusEntries"
        :key="entry.status"
        class="p-4 rounded-lg border-2 transition-all duration-200 hover:scale-105 hover:shadow-[var(--shadow-card)] cursor-pointer group relative"
        :class="entry.cardClass"
        @click="handleStatusClick(entry.status)"
        @mouseenter="hoveredStatus = entry.status"
        @mouseleave="hoveredStatus = null"
      >
        <div class="flex items-center justify-between mb-2">
          <div class="text-xs font-medium uppercase tracking-wide opacity-70 group-hover:opacity-100 transition-opacity">
            {{ entry.label }}
          </div>
          <div
            class="w-2 h-2 rounded-full transition-all duration-200"
            :class="entry.dotClass"
          ></div>
        </div>
        <div
          class="text-3xl font-bold"
          :class="entry.textClass"
        >
          {{ entry.count }}
        </div>
        <div
          v-if="entry.count > 0"
          class="text-xs opacity-60 mt-1"
        >
          {{ entry.percentage }}% от всех
        </div>
        <div
          v-if="hoveredStatus === entry.status && entry.count > 0"
          class="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-3 py-2 bg-[color:var(--bg-surface-strong)] border border-[color:var(--border-muted)] rounded-lg shadow-[var(--shadow-card)] text-xs z-50 whitespace-nowrap pointer-events-none"
        >
          <div class="text-[color:var(--text-primary)] font-medium mb-1">
            {{ entry.label }}
          </div>
          <div class="text-[color:var(--text-muted)]">
            {{ entry.count }} {{ entry.countLabel }}
          </div>
          <div class="text-[color:var(--text-dim)] mt-1">
            Клик для просмотра →
          </div>
          <div class="absolute top-full left-1/2 transform -translate-x-1/2 -mt-px">
            <div class="w-2 h-2 bg-[color:var(--bg-surface-strong)] border-r border-b border-[color:var(--border-muted)] transform rotate-45"></div>
          </div>
        </div>
      </div>
    </div>

    <div class="mt-4 pt-4 border-t border-[color:var(--border-muted)] flex flex-wrap gap-4 text-xs text-[color:var(--text-muted)]">
      <div
        v-for="legend in legendItems"
        :key="legend.text"
        class="flex items-center gap-2"
      >
        <div
          :class="legend.dot"
          class="w-3 h-3 rounded"
        ></div>
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
    cardClass: 'bg-[color:var(--badge-success-bg)] border-[color:var(--badge-success-border)] hover:border-[color:var(--accent-green)] hover:bg-[color:var(--badge-success-bg)]',
    dotClass: 'bg-[color:var(--accent-green)] animate-pulse',
    textClass: 'text-[color:var(--accent-green)]',
  },
  PAUSED: {
    label: 'Приостановлено',
    cardClass: 'bg-[color:var(--bg-elevated)] border-[color:var(--border-muted)] hover:border-[color:var(--border-strong)] hover:bg-[color:var(--bg-elevated)]',
    dotClass: 'bg-[color:var(--text-dim)]',
    textClass: 'text-[color:var(--text-primary)]',
  },
  WARNING: {
    label: 'Предупреждение',
    cardClass: 'bg-[color:var(--badge-warning-bg)] border-[color:var(--badge-warning-border)] hover:border-[color:var(--accent-amber)] hover:bg-[color:var(--badge-warning-bg)]',
    dotClass: 'bg-[color:var(--accent-amber)]',
    textClass: 'text-[color:var(--accent-amber)]',
  },
  ALARM: {
    label: 'Тревога',
    cardClass: 'bg-[color:var(--badge-danger-bg)] border-[color:var(--badge-danger-border)] hover:border-[color:var(--accent-red)] hover:bg-[color:var(--badge-danger-bg)]',
    dotClass: 'bg-[color:var(--accent-red)]',
    textClass: 'text-[color:var(--accent-red)]',
  },
}

const totalZones = computed(() => {
  return Object.values(props.zonesByStatus || {}).reduce((sum, current) => sum + (current || 0), 0)
})

const fallbackClass = 'bg-[color:var(--bg-elevated)] border-[color:var(--border-muted)] hover:border-[color:var(--border-strong)] hover:bg-[color:var(--bg-elevated)]'
const fallbackDot = 'bg-[color:var(--text-dim)]'
const fallbackText = 'text-[color:var(--text-primary)]'

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
  { text: 'Запущено', dot: 'bg-[color:var(--accent-green)]' },
  { text: 'Приостановлено', dot: 'bg-[color:var(--text-dim)]' },
  { text: 'Предупреждение', dot: 'bg-[color:var(--accent-amber)]' },
  { text: 'Тревога', dot: 'bg-[color:var(--accent-red)]' },
]

const isRouterAvailable = typeof router !== 'undefined' && typeof router.visit === 'function'

function handleStatusClick(status: StatusKey): void {
  emit('filter', status)
  if (!isRouterAvailable) return
  const statusParam = status === 'ALL' ? '' : `?status=${status}`
  router.visit(`/zones${statusParam}`, {
    preserveUrl: false,
  })
}
</script>

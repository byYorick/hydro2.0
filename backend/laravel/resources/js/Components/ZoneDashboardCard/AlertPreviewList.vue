<template>
  <div
    v-if="displayedAlerts.length > 0"
    class="space-y-1.5"
  >
    <div class="text-[10px] uppercase tracking-wider text-[color:var(--text-muted)]">
      Последние алерты
    </div>
    <ul class="space-y-1">
      <li
        v-for="alert in displayedAlerts"
        :key="alert.id"
        class="flex items-start gap-2 rounded-md border px-2 py-1.5 text-[11px]"
        :class="severityClass(alert.severity)"
      >
        <span
          class="inline-block w-1.5 h-1.5 rounded-full shrink-0 mt-1.5"
          :class="dotClass(alert.severity)"
        ></span>
        <div class="min-w-0 flex-1">
          <div class="truncate font-medium text-[color:var(--text-primary)]">
            {{ alert.title }}
          </div>
          <div
            v-if="alert.reason"
            class="truncate text-[10px] text-[color:var(--text-dim)]"
          >
            {{ alert.reason }}
          </div>
        </div>
        <span class="text-[9px] text-[color:var(--text-dim)] tabular-nums shrink-0">
          {{ formatTime(alert.created_at) }}
        </span>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

export interface AlertPreviewItem {
  id: number
  severity: 'alert' | 'warning' | 'info'
  title: string
  reason?: string | null
  created_at: string
}

interface Props {
  alerts: AlertPreviewItem[]
  /** По умолчанию показываем 3 последних */
  limit?: number
}

const props = withDefaults(defineProps<Props>(), {
  limit: 3,
})

const displayedAlerts = computed(() =>
  [...props.alerts]
    .filter((a) => a.severity === 'alert' || a.severity === 'warning')
    .slice(0, props.limit)
)

function severityClass(sev: AlertPreviewItem['severity']): string {
  switch (sev) {
    case 'alert':
      return 'border-[color:var(--badge-danger-border)] bg-[color:var(--badge-danger-bg)]'
    case 'warning':
      return 'border-[color:var(--badge-warning-border)] bg-[color:var(--badge-warning-bg)]'
    default:
      return 'border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]'
  }
}

function dotClass(sev: AlertPreviewItem['severity']): string {
  switch (sev) {
    case 'alert': return 'bg-[color:var(--accent-red)]'
    case 'warning': return 'bg-[color:var(--accent-amber)]'
    default: return 'bg-[color:var(--text-dim)]'
  }
}

function formatTime(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}
</script>

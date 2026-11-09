<template>
  <section
    class="surface-card rounded-2xl border border-[color:var(--border-muted)] p-4 md:p-5"
    data-testid="dashboard-agronomy-overview"
  >
    <div class="space-y-4">
      <div class="grid grid-cols-3 gap-3">
        <div class="min-w-0">
          <div class="text-xs text-[color:var(--text-muted)]">
            Требуют решения
          </div>
          <div class="mt-2 text-3xl font-semibold tabular-nums text-[color:var(--status-warning)]">
            {{ decisionCount }}
          </div>
          <div class="mt-1 text-xs text-[color:var(--text-muted)]">
            Отклонения и блокировки
          </div>
        </div>
        <div class="min-w-0">
          <div class="text-xs text-[color:var(--text-muted)]">
            Без оценки
          </div>
          <div class="mt-2 text-3xl font-semibold tabular-nums">
            {{ corridor.unknown }}
          </div>
          <div class="mt-1 text-xs text-[color:var(--text-muted)]">
            Нет свежих данных или целей
          </div>
        </div>
        <div class="min-w-0">
          <div class="text-xs text-[color:var(--text-muted)]">
            Фазы и сбор
          </div>
          <div class="mt-2 text-3xl font-semibold tabular-nums">
            {{ transitions.length }}
          </div>
          <div class="mt-1 text-xs text-[color:var(--text-muted)]">
            До пяти ближайших решений
          </div>
        </div>
      </div>

      <details v-if="transitions.length > 0">
        <summary class="cursor-pointer text-sm font-semibold text-[color:var(--text-primary)]">
          Ближайшие фазы и сбор · {{ transitions.length }}
        </summary>
        <ul class="mt-3 space-y-1.5">
          <li
            v-for="item in transitions"
            :key="`${item.zoneId}-${item.at}`"
            class="flex flex-wrap items-baseline justify-between gap-2 text-sm"
          >
            <Link
              :href="`/zones/${item.zoneId}`"
              class="text-[color:var(--status-info)] hover:underline"
            >
              {{ item.zoneName }}
            </Link>
            <span class="text-[color:var(--text-muted)]">
              {{ item.phaseName }} · {{ formatDate(item.at) }}
            </span>
          </li>
        </ul>
      </details>
    </div>
  </section>
</template>

<script setup lang="ts">
import { Link } from '@inertiajs/vue3'
import type { AgronomyCorridorSummary, UpcomingPhaseTransition } from './dashboardRoleView'

defineProps<{
  decisionCount: number
  corridor: AgronomyCorridorSummary
  transitions: UpcomingPhaseTransition[]
}>()

function formatDate(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}
</script>

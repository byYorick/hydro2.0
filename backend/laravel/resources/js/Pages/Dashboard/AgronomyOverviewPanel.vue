<template>
  <section
    class="surface-card rounded-2xl border border-[color:var(--border-muted)] p-4 md:p-5"
    data-testid="dashboard-agronomy-overview"
  >
    <div class="space-y-4">
      <div class="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <div>
          <div class="text-xs text-[color:var(--text-muted)]">
            В норме
          </div>
          <div class="text-xl font-semibold text-[color:var(--accent-green)]">
            {{ corridor.inRange }}
          </div>
          <div class="text-xs text-[color:var(--text-dim)]">
            pH/EC в коридоре
          </div>
        </div>
        <div>
          <div class="text-xs text-[color:var(--text-muted)]">
            Вне коридора
          </div>
          <div
            class="text-xl font-semibold"
            :class="corridor.outOfRange > 0 ? 'text-[color:var(--accent-amber)]' : ''"
          >
            {{ corridor.outOfRange }}
          </div>
          <div class="text-xs text-[color:var(--text-dim)]">
            из {{ corridor.total }} зон
          </div>
        </div>
        <div
          v-if="corridor.unknown > 0"
          class="col-span-2 sm:col-span-1"
        >
          <div class="text-xs text-[color:var(--text-muted)]">
            Без оценки
          </div>
          <div class="text-xl font-semibold text-[color:var(--text-muted)]">
            {{ corridor.unknown }}
          </div>
        </div>
      </div>

      <div v-if="transitions.length > 0">
        <h2 class="mb-2 text-sm font-semibold text-[color:var(--text-primary)]">
          Ближайшие переходы фаз
        </h2>
        <ul class="space-y-1.5">
          <li
            v-for="item in transitions"
            :key="`${item.zoneId}-${item.at}`"
            class="flex flex-wrap items-baseline justify-between gap-2 text-sm"
          >
            <Link
              :href="`/zones/${item.zoneId}`"
              class="text-[color:var(--accent-cyan)] hover:underline"
            >
              {{ item.zoneName }}
            </Link>
            <span class="text-[color:var(--text-muted)]">
              {{ item.phaseName }} · {{ formatDate(item.at) }}
            </span>
          </li>
        </ul>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { Link } from '@inertiajs/vue3'
import type { AgronomyCorridorSummary, UpcomingPhaseTransition } from './dashboardRoleView'

defineProps<{
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

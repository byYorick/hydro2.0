<template>
  <div class="surface-card surface-card--elevated rounded-2xl border border-[color:var(--border-muted)] p-4">
    <div class="flex items-center justify-between">
      <div class="text-sm font-semibold text-[color:var(--text-primary)]">
        События
      </div>
      <span class="text-xs text-[color:var(--text-muted)]">
        {{ events.length }} последних
      </span>
    </div>

    <div
      v-if="events.length === 0"
      class="mt-4 rounded-xl border border-dashed border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/25 p-4 text-sm text-[color:var(--text-dim)]"
    >
      Нет событий
    </div>

    <div
      v-else
      class="mt-3 space-y-1"
      data-testid="zone-events-list"
    >
      <div
        v-for="(event, index) in events"
        :key="event.id"
        :data-testid="`zone-event-item-${event.id}`"
        class="relative flex gap-3"
      >
        <div class="relative flex w-4 shrink-0 justify-center">
          <span
            class="mt-2 h-2 w-2 rounded-full"
            :class="eventDotClass(event.kind)"
          ></span>
          <span
            v-if="index < events.length - 1"
            class="absolute bottom-0 top-3.5 w-px bg-[color:var(--border-muted)]"
          ></span>
        </div>

        <div class="min-w-0 flex-1 py-1.5">
          <div class="flex flex-wrap items-center gap-2">
            <Badge
              :variant="getEventVariant(event.kind)"
              class="shrink-0 text-xs"
            >
              {{ translateEventKind(event.kind) }}
            </Badge>
            <span class="text-xs text-[color:var(--text-dim)]">
              {{ event.occurred_at ? new Date(event.occurred_at).toLocaleString('ru-RU') : '—' }}
            </span>
          </div>
          <p class="mt-0.5 text-sm text-[color:var(--text-primary)]">
            {{ event.message }}
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import Badge from '@/Components/Badge.vue'
import { translateEventKind, classifyEventKind } from '@/utils/i18n'
import type { ZoneEvent } from '@/types/ZoneEvent'

defineProps<{
  events: ZoneEvent[]
}>()

function getEventVariant(kind: string): 'danger' | 'warning' | 'info' | 'neutral' {
  const category = classifyEventKind(kind)
  if (category === 'ALERT') return 'danger'
  if (category === 'WARNING') return 'warning'
  if (category === 'INFO') return 'info'
  return 'neutral'
}

function eventDotClass(kind: string): string {
  const category = classifyEventKind(kind)
  if (category === 'ALERT') return 'bg-[color:var(--accent-red)]'
  if (category === 'WARNING') return 'bg-[color:var(--accent-amber)]'
  if (category === 'INFO') return 'bg-[color:var(--accent-cyan)]'
  return 'bg-[color:var(--text-muted)]'
}
</script>

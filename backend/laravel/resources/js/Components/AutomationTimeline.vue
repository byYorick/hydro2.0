<template>
  <div class="mt-4 border-t border-[color:var(--border-muted)] pt-3">
    <h4 class="text-xs uppercase tracking-[0.18em] text-[color:var(--text-dim)] mb-2">Timeline</h4>
    <ul class="space-y-2 max-h-44 overflow-y-auto pr-1">
      <li
        v-for="event in events"
        :key="`${event.event}-${event.timestamp}`"
        class="timeline-item"
        :class="{ 'timeline-item--active': event.active }"
      >
        <span class="timeline-dot"></span>
        <span class="timeline-label">{{ event.label || event.event }}</span>
        <span class="timeline-time">{{ formatTime(event.timestamp) }}</span>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import type { AutomationTimelineEvent } from '@/types/Automation'

interface Props {
  events: AutomationTimelineEvent[]
}

defineProps<Props>()

function formatTime(timestamp: string): string {
  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) {
    return timestamp
  }
  return date.toLocaleTimeString('ru-RU', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}
</script>

<style scoped>
.timeline-item {
  display: grid;
  grid-template-columns: 12px 1fr auto;
  align-items: center;
  gap: 8px;
  padding: 5px 0;
  opacity: 0.66;
  transition: opacity 0.2s ease;
}

.timeline-item--active {
  opacity: 1;
}

.timeline-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: var(--border-muted);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--border-muted) 25%, transparent);
}

.timeline-item--active .timeline-dot {
  background: var(--accent-cyan);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent-cyan) 35%, transparent);
}

.timeline-label {
  color: var(--text-primary);
  font-size: 12px;
}

.timeline-time {
  color: var(--text-dim);
  font-size: 11px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
</style>

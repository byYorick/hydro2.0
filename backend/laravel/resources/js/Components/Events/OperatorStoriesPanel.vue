<template>
  <section
    class="surface-card rounded-xl border border-[color:var(--border-muted)] p-2"
    data-testid="zone-events-operator"
  >
    <div class="flex items-center gap-1.5 px-1.5 pb-1.5">
      <span class="text-xs font-semibold text-[color:var(--text-primary)]">Оператор</span>
      <Badge
        variant="info"
        size="sm"
      >
        {{ stories.length }}
      </Badge>
    </div>

    <div
      v-if="stories.length === 0"
      class="py-6 text-center text-[11px] text-[color:var(--text-dim)]"
    >
      Нет значимых событий для оператора
    </div>

    <div
      v-else
      class="max-h-[calc(100vh-300px)] space-y-1.5 overflow-y-auto pr-0.5"
    >
      <article
        v-for="story in stories"
        :key="story.id"
        class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]/30"
      >
        <button
          type="button"
          class="flex w-full flex-wrap items-start justify-between gap-1.5 px-2.5 py-2 text-left hover:bg-[color:var(--bg-elevated)]/50 transition-colors rounded-lg"
          @click="toggle(story.id)"
        >
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-1.5">
              <Badge
                :variant="severityVariant(story.severity)"
                size="sm"
              >
                {{ story.title }}
              </Badge>
              <span class="text-[10px] text-[color:var(--text-muted)]">
                {{ formatTime(story.occurredAt) }}
              </span>
            </div>
            <p class="mt-1 text-[12px] leading-snug text-[color:var(--text-primary)]">
              {{ story.summary }}
            </p>
            <p
              v-if="story.collapsedNoise?.length"
              class="mt-0.5 text-[10px] text-[color:var(--text-dim)]"
            >
              + {{ noiseLabel(story.collapsedNoise) }}
            </p>
          </div>
          <span class="shrink-0 text-[10px] text-[color:var(--text-dim)] pt-0.5">
            {{ expandedIds.has(story.id) ? '▲' : '▼' }}
          </span>
        </button>

        <div
          v-if="expandedIds.has(story.id)"
          class="border-t border-[color:var(--border-muted)]/60 px-2.5 py-2 space-y-1"
        >
          <div
            v-for="(step, idx) in story.steps"
            :key="`${story.id}-${idx}`"
            class="flex gap-2 text-[11px]"
          >
            <span class="shrink-0 text-[color:var(--text-dim)] w-16">
              {{ formatShortTime(step.at) }}
            </span>
            <span class="text-[color:var(--text-muted)]">{{ step.label }}</span>
          </div>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import Badge from '@/Components/Badge.vue'
import type { BadgeVariant } from '@/Components/Badge.vue'
import type { OperatorStory, OperatorStorySeverity } from '@/utils/eventOperatorView'

defineProps<{
  stories: OperatorStory[]
}>()

const expandedIds = ref<Set<string>>(new Set())

function toggle(id: string): void {
  const next = new Set(expandedIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedIds.value = next
}

function severityVariant(severity: OperatorStorySeverity): BadgeVariant {
  if (severity === 'alert') return 'danger'
  if (severity === 'warning') return 'warning'
  if (severity === 'action') return 'success'
  if (severity === 'success') return 'success'
  return 'info'
}

function formatTime(value: string): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('ru-RU')
}

function formatShortTime(value: string): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function noiseLabel(noise: NonNullable<OperatorStory['collapsedNoise']>): string {
  return noise.map((item) => `${item.count}× ${item.label}`).join(', ')
}
</script>

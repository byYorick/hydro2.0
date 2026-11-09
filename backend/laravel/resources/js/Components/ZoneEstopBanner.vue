<template>
  <section
    class="flex items-start gap-3 rounded-xl border border-[color:var(--badge-danger-border)] bg-[color:var(--badge-danger-bg)] px-4 py-3"
    role="alert"
    data-testid="zone-estop-banner"
  >
    <span
      class="mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[color:var(--status-critical)] text-sm font-bold text-[color:var(--bg-surface)]"
      aria-hidden="true"
    >!</span>
    <div class="min-w-0 space-y-1">
      <h2 class="text-sm font-semibold text-[color:var(--status-critical)]">
        {{ banner }}
      </h2>
      <p
        v-if="sinceLabel"
        class="text-xs text-[color:var(--text-secondary)]"
      >
        С {{ sinceLabel }}
      </p>
      <p
        v-if="solutionLabel"
        class="text-xs text-[color:var(--text-secondary)]"
        data-testid="zone-estop-banner-solution"
      >
        {{ solutionLabel }}
      </p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ESTOP_ACTIVE_BANNER } from '@/utils/zoneEstop'

interface Props {
  since?: string | null
  solutionLabel?: string | null
}

const props = withDefaults(defineProps<Props>(), {
  since: null,
  solutionLabel: null,
})

const banner = ESTOP_ACTIVE_BANNER

const sinceLabel = computed(() => {
  if (!props.since) return null
  const date = new Date(props.since)
  if (Number.isNaN(date.getTime())) return null
  return date.toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
})
</script>

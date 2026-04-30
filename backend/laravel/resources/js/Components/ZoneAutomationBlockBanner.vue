<template>
  <section
    v-if="block"
    class="rounded-lg border border-[color:var(--badge-danger-border)] bg-[color:var(--badge-danger-bg)]/15 p-3 flex items-start gap-3"
    data-testid="zone-automation-block-banner"
    role="alert"
  >
    <div
      class="mt-0.5 inline-flex items-center justify-center w-6 h-6 rounded-full bg-[color:var(--accent-red)]/20 text-[color:var(--accent-red)] shrink-0"
      aria-hidden="true"
    >
      <span class="text-sm font-semibold">!</span>
    </div>
    <div class="min-w-0 flex-1">
      <div class="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
        <h3 class="text-sm font-semibold text-[color:var(--accent-red)]">
          Автоматика остановлена ошибкой
        </h3>
        <span
          v-if="block.reason_code"
          class="text-[10px] uppercase tracking-wide text-[color:var(--text-dim)] font-mono"
        >
          {{ block.reason_code }}
        </span>
        <span
          v-if="sinceText"
          class="text-[10px] text-[color:var(--text-dim)]"
        >
          · с {{ sinceText }}
        </span>
      </div>
      <p class="text-sm text-[color:var(--text-primary)] mt-0.5">
        {{ reasonLabel }}
      </p>
      <p
        v-if="block.message"
        class="text-xs text-[color:var(--text-secondary)] mt-0.5 break-words"
      >
        {{ block.message }}
      </p>
      <p class="text-xs text-[color:var(--text-muted)] mt-1">
        {{ hint }}
      </p>
      <div class="mt-2 flex flex-wrap items-center gap-2">
        <button
          type="button"
          class="inline-flex items-center gap-1 rounded-md border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] px-2.5 py-1 text-xs font-medium text-[color:var(--text-primary)] hover:border-[color:var(--accent-red)]"
          data-testid="zone-automation-block-open-alerts"
          @click="$emit('open-alerts')"
        >
          Перейти к алертам
        </button>
        <span
          v-if="block.alerts_count > 1"
          class="text-[11px] text-[color:var(--text-dim)]"
        >
          Активных блокирующих алертов: {{ block.alerts_count }}
        </span>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  automationBlockHint,
  automationBlockLabel,
  type AutomationBlockPayload,
} from '@/utils/automationBlock'

interface Props {
  block: AutomationBlockPayload | null
}

const props = defineProps<Props>()

defineEmits<{
  (event: 'open-alerts'): void
}>()

const reasonLabel = computed(() => automationBlockLabel(props.block?.reason_code ?? null))
const hint = computed(() => automationBlockHint(props.block?.reason_code ?? null))

const sinceText = computed(() => {
  const value = props.block?.since
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
})
</script>

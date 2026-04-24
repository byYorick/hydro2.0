<template>
  <section
    class="flex min-h-0 flex-1 flex-col rounded-2xl border p-3.5"
    :class="isFailed
      ? 'border-[color:var(--accent-red)]/40 bg-[color:var(--accent-red)]/5'
      : 'border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]/70'"
    data-testid="scheduler-causal-chain"
  >
    <header class="flex items-start justify-between gap-2">
      <div class="min-w-0">
        <div class="flex flex-wrap items-center gap-2">
          <span class="font-mono text-[13px] font-bold text-[color:var(--text-primary)]">
            #{{ run.execution_id }}
          </span>
          <Badge
            :variant="headerBadgeVariant"
            size="xs"
          >
            {{ headerBadgeLabel }}
          </Badge>
        </div>
        <div class="mt-1 text-[11px] text-[color:var(--text-dim)]">
          {{ laneLabel(run.schedule_task_type ?? run.task_type) }}
          <span v-if="run.decision_bundle_revision"> · bundle {{ run.decision_bundle_revision }}</span>
        </div>
        <div
          v-if="run.correlation_id"
          class="mt-0.5 font-mono text-[10px] text-[color:var(--text-muted)]"
        >
          correction_window: {{ run.correlation_id }}
        </div>
      </div>
      <button
        type="button"
        class="rounded-md border border-[color:var(--border-muted)] px-2 py-1 text-[11px] text-[color:var(--text-dim)] hover:text-[color:var(--text-primary)]"
        data-testid="scheduler-chain-close"
        @click="$emit('close')"
      >
        ✕
      </button>
    </header>

    <div
      v-if="run.error_code"
      class="mt-3 rounded-lg border border-[color:var(--accent-red)]/40 bg-[color:var(--accent-red)]/10 px-2.5 py-2"
      data-testid="scheduler-chain-error"
    >
      <div class="text-[11px] font-semibold text-[color:var(--accent-red)]">
        {{ run.error_code }}
      </div>
      <div
        v-if="errorText"
        class="mt-0.5 text-[10px] text-[color:var(--text-dim)]"
      >
        {{ errorText }}
      </div>
    </div>

    <div class="mt-3 text-[10px] font-bold tracking-[0.12em] text-[color:var(--text-muted)]">
      ЦЕПОЧКА РЕШЕНИЙ
    </div>

    <div
      v-if="steps.length === 0"
      class="mt-2 text-[11px] text-[color:var(--text-muted)]"
    >
      Нет шагов цепочки — возможно, execution ещё в очереди.
    </div>

    <ol
      v-else
      class="mt-2 flex flex-1 flex-col gap-0.5 overflow-auto"
    >
      <li
        v-for="(step, index) in steps"
        :key="`${step.step}-${step.ref}-${index}`"
        class="grid gap-2"
        :style="{ gridTemplateColumns: '16px minmax(0, 1fr)' }"
        :data-testid="`scheduler-chain-step-${step.step}`"
      >
        <div class="flex flex-col items-center">
          <span
            class="mt-1.5 h-2.5 w-2.5 rounded-full"
            :class="step.live ? 'chain-dot-live' : ''"
            :style="{
              background: STATUS_COLOR[step.status] ?? 'var(--text-muted)',
            }"
          ></span>
          <span
            v-if="index < steps.length - 1"
            class="mt-0.5 min-h-[10px] w-0.5 flex-1 bg-[color:var(--border-muted)]"
          ></span>
        </div>
        <div class="pb-2">
          <div class="flex flex-wrap items-baseline gap-1.5">
            <Badge
              variant="neutral"
              size="xs"
            >
              {{ step.step }}
            </Badge>
            <span class="font-mono text-[10px] text-[color:var(--text-muted)]">
              {{ step.ref }}
            </span>
            <span
              v-if="step.at"
              class="ml-auto font-mono text-[10px] text-[color:var(--text-muted)]"
            >{{ formatAt(step.at) }}</span>
          </div>
          <div
            class="mt-0.5 text-[11px]"
            :class="step.status === 'run'
              ? 'font-semibold text-[color:var(--accent-cyan)]'
              : 'text-[color:var(--text-primary)]'"
          >
            {{ step.detail }}
          </div>
        </div>
      </li>
    </ol>

    <footer class="mt-2 flex gap-1.5">
      <button
        v-if="isFailed"
        type="button"
        class="flex-1 rounded-md border border-[color:var(--border-muted)] px-2 py-1 text-[11px] text-[color:var(--text-primary)] hover:bg-[color:var(--bg-elevated)]"
        data-testid="scheduler-chain-retry"
        @click="$emit('retry', run.execution_id)"
      >
        Повторить
      </button>
      <button
        type="button"
        class="flex-1 rounded-md border border-[color:var(--border-muted)] px-2 py-1 text-[11px] text-[color:var(--text-primary)] hover:bg-[color:var(--bg-elevated)]"
        data-testid="scheduler-chain-open-events"
        @click="$emit('open-events', run.execution_id)"
      >
        В Events →
      </button>
      <button
        v-if="run.correlation_id"
        type="button"
        class="rounded-md border border-[color:var(--border-muted)] px-2 py-1 text-[11px] text-[color:var(--text-dim)] hover:bg-[color:var(--bg-elevated)]"
        :title="`Скопировать correction_window_id: ${run.correlation_id}`"
        data-testid="scheduler-chain-copy"
        @click="copyCorrelation"
      >
        ⎘
      </button>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Badge from '@/Components/Badge.vue'
import type {
  ChainStep,
  ChainStepStatus,
  ExecutionRun,
} from '@/composables/zoneScheduleWorkspaceTypes'

interface Props {
  run: ExecutionRun
  errorText?: string | null
  formatDateTime?: (value: string | null | undefined) => string
  laneLabel?: (taskType: string | null | undefined) => string
}

const props = withDefaults(defineProps<Props>(), {
  errorText: null,
  formatDateTime: undefined,
  laneLabel: (value: string | null | undefined) => value ?? '—',
})

defineEmits<{
  close: []
  retry: [executionId: string]
  'open-events': [executionId: string]
}>()

const STATUS_COLOR: Record<ChainStepStatus, string> = {
  ok: 'var(--accent-green)',
  err: 'var(--accent-red)',
  skip: 'var(--text-dim)',
  run: 'var(--accent-cyan)',
  warn: 'var(--accent-amber)',
}

const steps = computed<ChainStep[]>(() => props.run.chain ?? [])

const isFailed = computed(() => {
  const status = String(props.run.status ?? '').toLowerCase()
  return status === 'failed' || status === 'fail' || Boolean(props.run.error_code)
})

const headerBadgeLabel = computed<string>(() => {
  if (isFailed.value) return 'FAIL'
  const outcome = String(props.run.decision_outcome ?? '').toLowerCase()
  if (outcome === 'skip') return 'SKIP'
  if (props.run.is_active) return 'RUN'
  return String(props.run.status ?? '').toUpperCase() || '—'
})

const headerBadgeVariant = computed<'info' | 'success' | 'danger' | 'secondary'>(() => {
  if (isFailed.value) return 'danger'
  if (props.run.is_active) return 'info'
  const outcome = String(props.run.decision_outcome ?? '').toLowerCase()
  if (outcome === 'skip') return 'secondary'
  return 'success'
})

function formatAt(value: string | null | undefined): string {
  if (!value) return ''
  if (props.formatDateTime) return props.formatDateTime(value)
  return String(value)
}

function copyCorrelation(): void {
  const id = props.run.correlation_id
  if (!id) return
  if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
    void navigator.clipboard.writeText(id)
  }
}
</script>

<style scoped>
.chain-dot-live {
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--accent-cyan) 20%, transparent);
  animation: chain-dot-ping 1.6s ease-out infinite;
}

@keyframes chain-dot-ping {
  0% {
    box-shadow: 0 0 0 0 color-mix(in srgb, var(--accent-cyan) 45%, transparent);
  }
  70% {
    box-shadow: 0 0 0 10px color-mix(in srgb, var(--accent-cyan) 0%, transparent);
  }
  100% {
    box-shadow: 0 0 0 0 color-mix(in srgb, var(--accent-cyan) 0%, transparent);
  }
}
</style>

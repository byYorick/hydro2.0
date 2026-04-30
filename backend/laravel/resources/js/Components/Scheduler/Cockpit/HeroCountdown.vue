<template>
  <section
    class="hero-countdown rounded-2xl border p-4"
    data-testid="scheduler-hero-countdown"
  >
    <template v-if="run">
      <div class="flex items-start justify-between gap-3">
        <div class="min-w-0">
          <div class="flex items-center gap-1.5 text-[10px] font-bold tracking-[0.15em] text-[color:var(--accent-cyan)]">
            <span class="hero-dot"></span>
            <span>ИСПОЛНЯЕТСЯ</span>
            <span
              v-if="run.execution_id"
              class="font-mono text-[11px] font-semibold"
            >
              #{{ run.execution_id }}
            </span>
          </div>
          <div
            class="mt-2 tabular-nums text-[46px] font-bold leading-none tracking-[-0.04em]"
            :class="isExpired ? 'text-[color:var(--accent-amber)]' : 'text-[color:var(--text-primary)]'"
            data-testid="scheduler-hero-countdown-value"
          >
            {{ displayLabel }}
          </div>
        </div>
        <span
          class="hero-radar"
          aria-hidden="true"
        ></span>
      </div>
      <div class="mt-1 text-[11px] text-[color:var(--text-dim)]">
        {{ isExpired ? 'таймер истёк — ожидаем завершение' : etaHint }}
      </div>
      <div
        v-if="isExpired && expectedDeadlineLabel"
        class="mt-1 text-[11px] font-medium text-[color:var(--accent-amber)]"
        data-testid="scheduler-hero-expected-deadline"
      >
        Ожидалось до {{ expectedDeadlineLabel }}
      </div>

      <div class="mt-4 flex flex-col gap-1.5">
        <div class="flex flex-wrap items-center gap-1.5">
          <Badge
            v-if="laneLabel"
            variant="info"
            size="sm"
          >
            {{ laneLabel }}
          </Badge>
          <Badge
            v-if="etaEstimated"
            variant="warning"
            size="sm"
          >
            расчётный ETA
          </Badge>
          <span class="text-[11px] text-[color:var(--text-dim)]">· этап</span>
          <span class="text-[11px] font-semibold text-[color:var(--text-primary)]">{{ stageLabel ?? 'этап не определён' }}</span>
        </div>

        <div
          v-if="progressSteps.length > 0"
          class="mt-1.5 flex gap-[3px]"
        >
          <div
            v-for="(step, index) in progressSteps"
            :key="step"
            class="h-1 flex-1 rounded-sm transition-colors"
            :class="index <= currentStep ? 'bg-[color:var(--accent-cyan)]' : 'bg-[color:var(--border-muted)]'"
          ></div>
        </div>

        <div
          v-if="progressSteps.length > 0"
          class="mt-0.5 flex gap-0.5 text-[9px] text-[color:var(--text-muted)]"
        >
          <span
            v-for="(step, index) in progressSteps"
            :key="`label-${step}`"
            class="flex-1 truncate"
            :class="index === currentStep ? 'text-[color:var(--accent-cyan)] font-semibold' : ''"
          >{{ step }}</span>
        </div>

        <details
          v-if="hasTechnicalDetails"
          class="group mt-2 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]/35 px-2 py-1.5 text-[10px] text-[color:var(--text-muted)]"
        >
          <summary class="cursor-pointer select-none font-medium text-[color:var(--text-dim)] marker:text-[color:var(--text-dim)]">
            Технические детали
          </summary>
          <div class="mt-1.5 space-y-1 font-mono text-[10px] leading-snug break-all">
            <p v-if="run.decision_strategy">
              <span class="text-[color:var(--text-dim)]">strategy</span> {{ run.decision_strategy }}
            </p>
            <p v-if="run.decision_bundle_revision">
              <span class="text-[color:var(--text-dim)]">bundle</span> {{ run.decision_bundle_revision }}
            </p>
            <p v-if="run.correlation_id">
              <span class="text-[color:var(--text-dim)]">correlation</span> {{ run.correlation_id }}
            </p>
          </div>
        </details>
      </div>
    </template>

    <template v-else>
      <div class="flex min-h-[150px] flex-col items-center justify-center gap-2 text-center">
        <span
          class="hero-radar hero-radar--idle"
          aria-hidden="true"
        ></span>
        <span class="text-[10px] font-bold tracking-[0.15em] text-[color:var(--text-dim)]">
          ИСПОЛНЕНИЙ СЕЙЧАС НЕТ
        </span>
        <span class="text-[11px] text-[color:var(--text-muted)]">
          Ожидание ближайшего окна
        </span>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, toRef } from 'vue'
import Badge from '@/Components/Badge.vue'
import type { ExecutionRun } from '@/composables/zoneScheduleWorkspaceTypes'
import { useRafCountdown } from '@/composables/useRafCountdown'

interface Props {
  run: ExecutionRun | null
  laneLabel?: string | null
  stageLabel?: string | null
  /** Static fallback label, если `endAt` не задан. */
  etaLabel?: string
  etaHint?: string
  etaEstimated?: boolean
  /**
   * Конечный момент, до которого идёт countdown. Если задан — компонент
   * обновляет таймер в реальном времени через `useRafCountdown`,
   * игнорируя `etaLabel`.
   */
  endAt?: string | Date | null
  /** Отображение крайнего срока при просрочке (из родителя). */
  formatDateTime?: (value: string | null | undefined) => string
}

const props = withDefaults(defineProps<Props>(), {
  laneLabel: null,
  stageLabel: null,
  etaLabel: '—',
  etaHint: 'осталось до завершения',
  etaEstimated: false,
  endAt: null,
  formatDateTime: undefined,
})

const endAtRef = toRef(props, 'endAt')
const { label: liveLabel, remainingSeconds } = useRafCountdown(endAtRef)

function formatOverdue(totalSeconds: number): string {
  const safe = Math.max(0, Math.abs(totalSeconds))
  const hours = Math.floor(safe / 3600)
  const minutes = Math.floor((safe % 3600) / 60)
  const seconds = safe % 60
  const mm = String(minutes).padStart(2, '0')
  const ss = String(seconds).padStart(2, '0')
  if (hours > 0) {
    return `+${String(hours).padStart(2, '0')}:${mm}:${ss}`
  }
  return `+${mm}:${ss}`
}

const displayLabel = computed<string>(() => {
  if (props.endAt) {
    const remaining = remainingSeconds.value
    if (remaining !== null && remaining <= 0) {
      return formatOverdue(remaining)
    }
    return liveLabel.value
  }
  return props.etaLabel
})

const isExpired = computed<boolean>(() => {
  if (!props.endAt) return false
  const remaining = remainingSeconds.value
  return remaining !== null && remaining <= 0
})

function defaultFormatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return '—'
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(parsed)
}

const expectedDeadlineLabel = computed<string | null>(() => {
  if (!props.endAt || !isExpired.value) return null
  const fmt = props.formatDateTime ?? defaultFormatDateTime
  return fmt(typeof props.endAt === 'string' ? props.endAt : props.endAt.toISOString())
})

const hasTechnicalDetails = computed<boolean>(() => {
  const run = props.run
  if (!run) return false
  return Boolean(run.decision_strategy || run.decision_bundle_revision || run.correlation_id)
})

const progressSteps = computed<string[]>(() => {
  const raw = (props.run?.decision_config as Record<string, unknown> | undefined)?.progress_steps
  if (Array.isArray(raw)) {
    return raw.filter((item): item is string => typeof item === 'string')
  }
  return []
})

const currentStep = computed<number>(() => {
  const raw = (props.run?.decision_config as Record<string, unknown> | undefined)?.current_step
  return typeof raw === 'number' ? raw : -1
})
</script>

<style scoped>
.hero-countdown {
  border-color: color-mix(in srgb, var(--accent-cyan) 30%, transparent);
  background:
    radial-gradient(90% 70% at 18% 0%, color-mix(in srgb, var(--accent-cyan) 17%, transparent), transparent 62%),
    linear-gradient(180deg, color-mix(in srgb, var(--accent-cyan) 8%, transparent), color-mix(in srgb, var(--bg-elevated) 72%, transparent));
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.06),
    0 20px 44px color-mix(in srgb, var(--accent-cyan) 8%, transparent);
}

.hero-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: var(--accent-cyan);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--accent-cyan) 18%, transparent);
  animation: hero-countdown-ping 1.6s ease-out infinite;
}

.hero-radar {
  display: inline-block;
  width: 2.7rem;
  height: 2.7rem;
  flex: 0 0 auto;
  border: 1px solid color-mix(in srgb, var(--accent-cyan) 34%, transparent);
  border-radius: 999px;
  background:
    radial-gradient(circle at 50% 50%, var(--accent-cyan) 0 2px, transparent 3px),
    repeating-radial-gradient(circle at 50% 50%, transparent 0 8px, color-mix(in srgb, var(--accent-cyan) 20%, transparent) 9px 10px),
    conic-gradient(from 180deg, color-mix(in srgb, var(--accent-cyan) 42%, transparent), transparent 45%);
  box-shadow: 0 0 34px color-mix(in srgb, var(--accent-cyan) 18%, transparent);
}

.hero-radar--idle {
  opacity: 0.62;
  filter: grayscale(0.25);
}

@keyframes hero-countdown-ping {
  0% {
    box-shadow: 0 0 0 0 color-mix(in srgb, var(--accent-cyan) 50%, transparent);
  }
  70% {
    box-shadow: 0 0 0 10px color-mix(in srgb, var(--accent-cyan) 0%, transparent);
  }
  100% {
    box-shadow: 0 0 0 0 color-mix(in srgb, var(--accent-cyan) 0%, transparent);
  }
}
</style>

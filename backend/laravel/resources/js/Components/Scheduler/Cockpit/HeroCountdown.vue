<template>
  <section
    class="hero-countdown rounded-2xl border p-4"
    data-testid="scheduler-hero-countdown"
  >
    <template v-if="run">
      <div class="flex items-center gap-1.5 text-[10px] font-bold tracking-[0.15em] text-[color:var(--accent-cyan)]">
        <span class="hero-dot"></span>
        <span>ИСПОЛНЯЕТСЯ</span>
        <span
          v-if="run.execution_id"
          class="font-mono text-[11px] font-semibold"
        >
          · #{{ run.execution_id }}
        </span>
      </div>
      <div
        class="mt-1.5 tabular-nums text-[44px] font-bold leading-none"
        :class="isExpired ? 'text-[color:var(--accent-amber)]' : 'text-[color:var(--text-primary)]'"
        data-testid="scheduler-hero-countdown-value"
      >
        {{ displayLabel }}
      </div>
      <div class="mt-1 text-[11px] text-[color:var(--text-dim)]">
        {{ isExpired ? 'таймер истёк — ожидаем завершение' : etaHint }}
      </div>

      <div class="mt-3 flex flex-col gap-1.5">
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
          <span class="text-[11px] font-semibold text-[color:var(--text-primary)]">{{ stageLabel }}</span>
        </div>

        <div
          v-if="progressSteps.length > 0"
          class="mt-1 flex gap-[3px]"
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

        <div class="mt-1 flex flex-wrap gap-1.5 text-[10px] text-[color:var(--text-muted)]">
          <span v-if="run.decision_strategy">🧩 {{ run.decision_strategy }}</span>
          <span v-if="run.decision_bundle_revision">·</span>
          <span v-if="run.decision_bundle_revision">bundle {{ run.decision_bundle_revision }}</span>
          <span v-if="run.correlation_id">·</span>
          <span
            v-if="run.correlation_id"
            class="font-mono"
          >{{ run.correlation_id }}</span>
        </div>
      </div>
    </template>

    <template v-else>
      <div class="flex min-h-[120px] flex-col items-center justify-center gap-1 text-center">
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
}

const props = withDefaults(defineProps<Props>(), {
  laneLabel: null,
  stageLabel: null,
  etaLabel: '—',
  etaHint: 'осталось до завершения',
  etaEstimated: false,
  endAt: null,
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
  const remaining = remainingSeconds.value
  return remaining !== null && remaining <= 0
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
  background: linear-gradient(
    180deg,
    color-mix(in srgb, var(--accent-cyan) 10%, transparent),
    color-mix(in srgb, var(--accent-cyan) 2%, transparent)
  );
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

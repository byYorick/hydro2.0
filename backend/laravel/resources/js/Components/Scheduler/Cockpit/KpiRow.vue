<template>
  <section
    class="grid grid-cols-2 gap-2.5 md:grid-cols-4"
    data-testid="scheduler-kpi-row"
  >
    <div
      v-for="kpi in kpis"
      :key="kpi.key"
      class="scheduler-kpi-card group"
      :style="{ '--scheduler-kpi-accent': kpi.color }"
      :data-testid="`scheduler-kpi-${kpi.key}`"
    >
      <div class="flex items-start justify-between gap-2">
        <div class="min-w-0">
          <div class="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.12em] text-[color:var(--text-dim)]">
            <span
              v-if="kpi.live"
              class="inline-block h-1.5 w-1.5 rounded-full bg-[color:var(--scheduler-kpi-accent)] shadow-[0_0_0_3px_color-mix(in_srgb,var(--scheduler-kpi-accent)_18%,transparent)]"
            ></span>
            <span class="truncate">{{ kpi.label }}</span>
          </div>
          <div
            class="mt-1 tabular-nums text-2xl font-bold leading-tight md:text-[28px]"
            :style="{ color: kpi.color }"
          >
            {{ kpi.value }}
          </div>
        </div>
        <span
          class="scheduler-kpi-card__orb"
          aria-hidden="true"
        ></span>
      </div>

      <div class="mt-2 h-1.5 overflow-hidden rounded-full bg-[color:var(--border-muted)]/45">
        <span
          class="block h-full rounded-full bg-[color:var(--scheduler-kpi-accent)] transition-all duration-300"
          :style="{ width: `${kpi.meter}%` }"
        ></span>
      </div>
      <div class="mt-1.5 text-[10px] text-[color:var(--text-muted)]">
        {{ kpi.sub }}
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Counters {
  active: number
  completed_24h: number
  failed_24h: number
}

interface Props {
  counters: Counters
  executableWindowsCount: number
  runtime?: string | null
  slo24h?: number | null
  windowTypeCount?: number
}

const props = withDefaults(defineProps<Props>(), {
  runtime: null,
  slo24h: null,
  windowTypeCount: 0,
})

const sloPercent = computed<string>(() => {
  if (props.slo24h === null || props.slo24h === undefined) {
    const total = props.counters.completed_24h + props.counters.failed_24h
    if (total === 0) return '—'
    return `${Math.round((props.counters.completed_24h / total) * 1000) / 10}%`
  }
  return `${Math.round(props.slo24h * 1000) / 10}%`
})

const failPercent = computed<string>(() => {
  const total = props.counters.completed_24h + props.counters.failed_24h
  if (total === 0) return '—'
  return `${Math.round((props.counters.failed_24h / total) * 1000) / 10}%`
})

const totalAttempts24h = computed<number>(() =>
  props.counters.completed_24h + props.counters.failed_24h,
)

const failureRatio = computed<number | null>(() => {
  const total = totalAttempts24h.value
  if (total <= 0) return null
  return props.counters.failed_24h / total
})

function meter(value: number, max: number): number {
  if (!Number.isFinite(value) || value <= 0) return 0
  return Math.min(100, Math.max(12, Math.round((value / max) * 100)))
}

const kpis = computed(() => {
  const total = totalAttempts24h.value
  const totalNote = total > 0 ? `всего ${total} за 24ч` : 'нет попыток за 24ч'
  const failHigh =
    failureRatio.value !== null
    && failureRatio.value >= 0.25
    && props.counters.failed_24h > 0

  return [
    {
      key: 'active',
      label: 'Активные',
      value: props.counters.active,
      sub: props.runtime ? `runtime=${props.runtime}` : 'runtime=—',
      color: 'var(--accent-cyan)',
      live: props.counters.active > 0,
      meter: meter(props.counters.active, 3),
    },
    {
      key: 'completed',
      label: 'Успешные за 24ч',
      value: props.counters.completed_24h,
      sub: `${sloPercent.value} SLO · ${totalNote}`,
      color: 'var(--accent-green)',
      live: false,
      meter: meter(props.counters.completed_24h, Math.max(4, props.counters.completed_24h + props.counters.failed_24h)),
    },
    {
      key: 'failed',
      label: 'Ошибки за 24ч',
      value: props.counters.failed_24h,
      sub:
        failHigh
          ? `${failPercent.value} · высокая доля ошибок — проверьте узлы и каналы · ${totalNote}`
          : `${failPercent.value} · ${totalNote}`,
      color: 'var(--accent-red)',
      live: false,
      meter: meter(props.counters.failed_24h, Math.max(4, props.counters.completed_24h + props.counters.failed_24h)),
    },
    {
      key: 'windows',
      label: 'Окна на горизонте',
      value: props.executableWindowsCount,
      sub: props.windowTypeCount > 0 ? `${props.windowTypeCount} типа` : '—',
      color: 'var(--accent-amber)',
      live: false,
      meter: meter(props.executableWindowsCount, 6),
    },
  ]
})
</script>

<style scoped>
.scheduler-kpi-card {
  --scheduler-kpi-accent: var(--accent-cyan);
  position: relative;
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--scheduler-kpi-accent) 24%, var(--border-muted));
  border-radius: 1rem;
  background:
    radial-gradient(90% 90% at 100% 0%, color-mix(in srgb, var(--scheduler-kpi-accent) 14%, transparent), transparent 62%),
    color-mix(in srgb, var(--bg-elevated) 78%, transparent);
  padding: 0.75rem;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05);
  transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
}

.scheduler-kpi-card:hover {
  transform: translateY(-1px);
  border-color: color-mix(in srgb, var(--scheduler-kpi-accent) 52%, var(--border-strong));
  box-shadow: 0 18px 40px color-mix(in srgb, var(--scheduler-kpi-accent) 12%, transparent);
}

.scheduler-kpi-card__orb {
  width: 2rem;
  height: 2rem;
  flex: 0 0 auto;
  border-radius: 999px;
  background:
    radial-gradient(circle at 50% 50%, var(--scheduler-kpi-accent) 0 2px, transparent 3px),
    conic-gradient(from 120deg, color-mix(in srgb, var(--scheduler-kpi-accent) 58%, transparent), transparent 42%, color-mix(in srgb, var(--scheduler-kpi-accent) 36%, transparent));
  opacity: 0.72;
}
</style>

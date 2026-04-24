<template>
  <section
    class="grid grid-cols-2 gap-2 md:grid-cols-4"
    data-testid="scheduler-kpi-row"
  >
    <div
      v-for="kpi in kpis"
      :key="kpi.key"
      class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]/70 px-3 py-2.5"
      :data-testid="`scheduler-kpi-${kpi.key}`"
    >
      <div class="flex items-center gap-1 text-[11px] text-[color:var(--text-dim)]">
        <span
          v-if="kpi.live"
          class="inline-block h-1.5 w-1.5 rounded-full bg-[color:var(--accent-cyan)] shadow-[0_0_0_3px_color-mix(in_srgb,var(--accent-cyan)_18%,transparent)]"
        ></span>
        <span>{{ kpi.label }}</span>
      </div>
      <div
        class="mt-0.5 tabular-nums text-2xl font-bold leading-tight"
        :style="{ color: kpi.color }"
      >
        {{ kpi.value }}
      </div>
      <div class="text-[10px] text-[color:var(--text-muted)]">
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

const kpis = computed(() => [
  {
    key: 'active',
    label: 'Активные',
    value: props.counters.active,
    sub: props.runtime ? `runtime=${props.runtime}` : 'runtime=—',
    color: 'var(--accent-cyan)',
    live: props.counters.active > 0,
  },
  {
    key: 'completed',
    label: 'Успешные за 24ч',
    value: props.counters.completed_24h,
    sub: `${sloPercent.value} SLO`,
    color: 'var(--accent-green)',
    live: false,
  },
  {
    key: 'failed',
    label: 'Ошибки за 24ч',
    value: props.counters.failed_24h,
    sub: failPercent.value,
    color: 'var(--accent-red)',
    live: false,
  },
  {
    key: 'windows',
    label: 'Окна на горизонте',
    value: props.executableWindowsCount,
    sub: props.windowTypeCount > 0 ? `${props.windowTypeCount} типа` : '—',
    color: 'var(--accent-amber)',
    live: false,
  },
])
</script>

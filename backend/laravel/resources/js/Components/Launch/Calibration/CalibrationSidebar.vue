<template>
  <aside
    class="flex flex-col gap-3.5 p-2.5 rounded-md border border-[var(--border-muted)] bg-[var(--bg-surface-strong)] w-full lg:w-60 lg:min-w-[240px] shrink-0 lg:sticky lg:top-[108px] lg:self-start lg:max-h-[calc(100vh-148px)] lg:overflow-y-auto lg:z-10"
  >
    <div
      v-for="group in groups"
      :key="group.title"
      class="flex flex-col gap-0.5"
    >
      <div
        class="text-[10px] font-bold uppercase tracking-widest text-[var(--text-dim)] px-1.5 pb-1"
      >
        {{ group.title }}
      </div>
      <button
        v-for="it in group.items"
        :key="it.id"
        type="button"
        :aria-current="current === it.id ? 'page' : undefined"
        :class="[
          'flex items-center gap-2 w-full px-2 py-2 border-0 rounded-md text-left',
          current === it.id ? 'bg-brand-soft text-brand-ink' : 'bg-transparent',
          stateOf(it.id) === 'optional' && current !== it.id
            ? 'text-[var(--text-dim)]'
            : current === it.id
              ? 'text-brand-ink'
              : 'text-[var(--text-primary)]',
        ]"
        @click="$emit('select', it.id)"
      >
        <span
          :class="[
            'w-5 h-5 rounded-full inline-flex items-center justify-center text-[11px] font-semibold border shrink-0',
            bulletClass(it.id),
          ]"
          aria-hidden="true"
        >
          <template v-if="stateOf(it.id) === 'passed'">✓</template>
          <template v-else-if="stateOf(it.id) === 'blocker'">!</template>
          <template v-else-if="stateOf(it.id) === 'waiting'">⏳</template>
          <span
            v-else
            class="font-mono"
          >{{ it.idx }}</span>
        </span>
        <span class="flex flex-col leading-tight flex-1 min-w-0">
          <span class="text-sm font-medium flex justify-between gap-1.5">
            <span class="truncate">{{ it.title }}</span>
            <span
              class="font-mono text-[11px] shrink-0"
              :class="current === it.id ? 'text-brand-ink' : 'text-[var(--text-dim)]'"
            >{{ countOf(it.id) }}</span>
          </span>
          <span class="text-[11px] text-[var(--text-dim)] truncate">
            {{ it.subtitle }}<template v-if="waitingLabelOf(it.id)"> · {{ waitingLabelOf(it.id) }}</template>
          </span>
        </span>
      </button>
    </div>
  </aside>
</template>

<script setup lang="ts">
export type CalibrationSubKey =
  | 'sensors'
  | 'pumps'
  | 'process'
  | 'correction'
  | 'pid'

export type CalibrationNavState = 'passed' | 'active' | 'blocker' | 'optional' | 'waiting'

export interface CalibrationNavInfo {
  state: CalibrationNavState
  count: string
  waitingLabel?: string
}

export type CalibrationNavMap = Record<CalibrationSubKey, CalibrationNavInfo>

interface Item {
  id: CalibrationSubKey
  title: string
  subtitle: string
  idx: number
}

const props = defineProps<{
  current: CalibrationSubKey
  nav: CalibrationNavMap
}>()

defineEmits<{ (e: 'select', id: CalibrationSubKey): void }>()

const groups: Array<{ title: string; items: Item[] }> = [
  {
    title: 'Базовая калибровка',
    items: [
      { id: 'sensors', title: 'Сенсоры', subtitle: 'pH · EC · история', idx: 1 },
      { id: 'pumps', title: 'Насосы', subtitle: 'дозирование · runtime', idx: 2 },
      { id: 'process', title: 'Процесс', subtitle: 'окно · отклик · 4 фазы', idx: 3 },
    ],
  },
  {
    title: 'Тонкая настройка',
    items: [
      { id: 'correction', title: 'Коррекция', subtitle: 'authority · пресеты', idx: 4 },
      { id: 'pid', title: 'PID и autotune', subtitle: 'доводка контура', idx: 5 },
    ],
  },
]

function stateOf(id: CalibrationSubKey): CalibrationNavState {
  return props.nav[id].state
}

function countOf(id: CalibrationSubKey): string {
  return props.nav[id].count
}

function waitingLabelOf(id: CalibrationSubKey): string | undefined {
  return props.nav[id].waitingLabel
}

function bulletClass(id: CalibrationSubKey): string {
  const state = stateOf(id)
  if (props.current === id)
    return 'border-brand text-brand bg-[var(--bg-surface)] ring-2 ring-brand-soft'
  if (state === 'passed') return 'bg-growth text-white border-growth'
  if (state === 'blocker') return 'bg-alert text-white border-alert'
  if (state === 'waiting') return 'bg-[var(--bg-elevated)] text-[var(--text-muted)] border-[var(--border-strong)]'
  return 'bg-[var(--bg-surface)] text-[var(--text-muted)] border-[var(--border-strong)]'
}
</script>

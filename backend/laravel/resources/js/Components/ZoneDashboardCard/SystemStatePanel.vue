<template>
  <section class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3">
    <div class="space-y-1.5">
      <div class="flex items-center justify-between gap-2">
        <div class="text-[10px] uppercase tracking-wider text-[color:var(--text-muted)]">
          Состояние системы
        </div>
        <div class="inline-flex items-center gap-1.5 rounded-md border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] px-2 py-1 shrink-0">
          <span
            class="inline-block w-1.5 h-1.5 rounded-full"
            :class="irrigNodeOnline ? 'bg-[color:var(--accent-green)]' : 'bg-[color:var(--accent-red)]'"
          ></span>
          <span class="text-[10px] font-medium text-[color:var(--text-primary)]">IRR</span>
          <span class="text-[10px]" :class="irrigNodeOnline ? 'text-[color:var(--accent-green)]' : 'text-[color:var(--accent-red)]'">
            {{ irrigNodeOnline ? 'online' : 'offline' }}
          </span>
        </div>
      </div>

      <div class="flex items-center justify-between gap-2 min-w-0">
        <div class="min-w-0 flex items-center gap-2">
          <span
            class="inline-block w-1.5 h-1.5 rounded-full shrink-0"
            :class="phaseDotClass"
          ></span>
          <span
            class="text-sm font-medium truncate"
            :class="(offline || automationBlocked) ? 'text-[color:var(--accent-red)]' : 'text-[color:var(--text-primary)]'"
            :title="automationBlocked ? (automationBlockReason || 'Автоматика остановлена') : undefined"
          >
            {{ phaseLabel }}
          </span>
        </div>
        <span
          class="text-[9px] uppercase tracking-wide shrink-0"
          :class="processStateClass"
        >
          {{ processStateLabel }}
        </span>
        <span
          v-if="offline && !automationBlocked"
          class="text-[9px] uppercase tracking-wide text-[color:var(--accent-red)] shrink-0"
        >
          нет связи
        </span>
      </div>
    </div>

    <div
      v-if="topologyLabel !== '—'"
      class="mt-1 text-[9px] text-[color:var(--text-dim)]"
    >
      Топология: {{ topologyLabel }}
    </div>

    <div class="mt-2.5 grid gap-2" :class="tankGridClass">
      <TankLevelIndicator
        v-for="tank in resolvedTankCards"
        :key="tank.key"
        :label="tank.label"
        :percent="tank.percent"
        :offline="tank.offline"
      />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import TankLevelIndicator from '@/Components/ZoneDashboardCard/TankLevelIndicator.vue'

export interface SystemStateTankLevels {
  clean_percent: number | null
  solution_percent: number | null
  buffer_percent?: number | null
  clean_offline?: boolean
  solution_offline?: boolean
  buffer_offline?: boolean
  clean_present?: boolean
  solution_present?: boolean
  buffer_present?: boolean
  topology_count?: number | null
}

interface Props {
  /** Текстовая метка фазы (например "Полив") */
  phaseLabel: string | null
  /** Workflow phase код (idle/preparing/waiting/irrigating/...) */
  phaseCode?: string | null
  /** true если данные workflow state не получены */
  offline?: boolean
  /** true если irrig-нода зоны online */
  irrigNodeOnline?: boolean
  tankLevels?: SystemStateTankLevels | null
  /**
   * true если автоматика остановлена ACTIVE-алертом из POLICY_MANAGED_CODES.
   * После fail-closed AE3 фаза workflow становится `idle`, поэтому без этого
   * флага панель ошибочно показывает «ожидание».
   */
  automationBlocked?: boolean
  /** Короткая человеческая причина блокировки (например «Задача AE3 завершилась ошибкой»). */
  automationBlockReason?: string | null
}

const props = withDefaults(defineProps<Props>(), {
  phaseCode: null,
  offline: false,
  irrigNodeOnline: false,
  tankLevels: null,
  automationBlocked: false,
  automationBlockReason: null,
})

const phaseLabel = computed(() => {
  if (props.automationBlocked) {
    return props.automationBlockReason || 'Автоматика остановлена'
  }
  if (props.offline) return 'Нет связи'
  return props.phaseLabel || 'Ожидание'
})

const phaseDotClass = computed(() => {
  if (props.automationBlocked) return 'bg-[color:var(--accent-red)] animate-pulse'
  if (props.offline) return 'bg-[color:var(--accent-red)]'
  const code = (props.phaseCode ?? '').toLowerCase()
  // Активные фазы (running)
  if (['irrigating', 'irrig_recirc', 'recirculation', 'preparing', 'clean_fill', 'solution_fill'].includes(code)) {
    return 'bg-[color:var(--accent-cyan)] animate-pulse'
  }
  // Ожидание — нейтрально
  if (['idle', 'waiting', 'ready'].includes(code)) {
    return 'bg-[color:var(--text-dim)]'
  }
  // Проблемные
  if (['error', 'failed', 'degraded'].includes(code)) {
    return 'bg-[color:var(--accent-red)]'
  }
  return 'bg-[color:var(--accent-green)]'
})

const irrigNodeOnline = computed(() => Boolean(props.irrigNodeOnline))

const resolvedTankCards = computed(() => {
  const levels = props.tankLevels
  if (!levels) {
    return [
      { key: 'clean', label: 'Чистая вода', percent: null, offline: true },
      { key: 'solution', label: 'Раствор', percent: null, offline: true },
    ]
  }

  const topologyCount = levels.topology_count ?? null
  const cleanPresent = levels.clean_present ?? false
  const solutionPresent = levels.solution_present ?? false
  const bufferPresent = levels.buffer_present ?? false

  if (topologyCount === 3 || bufferPresent) {
    return [
      {
        key: 'clean',
        label: 'Чистая вода',
        percent: levels.clean_percent ?? null,
        offline: props.offline || (levels.clean_offline ?? false),
      },
      {
        key: 'solution',
        label: 'Раствор',
        percent: levels.solution_percent ?? null,
        offline: props.offline || (levels.solution_offline ?? false),
      },
      {
        key: 'buffer',
        label: 'Буфер',
        percent: levels.buffer_percent ?? null,
        offline: props.offline || (levels.buffer_offline ?? false),
      },
    ]
  }

  // Топология 1 бак: если явно видим только один канал.
  if (cleanPresent && !solutionPresent) {
    return [{
      key: 'clean',
      label: 'Бак',
      percent: levels.clean_percent ?? null,
      offline: props.offline || (levels.clean_offline ?? false),
    }]
  }
  if (!cleanPresent && solutionPresent) {
    return [{
      key: 'solution',
      label: 'Бак',
      percent: levels.solution_percent ?? null,
      offline: props.offline || (levels.solution_offline ?? false),
    }]
  }

  // По умолчанию (или когда топология неочевидна) — two-tank представление.
  return [
    {
      key: 'clean',
      label: 'Чистая вода',
      percent: levels.clean_percent ?? null,
      offline: props.offline || (levels.clean_offline ?? false),
    },
    {
      key: 'solution',
      label: 'Раствор',
      percent: levels.solution_percent ?? null,
      offline: props.offline || (levels.solution_offline ?? false),
    },
  ]
})

const topologyLabel = computed(() => {
  const levels = props.tankLevels
  if (!levels) {
    return '—'
  }
  const topologyCount = levels.topology_count ?? null
  if (topologyCount === 3) {
    return '3 бака'
  }
  if (topologyCount === 2) {
    return '2 бака'
  }
  const cleanPresent = levels.clean_present ?? false
  const solutionPresent = levels.solution_present ?? false
  const bufferPresent = levels.buffer_present ?? false
  if (bufferPresent) {
    return '3 бака'
  }
  if (cleanPresent && solutionPresent) {
    return '2 бака'
  }
  if (cleanPresent || solutionPresent) {
    return '1 бак'
  }
  return '—'
})

const tankGridClass = computed(() => {
  if (resolvedTankCards.value.length >= 3) {
    return 'grid-cols-3'
  }
  if (resolvedTankCards.value.length === 2) {
    return 'grid-cols-2'
  }

  return 'grid-cols-1'
})

const processStateLabel = computed(() => {
  if (props.automationBlocked) {
    return 'остановлено'
  }
  if (props.offline) {
    return 'ошибка'
  }
  const code = (props.phaseCode ?? '').toLowerCase()
  if (['error', 'failed', 'degraded'].includes(code)) {
    return 'ошибка'
  }
  if (['idle', 'waiting', 'ready'].includes(code)) {
    return 'ожидание'
  }

  return 'выполняется'
})

const processStateClass = computed(() => {
  if (props.automationBlocked || processStateLabel.value === 'ошибка') {
    return 'text-[color:var(--accent-red)]'
  }
  if (processStateLabel.value === 'ожидание') {
    return 'text-[color:var(--text-dim)]'
  }

  return 'text-[color:var(--accent-cyan)]'
})
</script>

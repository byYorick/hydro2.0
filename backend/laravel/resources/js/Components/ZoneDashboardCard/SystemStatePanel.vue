<template>
  <section class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3">
    <div class="flex items-start justify-between gap-3">
      <div class="min-w-0 flex-1">
        <div class="text-[10px] uppercase tracking-wider text-[color:var(--text-muted)]">
          Состояние системы
        </div>
        <div class="mt-0.5 flex items-center gap-2">
          <span
            class="inline-block w-1.5 h-1.5 rounded-full shrink-0"
            :class="phaseDotClass"
          ></span>
          <span
            class="text-sm font-medium truncate"
            :class="offline ? 'text-[color:var(--accent-red)]' : 'text-[color:var(--text-primary)]'"
          >
            {{ phaseLabel }}
          </span>
        </div>
      </div>

      <div
        v-if="offline"
        class="inline-flex items-center gap-1 rounded-full border border-[color:var(--badge-danger-border)] bg-[color:var(--badge-danger-bg)] px-2 py-0.5 text-[10px] font-medium text-[color:var(--badge-danger-text)] shrink-0"
      >
        <span aria-hidden="true">📡</span>
        нет связи
      </div>
    </div>

    <div class="mt-2.5 grid grid-cols-2 gap-2">
      <TankLevelIndicator
        label="Чистая вода"
        :percent="tankLevels?.clean_percent ?? null"
        :offline="offline || (tankLevels?.clean_offline ?? false)"
      />
      <TankLevelIndicator
        label="Раствор"
        :percent="tankLevels?.solution_percent ?? null"
        :offline="offline || (tankLevels?.solution_offline ?? false)"
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
  clean_offline?: boolean
  solution_offline?: boolean
}

interface Props {
  /** Текстовая метка фазы (например "Полив") */
  phaseLabel: string | null
  /** Workflow phase код (idle/preparing/waiting/irrigating/...) */
  phaseCode?: string | null
  /** true если данные workflow state не получены */
  offline?: boolean
  tankLevels?: SystemStateTankLevels | null
}

const props = withDefaults(defineProps<Props>(), {
  phaseCode: null,
  offline: false,
  tankLevels: null,
})

const phaseLabel = computed(() => {
  if (props.offline) return 'Нет связи'
  return props.phaseLabel || 'Ожидание'
})

const phaseDotClass = computed(() => {
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
</script>

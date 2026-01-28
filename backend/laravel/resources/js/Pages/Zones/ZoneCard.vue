<template>
  <div
    :data-testid="`zone-card-${zone.id}`"
    class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] p-4 hover:border-[color:var(--border-strong)] transition-all duration-200"
  >
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-2 flex-1 min-w-0">
        <button
          class="p-1 rounded hover:bg-[color:var(--bg-elevated)] transition-colors shrink-0"
          :title="isFavorite ? 'Удалить из избранного' : 'Добавить в избранное'"
          @click.stop="toggleFavorite"
        >
          <svg
            class="w-4 h-4 transition-colors"
            :class="isFavorite ? 'text-[color:var(--accent-amber)] fill-[color:var(--accent-amber)]' : 'text-[color:var(--text-dim)]'"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z"
            />
          </svg>
        </button>
        <div class="text-sm font-semibold truncate">
          {{ zone.name }}
        </div>
      </div>
      <Badge
        :variant="variant"
        data-testid="zone-card-status"
      >
        {{ translateStatus(zone.status) }}
      </Badge>
    </div>
    
    <div class="mt-2 text-xs text-[color:var(--text-muted)]">
      <div v-if="zone.description">
        {{ zone.description }}
      </div>
      <div
        v-if="zone.greenhouse"
        class="mt-1"
      >
        Теплица: {{ zone.greenhouse.name }}
      </div>
    </div>

    <!-- Стадия и прогресс -->
    <div
      v-if="activeGrowCycle"
      class="mt-3 space-y-2"
    >
      <div class="flex items-center justify-between">
        <GrowCycleStageHeader :stage="currentStage" />
        <GrowCycleProgressRing
          v-if="cycleProgress !== null"
          :progress="cycleProgress"
          :size="48"
          :stroke-width="4"
        />
      </div>
    </div>

    <!-- Мини-метрики -->
    <div
      v-if="telemetry"
      class="mt-3"
    >
      <ZoneMiniMetrics
        :telemetry="telemetry"
        :targets="zoneTargets"
      />
    </div>

    <!-- Статус узлов и алерты -->
    <div
      v-if="hasStatusInfo"
      class="mt-3 flex items-center justify-between text-xs pt-2 border-t border-[color:var(--border-muted)]"
    >
      <div class="flex items-center gap-3">
        <div
          v-if="nodesOnline !== null || nodesTotal !== null"
          class="flex items-center gap-1"
        >
          <div
            class="w-1.5 h-1.5 rounded-full"
            :class="nodesOnline && nodesOnline > 0 ? 'bg-[color:var(--accent-green)]' : 'bg-[color:var(--text-dim)]'"
          ></div>
          <span class="text-[color:var(--text-muted)]">
            Узлы: <span class="text-[color:var(--text-primary)]">{{ nodesOnline || 0 }}/{{ nodesTotal || 0 }}</span>
          </span>
        </div>
        <div
          v-if="alertsCount !== null && alertsCount > 0"
          class="flex items-center gap-1 text-[color:var(--accent-red)]"
        >
          <svg
            class="w-3 h-3"
            fill="currentColor"
            viewBox="0 0 20 20"
          >
            <path
              fill-rule="evenodd"
              d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
              clip-rule="evenodd"
            />
          </svg>
          <span>{{ alertsCount }}</span>
        </div>
      </div>
    </div>

    <div class="mt-3 flex gap-2">
      <Link
        :href="`/zones/${zone.id}`"
        class="inline-block"
        data-testid="zone-card-link"
      >
        <Button
          size="sm"
          variant="secondary"
        >
          Подробнее
        </Button>
      </Link>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Link } from '@inertiajs/vue3'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import GrowCycleStageHeader from '@/Components/GrowCycleStageHeader.vue'
import GrowCycleProgressRing from '@/Components/GrowCycleProgressRing.vue'
import ZoneMiniMetrics from '@/Components/ZoneMiniMetrics.vue'
import { translateStatus } from '@/utils/i18n'
import { useFavorites } from '@/composables/useFavorites'
import {
  getStageForPhase,
  calculateCycleProgress,
  type GrowStage,
} from '@/utils/growStages'
import { calculateProgressFromDuration } from '@/utils/growCycleProgress'
import { normalizeGrowCycle } from '@/utils/normalizeGrowCycle'
import type { Zone, ZoneTelemetry, ZoneTargets } from '@/types'

type BadgeVariant = 'success' | 'warning' | 'danger' | 'info' | 'neutral'

interface Props {
  zone: Zone
  telemetry?: ZoneTelemetry | null
  targets?: ZoneTargets | any | null
  alertsCount?: number | null
  nodesOnline?: number | null
  nodesTotal?: number | null
}

const props = withDefaults(defineProps<Props>(), {
  telemetry: null,
  targets: null,
  alertsCount: null,
  nodesOnline: null,
  nodesTotal: null,
})

const { isZoneFavorite, toggleZoneFavorite } = useFavorites()

const isFavorite = computed(() => isZoneFavorite(props.zone.id))

function toggleFavorite(): void {
  toggleZoneFavorite(props.zone.id)
}

const variant = computed<BadgeVariant>(() => {
  switch (props.zone.status) {
    case 'RUNNING': return 'success'
    case 'PAUSED': return 'neutral'
    case 'WARNING': return 'warning'
    case 'ALARM': return 'danger'
    default: return 'neutral'
  }
})

const activeGrowCycle = computed(() => {
  const zone = props.zone as any
  return normalizeGrowCycle(zone.activeGrowCycle || zone.active_grow_cycle || null) as any
})

const cyclePhaseTemplates = computed(() => {
  return activeGrowCycle.value?.recipeRevision?.phases || []
})

const cyclePhaseSnapshots = computed(() => {
  return activeGrowCycle.value?.phases || []
})

const cyclePhasesForProgress = computed(() => {
  if (cyclePhaseTemplates.value.length > 0) {
    if (cyclePhaseSnapshots.value.length === 0) {
      return cyclePhaseTemplates.value
    }
    if (cyclePhaseSnapshots.value.length < cyclePhaseTemplates.value.length) {
      return cyclePhaseTemplates.value
    }
  }
  return cyclePhaseSnapshots.value.length ? cyclePhaseSnapshots.value : cyclePhaseTemplates.value
})

// Определяем текущую стадию
const currentStage = computed<GrowStage | null>(() => {
  // Используем новую модель: activeGrowCycle
  if (activeGrowCycle.value?.currentPhase) {
    const currentPhase = activeGrowCycle.value.currentPhase
    const phases = cyclePhasesForProgress.value
    const phaseIndex = currentPhase.phase_index ?? -1
    
    if (phaseIndex >= 0) {
      const phaseTemplate = phases.find((phase: any) => phase.phase_index === phaseIndex)
      const stageTemplateCode = phaseTemplate?.stageTemplate?.code || phaseTemplate?.stage_template?.code || null
      return getStageForPhase(
        currentPhase.name,
        phaseIndex,
        phases.length || 1,
        stageTemplateCode
      ) ?? null
    }
  }
  
  return null
})

// Вычисляем прогресс цикла
const cycleProgress = computed<number | null>(() => {
  // Используем новую модель: activeGrowCycle
  if (activeGrowCycle.value) {
    const cycle = activeGrowCycle.value
    const phases = cyclePhasesForProgress.value
    const currentPhase = cycle.currentPhase
    
    if (currentPhase && phases.length > 0 && cycle.started_at) {
      const phaseIndex = currentPhase.phase_index ?? -1
      if (phaseIndex >= 0) {
        const startedAt = cycle.started_at
        const phaseStartedAt = cycle.phase_started_at || startedAt
        const phaseProgress = calculateProgressFromDuration(
          phaseStartedAt,
          currentPhase.duration_hours,
          currentPhase.duration_days
        ) ?? 0
        
        return calculateCycleProgress(
          phaseIndex,
          phases,
          startedAt,
          phaseProgress
        )
      }
    }
  }
  
  return null
})

// Получаем targets из зоны (если есть current_phase.targets или старый формат)
const zoneTargets = computed(() => {
  if (props.targets) {
    return props.targets
  }
  
  // Пробуем получить из zone (если есть)
  const zone = props.zone as any
  if (zone.current_phase?.targets) {
    return zone.current_phase.targets
  }
  
  if (zone.targets) {
    return zone.targets
  }
  
  return null
})

const hasStatusInfo = computed(() => {
  return props.nodesOnline !== null || props.nodesTotal !== null || (props.alertsCount !== null && props.alertsCount > 0)
})
</script>

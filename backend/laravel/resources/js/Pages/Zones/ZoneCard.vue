<template>
  <div
    :data-testid="`zone-card-${zone.id}`"
    class="zone-card group relative flex flex-col overflow-hidden rounded-2xl border bg-[color:var(--bg-surface)] transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[var(--shadow-card)]"
    :class="cardBorderClass"
  >
    <div
      class="absolute inset-y-0 left-0 w-1"
      :class="accentBarClass"
    />

    <div class="flex flex-1 flex-col gap-3 p-4 pl-5">
      <header class="flex items-start justify-between gap-3">
        <div class="min-w-0 flex-1 space-y-1.5">
          <div class="flex items-center gap-2">
            <button
              type="button"
              class="shrink-0 rounded-lg p-1 transition-colors hover:bg-[color:var(--bg-elevated)]"
              :title="isFavorite ? 'Удалить из избранного' : 'Добавить в избранное'"
              @click.stop="toggleFavorite"
            >
              <svg
                class="h-4 w-4 transition-colors"
                :class="isFavorite ? 'fill-[color:var(--accent-amber)] text-[color:var(--accent-amber)]' : 'text-[color:var(--text-dim)]'"
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
            <h3 class="truncate text-base font-semibold tracking-tight text-[color:var(--text-primary)]">
              {{ zone.name }}
            </h3>
          </div>

          <div class="flex flex-wrap items-center gap-1.5">
            <Badge
              :variant="variant"
              data-testid="zone-card-status"
            >
              {{ translateStatus(zone.status) }}
            </Badge>
            <GrowCycleStageHeader
              v-if="currentStage"
              :stage="currentStage"
            />
          </div>

          <p
            v-if="zone.description"
            class="line-clamp-2 text-xs text-[color:var(--text-muted)]"
          >
            {{ zone.description }}
          </p>
          <p
            v-else-if="zone.greenhouse"
            class="text-xs text-[color:var(--text-muted)]"
          >
            {{ zone.greenhouse.name }}
          </p>
        </div>

        <div
          v-if="cycleProgress !== null"
          class="shrink-0 rounded-2xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]/45 p-1.5"
        >
          <GrowCycleProgressRing
            :progress="cycleProgress"
            :size="56"
            :stroke-width="4"
            class="zone-card__progress"
          />
        </div>
      </header>

      <div
        v-if="telemetry"
        class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]/30 px-3 py-2.5"
      >
        <ZoneMiniMetrics
          class="zone-card__metrics"
          :telemetry="telemetry"
          :targets="zoneTargets"
          :show-metrics="['ph', 'ec', 'temperature', 'humidity']"
        />
      </div>

      <div
        v-else
        class="rounded-xl border border-dashed border-[color:var(--border-muted)] px-3 py-3 text-center text-xs text-[color:var(--text-muted)]"
      >
        Нет свежей телеметрии
      </div>

      <footer class="mt-auto flex items-center justify-between gap-3 border-t border-[color:var(--border-muted)] pt-3">
        <div class="flex min-w-0 flex-wrap items-center gap-2 text-xs">
          <span
            v-if="nodesOnline !== null || nodesTotal !== null"
            class="inline-flex items-center gap-1.5 rounded-full border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]/50 px-2 py-1 text-[color:var(--text-muted)]"
          >
            <span
              class="h-1.5 w-1.5 rounded-full"
              :class="nodesHealthClass"
            />
            Узлы
            <span class="tabular-nums text-[color:var(--text-primary)]">
              {{ nodesOnline || 0 }}/{{ nodesTotal || 0 }}
            </span>
          </span>

          <span
            v-if="alertsCount !== null && alertsCount > 0"
            class="inline-flex items-center gap-1 rounded-full border border-[color:var(--accent-red)]/35 bg-[color:var(--accent-red)]/10 px-2 py-1 text-[color:var(--accent-red)]"
          >
            <svg
              class="h-3 w-3"
              fill="currentColor"
              viewBox="0 0 20 20"
            >
              <path
                fill-rule="evenodd"
                d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                clip-rule="evenodd"
              />
            </svg>
            <span class="tabular-nums font-medium">{{ alertsCount }}</span>
          </span>
        </div>

        <Link
          :href="`/zones/${zone.id}`"
          class="shrink-0"
          data-testid="zone-card-link"
        >
          <Button
            size="sm"
            variant="secondary"
          >
            Подробнее
          </Button>
        </Link>
      </footer>
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

const hasAlerts = computed(() => props.alertsCount !== null && props.alertsCount > 0)

const cardBorderClass = computed(() => {
  if (props.zone.status === 'ALARM' || hasAlerts.value) {
    return 'border-[color:var(--accent-red)]/35 hover:border-[color:var(--accent-red)]/55'
  }
  if (props.zone.status === 'WARNING') {
    return 'border-[color:var(--accent-amber)]/35 hover:border-[color:var(--accent-amber)]/55'
  }
  if (props.zone.status === 'RUNNING') {
    return 'border-[color:var(--border-muted)] hover:border-[color:var(--accent-green)]/40'
  }
  return 'border-[color:var(--border-muted)] hover:border-[color:var(--border-strong)]'
})

const accentBarClass = computed(() => {
  if (props.zone.status === 'ALARM' || hasAlerts.value) return 'bg-[color:var(--accent-red)]'
  if (props.zone.status === 'WARNING') return 'bg-[color:var(--accent-amber)]'
  if (props.zone.status === 'RUNNING') return 'bg-[color:var(--accent-green)]'
  if (props.zone.status === 'PAUSED') return 'bg-[color:var(--text-dim)]'
  return 'bg-[color:var(--accent-cyan)]'
})

const nodesHealthClass = computed(() => {
  const online = props.nodesOnline || 0
  const total = props.nodesTotal || 0
  if (total === 0) return 'bg-[color:var(--text-dim)]'
  if (online === 0) return 'bg-[color:var(--accent-red)]'
  if (online < total) return 'bg-[color:var(--accent-amber)]'
  return 'bg-[color:var(--accent-green)]'
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

const currentStage = computed<GrowStage | null>(() => {
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

const cycleProgress = computed<number | null>(() => {
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

const zoneTargets = computed(() => {
  if (props.targets) {
    return props.targets
  }

  const zone = props.zone as any
  if (zone.current_phase?.targets) {
    return zone.current_phase.targets
  }

  if (zone.targets) {
    return zone.targets
  }

  return null
})
</script>

<style scoped>
.zone-card__progress :deep(span.text-2xl) {
  font-size: 0.85rem;
  line-height: 1;
  font-weight: 700;
}

.zone-card__metrics {
  display: grid !important;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.45rem 0.75rem;
}

.zone-card__metrics > * {
  margin: 0 !important;
  border-radius: 0.65rem;
  background: color-mix(in srgb, var(--bg-surface) 80%, transparent);
  border: 1px solid var(--border-muted);
  padding: 0.4rem 0.55rem;
}

.zone-card__metrics > * > span:first-child {
  font-size: 0.65rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.zone-card__metrics :deep(.font-semibold) {
  font-variant-numeric: tabular-nums;
  font-size: 0.86rem;
}

@media (prefers-reduced-motion: reduce) {
  .zone-card {
    transition: none;
  }

  .zone-card:hover {
    transform: none;
  }
}
</style>

<template>
  <div class="space-y-4">
    <!-- ===== ACTIVE CYCLE ===== -->
    <template v-if="hasCycle">
      <!-- Hero bar -->
      <section class="surface-card relative z-10 overflow-visible rounded-2xl border border-[color:var(--border-muted)] p-4 md:p-5">
        <div class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div class="min-w-0">
            <p class="text-[10px] font-semibold uppercase tracking-[0.18em] text-[color:var(--text-dim)]">
              Цикл выращивания
            </p>
            <div class="mt-1 flex flex-wrap items-center gap-2">
              <h2 class="text-lg font-bold text-[color:var(--text-primary)] truncate">
                {{ zone.name }}
              </h2>
              <Badge :variant="variant" data-testid="zone-status-badge">{{ translateStatus(zone.status) }}</Badge>
              <Badge :variant="cycleStatusVariant" size="sm">{{ cycleStatusLabel }}</Badge>
            </div>
            <!-- Рецепт и фаза -->
            <div v-if="recipeName" class="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs text-[color:var(--text-muted)]">
              <span>{{ recipeName }}</span>
              <span v-if="currentPhaseName" class="text-[color:var(--border-strong)]">&middot;</span>
              <span v-if="currentPhaseName">
                Фаза {{ currentPhaseIndex }}: {{ currentPhaseName }}
              </span>
              <span v-if="phaseTimeLeftLabel" class="text-[color:var(--border-strong)]">&middot;</span>
              <span v-if="phaseTimeLeftLabel" class="text-[color:var(--accent-cyan)]">
                {{ phaseTimeLeftLabel }}
              </span>
            </div>
          </div>
          <CycleActionsDropdown
            :cycle-status="activeGrowCycle?.status ?? null"
            :can-manage="canManageCycle"
            :can-operate="canOperateZone"
            :loading="actionsLoading"
            :control-mode="controlMode ?? null"
            :phase-duration-complete="phaseDurationComplete"
            @start-irrigation="$emit('start-irrigation')"
            @force-irrigation="$emit('force-irrigation')"
            @pause="$emit('pause')"
            @resume="$emit('resume')"
            @harvest="$emit('harvest')"
            @abort="$emit('abort')"
            @next-phase="$emit('next-phase')"
          />
        </div>
      </section>

      <!-- KPI: pH / EC / Температура / Влажность -->
      <ZoneTargets :telemetry="telemetry" :targets="targets" />

      <!-- Прогресс фаз -->
      <Card v-if="activeGrowCycle?.recipeRevision">
        <StageProgress
          :grow-cycle="activeGrowCycle"
          :phase-progress="computedPhaseProgress"
          :phase-days-elapsed="computedPhaseDaysElapsed"
          :phase-days-total="computedPhaseDaysTotal"
          :started-at="activeGrowCycle.started_at"
        />
      </Card>

      <!-- Лог событий цикла -->
      <CycleEventLog
        :zone-id="activeGrowCycle?.zone_id ?? zone.id"
        :phase-id="activeGrowCycle?.currentPhase?.id"
        :limit="10"
        paginated
      />
    </template>

    <!-- ===== NO CYCLE ===== -->
    <section
      v-else
      class="surface-card flex flex-col items-center justify-center rounded-2xl border border-dashed border-[color:var(--border-muted)] px-6 py-16 text-center"
    >
      <div class="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-[color:var(--bg-elevated)]">
        <svg class="h-7 w-7 text-[color:var(--text-dim)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 6v6l4 2m6-2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      </div>
      <p class="text-sm font-medium text-[color:var(--text-primary)]">Цикл выращивания не запущен</p>
      <Badge :variant="variant" data-testid="zone-status-badge" class="mt-2">{{ translateStatus(zone.status) }}</Badge>
      <p class="mt-1 text-xs text-[color:var(--text-dim)]">Запустите цикл, чтобы начать выращивание в этой зоне</p>
      <button
        v-if="canManageRecipe"
        type="button"
        class="mt-5 inline-flex items-center gap-2 rounded-lg border border-[color:var(--accent-cyan)]/40 bg-[color:var(--accent-cyan)]/10 px-4 py-2 text-sm font-medium text-[color:var(--accent-cyan)] transition-colors hover:bg-[color:var(--accent-cyan)]/20"
        @click="$emit('run-cycle')"
      >
        <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        Запустить цикл
      </button>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Badge from '@/Components/Badge.vue'
import Card from '@/Components/Card.vue'
import StageProgress from '@/Components/StageProgress.vue'
import ZoneTargets from '@/Components/ZoneTargets.vue'
import CycleEventLog from '@/Components/GrowCycle/CycleEventLog.vue'
import CycleActionsDropdown from '@/Components/GrowCycle/CycleActionsDropdown.vue'
import { translateStatus } from '@/utils/i18n'
import type { BadgeVariant } from '@/Components/Badge.vue'
import type { Zone, ZoneTargets as ZoneTargetsType, ZoneTelemetry } from '@/types'
import type { GrowCycle } from '@/types/GrowCycle'
import type { AutomationControlMode } from '@/types/Automation'

interface CycleLoadingState {
  irrigate: boolean
  cyclePause: boolean
  cycleResume: boolean
  cycleHarvest: boolean
  cycleAbort: boolean
  nextPhase: boolean
}

interface Props {
  zone: Zone
  variant: BadgeVariant
  activeGrowCycle?: GrowCycle | null
  canOperateZone: boolean
  targets: ZoneTargetsType
  telemetry: ZoneTelemetry
  computedPhaseProgress: number | null
  computedPhaseDaysElapsed: number | null
  computedPhaseDaysTotal: number | null
  cycleStatusLabel: string
  cycleStatusVariant: BadgeVariant
  phaseTimeLeftLabel: string
  canManageRecipe: boolean
  canManageCycle: boolean
  loading: CycleLoadingState
  /** См. CONTROL_MODES_SPEC.md §4.5: в auto "next phase" недоступен, в semi/manual — доступен. */
  controlMode?: AutomationControlMode | null
  /** true если phase_started_at + duration_hours/days < now (фаза готова к advance). */
  phaseDurationComplete?: boolean
}

const props = defineProps<Props>()

defineEmits<{
  'start-irrigation': []
  'force-irrigation': []
  'run-cycle': []
  'refresh-cycle': []
  'change-recipe': []
  'pause': []
  'resume': []
  'harvest': []
  'abort': []
  'next-phase': []
}>()

const hasCycle = computed(() =>
  Boolean(props.activeGrowCycle) || props.zone.status === 'RUNNING' || props.zone.status === 'PAUSED',
)

const recipeName = computed(() =>
  props.activeGrowCycle?.recipeRevision?.recipe?.name
  ?? props.activeGrowCycle?.recipe?.name
  ?? null,
)

const currentPhaseName = computed(() =>
  props.activeGrowCycle?.currentPhase?.name
  ?? props.activeGrowCycle?.current_phase_name
  ?? null,
)

const currentPhaseIndex = computed(() => {
  const idx = props.activeGrowCycle?.currentPhase?.phase_index
    ?? props.activeGrowCycle?.current_phase_index
  return idx != null ? idx + 1 : null
})

const actionsLoading = computed(() => ({
  irrigate: props.loading.irrigate,
  cyclePause: props.loading.cyclePause,
  cycleResume: props.loading.cycleResume,
  cycleHarvest: props.loading.cycleHarvest,
  cycleAbort: props.loading.cycleAbort,
  nextPhase: props.loading.nextPhase,
}))
</script>

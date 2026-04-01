<template>
  <div class="space-y-4">
    <CycleRecipeCard
      :grow-cycle="activeGrowCycle"
      :zone-has-cycle="zoneHasCycle"
      :cycle-status-label="cycleStatusLabel"
      :cycle-status-variant="cycleStatusVariant"
      :phase-time-left-label="phaseTimeLeftLabel"
      :can-manage-recipe="canManageRecipe"
      @run-cycle="$emit('run-cycle')"
      @change-recipe="$emit('change-recipe')"
      @refresh-cycle="$emit('refresh-cycle')"
    />

    <CycleSubsystemsGrid :cycles="cyclesList" />

    <CycleControlPanel
      v-if="activeGrowCycle"
      :cycle="activeGrowCycle"
      :grow-cycle="activeGrowCycle"
      :phase-progress="computedPhaseProgress"
      :phase-days-elapsed="computedPhaseDaysElapsed"
      :phase-days-total="computedPhaseDaysTotal"
      :can-manage="canManageCycle"
      :loading="loading.cyclePause || loading.cycleResume || loading.cycleHarvest || loading.cycleAbort"
      :loading-next-phase="loading.nextPhase"
      @pause="$emit('pause')"
      @resume="$emit('resume')"
      @harvest="$emit('harvest')"
      @abort="$emit('abort')"
      @next-phase="$emit('next-phase')"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import CycleRecipeCard from '@/Components/GrowCycle/CycleRecipeCard.vue'
import CycleSubsystemsGrid from '@/Components/GrowCycle/CycleSubsystemsGrid.vue'
import CycleControlPanel from '@/Components/GrowCycle/CycleControlPanel.vue'
import type { BadgeVariant } from '@/Components/Badge.vue'
import type { GrowCycle } from '@/types/GrowCycle'
import type { SubsystemCycle } from '@/types/Cycle'

interface LoadingStateProps {
  cyclePause: boolean
  cycleResume: boolean
  cycleHarvest: boolean
  cycleAbort: boolean
  nextPhase: boolean
}

interface Props {
  activeGrowCycle?: GrowCycle | null
  zoneStatus?: string
  cyclesList: SubsystemCycle[]
  computedPhaseProgress: number | null
  computedPhaseDaysElapsed: number | null
  computedPhaseDaysTotal: number | null
  cycleStatusLabel: string
  cycleStatusVariant: BadgeVariant
  phaseTimeLeftLabel: string
  canManageRecipe: boolean
  canManageCycle: boolean
  loading: LoadingStateProps
}

const props = defineProps<Props>()

defineEmits<{
  (e: 'run-cycle'): void
  (e: 'refresh-cycle'): void
  (e: 'change-recipe'): void
  (e: 'pause'): void
  (e: 'resume'): void
  (e: 'harvest'): void
  (e: 'abort'): void
  (e: 'next-phase'): void
}>()

/** Зона RUNNING/PAUSED, но growCycle ещё не пришёл с сервера */
const zoneHasCycle = computed(
  () => props.zoneStatus === 'RUNNING' || props.zoneStatus === 'PAUSED',
)
</script>

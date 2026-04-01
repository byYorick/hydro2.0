<template>
  <div class="space-y-4">
    <OverviewHeroCard
      :zone="zone"
      :variant="variant"
      :active-grow-cycle="activeGrowCycle"
      :has-cycle="Boolean(displayCycle)"
      :can-operate-zone="canOperateZone"
      :loading-irrigate="loading.irrigate"
      :telemetry="telemetry"
      @start-irrigation="$emit('start-irrigation')"
      @force-irrigation="$emit('force-irrigation')"
    />

    <OverviewTargetsCard
      :targets="targets"
      :telemetry="telemetry"
    />

    <OverviewCycleCard
      :active-grow-cycle="displayCycle"
      :zone-status="zone.status"
      :phase-progress="computedPhaseProgress"
      :phase-days-elapsed="computedPhaseDaysElapsed"
      :phase-days-total="computedPhaseDaysTotal"
    />

    <OverviewRecentEvents :events="recentEvents" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import OverviewHeroCard from '@/Components/Overview/OverviewHeroCard.vue'
import OverviewTargetsCard from '@/Components/Overview/OverviewTargetsCard.vue'
import OverviewCycleCard from '@/Components/Overview/OverviewCycleCard.vue'
import OverviewRecentEvents from '@/Components/Overview/OverviewRecentEvents.vue'
import type { BadgeVariant } from '@/Components/Badge.vue'
import type { Zone, ZoneTargets as ZoneTargetsType, ZoneTelemetry } from '@/types'
import type { ZoneEvent } from '@/types/ZoneEvent'

interface OverviewLoadingState {
  irrigate: boolean
}

interface Props {
  zone: Zone
  variant: BadgeVariant
  activeGrowCycle?: any
  activeCycle?: any
  loading: OverviewLoadingState
  canOperateZone: boolean
  targets: ZoneTargetsType
  telemetry: ZoneTelemetry
  computedPhaseProgress: number | null
  computedPhaseDaysElapsed: number | null
  computedPhaseDaysTotal: number | null
  events: ZoneEvent[]
}

const props = defineProps<Props>()

defineEmits<{
  'start-irrigation': []
  'force-irrigation': []
}>()

const displayCycle = computed(() => props.activeGrowCycle ?? props.activeCycle ?? null)

const recentEvents = computed(() =>
  Array.isArray(props.events) ? props.events.slice(0, 5) : [],
)
</script>

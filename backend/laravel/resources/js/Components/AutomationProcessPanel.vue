<template>
  <section class="automation-process-panel surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4 md:p-5">
    <AutomationStatusHeader
      :state-code="stateCode"
      :state-label="stateLabel"
      :state-variant="stateVariant"
      :is-process-active="isProcessActive"
      :progress-summary="progressSummary"
      :error-message="errorMessage"
      :setup-stages="setupStages"
      :current-setup-stage-label="currentSetupStageLabel"
    />

    <AutomationProcessDiagram
      :flow-offset="flowOffset"
      :clean-tank-level="cleanTankLevel"
      :nutrient-tank-level="nutrientTankLevel"
      :buffer-tank-level="bufferTankLevel"
      :is-pump-in-active="isPumpInActive"
      :is-circulation-active="isCirculationActive"
      :is-ph-correction-active="isPhCorrectionActive"
      :is-ec-correction-active="isEcCorrectionActive"
      :is-water-inlet-active="isWaterInletActive"
      :is-tank-refill-active="isTankRefillActive"
      :is-irrigation-active="isIrrigationActive"
      :is-process-active="isProcessActive"
      :automation-state="automationState"
    />

    <AutomationTimeline :events="timelineEvents" />
  </section>
</template>

<script setup lang="ts">
import AutomationStatusHeader from '@/Components/AutomationStatusHeader.vue'
import AutomationProcessDiagram from '@/Components/AutomationProcessDiagram.vue'
import AutomationTimeline from '@/Components/AutomationTimeline.vue'
import type { AutomationStateType } from '@/types/Automation'
import type { IrrigationSystem } from '@/composables/zoneAutomationTypes'
import { useAutomationPanel } from '@/composables/useAutomationPanel'

interface Props {
  zoneId: number | null
  fallbackTanksCount?: number
  fallbackSystemType?: IrrigationSystem
}

const props = withDefaults(defineProps<Props>(), {
  fallbackTanksCount: 2,
  fallbackSystemType: 'drip',
})

const emit = defineEmits<{
  (e: 'state-change', state: AutomationStateType): void
}>()

const {
  automationState,
  errorMessage,
  flowOffset,
  stateCode,
  stateLabel,
  stateVariant,
  isProcessActive,
  cleanTankLevel,
  nutrientTankLevel,
  bufferTankLevel,
  isPumpInActive,
  isCirculationActive,
  isPhCorrectionActive,
  isEcCorrectionActive,
  isWaterInletActive,
  isTankRefillActive,
  isIrrigationActive,
  setupStages,
  currentSetupStageLabel,
  progressSummary,
  timelineEvents,
} = useAutomationPanel(props, emit)
</script>

<style scoped>
.automation-process-panel {
  position: relative;
}
</style>

<template>
  <section
    class="zone-automation-runtime surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl overflow-hidden"
    aria-labelledby="zone-automation-runtime-title"
  >
    <div class="border-b border-[color:var(--border-muted)]/70 bg-[color:var(--surface-muted)]/20 px-4 py-3 md:px-5">
      <div class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2
            id="zone-automation-runtime-title"
            class="text-sm font-semibold text-[color:var(--text-primary)]"
          >
            Процесс автоматики
          </h2>
          <p class="text-xs text-[color:var(--text-muted)] mt-0.5">
            Состояние AE3, схема контура и журнал событий
          </p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <Badge :variant="stateBadgeVariant">
            {{ stateCode }}
          </Badge>
          <Badge
            v-if="isProcessActive"
            variant="info"
          >
            Активно
          </Badge>
        </div>
      </div>
    </div>

    <div class="p-4 md:p-5 space-y-4">
      <AutomationStatusHeader
        :state-code="stateCode"
        :state-label="stateLabel"
        :macro-phase-label="macroPhaseLabel"
        :show-macro-phase-subtitle="showMacroPhaseSubtitle"
        :state-variant="stateVariant"
        :is-process-active="isProcessActive"
        :progress-summary="progressSummary"
        :display-elapsed-sec="displayElapsedSec"
        :progress-percent="progressPercent"
        :show-progress-percent="showProgressPercent"
        :error-message="null"
        :warning-message="null"
        :workflow-stages="workflowStages"
        :current-workflow-stage-label="currentWorkflowStageLabel"
      />

      <AutomationRuntimeAlerts
        :failed="runtimeMeta.hasFailed.value"
        :human-error-message="runtimeMeta.humanErrorMessage.value"
        :error-code="runtimeMeta.errorCode.value"
        :error-message="errorMessage"
        :connectivity-warning="connectivityWarning"
        :is-stale="runtimeMeta.isStale.value"
        :stale-duration="runtimeMeta.staleDuration.value"
        :data-timestamp="runtimeMeta.dataTimestamp.value"
      />

      <div class="grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(280px,0.65fr)]">
        <div class="min-w-0 rounded-xl border border-[color:var(--border-muted)]/50 bg-[color:var(--surface-card)]/30 p-2 md:p-3 flex items-center justify-center">
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
            :irr-node-state="irrNodeState"
          />
        </div>

        <aside class="space-y-4 min-w-0">
          <AutomationRuntimeMetrics
            :automation-state="automationState"
            :clean-tank-level="cleanTankLevel"
            :nutrient-tank-level="nutrientTankLevel"
            :buffer-tank-level="bufferTankLevel"
            :is-pump-in-active="isPumpInActive"
            :is-circulation-active="isCirculationActive"
            :is-ph-correction-active="isPhCorrectionActive"
            :is-ec-correction-active="isEcCorrectionActive"
            :is-irrigation-active="isIrrigationActive"
          />
          <AutomationObservabilityPanel :automation-state="automationState" />
          <AutomationTimeline :events="timelineEvents" />
        </aside>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AutomationStatusHeader from '@/Components/AutomationStatusHeader.vue'
import AutomationProcessDiagram from '@/Components/AutomationProcessDiagram.vue'
import AutomationTimeline from '@/Components/AutomationTimeline.vue'
import AutomationRuntimeAlerts from '@/Components/ZoneAutomation/AutomationRuntimeAlerts.vue'
import AutomationRuntimeMetrics from '@/Components/ZoneAutomation/AutomationRuntimeMetrics.vue'
import AutomationObservabilityPanel from '@/Components/ZoneAutomation/AutomationObservabilityPanel.vue'
import Badge from '@/Components/Badge.vue'
import { useAutomationPanel } from '@/composables/useAutomationPanel'
import { useAutomationRuntimeMeta } from '@/composables/useAutomationRuntimeMeta'
import type { AutomationState, AutomationStateType } from '@/types/Automation'
import type { IrrigationSystem } from '@/composables/zoneAutomationTypes'

interface Props {
  zoneId: number | null
  fallbackTanksCount?: number
  fallbackSystemType?: IrrigationSystem
  automationStateRefreshSeq?: number
}

const props = withDefaults(defineProps<Props>(), {
  fallbackTanksCount: 2,
  fallbackSystemType: 'drip',
  automationStateRefreshSeq: 0,
})

const emit = defineEmits<{
  (e: 'state-change', state: AutomationStateType): void
  (e: 'state-snapshot', snapshot: AutomationState): void
}>()

const {
  automationState,
  errorMessage,
  connectivityWarning,
  flowOffset,
  stateCode,
  stateLabel,
  macroPhaseLabel,
  showMacroPhaseSubtitle,
  stateVariant,
  isProcessActive,
  displayElapsedSec,
  progressPercent,
  showProgressPercent,
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
  workflowStages,
  currentWorkflowStageLabel,
  progressSummary,
  timelineEvents,
  irrNodeState,
} = useAutomationPanel(props, emit)

const runtimeMeta = useAutomationRuntimeMeta(automationState)

const stateBadgeVariant = computed<'neutral' | 'info' | 'warning' | 'success'>(() => {
  const map: Record<AutomationStateType, 'neutral' | 'info' | 'warning' | 'success'> = {
    IDLE: 'neutral',
    TANK_FILLING: 'info',
    TANK_RECIRC: 'warning',
    READY: 'success',
    IRRIGATING: 'info',
    IRRIG_RECIRC: 'warning',
  }
  return map[stateCode.value]
})
</script>

<style scoped>
.zone-automation-runtime {
  position: relative;
}
</style>

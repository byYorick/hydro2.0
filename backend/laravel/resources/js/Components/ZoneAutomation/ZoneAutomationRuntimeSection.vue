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
          <Badge
            v-if="isAutomationStateLoading"
            variant="info"
          >
            Загрузка…
          </Badge>
          <Badge
            v-else
            :variant="stateBadgeVariant"
          >
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
        :display-remaining-sec="displayRemainingSec"
        :progress-basis="progressBasis"
        :show-elapsed-metrics="showElapsedMetrics"
        :progress-percent="progressPercent"
        :show-progress-percent="showProgressPercent"
        :error-message="null"
        :warning-message="null"
        :workflow-stages="workflowStages"
        :current-workflow-stage-label="currentWorkflowStageLabel"
      />

      <AutomationRuntimeAlerts
        :failed="runtimeMeta.hasActiveFailure.value"
        :active-failure="runtimeMeta.hasActiveFailure.value"
        :historical-failure="false"
        :human-error-message="runtimeMeta.hasActiveFailure.value ? runtimeMeta.humanErrorMessage.value : null"
        :error-code="runtimeMeta.hasActiveFailure.value ? runtimeMeta.errorCode.value : null"
        :error-message="errorMessage"
        :connectivity-warning="connectivityWarning"
        :is-stale="runtimeMeta.isStale.value"
        :stale-duration="runtimeMeta.staleDuration.value"
        :data-timestamp="runtimeMeta.dataTimestamp.value"
      />

      <div
        v-if="plantingDecisionMessage"
        class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--surface-muted)]/30 px-3 py-2"
        data-testid="zone-planting-decision"
      >
        <p class="text-sm text-[color:var(--text-primary)]">
          {{ plantingDecisionMessage }}
        </p>
      </div>

      <div
        v-if="unattendedReady !== null"
        class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--surface-muted)]/20 px-3 py-2 space-y-2"
        data-testid="zone-unattended-ready"
      >
        <p
          class="text-sm font-medium"
          :class="unattendedReady
            ? 'text-[color:var(--text-primary)]'
            : 'text-[color:var(--warning)]'"
          data-testid="zone-unattended-status"
        >
          {{ unattendedReady ? 'Можно уйти на неделю' : 'Уйти нельзя' }}
        </p>
        <ul
          v-if="unattendedBlockerMessages.length > 0"
          class="list-disc pl-5 space-y-1 text-sm text-[color:var(--text-primary)]"
          data-testid="zone-unattended-blockers"
        >
          <li
            v-for="(message, index) in unattendedBlockerMessages"
            :key="`${index}-${message}`"
          >
            {{ message }}
          </li>
        </ul>
      </div>

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
            :active-dose-channels="activeDoseChannels"
            :pump-hover-by-channel="pumpHoverByChannel"
            :is-water-inlet-active="isWaterInletActive"
            :is-clean-supply-active="isCleanSupplyActive"
            :is-solution-supply-active="isSolutionSupplyActive"
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
import { computed, toRef } from 'vue'
import AutomationStatusHeader from '@/Components/AutomationStatusHeader.vue'
import AutomationProcessDiagram from '@/Components/AutomationProcessDiagram.vue'
import AutomationTimeline from '@/Components/AutomationTimeline.vue'
import AutomationRuntimeAlerts from '@/Components/ZoneAutomation/AutomationRuntimeAlerts.vue'
import AutomationRuntimeMetrics from '@/Components/ZoneAutomation/AutomationRuntimeMetrics.vue'
import AutomationObservabilityPanel from '@/Components/ZoneAutomation/AutomationObservabilityPanel.vue'
import Badge from '@/Components/Badge.vue'
import { useAutomationPanel } from '@/composables/useAutomationPanel'
import { useAutomationRuntimeMeta } from '@/composables/useAutomationRuntimeMeta'
import { useCorrectionPumpHoverData } from '@/composables/useCorrectionPumpHoverData'
import type { AutomationState, AutomationStateType } from '@/types/Automation'
import type { IrrigationSystem } from '@/composables/zoneAutomationTypes'

interface Props {
  zoneId: number | null
  fallbackTanksCount?: number
  fallbackSystemType?: IrrigationSystem
  automationStateRefreshSeq?: number
  pumpCalibrationSaveSeq?: number
}

const props = withDefaults(defineProps<Props>(), {
  fallbackTanksCount: 2,
  fallbackSystemType: 'drip',
  automationStateRefreshSeq: 0,
  pumpCalibrationSaveSeq: 0,
})

const emit = defineEmits<{
  (e: 'state-change', state: AutomationStateType): void
  (e: 'state-snapshot', snapshot: AutomationState): void
}>()

const {
  automationState,
  isAutomationStateLoading,
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
  displayRemainingSec,
  progressBasis,
  showElapsedMetrics,
  progressPercent,
  showProgressPercent,
  cleanTankLevel,
  nutrientTankLevel,
  bufferTankLevel,
  isPumpInActive,
  isCirculationActive,
  isPhCorrectionActive,
  isEcCorrectionActive,
  activeDoseChannels,
  isWaterInletActive,
  isCleanSupplyActive,
  isSolutionSupplyActive,
  isTankRefillActive,
  isIrrigationActive,
  workflowStages,
  currentWorkflowStageLabel,
  progressSummary,
  timelineEvents,
  irrNodeState,
} = useAutomationPanel(props, emit)

const { pumpHoverByChannel } = useCorrectionPumpHoverData(
  toRef(props, 'zoneId'),
  toRef(props, 'pumpCalibrationSaveSeq'),
)

const runtimeMeta = useAutomationRuntimeMeta(automationState)

const plantingDecisionMessage = computed(() => {
  const decision = automationState.value?.planting_decision
  if (!decision || decision.failed === true) {
    return null
  }
  const text = String(decision.human_message || '').trim()
  return text || null
})

const unattendedReady = computed<boolean | null>(() => {
  const value = automationState.value?.unattended_ready
  return typeof value === 'boolean' ? value : null
})

const unattendedBlockerMessages = computed(() => {
  const blockers = automationState.value?.unattended_blockers
  if (!Array.isArray(blockers)) {
    return [] as string[]
  }
  return blockers
    .map((item) => {
      const human = String(item.human_message || '').trim()
      if (human) {
        return human
      }
      return ''
    })
    .filter((text) => text !== '')
})

const stateBadgeVariant = computed<'neutral' | 'info' | 'warning' | 'success' | 'danger'>(() => {
  if (runtimeMeta.hasActiveFailure.value) {
    return 'danger'
  }
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

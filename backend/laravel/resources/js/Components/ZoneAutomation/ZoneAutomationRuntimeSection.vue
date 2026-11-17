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
            Ход задачи, данные контура и причины ожидания
          </p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant="secondary"
            :disabled="isAutomationStateLoading"
            data-testid="automation-state-refresh"
            @click="refresh"
          >
            {{ isAutomationStateLoading ? 'Обновление…' : 'Обновить состояние' }}
          </Button>
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
            {{ automationState ? stateLabel : 'Состояние не получено' }}
          </Badge>
          <Badge
            v-if="isProcessActive"
            variant="info"
          >
            Задача в работе
          </Badge>
        </div>
      </div>
    </div>

    <div class="p-4 md:p-5 space-y-4">
      <AutomationRuntimeAlerts
        :failed="runtimeMeta.hasActiveFailure.value"
        :active-failure="runtimeMeta.hasActiveFailure.value"
        :historical-failure="false"
        :human-error-message="runtimeMeta.hasActiveFailure.value ? runtimeMeta.humanErrorMessage.value : null"
        :error-code="runtimeMeta.hasActiveFailure.value ? runtimeMeta.errorCode.value : null"
        :error-message="errorMessage"
        :connectivity-warning="connectivityWarning"
        :is-stale="snapshotUnreliable"
        :stale-duration="runtimeMeta.staleDuration.value"
        :data-timestamp="runtimeMeta.dataTimestamp.value"
      />
      <p
        v-if="lastReceivedAt"
        class="text-xs text-[color:var(--text-muted)]"
        data-testid="automation-state-freshness"
      >
        Ответ получен: {{ formatDateTime(lastReceivedAt) }}. Время последнего успешного получения состояния: {{ formatDateTime(automationState?.state_meta?.observed_at) }}.
      </p>
      <SkeletonBlock
        v-if="isAutomationStateLoading && !automationState"
        class="h-32"
        data-testid="automation-state-loading"
      />
      <div
        v-else-if="!automationState"
        data-testid="automation-state-empty"
      >
        <EmptyState
          title="Состояние автоматики недоступно"
          description="Текущее выполнение и состояние оборудования неизвестны. Нажмите «Обновить состояние», чтобы повторить запрос."
        />
      </div>
      <template v-if="automationState">
        <AutomationStatusHeader
          :snapshot-stale="snapshotUnreliable"
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

        <div class="grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(280px,0.65fr)]">
          <div class="min-w-0 rounded-xl border border-[color:var(--border-muted)]/50 bg-[color:var(--surface-card)]/30 p-2 md:p-3 min-w-0">
            <p class="mb-2 text-xs text-[color:var(--text-muted)]">
              Схема этапа по данным задачи. Движение на схеме не подтверждает расход воды. Отметки уровня по дискретным датчикам условны.
            </p>
            <AutomationProcessDiagram
              v-if="cleanTankLevel !== null && nutrientTankLevel !== null && !snapshotUnreliable"
              :flow-offset="flowOffset"
              :clean-tank-level="cleanTankLevel"
              :nutrient-tank-level="nutrientTankLevel"
              :buffer-tank-level="bufferTankLevel ?? 0"
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
            <div
              v-else
              data-testid="automation-diagram-unavailable"
            >
              <EmptyState
                :title="snapshotUnreliable ? 'Схема приостановлена' : 'Нет данных об уровнях баков'"
                :description="snapshotUnreliable ? 'Данные могли устареть. Текущее положение клапанов и работа насосов не подтверждены.' : 'Неизвестный уровень не означает пустой бак. Показания появятся после получения данных.'"
              />
            </div>
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
            <CropDaySection
              :automation-state="automationState"
              :recipe-phase="recipePhase"
            />
          </aside>
        </div>
        <AutomationObservabilityPanel :automation-state="displayState" />
        <AutomationTimeline :events="timelineEvents" />
      </template>
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
import CropDaySection from '@/Components/ZoneAutomation/CropDaySection.vue'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import EmptyState from '@/Components/EmptyState.vue'
import SkeletonBlock from '@/Components/SkeletonBlock.vue'
import { formatDateTime } from '@/utils/schedulerLabels'
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
  recipePhase?: unknown
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
  snapshotUnreliable,
  lastReceivedAt,
  refresh,
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
const displayState = computed(() => automationState.value && snapshotUnreliable.value ? { ...automationState.value, state_meta: { ...automationState.value.state_meta, is_stale: true } } : automationState.value)

const stateBadgeVariant = computed<'neutral' | 'info' | 'warning' | 'success' | 'danger'>(() => {
  if (snapshotUnreliable.value) return 'warning'
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

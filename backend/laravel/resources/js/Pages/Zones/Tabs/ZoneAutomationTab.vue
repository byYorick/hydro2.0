<template>
  <div class="space-y-4">
    <div
      v-if="!zoneId"
      class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4 text-sm text-[color:var(--text-dim)]"
    >
      Нет данных зоны для автоматизации.
    </div>

    <template v-else>
      <AutomationProfileCard
        :can-configure-automation="canConfigureAutomation"
        :telemetry-label="telemetryLabel"
        :water-topology-label="waterTopologyLabel"
        :climate-form="climateForm"
        :water-form="waterForm"
        :lighting-form="lightingForm"
        @edit="showEditWizard = true"
      />

      <p
        v-if="isSystemTypeLocked"
        class="text-xs text-[color:var(--text-dim)]"
      >
        Тип системы зафиксирован для активного цикла.
      </p>

      <AutomationWorkflowCard
        :zone-id="zoneId"
        :fallback-tanks-count="waterForm.tanksCount"
        :fallback-system-type="waterForm.systemType"
        @state-snapshot="handleProcessStateSnapshot"
      />

      <AutomationQuickActionsCard
        :can-operate-automation="canOperateAutomation"
        :quick-actions="quickActions"
        @manual-irrigation="runManualIrrigation"
        @manual-climate="runManualClimate"
        @manual-lighting="runManualLighting"
        @manual-ph="runManualPh"
        @manual-ec="runManualEc"
      />

      <section class="grid gap-4 xl:grid-cols-2">
        <PidConfigForm
          :zone-id="Number(zoneId)"
          @saved="onPidSaved"
        />
        <RelayAutotuneTrigger :zone-id="Number(zoneId)" />
      </section>

      <PumpCalibrationsPanel :zone-id="Number(zoneId)" />

      <AutomationControlModeCard
        :can-operate-automation="canOperateAutomation"
        :automation-control-mode="automationControlMode"
        :allowed-manual-steps="allowedManualSteps"
        :automation-control-mode-loading="automationControlModeLoading"
        :automation-control-mode-saving="automationControlModeSaving"
        :manual-step-loading="manualStepLoading"
        :pending-control-mode-value="pendingControlModeValue"
        :automation-state-meta-label="automationStateMetaLabel"
        @select-mode="onControlModeSelect"
        @run-manual-step="runManualStep"
      />

      <section class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4 space-y-4">
        <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
          <div>
            <h3 class="text-base font-semibold text-[color:var(--text-primary)]">Применение профиля автоматики</h3>
            <p class="text-xs text-[color:var(--text-dim)] mt-1">
              Профиль сначала сохраняется в БД, затем отправляется `GROWTH_CYCLE_CONFIG` (`mode=adjust`, `profile_mode`).
            </p>
          </div>
          <div class="text-xs text-[color:var(--text-muted)]">
            <span v-if="lastAppliedAt">Последнее применение: {{ formatDateTime(lastAppliedAt) }}</span>
            <span v-else>Профиль ещё не применялся</span>
          </div>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-[220px,1fr] gap-3 items-end">
          <label class="text-xs text-[color:var(--text-muted)]">
            Режим профиля
            <select
              v-model="automationLogicMode"
              class="input-select mt-1 w-full"
              :disabled="!canConfigureAutomation || isApplyingProfile || isSyncingAutomationLogicProfile"
            >
              <option value="setup">setup</option>
              <option value="working">working</option>
            </select>
          </label>
          <div class="text-xs text-[color:var(--text-muted)]">
            <span v-if="isSyncingAutomationLogicProfile">Синхронизация профиля с бэкендом...</span>
            <span v-else-if="lastAutomationLogicSyncAt">Профиль в БД обновлён: {{ formatDateTime(lastAutomationLogicSyncAt) }}</span>
            <span v-else>Профиль в БД ещё не синхронизирован</span>
          </div>
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            :disabled="!canConfigureAutomation || isApplyingProfile || isSyncingAutomationLogicProfile"
            @click="applyAutomationProfile"
          >
            {{ isApplyingProfile ? 'Отправка профиля...' : (isSyncingAutomationLogicProfile ? 'Сохранение профиля...' : 'Применить профиль автоматики') }}
          </Button>
          <Button
            size="sm"
            variant="secondary"
            :disabled="isApplyingProfile || isSyncingAutomationLogicProfile"
            @click="resetToRecommended"
          >
            Восстановить рекомендуемые значения
          </Button>
        </div>
      </section>

      <AutomationSchedulerDevCard
        :scheduler-task-id-input="schedulerTaskIdInput"
        :scheduler-task-lookup-loading="schedulerTaskLookupLoading"
        :scheduler-task-list-loading="schedulerTaskListLoading"
        :scheduler-task-error="schedulerTaskError"
        :scheduler-task-status="schedulerTaskStatus"
        :scheduler-task-sla="schedulerTaskSla"
        :scheduler-task-done="schedulerTaskDone"
        :scheduler-task-timeline="schedulerTaskTimeline"
        :format-date-time="formatDateTime"
        :scheduler-task-status-variant="schedulerTaskStatusVariant"
        :scheduler-task-status-label="schedulerTaskStatusLabel"
        :scheduler-task-decision-label="schedulerTaskDecisionLabel"
        :scheduler-task-reason-label="schedulerTaskReasonLabel"
        :scheduler-task-error-label="schedulerTaskErrorLabel"
        :scheduler-task-process-status-variant="schedulerTaskProcessStatusVariant"
        :scheduler-task-process-status-label="schedulerTaskProcessStatusLabel"
        :scheduler-task-event-label="schedulerTaskEventLabel"
        :scheduler-task-timeline-step-label="schedulerTaskTimelineStepLabel"
        :scheduler-task-timeline-stage-label="schedulerTaskTimelineStageLabel"
        :filtered-recent-scheduler-tasks="filteredRecentSchedulerTasks"
        :scheduler-task-search="schedulerTaskSearch"
        :scheduler-task-preset="schedulerTaskPreset"
        :scheduler-task-preset-options="schedulerTaskPresetOptions"
        :scheduler-tasks-updated-at="schedulerTasksUpdatedAt"
        @lookup-task="lookupSchedulerTask"
        @refresh-list="fetchRecentSchedulerTasks"
        @update:scheduler-task-id-input="onSchedulerTaskIdInputUpdate"
        @update:scheduler-task-search="onSchedulerTaskSearchUpdate"
        @update:scheduler-task-preset="onSchedulerTaskPresetUpdate"
      />

      <div class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4">
        <AIPredictionsSection
          :zone-id="zoneId"
          :targets="predictionTargets"
          :horizon-minutes="60"
          :auto-refresh="true"
          :default-expanded="false"
        />
      </div>

      <ZoneAutomationEditWizard
        :open="showEditWizard"
        :climate-form="climateForm"
        :water-form="waterForm"
        :lighting-form="lightingForm"
        :is-applying="isApplyingProfile"
        :is-system-type-locked="isSystemTypeLocked"
        @close="showEditWizard = false"
        @apply="onApplyFromWizard"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, toRef } from 'vue'
import AIPredictionsSection from '@/Components/AIPredictionsSection.vue'
import AutomationControlModeCard from '@/Components/AutomationControlModeCard.vue'
import AutomationProfileCard from '@/Components/AutomationProfileCard.vue'
import AutomationQuickActionsCard from '@/Components/AutomationQuickActionsCard.vue'
import AutomationSchedulerDevCard from '@/Components/AutomationSchedulerDevCard.vue'
import AutomationWorkflowCard from '@/Components/AutomationWorkflowCard.vue'
import Button from '@/Components/Button.vue'
import PidConfigForm from '@/Components/PidConfigForm.vue'
import PumpCalibrationsPanel from '@/Components/PumpCalibrationsPanel.vue'
import RelayAutotuneTrigger from '@/Components/RelayAutotuneTrigger.vue'
import ZoneAutomationEditWizard from '@/Pages/Zones/Tabs/ZoneAutomationEditWizard.vue'
import type {
  ClimateFormState,
  LightingFormState,
  SchedulerTaskPreset,
  WaterFormState,
  ZoneAutomationTabProps,
} from '@/composables/zoneAutomationTypes'
import { useZoneAutomationTab } from '@/composables/useZoneAutomationTab'
import type { AutomationState } from '@/types/Automation'
import type { PidConfigWithMeta } from '@/types/PidConfig'

interface ZoneAutomationWizardApplyPayload {
  climateForm: ClimateFormState
  waterForm: WaterFormState
  lightingForm: LightingFormState
}

const props = defineProps<ZoneAutomationTabProps>()

const {
  canConfigureAutomation,
  canOperateAutomation,
  isSystemTypeLocked,
  climateForm,
  waterForm,
  lightingForm,
  quickActions,
  isApplyingProfile,
  isSyncingAutomationLogicProfile,
  lastAppliedAt,
  automationLogicMode,
  lastAutomationLogicSyncAt,
  predictionTargets,
  telemetryLabel,
  waterTopologyLabel,
  applyAutomationProfile,
  resetToRecommended,
  runManualIrrigation,
  runManualClimate,
  runManualLighting,
  runManualPh,
  runManualEc,
  schedulerTaskIdInput,
  schedulerTaskLookupLoading,
  schedulerTaskListLoading,
  schedulerTaskError,
  schedulerTaskStatus,
  automationControlMode,
  allowedManualSteps,
  automationControlModeLoading,
  automationControlModeSaving,
  manualStepLoading,
  filteredRecentSchedulerTasks,
  schedulerTaskSearch,
  schedulerTaskPreset,
  schedulerTaskPresetOptions,
  schedulerTasksUpdatedAt,
  fetchRecentSchedulerTasks,
  setAutomationControlMode,
  syncControlModeFromAutomationState,
  lookupSchedulerTask,
  runManualStep,
  schedulerTaskStatusVariant,
  schedulerTaskStatusLabel,
  schedulerTaskProcessStatusVariant,
  schedulerTaskProcessStatusLabel,
  schedulerTaskTimelineStageLabel,
  schedulerTaskTimelineStepLabel,
  schedulerTaskTimelineItems,
  schedulerTaskEventLabel,
  schedulerTaskDecisionLabel,
  schedulerTaskReasonLabel,
  schedulerTaskErrorLabel,
  schedulerTaskSlaMeta,
  schedulerTaskDoneMeta,
  formatDateTime,
} = useZoneAutomationTab(props)

const zoneId = toRef(props, 'zoneId')
const showEditWizard = ref(false)
const lastAutomationSnapshot = ref<AutomationState | null>(null)
const pendingControlModeValue = ref<'auto' | 'semi' | 'manual' | null>(null)

const schedulerTaskSla = computed(() => schedulerTaskSlaMeta(schedulerTaskStatus.value))
const schedulerTaskDone = computed(() => schedulerTaskDoneMeta(schedulerTaskStatus.value))
const schedulerTaskTimeline = computed(() => schedulerTaskTimelineItems(schedulerTaskStatus.value))

const automationStateMetaLabel = computed(() => {
  const snapshot = lastAutomationSnapshot.value
  if (!snapshot?.state_meta) return null
  const source = snapshot.state_meta.source === 'cache' ? 'кэш' : 'live'
  const stale = snapshot.state_meta.is_stale ? ' (stale)' : ''
  return `Состояние: ${snapshot.state_label || snapshot.state} · источник ${source}${stale}`
})

function handleProcessStateSnapshot(snapshot: AutomationState): void {
  lastAutomationSnapshot.value = snapshot
  syncControlModeFromAutomationState(snapshot)
}

async function onApplyFromWizard(payload: ZoneAutomationWizardApplyPayload): Promise<void> {
  Object.assign(climateForm, payload.climateForm)
  Object.assign(waterForm, payload.waterForm)
  Object.assign(lightingForm, payload.lightingForm)

  const success = await applyAutomationProfile()
  if (success) {
    showEditWizard.value = false
  }
}

function onPidSaved(_config: PidConfigWithMeta): void {
  void fetchRecentSchedulerTasks()
}

async function onControlModeSelect(mode: 'auto' | 'semi' | 'manual'): Promise<void> {
  if (mode === automationControlMode.value || automationControlModeSaving.value) return
  pendingControlModeValue.value = mode
  try {
    await setAutomationControlMode(mode)
  } finally {
    pendingControlModeValue.value = null
  }
}

function onSchedulerTaskIdInputUpdate(value: string): void {
  schedulerTaskIdInput.value = value
}

function onSchedulerTaskSearchUpdate(value: string): void {
  schedulerTaskSearch.value = value
}

function onSchedulerTaskPresetUpdate(value: SchedulerTaskPreset): void {
  schedulerTaskPreset.value = value
}
</script>

<template>
  <Modal
    :open="open"
    title="Редактирование автоматизации зоны"
    size="large"
    @close="$emit('close')"
  >
    <div class="space-y-4">
      <div class="rounded-2xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] px-4 py-3 text-xs text-[color:var(--text-dim)]">
        Общий климат теплицы редактируется на уровне теплицы. Здесь остаются полив, коррекция, zone climate и свет.
      </div>

      <ZoneAutomationProfileSections
        :water-form="draftWaterForm"
        :lighting-form="draftLightingForm"
        :zone-climate-form="draftZoneClimateForm"
        :can-configure="true"
        :is-system-type-locked="isSystemTypeLocked"
      />

      <p
        v-if="stepError"
        class="text-xs text-red-500"
      >
        {{ stepError }}
      </p>
    </div>

    <template #footer>
      <Button
        type="button"
        variant="outline"
        @click="resetDraft"
      >
        Сбросить к рекомендуемым
      </Button>
      <Button
        type="button"
        :disabled="isApplying"
        @click="emitApply"
      >
        {{ isApplying ? 'Отправка...' : 'Сохранить' }}
      </Button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { reactive, watch } from 'vue'
import Modal from '@/Components/Modal.vue'
import Button from '@/Components/Button.vue'
import ZoneAutomationProfileSections from '@/Components/ZoneAutomationProfileSections.vue'
import { useAutomationDefaults } from '@/composables/useAutomationDefaults'
import {
  clamp,
  resetToRecommended as resetFormsToRecommended,
  syncSystemToTankLayout,
  validateForms,
} from '@/composables/zoneAutomationFormLogic'
import type {
  ClimateFormState,
  LightingFormState,
  WaterFormState,
  ZoneClimateFormState,
} from '@/composables/zoneAutomationTypes'

interface Props {
  open: boolean
  climateForm: ClimateFormState
  waterForm: WaterFormState
  lightingForm: LightingFormState
  zoneClimateForm?: ZoneClimateFormState
  isApplying: boolean
  isSystemTypeLocked: boolean
}

interface ZoneAutomationWizardApplyPayload {
  climateForm: ClimateFormState
  waterForm: WaterFormState
  lightingForm: LightingFormState
  zoneClimateForm: ZoneClimateFormState
}

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'apply', payload: ZoneAutomationWizardApplyPayload): void
}>()

const props = withDefaults(defineProps<Props>(), {
  zoneClimateForm: () => ({ enabled: false }),
})
const automationDefaults = useAutomationDefaults()

const stepError = reactive<{ value: string | null }>({ value: null })
const draftClimateForm = reactive<ClimateFormState>({ ...props.climateForm })
const draftWaterForm = reactive<WaterFormState>({ ...props.waterForm })
const draftLightingForm = reactive<LightingFormState>({ ...props.lightingForm })
const draftZoneClimateForm = reactive<ZoneClimateFormState>({ ...props.zoneClimateForm })

function normalizeWaterRuntimeFields(form: WaterFormState): void {
  form.diagnosticsWorkflow = form.diagnosticsWorkflow === 'startup' ||
    form.diagnosticsWorkflow === 'cycle_start' ||
    form.diagnosticsWorkflow === 'diagnostics'
    ? form.diagnosticsWorkflow
    : (form.tanksCount === 2 ? 'startup' : 'cycle_start')

  if (form.startupCleanFillTimeoutSeconds === undefined || !Number.isFinite(Number(form.startupCleanFillTimeoutSeconds))) {
    form.startupCleanFillTimeoutSeconds = automationDefaults.value.water_startup_clean_fill_timeout_sec
  }
  if (form.startupSolutionFillTimeoutSeconds === undefined || !Number.isFinite(Number(form.startupSolutionFillTimeoutSeconds))) {
    form.startupSolutionFillTimeoutSeconds = automationDefaults.value.water_startup_solution_fill_timeout_sec
  }
  if (
    form.startupPrepareRecirculationTimeoutSeconds === undefined ||
    !Number.isFinite(Number(form.startupPrepareRecirculationTimeoutSeconds))
  ) {
    form.startupPrepareRecirculationTimeoutSeconds = automationDefaults.value.water_startup_prepare_recirculation_timeout_sec
  }
  if (form.startupCleanFillRetryCycles === undefined || !Number.isFinite(Number(form.startupCleanFillRetryCycles))) {
    form.startupCleanFillRetryCycles = automationDefaults.value.water_startup_clean_fill_retry_cycles
  }
  if (form.irrigationDecisionStrategy !== 'task' && form.irrigationDecisionStrategy !== 'smart_soil_v1') {
    form.irrigationDecisionStrategy = automationDefaults.value.water_irrigation_decision_strategy
  }
  if (
    form.irrigationDecisionLookbackSeconds === undefined ||
    !Number.isFinite(Number(form.irrigationDecisionLookbackSeconds))
  ) {
    form.irrigationDecisionLookbackSeconds = automationDefaults.value.water_irrigation_decision_lookback_sec
  }
  if (form.irrigationDecisionMinSamples === undefined || !Number.isFinite(Number(form.irrigationDecisionMinSamples))) {
    form.irrigationDecisionMinSamples = automationDefaults.value.water_irrigation_decision_min_samples
  }
  if (
    form.irrigationDecisionStaleAfterSeconds === undefined ||
    !Number.isFinite(Number(form.irrigationDecisionStaleAfterSeconds))
  ) {
    form.irrigationDecisionStaleAfterSeconds = automationDefaults.value.water_irrigation_decision_stale_after_sec
  }
  if (
    form.irrigationDecisionHysteresisPct === undefined ||
    !Number.isFinite(Number(form.irrigationDecisionHysteresisPct))
  ) {
    form.irrigationDecisionHysteresisPct = automationDefaults.value.water_irrigation_decision_hysteresis_pct
  }
  if (
    form.irrigationDecisionSpreadAlertThresholdPct === undefined ||
    !Number.isFinite(Number(form.irrigationDecisionSpreadAlertThresholdPct))
  ) {
    form.irrigationDecisionSpreadAlertThresholdPct =
      automationDefaults.value.water_irrigation_decision_spread_alert_threshold_pct
  }
  if (
    form.irrigationRecoveryMaxContinueAttempts === undefined ||
    !Number.isFinite(Number(form.irrigationRecoveryMaxContinueAttempts))
  ) {
    form.irrigationRecoveryMaxContinueAttempts = automationDefaults.value.water_irrigation_recovery_max_continue_attempts
  }
  if (form.irrigationRecoveryTimeoutSeconds === undefined || !Number.isFinite(Number(form.irrigationRecoveryTimeoutSeconds))) {
    form.irrigationRecoveryTimeoutSeconds = automationDefaults.value.water_irrigation_recovery_timeout_sec
  }
  if (form.irrigationAutoReplayAfterSetup === undefined) {
    form.irrigationAutoReplayAfterSetup = automationDefaults.value.water_irrigation_auto_replay_after_setup
  }
  if (form.irrigationMaxSetupReplays === undefined || !Number.isFinite(Number(form.irrigationMaxSetupReplays))) {
    form.irrigationMaxSetupReplays = automationDefaults.value.water_irrigation_max_setup_replays
  }
  if (form.stopOnSolutionMin === undefined) {
    form.stopOnSolutionMin = automationDefaults.value.water_irrigation_stop_on_solution_min
  }
  if (form.prepareToleranceEcPct === undefined || !Number.isFinite(Number(form.prepareToleranceEcPct))) {
    form.prepareToleranceEcPct = automationDefaults.value.water_prepare_tolerance_ec_pct
  }
  if (form.prepareTolerancePhPct === undefined || !Number.isFinite(Number(form.prepareTolerancePhPct))) {
    form.prepareTolerancePhPct = automationDefaults.value.water_prepare_tolerance_ph_pct
  }
  if (form.correctionMaxEcCorrectionAttempts === undefined || !Number.isFinite(Number(form.correctionMaxEcCorrectionAttempts))) {
    form.correctionMaxEcCorrectionAttempts = automationDefaults.value.water_correction_max_ec_attempts
  }
  if (form.correctionMaxPhCorrectionAttempts === undefined || !Number.isFinite(Number(form.correctionMaxPhCorrectionAttempts))) {
    form.correctionMaxPhCorrectionAttempts = automationDefaults.value.water_correction_max_ph_attempts
  }
  if (
    form.correctionPrepareRecirculationMaxAttempts === undefined ||
    !Number.isFinite(Number(form.correctionPrepareRecirculationMaxAttempts))
  ) {
    form.correctionPrepareRecirculationMaxAttempts = automationDefaults.value.water_correction_prepare_recirculation_max_attempts
  }
  if (
    form.correctionPrepareRecirculationMaxCorrectionAttempts === undefined ||
    !Number.isFinite(Number(form.correctionPrepareRecirculationMaxCorrectionAttempts))
  ) {
    form.correctionPrepareRecirculationMaxCorrectionAttempts =
      automationDefaults.value.water_correction_prepare_recirculation_max_correction_attempts
  }
  if (form.correctionStabilizationSec === undefined || !Number.isFinite(Number(form.correctionStabilizationSec))) {
    form.correctionStabilizationSec = automationDefaults.value.water_correction_stabilization_sec
  }

  form.startupCleanFillTimeoutSeconds = clamp(Math.round(form.startupCleanFillTimeoutSeconds), 30, 86400)
  form.startupSolutionFillTimeoutSeconds = clamp(Math.round(form.startupSolutionFillTimeoutSeconds), 30, 86400)
  form.startupPrepareRecirculationTimeoutSeconds = clamp(Math.round(form.startupPrepareRecirculationTimeoutSeconds), 30, 86400)
  form.startupCleanFillRetryCycles = clamp(Math.round(form.startupCleanFillRetryCycles), 0, 20)
  form.irrigationDecisionLookbackSeconds = clamp(Math.round(form.irrigationDecisionLookbackSeconds), 60, 86400)
  form.irrigationDecisionMinSamples = clamp(Math.round(form.irrigationDecisionMinSamples), 1, 100)
  form.irrigationDecisionStaleAfterSeconds = clamp(Math.round(form.irrigationDecisionStaleAfterSeconds), 30, 86400)
  form.irrigationDecisionHysteresisPct = clamp(form.irrigationDecisionHysteresisPct, 0, 100)
  form.irrigationDecisionSpreadAlertThresholdPct = clamp(form.irrigationDecisionSpreadAlertThresholdPct, 0, 100)
  form.irrigationRecoveryMaxContinueAttempts = clamp(Math.round(form.irrigationRecoveryMaxContinueAttempts), 1, 30)
  form.irrigationRecoveryTimeoutSeconds = clamp(Math.round(form.irrigationRecoveryTimeoutSeconds), 30, 86400)
  form.irrigationMaxSetupReplays = clamp(Math.round(form.irrigationMaxSetupReplays), 0, 10)
  form.prepareToleranceEcPct = clamp(form.prepareToleranceEcPct, 0.1, 100)
  form.prepareTolerancePhPct = clamp(form.prepareTolerancePhPct, 0.1, 100)
  form.correctionMaxEcCorrectionAttempts = clamp(Math.round(form.correctionMaxEcCorrectionAttempts), 1, 50)
  form.correctionMaxPhCorrectionAttempts = clamp(Math.round(form.correctionMaxPhCorrectionAttempts), 1, 50)
  form.correctionPrepareRecirculationMaxAttempts = clamp(Math.round(form.correctionPrepareRecirculationMaxAttempts), 1, 50)
  form.correctionPrepareRecirculationMaxCorrectionAttempts = clamp(
    Math.round(form.correctionPrepareRecirculationMaxCorrectionAttempts),
    1,
    500,
  )
  form.correctionStabilizationSec = clamp(Math.round(form.correctionStabilizationSec), 0, 3600)
}

function syncWorkflowByTopology(form: WaterFormState): void {
  if (form.tanksCount === 2 && form.diagnosticsWorkflow === 'cycle_start') {
    form.diagnosticsWorkflow = 'startup'
  } else if (form.tanksCount === 3 && form.diagnosticsWorkflow === 'startup') {
    form.diagnosticsWorkflow = 'cycle_start'
  }
}

function syncDraftFromProps(): void {
  Object.assign(draftClimateForm, props.climateForm)
  Object.assign(draftWaterForm, props.waterForm)
  Object.assign(draftLightingForm, props.lightingForm)
  Object.assign(draftZoneClimateForm, props.zoneClimateForm)
  normalizeWaterRuntimeFields(draftWaterForm)
  syncWorkflowByTopology(draftWaterForm)
}

function resetDraft(): void {
  resetFormsToRecommended({
    climateForm: draftClimateForm,
    waterForm: draftWaterForm,
    lightingForm: draftLightingForm,
  }, automationDefaults.value)
  draftZoneClimateForm.enabled = false
  normalizeWaterRuntimeFields(draftWaterForm)
  syncWorkflowByTopology(draftWaterForm)
  stepError.value = null
}

function emitApply(): void {
  normalizeWaterRuntimeFields(draftWaterForm)
  syncWorkflowByTopology(draftWaterForm)

  const validationError = validateForms({ climateForm: draftClimateForm, waterForm: draftWaterForm })
  if (validationError) {
    stepError.value = validationError
    return
  }

  const waterFormForApply: WaterFormState = { ...draftWaterForm }
  if (waterFormForApply.systemType === 'drip') {
    waterFormForApply.tanksCount = 2
    waterFormForApply.enableDrainControl = false
  } else {
    waterFormForApply.tanksCount = waterFormForApply.tanksCount === 3 ? 3 : 2
    if (waterFormForApply.tanksCount === 2) {
      waterFormForApply.enableDrainControl = false
    }
  }

  emit('apply', {
    climateForm: { ...draftClimateForm },
    waterForm: waterFormForApply,
    lightingForm: { ...draftLightingForm },
    zoneClimateForm: { ...draftZoneClimateForm },
  })
}

watch(
  () => draftWaterForm.systemType,
  (systemType) => {
    syncSystemToTankLayout(draftWaterForm, systemType)
    normalizeWaterRuntimeFields(draftWaterForm)
    syncWorkflowByTopology(draftWaterForm)
  },
  { immediate: true },
)

watch(
  () => draftWaterForm.tanksCount,
  (tanksCount) => {
    const normalizedTanksCount = Math.round(Number(tanksCount)) === 3 ? 3 : 2

    if (draftWaterForm.systemType === 'drip') {
      if (draftWaterForm.tanksCount !== 2) {
        draftWaterForm.tanksCount = 2
      }
      draftWaterForm.enableDrainControl = false
      syncWorkflowByTopology(draftWaterForm)
      return
    }

    if (draftWaterForm.tanksCount !== normalizedTanksCount) {
      draftWaterForm.tanksCount = normalizedTanksCount
    }
    if (normalizedTanksCount === 2) {
      draftWaterForm.enableDrainControl = false
    }
    syncWorkflowByTopology(draftWaterForm)
  },
)

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) {
      syncDraftFromProps()
      stepError.value = null
    }
  },
)
</script>

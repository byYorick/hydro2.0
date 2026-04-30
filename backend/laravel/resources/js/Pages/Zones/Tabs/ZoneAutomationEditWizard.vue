<template>
  <Modal
    :open="open"
    title="Редактирование автоматизации зоны"
    size="xlarge"
    @close="$emit('close')"
  >
    <div class="space-y-4">
      <div class="rounded-2xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] px-4 py-3 text-xs text-[color:var(--text-dim)]">
        <p class="m-0">
          Тот же интерфейс, что шаг
          <strong class="text-[color:var(--text-primary)]">«Автоматика»</strong>
          в мастере запуска цикла: контур, привязки нод, полив, коррекция, климат зоны, свет.
        </p>
        <p class="mt-2 mb-0">
          Общий климат теплицы редактируется на уровне теплицы.
        </p>
      </div>

      <div
        v-if="zoneId > 0"
        class="max-h-[min(72vh,880px)] overflow-y-auto pr-0.5"
      >
        <AutomationStep
          :key="automationStepKey"
          :zone-id="zoneId"
          :current-recipe-phase="currentRecipePhase ?? null"
          :recipe-summary="recipeSummary"
          :emit-profile-after-hydrate="true"
          @update:profile="onAutomationProfileSync"
        />
      </div>
      <p
        v-else
        class="text-xs text-red-500"
      >
        Не задан идентификатор зоны.
      </p>

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
        @click="reloadAutomationEditor"
      >
        Перечитать с сервера
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
import { reactive, ref, watch } from 'vue'
import Modal from '@/Components/Modal.vue'
import Button from '@/Components/Button.vue'
import AutomationStep from '@/Components/Launch/AutomationStep.vue'
import { useAutomationDefaults } from '@/composables/useAutomationDefaults'
import {
  clamp,
  syncSystemToTankLayout,
  validateForms,
} from '@/composables/zoneAutomationFormLogic'
import type {
  ClimateFormState,
  LightingFormState,
  WaterFormState,
  ZoneClimateFormState,
} from '@/composables/zoneAutomationTypes'
import type { AutomationProfile } from '@/schemas/automationProfile'

interface RecipeSummaryLite {
  name?: string | null
  revisionLabel?: string | null
  systemType?: string | null
  targetPh?: number | null
  targetEc?: number | null
}

interface Props {
  open: boolean
  zoneId: number
  climateForm: ClimateFormState
  waterForm: WaterFormState
  lightingForm: LightingFormState
  zoneClimateForm?: ZoneClimateFormState
  isApplying: boolean
  currentRecipePhase?: unknown | null
  recipeSummary?: RecipeSummaryLite | null
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
  recipeSummary: null,
})
const automationDefaults = useAutomationDefaults()

const stepError = reactive<{ value: string | null }>({ value: null })
const draftClimateForm = reactive<ClimateFormState>({ ...props.climateForm })
const draftWaterForm = reactive<WaterFormState>({ ...props.waterForm })
const draftLightingForm = reactive<LightingFormState>({ ...props.lightingForm })
const draftZoneClimateForm = reactive<ZoneClimateFormState>({ ...props.zoneClimateForm })
const automationStepKey = ref(0)

function onAutomationProfileSync(profile: AutomationProfile): void {
  Object.assign(draftWaterForm, profile.waterForm as WaterFormState)
  Object.assign(draftLightingForm, profile.lightingForm as LightingFormState)
  Object.assign(draftZoneClimateForm, profile.zoneClimateForm as ZoneClimateFormState)
  stepError.value = null
}

function reloadAutomationEditor(): void {
  stepError.value = null
  automationStepKey.value += 1
}

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
  if (form.cleanFillMinCheckDelayMs === undefined || !Number.isFinite(Number(form.cleanFillMinCheckDelayMs))) {
    form.cleanFillMinCheckDelayMs = automationDefaults.value.water_clean_fill_min_check_delay_ms
  }
  if (
    form.solutionFillCleanMinCheckDelayMs === undefined ||
    !Number.isFinite(Number(form.solutionFillCleanMinCheckDelayMs))
  ) {
    form.solutionFillCleanMinCheckDelayMs = automationDefaults.value.water_solution_fill_clean_min_check_delay_ms
  }
  if (
    form.solutionFillSolutionMinCheckDelayMs === undefined ||
    !Number.isFinite(Number(form.solutionFillSolutionMinCheckDelayMs))
  ) {
    form.solutionFillSolutionMinCheckDelayMs = automationDefaults.value.water_solution_fill_solution_min_check_delay_ms
  }
  if (form.recirculationStopOnSolutionMin === undefined) {
    form.recirculationStopOnSolutionMin = automationDefaults.value.water_recirculation_stop_on_solution_min
  }
  if (form.estopDebounceMs === undefined || !Number.isFinite(Number(form.estopDebounceMs))) {
    form.estopDebounceMs = automationDefaults.value.water_estop_debounce_ms
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
  form.cleanFillMinCheckDelayMs = clamp(Math.round(form.cleanFillMinCheckDelayMs), 0, 3600000)
  form.solutionFillCleanMinCheckDelayMs = clamp(Math.round(form.solutionFillCleanMinCheckDelayMs), 0, 3600000)
  form.solutionFillSolutionMinCheckDelayMs = clamp(Math.round(form.solutionFillSolutionMinCheckDelayMs), 0, 3600000)
  form.estopDebounceMs = clamp(Math.round(form.estopDebounceMs), 20, 5000)
  form.irrigationDecisionLookbackSeconds = clamp(Math.round(form.irrigationDecisionLookbackSeconds), 60, 86400)
  form.irrigationDecisionMinSamples = clamp(Math.round(form.irrigationDecisionMinSamples), 1, 100)
  form.irrigationDecisionStaleAfterSeconds = clamp(Math.round(form.irrigationDecisionStaleAfterSeconds), 30, 86400)
  form.irrigationDecisionHysteresisPct = clamp(form.irrigationDecisionHysteresisPct, 0, 100)
  form.irrigationDecisionSpreadAlertThresholdPct = clamp(form.irrigationDecisionSpreadAlertThresholdPct, 0, 100)
  form.irrigationRecoveryMaxContinueAttempts = clamp(Math.round(form.irrigationRecoveryMaxContinueAttempts), 1, 30)
  form.irrigationRecoveryTimeoutSeconds = clamp(Math.round(form.irrigationRecoveryTimeoutSeconds), 30, 86400)
  form.irrigationMaxSetupReplays = clamp(Math.round(form.irrigationMaxSetupReplays), 0, 10)
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
      automationStepKey.value += 1
    }
  },
)
</script>

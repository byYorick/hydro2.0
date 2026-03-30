import { computed, reactive, ref, watch } from 'vue'
import { usePage } from '@inertiajs/vue3'
import {
  createDefaultClimateForm,
  createDefaultLightingForm,
  createDefaultWaterForm,
  FALLBACK_AUTOMATION_DEFAULTS,
  useAutomationDefaults,
} from '@/composables/useAutomationDefaults'
import { logger } from '@/utils/logger'
import type { ZoneTargets as ZoneTargetsType } from '@/types'
import {
  applyAutomationFromRecipe,
  clamp,
  resetToRecommended as resetFormsToRecommended,
  syncSystemToTankLayout,
  type ClimateFormState,
  type IrrigationSystem,
  type LightingFormState,
  type WaterFormState,
  type ZoneClimateFormState,
} from '@/composables/zoneAutomationFormLogic'
import {
  toFiniteNumber,
  normalizeAutomationLogicMode,
  parseIsoDate,
  type AutomationLogicMode,
} from '@/composables/zoneAutomationUtils'
import type { PredictionTargets, ZoneAutomationTabProps } from '@/composables/zoneAutomationTypes'
import type { AutomationDefaultsSettings } from '@/types/SystemSettings'
import type { ToastVariant } from '@/composables/useToast'

// ─── Private sanitize helpers ─────────────────────────────────────────────────

function toBoolean(value: unknown, fallback: boolean): boolean {
  if (typeof value === 'boolean') return value
  if (value === 1 || value === '1' || value === 'true') return true
  if (value === 0 || value === '0' || value === 'false') return false
  return fallback
}

function toNumber(value: unknown, fallback: number): number {
  const parsed = toFiniteNumber(value)
  return parsed === null ? fallback : parsed
}

function toRoundedNumber(value: unknown, fallback: number): number {
  return Math.round(toNumber(value, fallback))
}

function toTimeHHmm(value: unknown, fallback: string): string {
  if (typeof value !== 'string') return fallback
  const match = value.trim().match(/^(\d{1,2}):(\d{2})/)
  if (!match) return fallback
  const hours = Number(match[1])
  const minutes = Number(match[2])
  if (
    !Number.isInteger(hours) ||
    !Number.isInteger(minutes) ||
    hours < 0 ||
    hours > 23 ||
    minutes < 0 ||
    minutes > 59
  ) {
    return fallback
  }
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`
}

function toIrrigationSystem(value: unknown, fallback: IrrigationSystem): IrrigationSystem {
  if (value === 'drip' || value === 'substrate_trays' || value === 'nft') {
    return value
  }
  return fallback
}

function sanitizeClimateForm(raw: Partial<ClimateFormState> | undefined, fallback: ClimateFormState): ClimateFormState {
  return {
    enabled: toBoolean(raw?.enabled, fallback.enabled),
    dayTemp: clamp(toNumber(raw?.dayTemp, fallback.dayTemp), 10, 35),
    nightTemp: clamp(toNumber(raw?.nightTemp, fallback.nightTemp), 10, 35),
    dayHumidity: clamp(toNumber(raw?.dayHumidity, fallback.dayHumidity), 30, 90),
    nightHumidity: clamp(toNumber(raw?.nightHumidity, fallback.nightHumidity), 30, 90),
    intervalMinutes: clamp(toRoundedNumber(raw?.intervalMinutes, fallback.intervalMinutes), 1, 1440),
    dayStart: toTimeHHmm(raw?.dayStart, fallback.dayStart),
    nightStart: toTimeHHmm(raw?.nightStart, fallback.nightStart),
    ventMinPercent: clamp(toRoundedNumber(raw?.ventMinPercent, fallback.ventMinPercent), 0, 100),
    ventMaxPercent: clamp(toRoundedNumber(raw?.ventMaxPercent, fallback.ventMaxPercent), 0, 100),
    useExternalTelemetry: toBoolean(raw?.useExternalTelemetry, fallback.useExternalTelemetry),
    outsideTempMin: clamp(toNumber(raw?.outsideTempMin, fallback.outsideTempMin), -30, 45),
    outsideTempMax: clamp(toNumber(raw?.outsideTempMax, fallback.outsideTempMax), -30, 45),
    outsideHumidityMax: clamp(toRoundedNumber(raw?.outsideHumidityMax, fallback.outsideHumidityMax), 20, 100),
    manualOverrideEnabled: toBoolean(raw?.manualOverrideEnabled, fallback.manualOverrideEnabled),
    overrideMinutes: clamp(toRoundedNumber(raw?.overrideMinutes, fallback.overrideMinutes), 5, 120),
  }
}

function sanitizeWaterForm(
  raw: Partial<WaterFormState> | undefined,
  fallback: WaterFormState,
  defaults: AutomationDefaultsSettings = FALLBACK_AUTOMATION_DEFAULTS,
): WaterFormState {
  const legacyRaw = raw as (Partial<WaterFormState> & { cycleStartWorkflowEnabled?: unknown }) | undefined
  const legacyFallback = fallback as WaterFormState & { cycleStartWorkflowEnabled?: boolean }
  const systemType = toIrrigationSystem(raw?.systemType, fallback.systemType)
  const tanksRaw = toRoundedNumber(raw?.tanksCount, fallback.tanksCount)
  const tanksCount = tanksRaw === 3 ? 3 : 2
  const fallbackWorkflow = fallback.diagnosticsWorkflow
  const rawWorkflow = typeof raw?.diagnosticsWorkflow === 'string'
    ? raw.diagnosticsWorkflow
    : typeof fallbackWorkflow === 'string'
      ? fallbackWorkflow
      : null
  const diagnosticsWorkflow =
    rawWorkflow === 'startup' || rawWorkflow === 'cycle_start' || rawWorkflow === 'diagnostics'
      ? rawWorkflow
      : toBoolean(legacyRaw?.cycleStartWorkflowEnabled, legacyFallback.cycleStartWorkflowEnabled ?? false)
        ? (tanksCount === 2 ? 'startup' : 'cycle_start')
        : 'diagnostics'
  const fallbackStepCount = (value: unknown, defaultValue: number): number => {
    if (typeof value === 'number' && Number.isFinite(value)) {
      return value
    }
    return defaultValue
  }
  const sanitizeStepCount = (value: unknown, fallbackValue: unknown, defaultValue: number): number => {
    return clamp(
      toRoundedNumber(value, fallbackStepCount(fallbackValue, defaultValue)),
      1,
      12
    )
  }

  const sanitized: WaterFormState = {
    systemType,
    tanksCount,
    cleanTankFillL: clamp(toRoundedNumber(raw?.cleanTankFillL, fallback.cleanTankFillL), 10, 5000),
    nutrientTankTargetL: clamp(toRoundedNumber(raw?.nutrientTankTargetL, fallback.nutrientTankTargetL), 10, 5000),
    irrigationBatchL: clamp(toRoundedNumber(raw?.irrigationBatchL, fallback.irrigationBatchL), 1, 500),
    intervalMinutes: clamp(toRoundedNumber(raw?.intervalMinutes, fallback.intervalMinutes), 5, 1440),
    durationSeconds: clamp(toRoundedNumber(raw?.durationSeconds, fallback.durationSeconds), 1, 3600),
    fillTemperatureC: clamp(toNumber(raw?.fillTemperatureC, fallback.fillTemperatureC), 5, 35),
    fillWindowStart: toTimeHHmm(raw?.fillWindowStart, fallback.fillWindowStart),
    fillWindowEnd: toTimeHHmm(raw?.fillWindowEnd, fallback.fillWindowEnd),
    targetPh: clamp(toNumber(raw?.targetPh, fallback.targetPh), 4, 9),
    targetEc: clamp(toNumber(raw?.targetEc, fallback.targetEc), 0.1, 10),
    phPct: clamp(toNumber(raw?.phPct, fallback.phPct), 1, 50),
    ecPct: clamp(toNumber(raw?.ecPct, fallback.ecPct), 1, 50),
    valveSwitching: toBoolean(raw?.valveSwitching, fallback.valveSwitching),
    correctionDuringIrrigation: toBoolean(raw?.correctionDuringIrrigation, fallback.correctionDuringIrrigation),
    enableDrainControl: toBoolean(raw?.enableDrainControl, fallback.enableDrainControl),
    drainTargetPercent: clamp(toRoundedNumber(raw?.drainTargetPercent, fallback.drainTargetPercent), 0, 100),
    diagnosticsEnabled: toBoolean(raw?.diagnosticsEnabled, fallback.diagnosticsEnabled),
    diagnosticsIntervalMinutes: clamp(
      toRoundedNumber(raw?.diagnosticsIntervalMinutes, fallback.diagnosticsIntervalMinutes),
      1,
      1440
    ),
    diagnosticsWorkflow,
    cleanTankFullThreshold: clamp(toNumber(raw?.cleanTankFullThreshold, fallback.cleanTankFullThreshold), 0.05, 1),
    refillDurationSeconds: clamp(toRoundedNumber(raw?.refillDurationSeconds, fallback.refillDurationSeconds), 1, 3600),
    refillTimeoutSeconds: clamp(toRoundedNumber(raw?.refillTimeoutSeconds, fallback.refillTimeoutSeconds), 30, 86400),
    startupCleanFillTimeoutSeconds: clamp(
      toRoundedNumber(
        raw?.startupCleanFillTimeoutSeconds,
        typeof fallback.startupCleanFillTimeoutSeconds === 'number'
          ? fallback.startupCleanFillTimeoutSeconds
          : defaults.water_startup_clean_fill_timeout_sec
      ),
      30,
      86400
    ),
    startupSolutionFillTimeoutSeconds: clamp(
      toRoundedNumber(
        raw?.startupSolutionFillTimeoutSeconds,
        typeof fallback.startupSolutionFillTimeoutSeconds === 'number'
          ? fallback.startupSolutionFillTimeoutSeconds
          : defaults.water_startup_solution_fill_timeout_sec
      ),
      30,
      86400
    ),
    startupPrepareRecirculationTimeoutSeconds: clamp(
      toRoundedNumber(
        raw?.startupPrepareRecirculationTimeoutSeconds,
        typeof fallback.startupPrepareRecirculationTimeoutSeconds === 'number'
          ? fallback.startupPrepareRecirculationTimeoutSeconds
          : defaults.water_startup_prepare_recirculation_timeout_sec
      ),
      30,
      86400
    ),
    startupCleanFillRetryCycles: clamp(
      toRoundedNumber(
        raw?.startupCleanFillRetryCycles,
        typeof fallback.startupCleanFillRetryCycles === 'number'
          ? fallback.startupCleanFillRetryCycles
          : defaults.water_startup_clean_fill_retry_cycles
      ),
      0,
      20
    ),
    irrigationDecisionStrategy:
      raw?.irrigationDecisionStrategy === 'task' || raw?.irrigationDecisionStrategy === 'smart_soil_v1'
        ? raw.irrigationDecisionStrategy
        : fallback.irrigationDecisionStrategy === 'task' || fallback.irrigationDecisionStrategy === 'smart_soil_v1'
          ? fallback.irrigationDecisionStrategy
          : defaults.water_irrigation_decision_strategy,
    irrigationDecisionLookbackSeconds: clamp(
      toRoundedNumber(
        raw?.irrigationDecisionLookbackSeconds,
        typeof fallback.irrigationDecisionLookbackSeconds === 'number'
          ? fallback.irrigationDecisionLookbackSeconds
          : defaults.water_irrigation_decision_lookback_sec
      ),
      60,
      86400
    ),
    irrigationDecisionMinSamples: clamp(
      toRoundedNumber(
        raw?.irrigationDecisionMinSamples,
        typeof fallback.irrigationDecisionMinSamples === 'number'
          ? fallback.irrigationDecisionMinSamples
          : defaults.water_irrigation_decision_min_samples
      ),
      1,
      100
    ),
    irrigationDecisionStaleAfterSeconds: clamp(
      toRoundedNumber(
        raw?.irrigationDecisionStaleAfterSeconds,
        typeof fallback.irrigationDecisionStaleAfterSeconds === 'number'
          ? fallback.irrigationDecisionStaleAfterSeconds
          : defaults.water_irrigation_decision_stale_after_sec
      ),
      30,
      86400
    ),
    irrigationDecisionHysteresisPct: clamp(
      toNumber(
        raw?.irrigationDecisionHysteresisPct,
        typeof fallback.irrigationDecisionHysteresisPct === 'number'
          ? fallback.irrigationDecisionHysteresisPct
          : defaults.water_irrigation_decision_hysteresis_pct
      ),
      0,
      100
    ),
    irrigationDecisionSpreadAlertThresholdPct: clamp(
      toNumber(
        raw?.irrigationDecisionSpreadAlertThresholdPct,
        typeof fallback.irrigationDecisionSpreadAlertThresholdPct === 'number'
          ? fallback.irrigationDecisionSpreadAlertThresholdPct
          : defaults.water_irrigation_decision_spread_alert_threshold_pct
      ),
      0,
      100
    ),
    irrigationRecoveryMaxContinueAttempts: clamp(
      toRoundedNumber(
        raw?.irrigationRecoveryMaxContinueAttempts,
        typeof fallback.irrigationRecoveryMaxContinueAttempts === 'number'
          ? fallback.irrigationRecoveryMaxContinueAttempts
          : defaults.water_irrigation_recovery_max_continue_attempts
      ),
      1,
      30
    ),
    irrigationRecoveryTimeoutSeconds: clamp(
      toRoundedNumber(
        raw?.irrigationRecoveryTimeoutSeconds,
        typeof fallback.irrigationRecoveryTimeoutSeconds === 'number'
          ? fallback.irrigationRecoveryTimeoutSeconds
          : defaults.water_irrigation_recovery_timeout_sec
      ),
      30,
      86400
    ),
    irrigationAutoReplayAfterSetup: toBoolean(
      raw?.irrigationAutoReplayAfterSetup,
      typeof fallback.irrigationAutoReplayAfterSetup === 'boolean'
        ? fallback.irrigationAutoReplayAfterSetup
        : defaults.water_irrigation_auto_replay_after_setup
    ),
    irrigationMaxSetupReplays: clamp(
      toRoundedNumber(
        raw?.irrigationMaxSetupReplays,
        typeof fallback.irrigationMaxSetupReplays === 'number'
          ? fallback.irrigationMaxSetupReplays
          : defaults.water_irrigation_max_setup_replays
      ),
      0,
      10
    ),
    stopOnSolutionMin: toBoolean(
      raw?.stopOnSolutionMin,
      typeof fallback.stopOnSolutionMin === 'boolean'
        ? fallback.stopOnSolutionMin
        : defaults.water_irrigation_stop_on_solution_min
    ),
    prepareToleranceEcPct: clamp(
      toNumber(
        raw?.prepareToleranceEcPct,
        typeof fallback.prepareToleranceEcPct === 'number'
          ? fallback.prepareToleranceEcPct
          : defaults.water_prepare_tolerance_ec_pct
      ),
      0.1,
      100
    ),
    prepareTolerancePhPct: clamp(
      toNumber(
        raw?.prepareTolerancePhPct,
        typeof fallback.prepareTolerancePhPct === 'number'
          ? fallback.prepareTolerancePhPct
          : defaults.water_prepare_tolerance_ph_pct
      ),
      0.1,
      100
    ),
    correctionMaxEcCorrectionAttempts: clamp(
      toRoundedNumber(
        raw?.correctionMaxEcCorrectionAttempts,
        typeof fallback.correctionMaxEcCorrectionAttempts === 'number'
          ? fallback.correctionMaxEcCorrectionAttempts
          : defaults.water_correction_max_ec_attempts
      ),
      1,
      50
    ),
    correctionMaxPhCorrectionAttempts: clamp(
      toRoundedNumber(
        raw?.correctionMaxPhCorrectionAttempts,
        typeof fallback.correctionMaxPhCorrectionAttempts === 'number'
          ? fallback.correctionMaxPhCorrectionAttempts
          : defaults.water_correction_max_ph_attempts
      ),
      1,
      50
    ),
    correctionPrepareRecirculationMaxAttempts: clamp(
      toRoundedNumber(
        raw?.correctionPrepareRecirculationMaxAttempts,
        typeof fallback.correctionPrepareRecirculationMaxAttempts === 'number'
          ? fallback.correctionPrepareRecirculationMaxAttempts
          : defaults.water_correction_prepare_recirculation_max_attempts
      ),
      1,
      50
    ),
    correctionPrepareRecirculationMaxCorrectionAttempts: clamp(
      toRoundedNumber(
        raw?.correctionPrepareRecirculationMaxCorrectionAttempts,
        typeof fallback.correctionPrepareRecirculationMaxCorrectionAttempts === 'number'
          ? fallback.correctionPrepareRecirculationMaxCorrectionAttempts
          : defaults.water_correction_prepare_recirculation_max_correction_attempts
      ),
      1,
      500
    ),
    correctionStabilizationSec: clamp(
      toRoundedNumber(
        raw?.correctionStabilizationSec,
        typeof fallback.correctionStabilizationSec === 'number'
          ? fallback.correctionStabilizationSec
          : defaults.water_correction_stabilization_sec
      ),
      0,
      3600
    ),
    twoTankCleanFillStartSteps: sanitizeStepCount(
      raw?.twoTankCleanFillStartSteps,
      fallback.twoTankCleanFillStartSteps,
      defaults.water_two_tank_clean_fill_start_steps
    ),
    twoTankCleanFillStopSteps: sanitizeStepCount(
      raw?.twoTankCleanFillStopSteps,
      fallback.twoTankCleanFillStopSteps,
      defaults.water_two_tank_clean_fill_stop_steps
    ),
    twoTankSolutionFillStartSteps: sanitizeStepCount(
      raw?.twoTankSolutionFillStartSteps,
      fallback.twoTankSolutionFillStartSteps,
      defaults.water_two_tank_solution_fill_start_steps
    ),
    twoTankSolutionFillStopSteps: sanitizeStepCount(
      raw?.twoTankSolutionFillStopSteps,
      fallback.twoTankSolutionFillStopSteps,
      defaults.water_two_tank_solution_fill_stop_steps
    ),
    twoTankPrepareRecirculationStartSteps: sanitizeStepCount(
      raw?.twoTankPrepareRecirculationStartSteps,
      fallback.twoTankPrepareRecirculationStartSteps,
      defaults.water_two_tank_prepare_recirculation_start_steps
    ),
    twoTankPrepareRecirculationStopSteps: sanitizeStepCount(
      raw?.twoTankPrepareRecirculationStopSteps,
      fallback.twoTankPrepareRecirculationStopSteps,
      defaults.water_two_tank_prepare_recirculation_stop_steps
    ),
    twoTankIrrigationRecoveryStartSteps: sanitizeStepCount(
      raw?.twoTankIrrigationRecoveryStartSteps,
      fallback.twoTankIrrigationRecoveryStartSteps,
      defaults.water_two_tank_irrigation_recovery_start_steps
    ),
    twoTankIrrigationRecoveryStopSteps: sanitizeStepCount(
      raw?.twoTankIrrigationRecoveryStopSteps,
      fallback.twoTankIrrigationRecoveryStopSteps,
      defaults.water_two_tank_irrigation_recovery_stop_steps
    ),
    refillRequiredNodeTypes:
      typeof raw?.refillRequiredNodeTypes === 'string' && raw.refillRequiredNodeTypes.trim() !== ''
        ? raw.refillRequiredNodeTypes.trim()
        : fallback.refillRequiredNodeTypes,
    refillPreferredChannel:
      typeof raw?.refillPreferredChannel === 'string'
        ? raw.refillPreferredChannel.trim()
        : fallback.refillPreferredChannel,
    solutionChangeEnabled: toBoolean(raw?.solutionChangeEnabled, fallback.solutionChangeEnabled),
    solutionChangeIntervalMinutes: clamp(
      toRoundedNumber(raw?.solutionChangeIntervalMinutes, fallback.solutionChangeIntervalMinutes),
      1,
      1440
    ),
    solutionChangeDurationSeconds: clamp(
      toRoundedNumber(raw?.solutionChangeDurationSeconds, fallback.solutionChangeDurationSeconds),
      1,
      86400
    ),
    manualIrrigationSeconds: clamp(
      toRoundedNumber(raw?.manualIrrigationSeconds, fallback.manualIrrigationSeconds),
      1,
      3600
    ),
  }

  syncSystemToTankLayout(sanitized, sanitized.systemType)
  sanitized.tanksCount = sanitized.systemType === 'drip' ? 2 : tanksCount
  if (sanitized.tanksCount === 2) {
    sanitized.enableDrainControl = false
  }
  return sanitized
}

function sanitizeLightingForm(
  raw: Partial<LightingFormState> | undefined,
  fallback: LightingFormState
): LightingFormState {
  return {
    enabled: toBoolean(raw?.enabled, fallback.enabled),
    luxDay: clamp(toRoundedNumber(raw?.luxDay, fallback.luxDay), 0, 120000),
    luxNight: clamp(toRoundedNumber(raw?.luxNight, fallback.luxNight), 0, 120000),
    hoursOn: clamp(toNumber(raw?.hoursOn, fallback.hoursOn), 0, 24),
    intervalMinutes: clamp(toRoundedNumber(raw?.intervalMinutes, fallback.intervalMinutes), 1, 1440),
    scheduleStart: toTimeHHmm(raw?.scheduleStart, fallback.scheduleStart),
    scheduleEnd: toTimeHHmm(raw?.scheduleEnd, fallback.scheduleEnd),
    manualIntensity: clamp(toRoundedNumber(raw?.manualIntensity, fallback.manualIntensity), 0, 100),
    manualDurationHours: clamp(toNumber(raw?.manualDurationHours, fallback.manualDurationHours), 0.5, 24),
  }
}

// ─── Composable ───────────────────────────────────────────────────────────────

export interface ZoneAutomationStateDeps {
  sendZoneCommand: (zoneId: number, type: string, params?: Record<string, unknown>) => Promise<unknown>
  showToast: (message: string, variant?: ToastVariant) => void
}

export function useZoneAutomationState(props: ZoneAutomationTabProps, deps: ZoneAutomationStateDeps) {
  const page = usePage<{ auth?: { user?: { role?: string } } }>()
  const automationDefaults = useAutomationDefaults()
  const { sendZoneCommand, showToast } = deps

  // ─── Role / permissions ────────────────────────────────────────────────────
  const role = computed(() => String(page.props.auth?.user?.role ?? 'viewer').trim().toLowerCase())
  const canConfigureAutomation = computed(() => role.value === 'agronomist' || role.value === 'admin')
  const canOperateAutomation = computed(
    () =>
      role.value === 'agronomist' ||
      role.value === 'admin' ||
      role.value === 'operator' ||
      role.value === 'engineer'
  )
  const isSystemTypeLocked = computed(() => {
    const status = String(props.activeGrowCycle?.status ?? '').toUpperCase()
    return status === 'RUNNING' || status === 'PAUSED' || status === 'PLANNED'
  })

  // ─── Forms ─────────────────────────────────────────────────────────────────
  const climateForm = reactive<ClimateFormState>(createDefaultClimateForm(automationDefaults.value))
  const waterForm = reactive<WaterFormState>(createDefaultWaterForm(automationDefaults.value))
  const lightingForm = reactive<LightingFormState>(createDefaultLightingForm(automationDefaults.value))
  const zoneClimateForm = reactive<ZoneClimateFormState>({ enabled: false })

  const quickActions = reactive({
    irrigation: false,
    climate: false,
    lighting: false,
    ph: false,
    ec: false,
  })

  // ─── Flags / refs ──────────────────────────────────────────────────────────
  const isApplyingProfile = ref(false)
  const isHydratingProfile = ref(false)
  const isSyncingAutomationLogicProfile = ref(false)
  const lastAppliedAt = ref<string | null>(null)
  const automationLogicMode = ref<AutomationLogicMode>('working')
  const lastAutomationLogicSyncAt = ref<string | null>(null)
  const pendingTargetsSyncForZoneChange = ref(false)

  // ─── Derived ───────────────────────────────────────────────────────────────
  const predictionTargets = computed<PredictionTargets>(() => {
    const targets = props.targets
    if (!targets || typeof targets !== 'object') return {}

    if ('ph_min' in targets || 'ec_min' in targets || 'temp_min' in targets || 'humidity_min' in targets) {
      const legacy = targets as ZoneTargetsType
      return {
        ph: { min: legacy.ph_min, max: legacy.ph_max },
        ec: { min: legacy.ec_min, max: legacy.ec_max },
        temp_air: { min: legacy.temp_min, max: legacy.temp_max },
        humidity_air: { min: legacy.humidity_min, max: legacy.humidity_max },
      }
    }

    return targets as PredictionTargets
  })

  const telemetryLabel = computed(() => {
    const temperature = toFiniteNumber(props.telemetry?.temperature)
    const humidity = toFiniteNumber(props.telemetry?.humidity)

    if (temperature === null || humidity === null) {
      return 'нет данных'
    }

    return `${temperature.toFixed(1)}°C / ${humidity.toFixed(0)}%`
  })

  const waterTopologyLabel = computed(() => {
    if (waterForm.tanksCount === 2) {
      return 'Чистая вода + раствор'
    }

    return 'Чистая вода + раствор + дренаж'
  })

  const profileStorageKey = computed(() => {
    return props.zoneId ? `zone:${props.zoneId}:automation-profile:v3` : null
  })

  // ─── Storage ───────────────────────────────────────────────────────────────
  function saveProfileToStorage(): void {
    if (isHydratingProfile.value) return
    if (typeof window === 'undefined' || !profileStorageKey.value) return

    const payload = {
      climate: { ...climateForm },
      water: { ...waterForm },
      lighting: { ...lightingForm },
      zoneClimate: { ...zoneClimateForm },
      automationLogicMode: automationLogicMode.value,
      lastAutomationLogicSyncAt: lastAutomationLogicSyncAt.value,
      lastAppliedAt: lastAppliedAt.value,
    }

    try {
      window.localStorage.setItem(profileStorageKey.value, JSON.stringify(payload))
    } catch (error) {
      logger.warn('[ZoneAutomationTab] Failed to save automation profile to storage', { error })
    }
  }

  function loadProfileFromStorage(): void {
    if (typeof window === 'undefined' || !profileStorageKey.value) return

    const raw = window.localStorage.getItem(profileStorageKey.value)
    if (!raw) return

    try {
      const parsed = JSON.parse(raw) as {
        climate?: Partial<ClimateFormState>
        water?: Partial<WaterFormState>
        lighting?: Partial<LightingFormState>
        zoneClimate?: Partial<ZoneClimateFormState>
        automationLogicMode?: string
        lastAutomationLogicSyncAt?: string | null
        lastAppliedAt?: string | null
      }

      if (parsed.climate) {
        Object.assign(climateForm, sanitizeClimateForm(parsed.climate, climateForm))
      }
      if (parsed.water) {
        Object.assign(waterForm, sanitizeWaterForm(parsed.water, waterForm, automationDefaults.value))
      }
      if (parsed.lighting) {
        Object.assign(lightingForm, sanitizeLightingForm(parsed.lighting, lightingForm))
      }
      if (parsed.zoneClimate) {
        zoneClimateForm.enabled = toBoolean(parsed.zoneClimate.enabled, zoneClimateForm.enabled)
      }
      automationLogicMode.value = normalizeAutomationLogicMode(parsed.automationLogicMode, automationLogicMode.value)

      const parsedLastAppliedAt = parseIsoDate(parsed.lastAppliedAt ?? null)
      lastAppliedAt.value = parsedLastAppliedAt ? parsedLastAppliedAt.toISOString() : null
      const parsedSyncedAt = parseIsoDate(parsed.lastAutomationLogicSyncAt ?? null)
      lastAutomationLogicSyncAt.value = parsedSyncedAt ? parsedSyncedAt.toISOString() : null
    } catch (error) {
      logger.warn('[ZoneAutomationTab] Failed to parse stored automation profile', { error })
    }
  }

  // ─── Watchers ──────────────────────────────────────────────────────────────
  watch(
    () => waterForm.systemType,
    (value) => syncSystemToTankLayout(waterForm, value),
    { immediate: true }
  )

  watch(climateForm, saveProfileToStorage, { deep: true })
  watch(waterForm, saveProfileToStorage, { deep: true })
  watch(lightingForm, saveProfileToStorage, { deep: true })
  watch(zoneClimateForm, saveProfileToStorage, { deep: true })
  watch(automationLogicMode, saveProfileToStorage)
  watch(lastAutomationLogicSyncAt, saveProfileToStorage)
  watch(lastAppliedAt, saveProfileToStorage)

  watch(
    () => props.targets,
    (targets) => {
      applyAutomationFromRecipe(targets, { climateForm, waterForm, lightingForm })
      pendingTargetsSyncForZoneChange.value = false
    },
    { deep: true }
  )

  // ─── Quick actions ─────────────────────────────────────────────────────────
  function resetToRecommended(): void {
    resetFormsToRecommended({ climateForm, waterForm, lightingForm }, automationDefaults.value)
    zoneClimateForm.enabled = false
  }

  async function withQuickAction(key: keyof typeof quickActions, callback: () => Promise<void>): Promise<void> {
    if (quickActions[key]) return

    if (!canOperateAutomation.value) {
      showToast('Команды выполнения доступны оператору и агроному.', 'warning')
      return
    }

    quickActions[key] = true
    try {
      await callback()
    } catch (error) {
      logger.error('[ZoneAutomationTab] Quick action failed', { key, error })
    } finally {
      quickActions[key] = false
    }
  }

  async function runManualIrrigation(): Promise<void> {
    if (!props.zoneId) return

    await withQuickAction('irrigation', async () => {
      await sendZoneCommand(props.zoneId as number, 'FORCE_IRRIGATION', {
        duration_sec: clamp(Math.round(waterForm.manualIrrigationSeconds), 1, 3600),
      })
    })
  }

  async function runManualClimate(): Promise<void> {
    if (!props.zoneId) return

    await withQuickAction('climate', async () => {
      await sendZoneCommand(props.zoneId as number, 'FORCE_CLIMATE', {
        target_temp: clamp(climateForm.dayTemp, 10, 35),
        target_humidity: clamp(climateForm.dayHumidity, 30, 90),
      })
    })
  }

  async function runManualLighting(): Promise<void> {
    if (!props.zoneId) return

    await withQuickAction('lighting', async () => {
      await sendZoneCommand(props.zoneId as number, 'FORCE_LIGHTING', {
        intensity: clamp(Math.round(lightingForm.manualIntensity), 0, 100),
        duration_hours: clamp(lightingForm.manualDurationHours, 0.5, 24),
      })
    })
  }

  async function runManualPh(): Promise<void> {
    if (!props.zoneId) return

    await withQuickAction('ph', async () => {
      await sendZoneCommand(props.zoneId as number, 'FORCE_PH_CONTROL', {
        target_ph: clamp(waterForm.targetPh, 4, 9),
      })
    })
  }

  async function runManualEc(): Promise<void> {
    if (!props.zoneId) return

    await withQuickAction('ec', async () => {
      await sendZoneCommand(props.zoneId as number, 'FORCE_EC_CONTROL', {
        target_ec: clamp(waterForm.targetEc, 0.1, 10),
      })
    })
  }

  return {
    // Role
    role,
    canConfigureAutomation,
    canOperateAutomation,
    isSystemTypeLocked,
    // Forms
    climateForm,
    waterForm,
    lightingForm,
    zoneClimateForm,
    quickActions,
    // Flags (public)
    isApplyingProfile,
    isHydratingProfile,
    isSyncingAutomationLogicProfile,
    lastAppliedAt,
    automationLogicMode,
    lastAutomationLogicSyncAt,
    // Internal coordination flag (not part of public composable API)
    pendingTargetsSyncForZoneChange,
    // Derived
    predictionTargets,
    telemetryLabel,
    waterTopologyLabel,
    // Storage (internal, needed by api)
    loadProfileFromStorage,
    saveProfileToStorage,
    profileStorageKey,
    // Actions
    resetToRecommended,
    runManualIrrigation,
    runManualClimate,
    runManualLighting,
    runManualPh,
    runManualEc,
  }
}

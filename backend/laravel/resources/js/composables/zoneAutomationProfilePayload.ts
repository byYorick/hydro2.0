import { isValidHHMM } from '@/services/automation/parsingUtils'
import { clamp, syncSystemToTankLayout } from './zoneAutomationTargetsParser'
import type { ZoneAutomationForms } from './zoneAutomationTypes'
import {
  createDefaultClimateForm,
  createDefaultLightingForm,
  createDefaultWaterForm,
  FALLBACK_AUTOMATION_DEFAULTS,
} from '@/composables/useAutomationDefaults'
import type {
  AutomationCommandTemplatesSettings,
  AutomationDefaultsSettings,
} from '@/types/SystemSettings'

function twoTankCommandsFromTemplates(
  templates: AutomationCommandTemplatesSettings,
): Record<string, Array<{ channel: string; cmd: string; params: { state: boolean } }>> {
  const keys: (keyof AutomationCommandTemplatesSettings)[] = [
    'irrigation_start',
    'irrigation_stop',
    'clean_fill_start',
    'clean_fill_stop',
    'solution_fill_start',
    'solution_fill_stop',
    'prepare_recirculation_start',
    'prepare_recirculation_stop',
    'irrigation_recovery_start',
    'irrigation_recovery_stop',
  ]
  const out: Record<string, Array<{ channel: string; cmd: string; params: { state: boolean } }>> = {}
  for (const key of keys) {
    out[key] = templates[key].map((step) => ({
      channel: step.channel,
      cmd: step.cmd,
      params: { state: step.params.state },
    }))
  }
  return out
}

function normalizeNumber(value: unknown, fallback: number): number {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }

  return fallback
}

function round(value: number, digits: number): number {
  const factor = 10 ** digits
  return Math.round(value * factor) / factor
}

function optionalAngle(value: unknown): number | null {
  if (value === null || value === undefined || value === '') {
    return null
  }

  const parsed = Number(value)
  if (!Number.isFinite(parsed)) {
    return null
  }

  return clamp(parsed, 0, 359.999)
}

function optionalPositiveId(value: unknown): number | null {
  if (value === null || value === undefined || value === '') {
    return null
  }

  const parsed = Math.round(Number(value))
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null
}

function readNumber(value: unknown, fallback: number): number {
  return normalizeNumber(value, fallback)
}

export function buildGreenhouseClimateSubsystemPayload(
  climateForm: ZoneAutomationForms['climateForm'],
  enabled: boolean,
): Record<string, unknown> {
  const intervalSec = clamp(Math.round(readNumber(climateForm.intervalMinutes, 5) * 60), 60, 3600)
  const overrideSec = clamp(Math.round(readNumber(climateForm.overrideMinutes, 30) * 60), 60, 86400)
  const ventMin = clamp(Math.round(readNumber(climateForm.ventMinPercent, 0)), 0, 100)
  const ventMax = clamp(Math.round(readNumber(climateForm.ventMaxPercent, 100)), ventMin, 100)
  const maxStep = clamp(Math.round(readNumber(climateForm.maxVentStepPct, 25)), 1, 100)
  const tempMin = Math.min(readNumber(climateForm.nightTemp, 20), readNumber(climateForm.dayTemp, 23))
  const tempMax = Math.max(readNumber(climateForm.nightTemp, 20), readNumber(climateForm.dayTemp, 23))
  const humidityMin = Math.min(readNumber(climateForm.nightHumidity, 70), readNumber(climateForm.dayHumidity, 62))
  const humidityMax = Math.max(readNumber(climateForm.nightHumidity, 70), readNumber(climateForm.dayHumidity, 62))
  const targetPolicy = climateForm.targetPolicy ?? 'greenhouse_targets'

  return {
    climate: {
      enabled,
      control_mode: climateForm.controlMode ?? 'auto',
      execution: {
        decision_interval_sec: intervalSec,
        emergency_decision_interval_sec: clamp(Math.round(readNumber(climateForm.emergencyIntervalSeconds, 60)), 10, intervalSec),
        min_command_interval_sec: clamp(Math.round(readNumber(climateForm.minCommandIntervalSeconds, 300)), 0, 3600),
        max_step_pct: maxStep,
        position_deadband_pct: clamp(Math.round(readNumber(climateForm.positionDeadbandPercent, Math.min(5, maxStep))), 0, maxStep),
        min_safe_open_pct: clamp(Math.round(readNumber(climateForm.minSafeOpenPercent, ventMin)), 0, 100),
        fallback_open_pct: clamp(Math.round(readNumber(climateForm.fallbackOpenPercent, Math.min(5, ventMax))), 0, ventMax),
        weather_stale_max_open_pct: clamp(Math.round(readNumber(climateForm.weatherStaleMaxOpenPercent, Math.min(20, ventMax))), 0, ventMax),
        emergency_open_pct: clamp(Math.round(readNumber(climateForm.emergencyOpenPercent, 100)), 0, 100),
        day_schedule: {
          start_local: climateForm.dayStart,
          end_local: climateForm.nightStart,
        },
        daylight_lux_threshold: clamp(Math.round(readNumber(climateForm.daylightLuxThreshold, 15000)), 0, 200000),
        night_base_open_pct: clamp(Math.round(readNumber(climateForm.nightBaseOpenPercent, ventMin)), 0, 100),
        night_min_open_pct: clamp(Math.round(readNumber(climateForm.nightMinOpenPercent, ventMin)), 0, 100),
        night_max_open_pct: clamp(Math.round(readNumber(climateForm.nightMaxOpenPercent, Math.min(20, ventMax))), 0, 100),
        day_base_open_pct: clamp(Math.round(readNumber(climateForm.dayBaseOpenPercent, Math.max(ventMin, Math.min(10, ventMax)))), 0, 100),
        day_min_open_pct: clamp(Math.round(readNumber(climateForm.dayMinOpenPercent, ventMin)), 0, 100),
        day_max_open_pct: clamp(Math.round(readNumber(climateForm.dayMaxOpenPercent, ventMax)), 0, 100),
        temp_full_open_delta_c: clamp(readNumber(climateForm.tempFullOpenDeltaC, 6), 0.1, 30),
        rh_full_open_delta_pct: clamp(readNumber(climateForm.rhFullOpenDeltaPercent, 20), 1, 100),
        inside_temp_spread_alert_c: clamp(readNumber(climateForm.insideTempSpreadAlertC, 4), 0, 30),
        inside_rh_spread_alert_pct: clamp(readNumber(climateForm.insideRhSpreadAlertPercent, 15), 0, 100),
        cold_guard_margin_c: clamp(readNumber(climateForm.coldGuardMarginC, 1), 0, 20),
        cold_guard_max_open_pct: clamp(Math.round(readNumber(climateForm.coldGuardMaxOpenPercent, Math.min(10, ventMax))), 0, 100),
        outside_hotter_gain: clamp(readNumber(climateForm.outsideHotterGain, 1), 0, 10),
        outside_wetter_gain: clamp(readNumber(climateForm.outsideWetterGain, 1), 0, 10),
        wind_reduce_threshold_ms: clamp(readNumber(climateForm.windReduceThresholdMs, 8), 0, 100),
        wind_close_threshold_ms: clamp(readNumber(climateForm.windCloseThresholdMs, 12), 0, 100),
        wind_reduce_windward_max_pct: clamp(Math.round(readNumber(climateForm.windReduceWindwardMaxPercent, Math.min(25, ventMax))), 0, 100),
        wind_reduce_leeward_max_pct: clamp(Math.round(readNumber(climateForm.windReduceLeewardMaxPercent, Math.min(50, ventMax))), 0, 100),
        wind_storm_windward_max_pct: clamp(Math.round(readNumber(climateForm.windStormWindwardMaxPercent, 0)), 0, 100),
        wind_storm_leeward_max_pct: clamp(Math.round(readNumber(climateForm.windStormLeewardMaxPercent, Math.min(10, ventMax))), 0, 100),
        rain_windward_position_pct: clamp(Math.round(readNumber(climateForm.rainWindwardPositionPercent, 0)), 0, 100),
        rain_leeward_position_pct: clamp(Math.round(readNumber(climateForm.rainLeewardPositionPercent, Math.min(10, ventMax))), 0, 100),
        rain_unknown_direction_max_pct: clamp(Math.round(readNumber(climateForm.rainUnknownDirectionMaxPercent, Math.min(5, ventMax))), 0, 100),
        overheat_emergency_temp_c: clamp(readNumber(climateForm.overheatEmergencyTempC, 38), 20, 80),
        sensor_freshness_sec: clamp(Math.round(readNumber(climateForm.sensorFreshnessSeconds, 1200)), 30, 86400),
        greenhouse_orientation_deg: optionalAngle(climateForm.greenhouseOrientationDeg),
        left_roof_normal_deg: optionalAngle(climateForm.leftRoofNormalDeg),
        right_roof_normal_deg: optionalAngle(climateForm.rightRoofNormalDeg),
        target_policy: targetPolicy,
        primary_zone_id: targetPolicy === 'primary_zone' ? optionalPositiveId(climateForm.primaryZoneId) : null,
        greenhouse_targets: {
          temp_min_c: tempMin,
          temp_max_c: tempMax,
          humidity_min_pct: humidityMin,
          humidity_max_pct: humidityMax,
        },
        manual_emergency_override_enabled: Boolean(climateForm.manualEmergencyOverrideEnabled ?? false),
        manual_override_max_sec: overrideSec,
      },
    },
  }
}

/** Валидация формы климата теплицы (без waterForm) — перед сохранением authority. */
export function validateGreenhouseClimateForm(climateForm: ZoneAutomationForms['climateForm']): string | null {
  if (climateForm.ventMinPercent > climateForm.ventMaxPercent) {
    return 'Минимум открытия форточек не может быть больше максимума.'
  }
  if (climateForm.intervalMinutes < 1 || climateForm.intervalMinutes > 1440) {
    return 'Интервал климата должен быть от 1 до 1440 минут.'
  }
  if (climateForm.maxVentStepPct < 1 || climateForm.maxVentStepPct > 100) {
    return 'Макс. шаг форточек (max_step_pct) должен быть от 1 до 100%.'
  }
  if ((climateForm.positionDeadbandPercent ?? 0) > climateForm.maxVentStepPct) {
    return 'Deadband форточек не может быть больше max_step_pct.'
  }
  if (climateForm.dayTemp < 10 || climateForm.dayTemp > 35 || climateForm.nightTemp < 10 || climateForm.nightTemp > 35) {
    return 'Температуры день/ночь должны быть в диапазоне 10–35 °C.'
  }
  if (climateForm.dayHumidity < 30 || climateForm.dayHumidity > 90 || climateForm.nightHumidity < 30 || climateForm.nightHumidity > 90) {
    return 'Влажность день/ночь должна быть в диапазоне 30–90%.'
  }
  if (!isValidHHMM(climateForm.dayStart) || !isValidHHMM(climateForm.nightStart)) {
    return 'Границы дня/ночи: укажите время в формате HH:MM (00:00–23:59).'
  }
  if (climateForm.useExternalTelemetry && climateForm.outsideTempMin > climateForm.outsideTempMax) {
    return 'Внешняя температура: минимум не может быть больше максимума.'
  }
  if (climateForm.targetPolicy === 'primary_zone' && !optionalPositiveId(climateForm.primaryZoneId)) {
    return 'Для target policy primary_zone укажите primary_zone_id.'
  }

  return null
}

export function validateForms(forms: Pick<ZoneAutomationForms, 'climateForm' | 'waterForm'>): string | null {
  const { climateForm, waterForm } = forms
  if (climateForm.ventMinPercent > climateForm.ventMaxPercent) {
    return 'Минимум открытия форточек не может быть больше максимума.'
  }

  if (waterForm.cleanTankFillL <= 0 || waterForm.nutrientTankTargetL <= 0) {
    return 'Укажите положительные объёмы баков.'
  }

  if (waterForm.tanksCount === 3 && waterForm.enableDrainControl && waterForm.drainTargetPercent <= 0) {
    return 'Для контроля дренажа задайте целевой процент больше 0.'
  }

  if (waterForm.cleanTankFullThreshold <= 0 || waterForm.cleanTankFullThreshold > 1) {
    return 'Порог полного бака должен быть в диапазоне (0;1].'
  }

  if (!isValidHHMM(waterForm.fillWindowStart) || !isValidHHMM(waterForm.fillWindowEnd)) {
    return 'Укажите корректное время окна заполнения (формат HH:MM, 00:00–23:59).'
  }

  return null
}

export function buildGrowthCycleConfigPayload(
  forms: ZoneAutomationForms,
  options?: {
    includeSystemType?: boolean
    includeClimateSubsystem?: boolean
    automationDefaults?: AutomationDefaultsSettings
    automationCommandTemplates?: AutomationCommandTemplatesSettings
  }
): Record<string, unknown> {
  const { climateForm, waterForm, lightingForm } = forms
  const zoneClimateForm = forms.zoneClimateForm ?? { enabled: false }
  const includeSystemType = options?.includeSystemType ?? true
  const includeClimateSubsystem = options?.includeClimateSubsystem ?? true
  const automationDefaults = options?.automationDefaults ?? FALLBACK_AUTOMATION_DEFAULTS
  const irrigationIntervalMinutes = clamp(Math.round(waterForm.intervalMinutes), 5, 1440)
  const irrigationDurationSeconds = clamp(Math.round(waterForm.durationSeconds), 1, 3600)
  const climateIntervalSec = clamp(Math.round(climateForm.intervalMinutes * 60), 60, 86400)
  const lightingIntervalSec = clamp(Math.round(lightingForm.intervalMinutes * 60), 60, 86400)
  const diagnosticsIntervalSec = clamp(Math.round(waterForm.diagnosticsIntervalMinutes * 60), 60, 86400)
  const solutionChangeIntervalSec = clamp(Math.round(waterForm.solutionChangeIntervalMinutes * 60), 60, 86400)
  const solutionChangeDurationSec = clamp(Math.round(waterForm.solutionChangeDurationSeconds), 1, 86400)
  const cleanTankFullThreshold = round(clamp(waterForm.cleanTankFullThreshold, 0.05, 1), 3)
  const isTwoTankTopology = waterForm.tanksCount === 2
  const derivedDiagnosticsWorkflow = isTwoTankTopology ? 'startup' : 'cycle_start'
  const diagnosticsWorkflowCandidate = typeof waterForm.diagnosticsWorkflow === 'string'
    ? waterForm.diagnosticsWorkflow
    : derivedDiagnosticsWorkflow
  const diagnosticsWorkflow =
    diagnosticsWorkflowCandidate === 'startup' ||
    diagnosticsWorkflowCandidate === 'cycle_start' ||
    diagnosticsWorkflowCandidate === 'diagnostics'
      ? diagnosticsWorkflowCandidate
      : derivedDiagnosticsWorkflow
  const normalizedDiagnosticsWorkflow =
    isTwoTankTopology && diagnosticsWorkflow === 'cycle_start'
      ? 'startup'
      : !isTwoTankTopology && diagnosticsWorkflow === 'startup'
        ? 'cycle_start'
        : diagnosticsWorkflow
  const refillDurationSec = clamp(Math.round(waterForm.refillDurationSeconds), 1, 3600)
  const refillTimeoutSec = clamp(Math.round(waterForm.refillTimeoutSeconds), 30, 86400)
  const startupCleanFillTimeoutSec = clamp(
    Math.round(
      normalizeNumber(
        waterForm.startupCleanFillTimeoutSeconds,
        automationDefaults.water_startup_clean_fill_timeout_sec
      )
    ),
    30,
    86400
  )
  const startupSolutionFillTimeoutSec = clamp(
    Math.round(
      normalizeNumber(
        waterForm.startupSolutionFillTimeoutSeconds,
        automationDefaults.water_startup_solution_fill_timeout_sec
      )
    ),
    30,
    86400
  )
  const startupPrepareRecirculationTimeoutSec = clamp(
    Math.round(
      normalizeNumber(
        waterForm.startupPrepareRecirculationTimeoutSeconds,
        automationDefaults.water_startup_prepare_recirculation_timeout_sec
      )
    ),
    30,
    86400
  )
  const startupCleanFillRetryCycles = clamp(
    Math.round(normalizeNumber(waterForm.startupCleanFillRetryCycles, automationDefaults.water_startup_clean_fill_retry_cycles)),
    0,
    20
  )
  const cleanFillMinCheckDelayMs = clamp(
    Math.round(normalizeNumber(waterForm.cleanFillMinCheckDelayMs, automationDefaults.water_clean_fill_min_check_delay_ms)),
    0,
    3600000
  )
  const solutionFillCleanMinCheckDelayMs = clamp(
    Math.round(
      normalizeNumber(
        waterForm.solutionFillCleanMinCheckDelayMs,
        automationDefaults.water_solution_fill_clean_min_check_delay_ms
      )
    ),
    0,
    3600000
  )
  const solutionFillSolutionMinCheckDelayMs = clamp(
    Math.round(
      normalizeNumber(
        waterForm.solutionFillSolutionMinCheckDelayMs,
        automationDefaults.water_solution_fill_solution_min_check_delay_ms
      )
    ),
    0,
    3600000
  )
  const recirculationStopOnSolutionMin =
    waterForm.recirculationStopOnSolutionMin ?? automationDefaults.water_recirculation_stop_on_solution_min
  const estopDebounceMs = clamp(
    Math.round(normalizeNumber(waterForm.estopDebounceMs, automationDefaults.water_estop_debounce_ms)),
    20,
    5000
  )
  const irrigationRecoveryMaxContinueAttempts = clamp(
    Math.round(
      normalizeNumber(waterForm.irrigationRecoveryMaxContinueAttempts, automationDefaults.water_irrigation_recovery_max_continue_attempts)
    ),
    1,
    30
  )
  const irrigationRecoveryTimeoutSec = clamp(
    Math.round(normalizeNumber(waterForm.irrigationRecoveryTimeoutSeconds, automationDefaults.water_irrigation_recovery_timeout_sec)),
    30,
    86400
  )
  const irrigationDecisionLookbackSec = clamp(
    Math.round(normalizeNumber(waterForm.irrigationDecisionLookbackSeconds, automationDefaults.water_irrigation_decision_lookback_sec)),
    60,
    86400
  )
  const irrigationDecisionMinSamples = clamp(
    Math.round(normalizeNumber(waterForm.irrigationDecisionMinSamples, automationDefaults.water_irrigation_decision_min_samples)),
    1,
    100
  )
  const irrigationDecisionStaleAfterSec = clamp(
    Math.round(
      normalizeNumber(waterForm.irrigationDecisionStaleAfterSeconds, automationDefaults.water_irrigation_decision_stale_after_sec)
    ),
    30,
    86400
  )
  const irrigationDecisionHysteresisPct = round(
    clamp(
      normalizeNumber(waterForm.irrigationDecisionHysteresisPct, automationDefaults.water_irrigation_decision_hysteresis_pct),
      0,
      100
    ),
    1
  )
  const irrigationDecisionSpreadAlertThresholdPct = round(
    clamp(
      normalizeNumber(
        waterForm.irrigationDecisionSpreadAlertThresholdPct,
        automationDefaults.water_irrigation_decision_spread_alert_threshold_pct
      ),
      0,
      100
    ),
    1
  )
  const irrigationDecisionStrategy =
    waterForm.irrigationDecisionStrategy === 'smart_soil_v1' || waterForm.irrigationDecisionStrategy === 'task'
      ? waterForm.irrigationDecisionStrategy
      : automationDefaults.water_irrigation_decision_strategy === 'smart_soil_v1'
        ? 'smart_soil_v1'
        : 'task'
  const irrigationAutoReplayAfterSetup =
    waterForm.irrigationAutoReplayAfterSetup ?? automationDefaults.water_irrigation_auto_replay_after_setup
  const irrigationMaxSetupReplays = clamp(
    Math.round(normalizeNumber(waterForm.irrigationMaxSetupReplays, automationDefaults.water_irrigation_max_setup_replays)),
    0,
    10
  )
  const irrigationStopOnSolutionMin =
    waterForm.stopOnSolutionMin ?? automationDefaults.water_irrigation_stop_on_solution_min
  const correctionMaxEcCorrectionAttempts = clamp(
    Math.round(normalizeNumber(waterForm.correctionMaxEcCorrectionAttempts, automationDefaults.water_correction_max_ec_attempts)),
    1,
    50
  )
  const correctionMaxPhCorrectionAttempts = clamp(
    Math.round(normalizeNumber(waterForm.correctionMaxPhCorrectionAttempts, automationDefaults.water_correction_max_ph_attempts)),
    1,
    50
  )
  const correctionPrepareRecirculationMaxAttempts = clamp(
    Math.round(
      normalizeNumber(
        waterForm.correctionPrepareRecirculationMaxAttempts,
        automationDefaults.water_correction_prepare_recirculation_max_attempts
      )
    ),
    1,
    50
  )
  const correctionPrepareRecirculationMaxCorrectionAttempts = clamp(
    Math.round(
      normalizeNumber(
        waterForm.correctionPrepareRecirculationMaxCorrectionAttempts,
        automationDefaults.water_correction_prepare_recirculation_max_correction_attempts
      )
    ),
    1,
    500
  )
  const correctionStabilizationSec = clamp(
    Math.round(normalizeNumber(waterForm.correctionStabilizationSec, automationDefaults.water_correction_stabilization_sec)),
    0,
    3600
  )
  const requiredNodeTypes = waterForm.refillRequiredNodeTypes
    .split(',')
    .map((item) => item.trim())
    .filter((item) => item.length > 0)
  const refillPreferredChannel = waterForm.refillPreferredChannel.trim()

  const diagnosticsExecution: Record<string, unknown> = {
    workflow: normalizedDiagnosticsWorkflow,
    clean_tank_full_threshold: cleanTankFullThreshold,
    required_node_types: requiredNodeTypes,
    refill_duration_sec: refillDurationSec,
    refill_timeout_sec: refillTimeoutSec,
    refill: {
      duration_sec: refillDurationSec,
      timeout_sec: refillTimeoutSec,
      ...(refillPreferredChannel ? { channel: refillPreferredChannel } : {}),
    },
  }
  if (isTwoTankTopology) {
    diagnosticsExecution.topology = 'two_tank_drip_substrate_trays'
    diagnosticsExecution.startup = {
      required_node_types:
        requiredNodeTypes.length > 0
          ? requiredNodeTypes
          : automationDefaults.water_refill_required_node_types_csv
              .split(',')
              .map((item) => item.trim())
              .filter((item) => item.length > 0),
      // AE3 runtime-plan contract requires this field in diagnostics.execution.startup.
      irr_state_wait_timeout_sec: 5.0,
      clean_fill_timeout_sec: startupCleanFillTimeoutSec,
      solution_fill_timeout_sec: startupSolutionFillTimeoutSec,
      prepare_recirculation_timeout_sec: startupPrepareRecirculationTimeoutSec,
      level_poll_interval_sec: automationDefaults.water_startup_level_poll_interval_sec,
      clean_fill_retry_cycles: startupCleanFillRetryCycles,
      level_switch_on_threshold: automationDefaults.water_startup_level_switch_on_threshold,
      clean_max_sensor_labels: [automationDefaults.water_startup_clean_max_sensor_label],
      solution_max_sensor_labels: [automationDefaults.water_startup_solution_max_sensor_label],
    }
    diagnosticsExecution.correction = {
      max_ec_correction_attempts: correctionMaxEcCorrectionAttempts,
      max_ph_correction_attempts: correctionMaxPhCorrectionAttempts,
      prepare_recirculation_max_attempts: correctionPrepareRecirculationMaxAttempts,
      prepare_recirculation_max_correction_attempts: correctionPrepareRecirculationMaxCorrectionAttempts,
      stabilization_sec: correctionStabilizationSec,
    }
    diagnosticsExecution.irrigation_recovery = {
      max_continue_attempts: irrigationRecoveryMaxContinueAttempts,
      timeout_sec: irrigationRecoveryTimeoutSec,
      target_tolerance: {
        ec_pct: automationDefaults.water_irrigation_recovery_target_tolerance_ec_pct,
        ph_pct: automationDefaults.water_irrigation_recovery_target_tolerance_ph_pct,
      },
      degraded_tolerance: {
        ec_pct: automationDefaults.water_irrigation_recovery_degraded_tolerance_ec_pct,
        ph_pct: automationDefaults.water_irrigation_recovery_degraded_tolerance_ph_pct,
      },
    }
    diagnosticsExecution.fail_safe_guards = {
      clean_fill_min_check_delay_ms: cleanFillMinCheckDelayMs,
      solution_fill_clean_min_check_delay_ms: solutionFillCleanMinCheckDelayMs,
      solution_fill_solution_min_check_delay_ms: solutionFillSolutionMinCheckDelayMs,
      recirculation_stop_on_solution_min: Boolean(recirculationStopOnSolutionMin),
      irrigation_stop_on_solution_min: Boolean(irrigationStopOnSolutionMin),
      estop_debounce_ms: estopDebounceMs,
    }
    if (options?.automationCommandTemplates) {
      diagnosticsExecution.two_tank_commands = twoTankCommandsFromTemplates(options.automationCommandTemplates)
    }
  } else if (waterForm.tanksCount === 3) {
    diagnosticsExecution.topology = 'three_tank_drip_substrate_trays'
  }

  const irrigationExecution: Record<string, unknown> = {
    interval_minutes: irrigationIntervalMinutes,
    interval_sec: irrigationIntervalMinutes * 60,
    duration_seconds: irrigationDurationSeconds,
    duration_sec: irrigationDurationSeconds,
    ...(includeSystemType ? { system_type: waterForm.systemType } : {}),
    tanks_count: waterForm.tanksCount,
    fill_strategy: 'volume',
    clean_tank_fill_l: clamp(Math.round(waterForm.cleanTankFillL), 10, 5000),
    nutrient_tank_target_l: clamp(Math.round(waterForm.nutrientTankTargetL), 10, 5000),
    irrigation_batch_l: clamp(Math.round(waterForm.irrigationBatchL), 1, 500),
    valve_switching_enabled: waterForm.valveSwitching,
    correction_during_irrigation: waterForm.correctionDuringIrrigation,
    fill_temperature_c: clamp(waterForm.fillTemperatureC, 5, 35),
    schedule: [
      {
        start: waterForm.fillWindowStart,
        end: waterForm.fillWindowEnd,
        action: 'fill_clean_tank_then_mix',
      },
    ],
    correction_node: {
      sensors_location: 'correction_node',
    },
    drain_control: {
      enabled: waterForm.tanksCount === 3 ? waterForm.enableDrainControl : false,
      target_percent: waterForm.tanksCount === 3 ? clamp(waterForm.drainTargetPercent, 0, 100) : null,
    },
  }

  const payload = {
    mode: 'adjust',
    subsystems: {
      ph: {
        enabled: true,
        execution: {},
      },
      ec: {
        enabled: true,
        execution: {},
      },
      irrigation: {
        enabled: true,
        execution: irrigationExecution,
        decision: {
          strategy: irrigationDecisionStrategy,
          config: {
            lookback_sec: irrigationDecisionLookbackSec,
            min_samples: irrigationDecisionMinSamples,
            stale_after_sec: irrigationDecisionStaleAfterSec,
            hysteresis_pct: irrigationDecisionHysteresisPct,
            spread_alert_threshold_pct: irrigationDecisionSpreadAlertThresholdPct,
          },
        },
        recovery: {
          max_continue_attempts: irrigationRecoveryMaxContinueAttempts,
          timeout_sec: irrigationRecoveryTimeoutSec,
          auto_replay_after_setup: Boolean(irrigationAutoReplayAfterSetup),
          max_setup_replays: irrigationMaxSetupReplays,
        },
        safety: {
          stop_on_solution_min: Boolean(irrigationStopOnSolutionMin),
        },
      },
      lighting: {
        enabled: lightingForm.enabled,
        execution: {
          interval_sec: lightingIntervalSec,
          lux: {
            day: clamp(Math.round(lightingForm.luxDay), 0, 120000),
            night: clamp(Math.round(lightingForm.luxNight), 0, 120000),
          },
          photoperiod: {
            hours_on: clamp(lightingForm.hoursOn, 0, 24),
            hours_off: round(clamp(24 - lightingForm.hoursOn, 0, 24), 1),
          },
          schedule: [
            {
              start: lightingForm.scheduleStart,
              end: lightingForm.scheduleEnd,
            },
          ],
          future_metrics: {
            ppfd: null,
            dli: null,
            ready: true,
          },
        }
      },
      zone_climate: {
        enabled: zoneClimateForm.enabled,
        execution: {},
      },
      diagnostics: {
        enabled: waterForm.diagnosticsEnabled,
        execution: {
          interval_sec: diagnosticsIntervalSec,
          // Все остальные поля берутся из diagnosticsExecution: workflow, clean_tank_full_threshold,
          // required_node_types, refill_*, topology, startup, two_tank_commands (для 2-tank)
          ...diagnosticsExecution,
        },
      },
      solution_change: {
        enabled: waterForm.solutionChangeEnabled,
        execution: {
          interval_sec: solutionChangeIntervalSec,
          duration_sec: solutionChangeDurationSec,
        }
      },
    },
  }

  if (includeClimateSubsystem) {
    const payloadSubsystems = payload.subsystems as Record<string, unknown>
    payloadSubsystems.climate = {
      enabled: climateForm.enabled,
      execution: {
        interval_sec: climateIntervalSec,
        temperature: {
          day: clamp(climateForm.dayTemp, 10, 35),
          night: clamp(climateForm.nightTemp, 10, 35),
        },
        humidity: {
          day: clamp(climateForm.dayHumidity, 30, 90),
          night: clamp(climateForm.nightHumidity, 30, 90),
        },
        vent_control: {
          role: 'vent',
          min_open_percent: clamp(Math.round(climateForm.ventMinPercent), 0, 100),
          max_open_percent: clamp(Math.round(climateForm.ventMaxPercent), 0, 100),
        },
        external_guard: {
          enabled: climateForm.useExternalTelemetry,
          temp_min: climateForm.outsideTempMin,
          temp_max: climateForm.outsideTempMax,
          humidity_max: climateForm.outsideHumidityMax,
        },
        limits: {
          strong_wind_mps: 10,
          low_outside_temp_c: clamp(climateForm.outsideTempMin, -30, 45),
        },
        schedule: [
          {
            start: climateForm.dayStart,
            end: climateForm.nightStart,
            profile: 'day',
          },
          {
            start: climateForm.nightStart,
            end: climateForm.dayStart,
            profile: 'night',
          },
        ],
        manual_override: {
          enabled: climateForm.manualOverrideEnabled,
          timeout_minutes: clamp(Math.round(climateForm.overrideMinutes), 5, 120),
        },
      },
    }
  }

  return payload
}

export function resetToRecommended(
  forms: ZoneAutomationForms,
  automationDefaults: AutomationDefaultsSettings = FALLBACK_AUTOMATION_DEFAULTS
): void {
  const { climateForm, waterForm, lightingForm } = forms
  Object.assign(climateForm, createDefaultClimateForm(automationDefaults))
  Object.assign(waterForm, createDefaultWaterForm(automationDefaults))
  Object.assign(lightingForm, createDefaultLightingForm(automationDefaults))

  syncSystemToTankLayout(waterForm, automationDefaults.water_system_type)
}

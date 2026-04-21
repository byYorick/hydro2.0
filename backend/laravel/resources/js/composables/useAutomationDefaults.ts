import { computed, ref } from 'vue'
import { useAutomationConfig } from '@/composables/useAutomationConfig'
import type {
  ClimateFormState,
  LightingFormState,
  WaterFormState,
} from '@/composables/zoneAutomationTypes'
import type { AutomationDefaultsSettings } from '@/types/SystemSettings'

const authorityAutomationDefaults = ref<Partial<AutomationDefaultsSettings> | null>(null)
let authorityAutomationDefaultsRequest: Promise<void> | null = null

export const FALLBACK_AUTOMATION_DEFAULTS: AutomationDefaultsSettings = {
  climate_enabled: true,
  climate_day_temp_c: 23,
  climate_night_temp_c: 20,
  climate_day_humidity_pct: 62,
  climate_night_humidity_pct: 70,
  climate_interval_min: 5,
  climate_day_start_hhmm: '07:00',
  climate_night_start_hhmm: '19:00',
  climate_vent_min_pct: 15,
  climate_vent_max_pct: 85,
  climate_use_external_telemetry: true,
  climate_outside_temp_min_c: 4,
  climate_outside_temp_max_c: 34,
  climate_outside_humidity_max_pct: 90,
  climate_manual_override_enabled: true,
  climate_manual_override_minutes: 30,
  water_system_type: 'drip',
  water_tanks_count: 2,
  water_clean_tank_fill_l: 300,
  water_nutrient_tank_target_l: 280,
  water_irrigation_batch_l: 20,
  water_interval_min: 30,
  water_duration_sec: 120,
  water_fill_temperature_c: 20,
  water_fill_window_start_hhmm: '05:00',
  water_fill_window_end_hhmm: '07:00',
  water_target_ph: 5.8,
  water_target_ec: 1.6,
  water_ph_pct: 5,
  water_ec_pct: 10,
  water_valve_switching_enabled: true,
  water_correction_during_irrigation: true,
  water_drain_control_enabled: false,
  water_drain_target_pct: 20,
  water_diagnostics_enabled: true,
  water_diagnostics_interval_min: 15,
  water_cycle_start_workflow_enabled: true,
  water_diagnostics_workflow: 'startup',
  water_clean_tank_full_threshold: 0.95,
  water_refill_duration_sec: 30,
  water_refill_timeout_sec: 600,
  water_startup_clean_fill_timeout_sec: 1200,
  water_startup_solution_fill_timeout_sec: 1800,
  water_startup_prepare_recirculation_timeout_sec: 1200,
  water_startup_clean_fill_retry_cycles: 1,
  water_startup_level_poll_interval_sec: 60,
  water_startup_level_switch_on_threshold: 0.5,
  water_startup_clean_max_sensor_label: 'level_clean_max',
  water_startup_solution_max_sensor_label: 'level_solution_max',
  water_clean_fill_min_check_delay_ms: 5000,
  water_solution_fill_clean_min_check_delay_ms: 5000,
  water_solution_fill_solution_min_check_delay_ms: 15000,
  water_recirculation_stop_on_solution_min: true,
  water_estop_debounce_ms: 80,
  water_irrigation_recovery_max_continue_attempts: 5,
  water_irrigation_recovery_timeout_sec: 600,
  water_irrigation_recovery_target_tolerance_ec_pct: 10,
  water_irrigation_recovery_target_tolerance_ph_pct: 5,
  water_irrigation_recovery_degraded_tolerance_ec_pct: 20,
  water_irrigation_recovery_degraded_tolerance_ph_pct: 10,
  water_irrigation_decision_strategy: 'task',
  water_irrigation_decision_lookback_sec: 1800,
  water_irrigation_decision_min_samples: 3,
  water_irrigation_decision_stale_after_sec: 600,
  water_irrigation_decision_hysteresis_pct: 2,
  water_irrigation_decision_spread_alert_threshold_pct: 12,
  water_irrigation_stop_on_solution_min: true,
  water_irrigation_auto_replay_after_setup: true,
  water_irrigation_max_setup_replays: 1,
  water_prepare_tolerance_ec_pct: 25,
  water_prepare_tolerance_ph_pct: 15,
  water_correction_max_ec_attempts: 5,
  water_correction_max_ph_attempts: 5,
  water_correction_prepare_recirculation_max_attempts: 3,
  water_correction_prepare_recirculation_max_correction_attempts: 20,
  water_correction_stabilization_sec: 60,
  water_two_tank_irrigation_start_steps: 3,
  water_two_tank_irrigation_stop_steps: 3,
  water_two_tank_clean_fill_start_steps: 1,
  water_two_tank_clean_fill_stop_steps: 1,
  water_two_tank_solution_fill_start_steps: 3,
  water_two_tank_solution_fill_stop_steps: 3,
  water_two_tank_prepare_recirculation_start_steps: 3,
  water_two_tank_prepare_recirculation_stop_steps: 3,
  water_two_tank_irrigation_recovery_start_steps: 4,
  water_two_tank_irrigation_recovery_stop_steps: 4,
  water_refill_required_node_types_csv: 'irrig',
  water_refill_preferred_channel: 'fill_valve',
  water_solution_change_enabled: false,
  water_solution_change_interval_min: 180,
  water_solution_change_duration_sec: 120,
  water_manual_irrigation_sec: 90,
  lighting_enabled: true,
  lighting_lux_day: 18000,
  lighting_lux_night: 0,
  lighting_hours_on: 16,
  lighting_interval_min: 30,
  lighting_schedule_start_hhmm: '06:00',
  lighting_schedule_end_hhmm: '22:00',
  lighting_manual_intensity_pct: 75,
  lighting_manual_duration_hours: 4,
}

export function normalizeAutomationDefaults(
  raw: Partial<AutomationDefaultsSettings> | null | undefined,
): AutomationDefaultsSettings {
  return {
    ...FALLBACK_AUTOMATION_DEFAULTS,
    ...(raw ?? {}),
  }
}

export function createDefaultClimateForm(defaults: AutomationDefaultsSettings): ClimateFormState {
  return {
    enabled: defaults.climate_enabled,
    dayTemp: defaults.climate_day_temp_c,
    nightTemp: defaults.climate_night_temp_c,
    dayHumidity: defaults.climate_day_humidity_pct,
    nightHumidity: defaults.climate_night_humidity_pct,
    intervalMinutes: defaults.climate_interval_min,
    dayStart: defaults.climate_day_start_hhmm,
    nightStart: defaults.climate_night_start_hhmm,
    ventMinPercent: defaults.climate_vent_min_pct,
    ventMaxPercent: defaults.climate_vent_max_pct,
    useExternalTelemetry: defaults.climate_use_external_telemetry,
    outsideTempMin: defaults.climate_outside_temp_min_c,
    outsideTempMax: defaults.climate_outside_temp_max_c,
    outsideHumidityMax: defaults.climate_outside_humidity_max_pct,
    manualOverrideEnabled: defaults.climate_manual_override_enabled,
    overrideMinutes: defaults.climate_manual_override_minutes,
  }
}

export function createDefaultWaterForm(defaults: AutomationDefaultsSettings): WaterFormState {
  return {
    systemType: defaults.water_system_type,
    tanksCount: defaults.water_tanks_count,
    cleanTankFillL: defaults.water_clean_tank_fill_l,
    nutrientTankTargetL: defaults.water_nutrient_tank_target_l,
    irrigationBatchL: defaults.water_irrigation_batch_l,
    intervalMinutes: defaults.water_interval_min,
    durationSeconds: defaults.water_duration_sec,
    fillTemperatureC: defaults.water_fill_temperature_c,
    fillWindowStart: defaults.water_fill_window_start_hhmm,
    fillWindowEnd: defaults.water_fill_window_end_hhmm,
    targetPh: defaults.water_target_ph,
    targetEc: defaults.water_target_ec,
    phPct: defaults.water_ph_pct,
    ecPct: defaults.water_ec_pct,
    valveSwitching: defaults.water_valve_switching_enabled,
    correctionDuringIrrigation: defaults.water_correction_during_irrigation,
    enableDrainControl: defaults.water_drain_control_enabled,
    drainTargetPercent: defaults.water_drain_target_pct,
    diagnosticsEnabled: defaults.water_diagnostics_enabled,
    diagnosticsIntervalMinutes: defaults.water_diagnostics_interval_min,
    diagnosticsWorkflow: defaults.water_diagnostics_workflow,
    cleanTankFullThreshold: defaults.water_clean_tank_full_threshold,
    refillDurationSeconds: defaults.water_refill_duration_sec,
    refillTimeoutSeconds: defaults.water_refill_timeout_sec,
    mainPumpFlowLpm: 10,
    cleanWaterFlowLpm: 15,
    workingTankL: 50,
    startupCleanFillTimeoutSeconds: defaults.water_startup_clean_fill_timeout_sec,
    startupSolutionFillTimeoutSeconds: defaults.water_startup_solution_fill_timeout_sec,
    startupPrepareRecirculationTimeoutSeconds: defaults.water_startup_prepare_recirculation_timeout_sec,
    startupCleanFillRetryCycles: defaults.water_startup_clean_fill_retry_cycles,
    cleanFillMinCheckDelayMs: defaults.water_clean_fill_min_check_delay_ms,
    solutionFillCleanMinCheckDelayMs: defaults.water_solution_fill_clean_min_check_delay_ms,
    solutionFillSolutionMinCheckDelayMs: defaults.water_solution_fill_solution_min_check_delay_ms,
    recirculationStopOnSolutionMin: defaults.water_recirculation_stop_on_solution_min,
    estopDebounceMs: defaults.water_estop_debounce_ms,
    irrigationDecisionStrategy: defaults.water_irrigation_decision_strategy,
    irrigationDecisionLookbackSeconds: defaults.water_irrigation_decision_lookback_sec,
    irrigationDecisionMinSamples: defaults.water_irrigation_decision_min_samples,
    irrigationDecisionStaleAfterSeconds: defaults.water_irrigation_decision_stale_after_sec,
    irrigationDecisionHysteresisPct: defaults.water_irrigation_decision_hysteresis_pct,
    irrigationDecisionSpreadAlertThresholdPct: defaults.water_irrigation_decision_spread_alert_threshold_pct,
    irrigationRecoveryMaxContinueAttempts: defaults.water_irrigation_recovery_max_continue_attempts,
    irrigationRecoveryTimeoutSeconds: defaults.water_irrigation_recovery_timeout_sec,
    irrigationAutoReplayAfterSetup: defaults.water_irrigation_auto_replay_after_setup,
    irrigationMaxSetupReplays: defaults.water_irrigation_max_setup_replays,
    stopOnSolutionMin: defaults.water_irrigation_stop_on_solution_min,
    correctionMaxEcCorrectionAttempts: defaults.water_correction_max_ec_attempts,
    correctionMaxPhCorrectionAttempts: defaults.water_correction_max_ph_attempts,
    correctionPrepareRecirculationMaxAttempts: defaults.water_correction_prepare_recirculation_max_attempts,
    correctionPrepareRecirculationMaxCorrectionAttempts: defaults.water_correction_prepare_recirculation_max_correction_attempts,
    correctionStabilizationSec: defaults.water_correction_stabilization_sec,
    refillRequiredNodeTypes: defaults.water_refill_required_node_types_csv,
    refillPreferredChannel: defaults.water_refill_preferred_channel,
    solutionChangeEnabled: defaults.water_solution_change_enabled,
    solutionChangeIntervalMinutes: defaults.water_solution_change_interval_min,
    solutionChangeDurationSeconds: defaults.water_solution_change_duration_sec,
    manualIrrigationSeconds: defaults.water_manual_irrigation_sec,
  }
}

export function createDefaultLightingForm(defaults: AutomationDefaultsSettings): LightingFormState {
  return {
    enabled: defaults.lighting_enabled,
    luxDay: defaults.lighting_lux_day,
    luxNight: defaults.lighting_lux_night,
    hoursOn: defaults.lighting_hours_on,
    intervalMinutes: defaults.lighting_interval_min,
    scheduleStart: defaults.lighting_schedule_start_hhmm,
    scheduleEnd: defaults.lighting_schedule_end_hhmm,
    manualIntensity: defaults.lighting_manual_intensity_pct,
    manualDurationHours: defaults.lighting_manual_duration_hours,
  }
}

export function useAutomationDefaults() {
  const automationConfig = useAutomationConfig()
  if (authorityAutomationDefaults.value === null && authorityAutomationDefaultsRequest === null) {
    authorityAutomationDefaultsRequest = automationConfig
      .getDocument<Partial<AutomationDefaultsSettings>>('system', 0, 'system.automation_defaults')
      .then((document) => {
        authorityAutomationDefaults.value = document.payload ?? null
      })
      .catch(() => {})
      .finally(() => {
        authorityAutomationDefaultsRequest = null
      })
  }

  return computed(() => normalizeAutomationDefaults(authorityAutomationDefaults.value))
}

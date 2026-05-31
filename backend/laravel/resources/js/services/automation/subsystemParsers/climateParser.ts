/**
 * Парсер подсистемы climate из recipe automation targets.
 *
 * Извлечён из applyAutomationFromRecipe (zoneAutomationTargetsParser.ts).
 * Читает `targets.extensions.subsystems.climate` + плоские fallback'и
 * (`targets.climate_request`, `targets.ventilation`) и заполняет climateForm:
 * enabled, temperature day/night, humidity day/night, vent control,
 * external guard, schedule, manual override.
 */

import { clamp } from '@/services/automation/parsingUtils'
import {
  asArray,
  asRecord,
  readBoolean,
  readNumber,
  toTimeHHmm,
  type Dictionary,
} from '@/services/automation/dictReaders'
import type { ClimateFormState } from '@/composables/zoneAutomationTypes'

export function applyClimateFromTargets(targets: Dictionary, climateForm: ClimateFormState): void {
  const extensions = asRecord(targets.extensions)
  const subsystems = asRecord(extensions?.subsystems)
  const climateSubsystem = asRecord(subsystems?.climate)
  const climateExecution = asRecord(climateSubsystem?.execution)
  const climateTargets = asRecord(climateSubsystem?.targets)
  const climateBehavior = climateExecution ?? climateTargets

  const climateRequest = asRecord(targets.climate_request)
  const ventilation = asRecord(targets.ventilation)

  const climateEnabled = readBoolean(climateSubsystem?.enabled)
  if (climateEnabled !== null) {
    climateForm.enabled = climateEnabled
  }
  const controlMode = typeof climateSubsystem?.control_mode === 'string' ? climateSubsystem.control_mode : null
  if (controlMode === 'auto' || controlMode === 'semi' || controlMode === 'manual') {
    climateForm.controlMode = controlMode
  }

  applyTemperatureHumidity(climateBehavior, climateTargets, climateRequest, climateForm)

  const climateIntervalSec = readNumber(
    climateBehavior?.decision_interval_sec,
    climateBehavior?.interval_sec,
    climateTargets?.interval_sec,
    ventilation?.interval_sec,
  )
  if (climateIntervalSec !== null) {
    climateForm.intervalMinutes = clamp(Math.round(climateIntervalSec / 60), 1, 1440)
  }
  applyV1ExecutionFields(climateBehavior, climateForm)

  applyVentControl(climateBehavior, climateTargets, climateForm)
  const maxStep = readNumber(climateBehavior?.max_step_pct)
  if (maxStep !== null) {
    climateForm.maxVentStepPct = clamp(Math.round(maxStep), 1, 100)
  }
  applyExternalGuard(climateBehavior, climateTargets, climateForm)
  applySchedule(climateBehavior, climateTargets, climateForm)
  applyManualOverride(climateBehavior, climateTargets, climateForm)
}

function applyTemperatureHumidity(
  climateBehavior: Dictionary | null,
  climateTargets: Dictionary | null,
  climateRequest: Dictionary | null,
  climateForm: ClimateFormState,
): void {
  const temperature = asRecord(climateBehavior?.temperature) ?? asRecord(climateTargets?.temperature)
  const humidity = asRecord(climateBehavior?.humidity) ?? asRecord(climateTargets?.humidity)
  const greenhouseTargets = asRecord(climateBehavior?.greenhouse_targets)

  const dayTemp = readNumber(temperature?.day, greenhouseTargets?.temp_max_c, climateRequest?.temp_air_target)
  const nightTemp = readNumber(temperature?.night, temperature?.day, greenhouseTargets?.temp_min_c, climateRequest?.temp_air_target)
  const dayHumidity = readNumber(humidity?.day, greenhouseTargets?.humidity_min_pct, climateRequest?.humidity_target)
  const nightHumidity = readNumber(humidity?.night, humidity?.day, greenhouseTargets?.humidity_max_pct, climateRequest?.humidity_target)

  if (dayTemp !== null) {
    climateForm.dayTemp = clamp(dayTemp, 10, 35)
  }
  if (nightTemp !== null) {
    climateForm.nightTemp = clamp(nightTemp, 10, 35)
  }
  if (dayHumidity !== null) {
    climateForm.dayHumidity = clamp(dayHumidity, 30, 90)
  }
  if (nightHumidity !== null) {
    climateForm.nightHumidity = clamp(nightHumidity, 30, 90)
  }
}

function applyVentControl(
  climateBehavior: Dictionary | null,
  climateTargets: Dictionary | null,
  climateForm: ClimateFormState,
): void {
  const ventControl = asRecord(climateBehavior?.vent_control) ?? asRecord(climateTargets?.vent_control)
  const ventMinPercent = readNumber(ventControl?.min_open_percent, climateBehavior?.day_min_open_pct, climateBehavior?.min_safe_open_pct)
  const ventMaxPercent = readNumber(ventControl?.max_open_percent, climateBehavior?.day_max_open_pct)

  if (ventMinPercent !== null) {
    climateForm.ventMinPercent = clamp(Math.round(ventMinPercent), 0, 100)
  }
  if (ventMaxPercent !== null) {
    climateForm.ventMaxPercent = clamp(Math.round(ventMaxPercent), 0, 100)
  }
}

function applyExternalGuard(
  climateBehavior: Dictionary | null,
  climateTargets: Dictionary | null,
  climateForm: ClimateFormState,
): void {
  const externalGuard = asRecord(climateBehavior?.external_guard) ?? asRecord(climateTargets?.external_guard)

  const externalEnabled = readBoolean(externalGuard?.enabled)
  if (externalEnabled !== null) {
    climateForm.useExternalTelemetry = externalEnabled
  }

  const outsideTempMin = readNumber(externalGuard?.temp_min)
  const outsideTempMax = readNumber(externalGuard?.temp_max)
  const outsideHumidityMax = readNumber(externalGuard?.humidity_max)

  if (outsideTempMin !== null) {
    climateForm.outsideTempMin = clamp(outsideTempMin, -30, 45)
  }
  if (outsideTempMax !== null) {
    climateForm.outsideTempMax = clamp(outsideTempMax, -30, 45)
  }
  if (outsideHumidityMax !== null) {
    climateForm.outsideHumidityMax = clamp(outsideHumidityMax, 20, 100)
  }
}

function applySchedule(
  climateBehavior: Dictionary | null,
  climateTargets: Dictionary | null,
  climateForm: ClimateFormState,
): void {
  const climateSchedule = asArray(climateBehavior?.schedule) ?? asArray(climateTargets?.schedule)
  const daySchedule = asRecord(climateBehavior?.day_schedule)
  const daySlot = asRecord(climateSchedule?.find((item) => asRecord(item)?.profile === 'day'))
  const nightSlot = asRecord(climateSchedule?.find((item) => asRecord(item)?.profile === 'night'))

  const dayStart = toTimeHHmm(daySchedule?.start_local) ?? toTimeHHmm(daySlot?.start)
  const nightStart = toTimeHHmm(daySchedule?.end_local) ?? toTimeHHmm(nightSlot?.start)

  if (dayStart) {
    climateForm.dayStart = dayStart
  }
  if (nightStart) {
    climateForm.nightStart = nightStart
  }
}

function applyManualOverride(
  climateBehavior: Dictionary | null,
  climateTargets: Dictionary | null,
  climateForm: ClimateFormState,
): void {
  const manualOverride = asRecord(climateBehavior?.manual_override) ?? asRecord(climateTargets?.manual_override)
  const manualOverrideEnabled = readBoolean(manualOverride?.enabled)
  const emergencyOverrideEnabled = readBoolean(climateBehavior?.manual_emergency_override_enabled)
  const overrideMinutes = readNumber(manualOverride?.timeout_minutes)
  const overrideSeconds = readNumber(climateBehavior?.manual_override_max_sec)

  if (manualOverrideEnabled !== null) {
    climateForm.manualOverrideEnabled = manualOverrideEnabled
  }
  if (emergencyOverrideEnabled !== null) {
    climateForm.manualEmergencyOverrideEnabled = emergencyOverrideEnabled
  }
  if (overrideMinutes !== null) {
    climateForm.overrideMinutes = clamp(Math.round(overrideMinutes), 5, 120)
  }
  if (overrideSeconds !== null) {
    climateForm.overrideMinutes = clamp(Math.round(overrideSeconds / 60), 1, 1440)
  }
}

function setNumber(
  climateForm: ClimateFormState,
  key: keyof ClimateFormState,
  value: unknown,
  min: number,
  max: number,
  roundValue = false,
): void {
  const parsed = readNumber(value)
  if (parsed === null) {
    return
  }

  (climateForm as unknown as Record<string, unknown>)[key] = roundValue
    ? Math.round(clamp(parsed, min, max))
    : clamp(parsed, min, max)
}

function setNullableAngle(climateForm: ClimateFormState, key: keyof ClimateFormState, value: unknown): void {
  const parsed = readNumber(value)
  ;(climateForm as unknown as Record<string, unknown>)[key] = parsed === null ? null : clamp(parsed, 0, 359.999)
}

function applyV1ExecutionFields(climateBehavior: Dictionary | null, climateForm: ClimateFormState): void {
  if (!climateBehavior) {
    return
  }

  setNumber(climateForm, 'emergencyIntervalSeconds', climateBehavior.emergency_decision_interval_sec, 10, 3600, true)
  setNumber(climateForm, 'minCommandIntervalSeconds', climateBehavior.min_command_interval_sec, 0, 3600, true)
  setNumber(climateForm, 'positionDeadbandPercent', climateBehavior.position_deadband_pct, 0, 50, true)
  setNumber(climateForm, 'minSafeOpenPercent', climateBehavior.min_safe_open_pct, 0, 100, true)
  setNumber(climateForm, 'fallbackOpenPercent', climateBehavior.fallback_open_pct, 0, 100, true)
  setNumber(climateForm, 'weatherStaleMaxOpenPercent', climateBehavior.weather_stale_max_open_pct, 0, 100, true)
  setNumber(climateForm, 'emergencyOpenPercent', climateBehavior.emergency_open_pct, 0, 100, true)
  setNumber(climateForm, 'daylightLuxThreshold', climateBehavior.daylight_lux_threshold, 0, 200000, true)
  setNumber(climateForm, 'nightBaseOpenPercent', climateBehavior.night_base_open_pct, 0, 100, true)
  setNumber(climateForm, 'nightMinOpenPercent', climateBehavior.night_min_open_pct, 0, 100, true)
  setNumber(climateForm, 'nightMaxOpenPercent', climateBehavior.night_max_open_pct, 0, 100, true)
  setNumber(climateForm, 'dayBaseOpenPercent', climateBehavior.day_base_open_pct, 0, 100, true)
  setNumber(climateForm, 'dayMinOpenPercent', climateBehavior.day_min_open_pct, 0, 100, true)
  setNumber(climateForm, 'dayMaxOpenPercent', climateBehavior.day_max_open_pct, 0, 100, true)
  setNumber(climateForm, 'tempFullOpenDeltaC', climateBehavior.temp_full_open_delta_c, 0.1, 30)
  setNumber(climateForm, 'rhFullOpenDeltaPercent', climateBehavior.rh_full_open_delta_pct, 1, 100)
  setNumber(climateForm, 'insideTempSpreadAlertC', climateBehavior.inside_temp_spread_alert_c, 0, 30)
  setNumber(climateForm, 'insideRhSpreadAlertPercent', climateBehavior.inside_rh_spread_alert_pct, 0, 100)
  setNumber(climateForm, 'coldGuardMarginC', climateBehavior.cold_guard_margin_c, 0, 20)
  setNumber(climateForm, 'coldGuardMaxOpenPercent', climateBehavior.cold_guard_max_open_pct, 0, 100, true)
  setNumber(climateForm, 'outsideHotterGain', climateBehavior.outside_hotter_gain, 0, 10)
  setNumber(climateForm, 'outsideWetterGain', climateBehavior.outside_wetter_gain, 0, 10)
  setNumber(climateForm, 'windReduceThresholdMs', climateBehavior.wind_reduce_threshold_ms, 0, 100)
  setNumber(climateForm, 'windCloseThresholdMs', climateBehavior.wind_close_threshold_ms, 0, 100)
  setNumber(climateForm, 'windReduceWindwardMaxPercent', climateBehavior.wind_reduce_windward_max_pct, 0, 100, true)
  setNumber(climateForm, 'windReduceLeewardMaxPercent', climateBehavior.wind_reduce_leeward_max_pct, 0, 100, true)
  setNumber(climateForm, 'windStormWindwardMaxPercent', climateBehavior.wind_storm_windward_max_pct, 0, 100, true)
  setNumber(climateForm, 'windStormLeewardMaxPercent', climateBehavior.wind_storm_leeward_max_pct, 0, 100, true)
  setNumber(climateForm, 'rainWindwardPositionPercent', climateBehavior.rain_windward_position_pct, 0, 100, true)
  setNumber(climateForm, 'rainLeewardPositionPercent', climateBehavior.rain_leeward_position_pct, 0, 100, true)
  setNumber(climateForm, 'rainUnknownDirectionMaxPercent', climateBehavior.rain_unknown_direction_max_pct, 0, 100, true)
  setNumber(climateForm, 'overheatEmergencyTempC', climateBehavior.overheat_emergency_temp_c, 20, 80)
  setNumber(climateForm, 'sensorFreshnessSeconds', climateBehavior.sensor_freshness_sec, 30, 86400, true)
  setNullableAngle(climateForm, 'greenhouseOrientationDeg', climateBehavior.greenhouse_orientation_deg)
  setNullableAngle(climateForm, 'leftRoofNormalDeg', climateBehavior.left_roof_normal_deg)
  setNullableAngle(climateForm, 'rightRoofNormalDeg', climateBehavior.right_roof_normal_deg)

  const targetPolicy = typeof climateBehavior.target_policy === 'string' ? climateBehavior.target_policy : null
  if (targetPolicy === 'greenhouse_targets' || targetPolicy === 'primary_zone' || targetPolicy === 'active_zones_strictest') {
    climateForm.targetPolicy = targetPolicy
  }

  const primaryZoneId = readNumber(climateBehavior.primary_zone_id)
  climateForm.primaryZoneId = primaryZoneId !== null && primaryZoneId > 0 ? Math.round(primaryZoneId) : null
}

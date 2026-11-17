import { isValidHHMM } from '@/services/automation/parsingUtils'
import { clamp } from './zoneAutomationTargetsParser'
import type { ZoneAutomationForms } from './zoneAutomationTypes'
import { normalizeNumber } from './zoneAutomationProfileNumbers'

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

/** Пустая строка остаётся пустой. Number('') дал бы 0 и включил бы контур. */
export function optionalKpa(value: unknown): number | null {
  if (value === null || value === undefined) {
    return null
  }
  if (typeof value === 'string' && value.trim() === '') {
    return null
  }
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

export function airVpdTargetError(minRaw: unknown, maxRaw: unknown): string | null {
  const min = optionalKpa(minRaw)
  const max = optionalKpa(maxRaw)
  if (min === null && max === null) {
    return null
  }
  if (min === null || max === null) {
    return 'VPD воздуха: заполните оба поля или оставьте оба пустыми.'
  }
  if (min < 0.1 || min > 3 || max < 0.1 || max > 3) {
    return 'VPD воздуха: каждое значение от 0.1 до 3.0 кПа.'
  }
  if (min >= max) {
    return 'VPD воздуха: минимум должен быть меньше максимума.'
  }
  return null
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
          vpd_min_kpa: optionalKpa(climateForm.vpdMinKpa),
          vpd_max_kpa: optionalKpa(climateForm.vpdMaxKpa),
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
    return 'Мёртвая зона форточек не может быть больше max_step_pct.'
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
  const vpdError = airVpdTargetError(climateForm.vpdMinKpa, climateForm.vpdMaxKpa)
  if (vpdError) {
    return vpdError
  }

  return null
}

/** Тело запроса климата. При ошибке формы payload нет: кривая пара VPD в запрос не попадает. */
export function greenhouseClimateSavePayload(
  climateForm: ZoneAutomationForms['climateForm'],
  enabled: boolean,
): { error: string; payload: null } | { error: null; payload: Record<string, unknown> } {
  const error = validateGreenhouseClimateForm(climateForm)
  if (error) {
    return { error, payload: null }
  }

  return {
    error: null,
    payload: buildGreenhouseClimateSubsystemPayload(climateForm, enabled),
  }
}

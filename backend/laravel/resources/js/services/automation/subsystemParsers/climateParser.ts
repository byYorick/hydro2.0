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

  applyTemperatureHumidity(climateBehavior, climateTargets, climateRequest, climateForm)

  const climateIntervalSec = readNumber(
    climateBehavior?.interval_sec,
    climateTargets?.interval_sec,
    ventilation?.interval_sec,
  )
  if (climateIntervalSec !== null) {
    climateForm.intervalMinutes = clamp(Math.round(climateIntervalSec / 60), 1, 1440)
  }

  applyVentControl(climateBehavior, climateTargets, climateForm)
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

  const dayTemp = readNumber(temperature?.day, climateRequest?.temp_air_target)
  const nightTemp = readNumber(temperature?.night, temperature?.day, climateRequest?.temp_air_target)
  const dayHumidity = readNumber(humidity?.day, climateRequest?.humidity_target)
  const nightHumidity = readNumber(humidity?.night, humidity?.day, climateRequest?.humidity_target)

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
  const ventMinPercent = readNumber(ventControl?.min_open_percent)
  const ventMaxPercent = readNumber(ventControl?.max_open_percent)

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
  const daySlot = asRecord(climateSchedule?.find((item) => asRecord(item)?.profile === 'day'))
  const nightSlot = asRecord(climateSchedule?.find((item) => asRecord(item)?.profile === 'night'))

  const dayStart = toTimeHHmm(daySlot?.start)
  const nightStart = toTimeHHmm(nightSlot?.start)

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
  const overrideMinutes = readNumber(manualOverride?.timeout_minutes)

  if (manualOverrideEnabled !== null) {
    climateForm.manualOverrideEnabled = manualOverrideEnabled
  }
  if (overrideMinutes !== null) {
    climateForm.overrideMinutes = clamp(Math.round(overrideMinutes), 5, 120)
  }
}

import type { IrrigationSystem, WaterFormState, ZoneAutomationForms } from './zoneAutomationTypes'

type Dictionary = Record<string, unknown>

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

function asRecord(value: unknown): Dictionary | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null
  }

  return value as Dictionary
}

function asArray(value: unknown): unknown[] | null {
  if (!Array.isArray(value)) {
    return null
  }

  return value
}

function readNumber(...values: unknown[]): number | null {
  for (const value of values) {
    if (typeof value === 'number' && Number.isFinite(value)) {
      return value
    }

    if (typeof value === 'string' && value.trim() !== '') {
      const parsed = Number(value)
      if (Number.isFinite(parsed)) {
        return parsed
      }
    }
  }

  return null
}

function readBoolean(...values: unknown[]): boolean | null {
  for (const value of values) {
    if (typeof value === 'boolean') {
      return value
    }
    if (value === 1 || value === '1' || value === 'true') {
      return true
    }
    if (value === 0 || value === '0' || value === 'false') {
      return false
    }
  }

  return null
}

function readString(...values: unknown[]): string | null {
  for (const value of values) {
    if (typeof value === 'string' && value.trim() !== '') {
      return value.trim()
    }
  }

  return null
}

function toTimeHHmm(value: unknown): string | null {
  const raw = readString(value)
  if (!raw) {
    return null
  }

  const match = raw.match(/^(\d{1,2}):(\d{2})/)
  if (!match) {
    return null
  }

  return `${match[1].padStart(2, '0')}:${match[2]}`
}

function asIrrigationSystem(value: unknown): IrrigationSystem | null {
  if (value === 'drip' || value === 'substrate_trays' || value === 'nft') {
    return value
  }

  return null
}

function midpoint(minValue: number | null, maxValue: number | null): number | null {
  if (minValue !== null && maxValue !== null) {
    return (minValue + maxValue) / 2
  }

  return minValue ?? maxValue
}

export function syncSystemToTankLayout(
  waterForm: WaterFormState,
  systemType: IrrigationSystem
): void {
  if (systemType === 'drip') {
    waterForm.tanksCount = 2
    waterForm.enableDrainControl = false
    return
  }

  waterForm.tanksCount = 3
}

export function applyAutomationFromRecipe(targetsInput: unknown, forms: ZoneAutomationForms): void {
  const { climateForm, waterForm, lightingForm } = forms
  const targets = asRecord(targetsInput)
  if (!targets) {
    return
  }

  const extensions = asRecord(targets.extensions)
  const subsystems = asRecord(extensions?.subsystems)
  const irrigationSubsystem = asRecord(subsystems?.irrigation)
  const irrigationTargets = asRecord(irrigationSubsystem?.targets)
  const climateSubsystem = asRecord(subsystems?.climate)
  const climateTargets = asRecord(climateSubsystem?.targets)
  const lightingSubsystem = asRecord(subsystems?.lighting)
  const lightingTargets = asRecord(lightingSubsystem?.targets)

  const phTarget = asRecord(targets.ph)
  const phMin = readNumber(phTarget?.min)
  const phMax = readNumber(phTarget?.max)
  const phValue = readNumber(phTarget?.target, midpoint(phMin, phMax))
  if (phValue !== null) {
    waterForm.targetPh = clamp(phValue, 4, 9)
  }

  const ecTarget = asRecord(targets.ec)
  const ecMin = readNumber(ecTarget?.min)
  const ecMax = readNumber(ecTarget?.max)
  const ecValue = readNumber(ecTarget?.target, midpoint(ecMin, ecMax))
  if (ecValue !== null) {
    waterForm.targetEc = clamp(ecValue, 0.1, 10)
  }

  const irrigation = asRecord(targets.irrigation)
  const intervalSec = readNumber(
    irrigationTargets?.interval_sec,
    irrigationTargets?.interval_seconds,
    irrigation?.interval_sec,
    (targets as Dictionary).irrigation_interval_sec
  )
  if (intervalSec !== null) {
    waterForm.intervalMinutes = clamp(Math.round(intervalSec / 60), 5, 1440)
  }

  const durationSec = readNumber(
    irrigationTargets?.duration_sec,
    irrigationTargets?.duration_seconds,
    irrigation?.duration_sec,
    (targets as Dictionary).irrigation_duration_sec
  )
  if (durationSec !== null) {
    waterForm.durationSeconds = clamp(Math.round(durationSec), 1, 3600)
  }

  const systemType = asIrrigationSystem(readString(irrigationTargets?.system_type))
  if (systemType) {
    waterForm.systemType = systemType
    syncSystemToTankLayout(waterForm, systemType)
  }

  const tanksCount = readNumber(irrigationTargets?.tanks_count)
  if (tanksCount === 2 || tanksCount === 3) {
    waterForm.tanksCount = tanksCount
    if (tanksCount === 2) {
      waterForm.enableDrainControl = false
    }
  }

  const cleanTankFill = readNumber(irrigationTargets?.clean_tank_fill_l)
  if (cleanTankFill !== null) {
    waterForm.cleanTankFillL = clamp(Math.round(cleanTankFill), 10, 5000)
  }

  const nutrientTankTarget = readNumber(irrigationTargets?.nutrient_tank_target_l)
  if (nutrientTankTarget !== null) {
    waterForm.nutrientTankTargetL = clamp(Math.round(nutrientTankTarget), 10, 5000)
  }

  const irrigationBatch = readNumber(irrigationTargets?.irrigation_batch_l)
  if (irrigationBatch !== null) {
    waterForm.irrigationBatchL = clamp(Math.round(irrigationBatch), 1, 500)
  }

  const fillTemperature = readNumber(irrigationTargets?.fill_temperature_c)
  if (fillTemperature !== null) {
    waterForm.fillTemperatureC = clamp(fillTemperature, 5, 35)
  }

  const irrigationSchedule = asArray(irrigationTargets?.schedule)
  const firstIrrigationWindow = asRecord(irrigationSchedule?.[0])
  const fillStart = toTimeHHmm(firstIrrigationWindow?.start)
  const fillEnd = toTimeHHmm(firstIrrigationWindow?.end)
  if (fillStart) {
    waterForm.fillWindowStart = fillStart
  }
  if (fillEnd) {
    waterForm.fillWindowEnd = fillEnd
  }

  const correctionNode = asRecord(irrigationTargets?.correction_node)
  const correctionPh = readNumber(correctionNode?.target_ph)
  const correctionEc = readNumber(correctionNode?.target_ec)
  if (correctionPh !== null) {
    waterForm.targetPh = clamp(correctionPh, 4, 9)
  }
  if (correctionEc !== null) {
    waterForm.targetEc = clamp(correctionEc, 0.1, 10)
  }

  const valveSwitching = readBoolean(irrigationTargets?.valve_switching_enabled)
  if (valveSwitching !== null) {
    waterForm.valveSwitching = valveSwitching
  }
  const correctionDuringIrrigation = readBoolean(irrigationTargets?.correction_during_irrigation)
  if (correctionDuringIrrigation !== null) {
    waterForm.correctionDuringIrrigation = correctionDuringIrrigation
  }

  const drainControl = asRecord(irrigationTargets?.drain_control)
  const drainEnabled = readBoolean(drainControl?.enabled)
  const drainTarget = readNumber(drainControl?.target_percent)
  if (drainEnabled !== null) {
    waterForm.enableDrainControl = drainEnabled
  }
  if (drainTarget !== null) {
    waterForm.drainTargetPercent = clamp(drainTarget, 0, 100)
  }

  const climateRequest = asRecord(targets.climate_request)
  const climateEnabled = readBoolean(climateSubsystem?.enabled)
  if (climateEnabled !== null) {
    climateForm.enabled = climateEnabled
  }

  const temperature = asRecord(climateTargets?.temperature)
  const humidity = asRecord(climateTargets?.humidity)
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

  const ventControl = asRecord(climateTargets?.vent_control)
  const ventMinPercent = readNumber(ventControl?.min_open_percent)
  const ventMaxPercent = readNumber(ventControl?.max_open_percent)
  if (ventMinPercent !== null) {
    climateForm.ventMinPercent = clamp(Math.round(ventMinPercent), 0, 100)
  }
  if (ventMaxPercent !== null) {
    climateForm.ventMaxPercent = clamp(Math.round(ventMaxPercent), 0, 100)
  }

  const externalGuard = asRecord(climateTargets?.external_guard)
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

  const climateSchedule = asArray(climateTargets?.schedule)
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

  const manualOverride = asRecord(climateTargets?.manual_override)
  const manualOverrideEnabled = readBoolean(manualOverride?.enabled)
  const overrideMinutes = readNumber(manualOverride?.timeout_minutes)
  if (manualOverrideEnabled !== null) {
    climateForm.manualOverrideEnabled = manualOverrideEnabled
  }
  if (overrideMinutes !== null) {
    climateForm.overrideMinutes = clamp(Math.round(overrideMinutes), 5, 120)
  }

  const lighting = asRecord(targets.lighting)
  const lightingEnabled = readBoolean(lightingSubsystem?.enabled)
  if (lightingEnabled !== null) {
    lightingForm.enabled = lightingEnabled
  }

  const lux = asRecord(lightingTargets?.lux)
  const luxDay = readNumber(lux?.day)
  const luxNight = readNumber(lux?.night)
  if (luxDay !== null) {
    lightingForm.luxDay = clamp(Math.round(luxDay), 0, 120000)
  }
  if (luxNight !== null) {
    lightingForm.luxNight = clamp(Math.round(luxNight), 0, 120000)
  }

  const photoperiod = asRecord(lightingTargets?.photoperiod)
  const hoursOn = readNumber(photoperiod?.hours_on, lighting?.photoperiod_hours, (targets as Dictionary).light_hours)
  if (hoursOn !== null) {
    lightingForm.hoursOn = clamp(hoursOn, 0, 24)
  }

  const lightingSchedule = asArray(lightingTargets?.schedule)
  const firstLightingWindow = asRecord(lightingSchedule?.[0])
  const scheduleStart = toTimeHHmm(firstLightingWindow?.start ?? lighting?.start_time)
  const scheduleEnd = toTimeHHmm(firstLightingWindow?.end)
  if (scheduleStart) {
    lightingForm.scheduleStart = scheduleStart
  }
  if (scheduleEnd) {
    lightingForm.scheduleEnd = scheduleEnd
  }
}

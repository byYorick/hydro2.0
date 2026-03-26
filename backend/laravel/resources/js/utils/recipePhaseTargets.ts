function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object') {
    return null
  }

  return value as Record<string, unknown>
}

function toFiniteNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }

  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }

  return null
}

function hasKeys(value: Record<string, unknown>): boolean {
  return Object.keys(value).length > 0
}

function getCurrentPhaseRecord(cycle: Record<string, unknown>): Record<string, unknown> | null {
  return asRecord(cycle.currentPhase ?? cycle.current_phase)
}

export function resolveRecipePhaseTargets(phase: unknown): Record<string, unknown> | null {
  const phaseRecord = asRecord(phase)
  if (!phaseRecord) {
    return null
  }

  const nestedTargets = asRecord(phaseRecord.targets)
  if (nestedTargets && hasKeys(nestedTargets)) {
    return nestedTargets
  }

  const targets: Record<string, unknown> = {}

  const phTarget = toFiniteNumber(phaseRecord.ph_target)
  const phMin = toFiniteNumber(phaseRecord.ph_min) ?? phTarget
  const phMax = toFiniteNumber(phaseRecord.ph_max) ?? phTarget
  if (phTarget !== null || phMin !== null || phMax !== null) {
    targets.ph = {
      target: phTarget,
      min: phMin,
      max: phMax,
    }
  }

  const ecTarget = toFiniteNumber(phaseRecord.ec_target)
  const ecMin = toFiniteNumber(phaseRecord.ec_min) ?? ecTarget
  const ecMax = toFiniteNumber(phaseRecord.ec_max) ?? ecTarget
  if (ecTarget !== null || ecMin !== null || ecMax !== null) {
    targets.ec = {
      target: ecTarget,
      min: ecMin,
      max: ecMax,
    }
  }

  const climateRequest: Record<string, unknown> = {}
  const tempAirTarget = toFiniteNumber(phaseRecord.temp_air_target)
  const humidityTarget = toFiniteNumber(phaseRecord.humidity_target)
  const co2Target = toFiniteNumber(phaseRecord.co2_target)

  if (tempAirTarget !== null) {
    climateRequest.temp_air_target = tempAirTarget
    targets.temp_air = tempAirTarget
  }

  if (humidityTarget !== null) {
    climateRequest.humidity_target = humidityTarget
    targets.humidity_air = humidityTarget
  }

  if (co2Target !== null) {
    climateRequest.co2_target = co2Target
  }

  if (hasKeys(climateRequest)) {
    targets.climate_request = climateRequest
  }

  const lightingPhotoperiodHours = toFiniteNumber(phaseRecord.lighting_photoperiod_hours)
  const lightingStartTime = typeof phaseRecord.lighting_start_time === 'string'
    ? phaseRecord.lighting_start_time
    : null

  if (lightingPhotoperiodHours !== null) {
    targets.light_hours = lightingPhotoperiodHours
  }

  if (lightingPhotoperiodHours !== null || lightingStartTime !== null) {
    targets.lighting = {
      photoperiod_hours: lightingPhotoperiodHours,
      start_time: lightingStartTime,
    }
  }

  const irrigationMode = typeof phaseRecord.irrigation_mode === 'string'
    ? phaseRecord.irrigation_mode
    : null
  const irrigationIntervalSec = toFiniteNumber(phaseRecord.irrigation_interval_sec)
  const irrigationDurationSec = toFiniteNumber(phaseRecord.irrigation_duration_sec)

  if (irrigationIntervalSec !== null) {
    targets.irrigation_interval_sec = irrigationIntervalSec
  }

  if (irrigationDurationSec !== null) {
    targets.irrigation_duration_sec = irrigationDurationSec
  }

  if (irrigationMode !== null || irrigationIntervalSec !== null || irrigationDurationSec !== null) {
    targets.irrigation = {
      mode: irrigationMode,
      interval_sec: irrigationIntervalSec,
      duration_sec: irrigationDurationSec,
    }
  }

  return hasKeys(targets) ? targets : null
}

export function resolveCurrentRecipePhase(cycle: unknown): Record<string, unknown> | null {
  const cycleRecord = asRecord(cycle)
  if (!cycleRecord) {
    return null
  }

  const currentPhase = getCurrentPhaseRecord(cycleRecord)
  const recipeRevision = asRecord(cycleRecord.recipeRevision ?? cycleRecord.recipe_revision)
  const phases = Array.isArray(recipeRevision?.phases) ? recipeRevision.phases : []

  if (!currentPhase || phases.length === 0) {
    return null
  }

  const recipeRevisionPhaseId = toFiniteNumber(currentPhase.recipe_revision_phase_id)
  if (recipeRevisionPhaseId !== null) {
    const byId = phases.find((phase) => toFiniteNumber(asRecord(phase)?.id) === recipeRevisionPhaseId)
    const phaseRecord = asRecord(byId)
    if (phaseRecord) {
      return phaseRecord
    }
  }

  const phaseIndex = toFiniteNumber(currentPhase.phase_index)
  if (phaseIndex !== null) {
    const byIndex = phases.find((phase) => toFiniteNumber(asRecord(phase)?.phase_index) === phaseIndex)
    const phaseRecord = asRecord(byIndex)
    if (phaseRecord) {
      return phaseRecord
    }
  }

  return null
}

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

function toTimeHHmm(value: unknown): string | null {
  if (typeof value !== 'string' || value.trim() === '') {
    return null
  }

  const match = value.trim().match(/^(\d{1,2}):(\d{2})/)
  if (!match) {
    return null
  }

  const h = Number(match[1])
  const m = Number(match[2])
  if (!Number.isFinite(h) || !Number.isFinite(m) || h < 0 || h > 23 || m < 0 || m > 59) {
    return null
  }

  return `${match[1].padStart(2, '0')}:${match[2]}`
}

function addHours(time: string, hours: number): string {
  const [h, m] = time.split(':').map(Number)
  const total = (h * 60 + m + Math.round(hours * 60)) % (24 * 60)
  const normalized = total < 0 ? total + 24 * 60 : total
  return `${String(Math.floor(normalized / 60)).padStart(2, '0')}:${String(normalized % 60).padStart(2, '0')}`
}

function mergeClimateTargetsFromDayNight(
  targets: Record<string, unknown>,
  phaseRecord: Record<string, unknown>,
): void {
  const extensions = asRecord(phaseRecord.extensions)
  const dayNight = asRecord(extensions?.day_night)
  if (!dayNight) {
    return
  }

  const climateTargets: Record<string, unknown> = {}
  const temperature = asRecord(dayNight.temperature)
  const tempDay = toFiniteNumber(temperature?.day)
  const tempNight = toFiniteNumber(temperature?.night)
  if (tempDay !== null || tempNight !== null) {
    climateTargets.temperature = {
      ...(tempDay !== null ? { day: tempDay } : {}),
      ...(tempNight !== null ? { night: tempNight } : {}),
    }
  }

  const humidity = asRecord(dayNight.humidity)
  const humidityDay = toFiniteNumber(humidity?.day)
  const humidityNight = toFiniteNumber(humidity?.night)
  if (humidityDay !== null || humidityNight !== null) {
    climateTargets.humidity = {
      ...(humidityDay !== null ? { day: humidityDay } : {}),
      ...(humidityNight !== null ? { night: humidityNight } : {}),
    }
  }

  const lighting = asRecord(dayNight.lighting)
  const dayStart = toTimeHHmm(lighting?.day_start_time)
  const dayHours = toFiniteNumber(lighting?.day_hours)
  if (dayStart !== null) {
    climateTargets.schedule = [
      { profile: 'day', start: dayStart },
      ...(dayHours !== null ? [{ profile: 'night', start: addHours(dayStart, dayHours) }] : []),
    ]
  }

  if (!hasKeys(climateTargets)) {
    return
  }

  const targetExtensions = asRecord(targets.extensions) ?? {}
  const subsystems = asRecord(targetExtensions.subsystems) ?? {}
  const climate = asRecord(subsystems.climate) ?? {}
  const existingTargets = asRecord(climate.targets) ?? {}

  targets.extensions = {
    ...targetExtensions,
    subsystems: {
      ...subsystems,
      climate: {
        ...climate,
        targets: {
          ...existingTargets,
          ...climateTargets,
        },
      },
    },
  }
}

export function resolveRecipePhaseTargets(phase: unknown): Record<string, unknown> | null {
  const phaseRecord = asRecord(phase)
  if (!phaseRecord) {
    return null
  }

  const nestedTargets = asRecord(phaseRecord.targets)
  const targets: Record<string, unknown> = nestedTargets && hasKeys(nestedTargets)
    ? { ...nestedTargets }
    : {}

  const phTarget = toFiniteNumber(phaseRecord.ph_target)
  const phMin = toFiniteNumber(phaseRecord.ph_min) ?? phTarget
  const phMax = toFiniteNumber(phaseRecord.ph_max) ?? phTarget
  if (!('ph' in targets) && (phTarget !== null || phMin !== null || phMax !== null)) {
    targets.ph = {
      target: phTarget,
      min: phMin,
      max: phMax,
    }
  }

  const ecTarget = toFiniteNumber(phaseRecord.ec_target)
  const ecMin = toFiniteNumber(phaseRecord.ec_min) ?? ecTarget
  const ecMax = toFiniteNumber(phaseRecord.ec_max) ?? ecTarget
  if (!('ec' in targets) && (ecTarget !== null || ecMin !== null || ecMax !== null)) {
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
    if (!('temp_air' in targets)) {
      targets.temp_air = tempAirTarget
    }
    climateRequest.temp_air_target = tempAirTarget
  }

  if (humidityTarget !== null) {
    if (!('humidity_air' in targets)) {
      targets.humidity_air = humidityTarget
    }
    climateRequest.humidity_target = humidityTarget
  }

  if (co2Target !== null) {
    climateRequest.co2_target = co2Target
  }

  if (!('climate_request' in targets) && hasKeys(climateRequest)) {
    targets.climate_request = climateRequest
  }

  const lightingPhotoperiodHours = toFiniteNumber(phaseRecord.lighting_photoperiod_hours)
  const lightingStartTime = typeof phaseRecord.lighting_start_time === 'string'
    ? phaseRecord.lighting_start_time
    : null

  if (!('light_hours' in targets) && lightingPhotoperiodHours !== null) {
    targets.light_hours = lightingPhotoperiodHours
  }

  if (!('lighting' in targets) && (lightingPhotoperiodHours !== null || lightingStartTime !== null)) {
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

  if (!('irrigation_interval_sec' in targets) && irrigationIntervalSec !== null) {
    targets.irrigation_interval_sec = irrigationIntervalSec
  }

  if (!('irrigation_duration_sec' in targets) && irrigationDurationSec !== null) {
    targets.irrigation_duration_sec = irrigationDurationSec
  }

  if (!('irrigation' in targets) && (irrigationMode !== null || irrigationIntervalSec !== null || irrigationDurationSec !== null)) {
    targets.irrigation = {
      mode: irrigationMode,
      interval_sec: irrigationIntervalSec,
      duration_sec: irrigationDurationSec,
    }
  }

  mergeClimateTargetsFromDayNight(targets, phaseRecord)

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

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

function readArrayLength(value: unknown): number | null {
  const items = asArray(value)
  if (!items) {
    return null
  }

  return items.length
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

function readStringList(...values: unknown[]): string[] | null {
  for (const value of values) {
    if (Array.isArray(value)) {
      const items = value
        .map((item) => (typeof item === 'string' ? item.trim() : String(item ?? '').trim()))
        .filter((item) => item.length > 0)
      if (items.length > 0) {
        return items
      }
      continue
    }

    if (typeof value === 'string' && value.trim() !== '') {
      const items = value
        .split(',')
        .map((item) => item.trim())
        .filter((item) => item.length > 0)
      if (items.length > 0) {
        return items
      }
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

  const h = Number(match[1])
  const m = Number(match[2])
  if (h < 0 || h > 23 || m < 0 || m > 59) {
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
  const irrigationExecution = asRecord(irrigationSubsystem?.execution)
  const irrigationTargets = asRecord(irrigationSubsystem?.targets)
  const irrigationBehavior = irrigationExecution ?? irrigationTargets
  const irrigationDecision = asRecord(irrigationSubsystem?.decision)
  const irrigationDecisionConfig = asRecord(irrigationDecision?.config)
  const irrigationRecoveryPolicy = asRecord(irrigationSubsystem?.recovery)
  const irrigationSafety = asRecord(irrigationSubsystem?.safety)
  const climateSubsystem = asRecord(subsystems?.climate)
  const climateExecution = asRecord(climateSubsystem?.execution)
  const climateTargets = asRecord(climateSubsystem?.targets)
  const climateBehavior = climateExecution ?? climateTargets
  const lightingSubsystem = asRecord(subsystems?.lighting)
  const lightingExecution = asRecord(lightingSubsystem?.execution)
  const lightingTargets = asRecord(lightingSubsystem?.targets)
  const lightingBehavior = lightingExecution ?? lightingTargets
  const diagnosticsSubsystem = asRecord(subsystems?.diagnostics)
  const diagnosticsExecution = asRecord(diagnosticsSubsystem?.execution)
  const diagnosticsTargets = asRecord(diagnosticsSubsystem?.targets)
  const diagnosticsBehavior = diagnosticsExecution ?? diagnosticsTargets
  const solutionSubsystem = asRecord(subsystems?.solution_change ?? subsystems?.solution)
  const solutionExecution = asRecord(solutionSubsystem?.execution)
  const solutionTargets = asRecord(solutionSubsystem?.targets)
  const solutionBehavior = solutionExecution ?? solutionTargets

  const phTarget = asRecord(targets.ph)
  const phValue = readNumber(phTarget?.target)
  if (phValue !== null) {
    waterForm.targetPh = clamp(phValue, 4, 9)
  }

  const ecTarget = asRecord(targets.ec)
  const ecValue = readNumber(ecTarget?.target)
  if (ecValue !== null) {
    waterForm.targetEc = clamp(ecValue, 0.1, 10)
  }

  const irrigation = asRecord(targets.irrigation)
  const intervalSec = readNumber(
    irrigationBehavior?.interval_sec,
    irrigationBehavior?.interval_seconds,
    irrigationTargets?.interval_sec,
    irrigationTargets?.interval_seconds,
    irrigation?.interval_sec,
    (targets as Dictionary).irrigation_interval_sec
  )
  if (intervalSec !== null) {
    waterForm.intervalMinutes = clamp(Math.round(intervalSec / 60), 5, 1440)
  }

  const durationSec = readNumber(
    irrigationBehavior?.duration_sec,
    irrigationBehavior?.duration_seconds,
    irrigationTargets?.duration_sec,
    irrigationTargets?.duration_seconds,
    irrigation?.duration_sec,
    (targets as Dictionary).irrigation_duration_sec
  )
  if (durationSec !== null) {
    waterForm.durationSeconds = clamp(Math.round(durationSec), 1, 3600)
  }

  const systemType = asIrrigationSystem(readString(irrigationBehavior?.system_type, irrigationTargets?.system_type))
  if (systemType) {
    waterForm.systemType = systemType
    syncSystemToTankLayout(waterForm, systemType)
  }

  const tanksCount = readNumber(irrigationBehavior?.tanks_count, irrigationTargets?.tanks_count)
  if (tanksCount === 2 || tanksCount === 3) {
    waterForm.tanksCount = tanksCount
    if (tanksCount === 2) {
      waterForm.enableDrainControl = false
    }
  }

  const cleanTankFill = readNumber(irrigationBehavior?.clean_tank_fill_l, irrigationTargets?.clean_tank_fill_l)
  if (cleanTankFill !== null) {
    waterForm.cleanTankFillL = clamp(Math.round(cleanTankFill), 10, 5000)
  }

  const nutrientTankTarget = readNumber(irrigationBehavior?.nutrient_tank_target_l, irrigationTargets?.nutrient_tank_target_l)
  if (nutrientTankTarget !== null) {
    waterForm.nutrientTankTargetL = clamp(Math.round(nutrientTankTarget), 10, 5000)
  }

  const irrigationBatch = readNumber(irrigationBehavior?.irrigation_batch_l, irrigationTargets?.irrigation_batch_l)
  if (irrigationBatch !== null) {
    waterForm.irrigationBatchL = clamp(Math.round(irrigationBatch), 1, 500)
  }

  const fillTemperature = readNumber(irrigationBehavior?.fill_temperature_c, irrigationTargets?.fill_temperature_c)
  if (fillTemperature !== null) {
    waterForm.fillTemperatureC = clamp(fillTemperature, 5, 35)
  }

  const irrigationSchedule = asArray(irrigationBehavior?.schedule) ?? asArray(irrigationTargets?.schedule)
  const firstIrrigationWindow = asRecord(irrigationSchedule?.[0])
  const fillStart = toTimeHHmm(firstIrrigationWindow?.start)
  const fillEnd = toTimeHHmm(firstIrrigationWindow?.end)
  if (fillStart) {
    waterForm.fillWindowStart = fillStart
  }
  if (fillEnd) {
    waterForm.fillWindowEnd = fillEnd
  }

  const correctionNode = asRecord(irrigationBehavior?.correction_node) ?? asRecord(irrigationTargets?.correction_node)
  const correctionTolerance = asRecord(correctionNode?.target_tolerance)
  const correctionPhPct = readNumber(
    correctionTolerance?.ph_pct,
    correctionNode?.ph_pct,
    irrigationBehavior?.ph_pct,
    irrigationTargets?.ph_pct
  )
  const correctionEcPct = readNumber(
    correctionTolerance?.ec_pct,
    correctionNode?.ec_pct,
    irrigationBehavior?.ec_pct,
    irrigationTargets?.ec_pct
  )
  if (correctionPhPct !== null) {
    waterForm.phPct = clamp(correctionPhPct, 1, 50)
  }
  if (correctionEcPct !== null) {
    waterForm.ecPct = clamp(correctionEcPct, 1, 50)
  }

  const valveSwitching = readBoolean(irrigationBehavior?.valve_switching_enabled, irrigationTargets?.valve_switching_enabled)
  if (valveSwitching !== null) {
    waterForm.valveSwitching = valveSwitching
  }
  const correctionDuringIrrigation = readBoolean(
    irrigationBehavior?.correction_during_irrigation,
    irrigationTargets?.correction_during_irrigation
  )
  if (correctionDuringIrrigation !== null) {
    waterForm.correctionDuringIrrigation = correctionDuringIrrigation
  }
  const irrigationDecisionStrategy = readString(irrigationDecision?.strategy)
  if (irrigationDecisionStrategy === 'task' || irrigationDecisionStrategy === 'smart_soil_v1') {
    waterForm.irrigationDecisionStrategy = irrigationDecisionStrategy
  }
  const irrigationDecisionLookbackSeconds = readNumber(irrigationDecisionConfig?.lookback_sec)
  if (irrigationDecisionLookbackSeconds !== null) {
    waterForm.irrigationDecisionLookbackSeconds = clamp(Math.round(irrigationDecisionLookbackSeconds), 60, 86400)
  }
  const irrigationDecisionMinSamples = readNumber(irrigationDecisionConfig?.min_samples)
  if (irrigationDecisionMinSamples !== null) {
    waterForm.irrigationDecisionMinSamples = clamp(Math.round(irrigationDecisionMinSamples), 1, 100)
  }
  const irrigationDecisionStaleAfterSeconds = readNumber(irrigationDecisionConfig?.stale_after_sec)
  if (irrigationDecisionStaleAfterSeconds !== null) {
    waterForm.irrigationDecisionStaleAfterSeconds = clamp(Math.round(irrigationDecisionStaleAfterSeconds), 30, 86400)
  }
  const irrigationDecisionHysteresisPct = readNumber(irrigationDecisionConfig?.hysteresis_pct)
  if (irrigationDecisionHysteresisPct !== null) {
    waterForm.irrigationDecisionHysteresisPct = clamp(irrigationDecisionHysteresisPct, 0, 100)
  }
  const irrigationDecisionSpreadAlertThresholdPct = readNumber(irrigationDecisionConfig?.spread_alert_threshold_pct)
  if (irrigationDecisionSpreadAlertThresholdPct !== null) {
    waterForm.irrigationDecisionSpreadAlertThresholdPct = clamp(irrigationDecisionSpreadAlertThresholdPct, 0, 100)
  }
  const irrigationAutoReplayAfterSetup = readBoolean(irrigationRecoveryPolicy?.auto_replay_after_setup)
  if (irrigationAutoReplayAfterSetup !== null) {
    waterForm.irrigationAutoReplayAfterSetup = irrigationAutoReplayAfterSetup
  }
  const irrigationMaxSetupReplays = readNumber(irrigationRecoveryPolicy?.max_setup_replays)
  if (irrigationMaxSetupReplays !== null) {
    waterForm.irrigationMaxSetupReplays = clamp(Math.round(irrigationMaxSetupReplays), 0, 10)
  }
  const irrigationStopOnSolutionMin = readBoolean(irrigationSafety?.stop_on_solution_min)
  if (irrigationStopOnSolutionMin !== null) {
    waterForm.stopOnSolutionMin = irrigationStopOnSolutionMin
  }

  const drainControl = asRecord(irrigationBehavior?.drain_control) ?? asRecord(irrigationTargets?.drain_control)
  const drainEnabled = readBoolean(drainControl?.enabled)
  const drainTarget = readNumber(drainControl?.target_percent)
  if (drainEnabled !== null) {
    waterForm.enableDrainControl = drainEnabled
  }
  if (drainTarget !== null) {
    waterForm.drainTargetPercent = clamp(drainTarget, 0, 100)
  }

  const climateRequest = asRecord(targets.climate_request)
  const ventilation = asRecord(targets.ventilation)
  const climateEnabled = readBoolean(climateSubsystem?.enabled)
  if (climateEnabled !== null) {
    climateForm.enabled = climateEnabled
  }

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

  const climateIntervalSec = readNumber(climateBehavior?.interval_sec, climateTargets?.interval_sec, ventilation?.interval_sec)
  if (climateIntervalSec !== null) {
    climateForm.intervalMinutes = clamp(Math.round(climateIntervalSec / 60), 1, 1440)
  }

  const ventControl = asRecord(climateBehavior?.vent_control) ?? asRecord(climateTargets?.vent_control)
  const ventMinPercent = readNumber(ventControl?.min_open_percent)
  const ventMaxPercent = readNumber(ventControl?.max_open_percent)
  if (ventMinPercent !== null) {
    climateForm.ventMinPercent = clamp(Math.round(ventMinPercent), 0, 100)
  }
  if (ventMaxPercent !== null) {
    climateForm.ventMaxPercent = clamp(Math.round(ventMaxPercent), 0, 100)
  }

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

  const manualOverride = asRecord(climateBehavior?.manual_override) ?? asRecord(climateTargets?.manual_override)
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

  const lightingIntervalSec = readNumber(lightingBehavior?.interval_sec, lightingTargets?.interval_sec, lighting?.interval_sec)
  if (lightingIntervalSec !== null) {
    lightingForm.intervalMinutes = clamp(Math.round(lightingIntervalSec / 60), 1, 1440)
  }

  const lux = asRecord(lightingBehavior?.lux) ?? asRecord(lightingTargets?.lux)
  const luxDay = readNumber(lux?.day)
  const luxNight = readNumber(lux?.night)
  if (luxDay !== null) {
    lightingForm.luxDay = clamp(Math.round(luxDay), 0, 120000)
  }
  if (luxNight !== null) {
    lightingForm.luxNight = clamp(Math.round(luxNight), 0, 120000)
  }

  const photoperiod = asRecord(lightingBehavior?.photoperiod) ?? asRecord(lightingTargets?.photoperiod)
  const hoursOn = readNumber(photoperiod?.hours_on, lighting?.photoperiod_hours, (targets as Dictionary).light_hours)
  if (hoursOn !== null) {
    lightingForm.hoursOn = clamp(hoursOn, 0, 24)
  }

  const lightingSchedule = asArray(lightingBehavior?.schedule) ?? asArray(lightingTargets?.schedule)
  const firstLightingWindow = asRecord(lightingSchedule?.[0])
  const scheduleStart = toTimeHHmm(firstLightingWindow?.start ?? lighting?.start_time)
  const scheduleEnd = toTimeHHmm(firstLightingWindow?.end)
  if (scheduleStart) {
    lightingForm.scheduleStart = scheduleStart
  }
  if (scheduleEnd) {
    lightingForm.scheduleEnd = scheduleEnd
  }

  const diagnostics = asRecord(targets.diagnostics)
  const diagnosticsEnabled = readBoolean(diagnosticsSubsystem?.enabled)
  if (diagnosticsEnabled !== null) {
    waterForm.diagnosticsEnabled = diagnosticsEnabled
  }

  const diagnosticsIntervalSec = readNumber(
    diagnosticsBehavior?.interval_sec,
    diagnosticsTargets?.interval_sec,
    diagnostics?.interval_sec
  )
  if (diagnosticsIntervalSec !== null) {
    waterForm.diagnosticsIntervalMinutes = clamp(Math.round(diagnosticsIntervalSec / 60), 1, 1440)
  }

  const diagnosticsExecutionResolved = asRecord(diagnosticsBehavior?.execution) ?? diagnosticsBehavior
  const diagnosticsWorkflow = readString(
    diagnosticsBehavior?.workflow,
    diagnosticsTargets?.workflow,
    diagnosticsExecutionResolved?.workflow,
    asRecord(diagnostics?.execution)?.workflow
  )
  if (
    diagnosticsWorkflow === 'startup' ||
    diagnosticsWorkflow === 'cycle_start' ||
    diagnosticsWorkflow === 'diagnostics'
  ) {
    waterForm.diagnosticsWorkflow = diagnosticsWorkflow
  }

  const cleanTankThreshold = readNumber(
    diagnosticsBehavior?.clean_tank_full_threshold,
    diagnosticsTargets?.clean_tank_full_threshold,
    diagnosticsExecutionResolved?.clean_tank_full_threshold
  )
  if (cleanTankThreshold !== null) {
    waterForm.cleanTankFullThreshold = clamp(cleanTankThreshold, 0.05, 1)
  }

  const refillDurationSec = readNumber(
    diagnosticsBehavior?.refill_duration_sec,
    diagnosticsTargets?.refill_duration_sec,
    diagnosticsExecutionResolved?.refill_duration_sec,
    asRecord(diagnosticsExecutionResolved?.refill)?.duration_sec
  )
  if (refillDurationSec !== null) {
    waterForm.refillDurationSeconds = clamp(Math.round(refillDurationSec), 1, 3600)
  }

  const refillTimeoutSec = readNumber(
    diagnosticsBehavior?.refill_timeout_sec,
    diagnosticsTargets?.refill_timeout_sec,
    diagnosticsExecutionResolved?.refill_timeout_sec,
    asRecord(diagnosticsExecutionResolved?.refill)?.timeout_sec
  )
  if (refillTimeoutSec !== null) {
    waterForm.refillTimeoutSeconds = clamp(Math.round(refillTimeoutSec), 30, 86400)
  }

  const refillRequiredNodeTypes = readStringList(
    diagnosticsBehavior?.required_node_types,
    diagnosticsTargets?.required_node_types,
    diagnosticsExecutionResolved?.required_node_types
  )
  if (refillRequiredNodeTypes && refillRequiredNodeTypes.length > 0) {
    waterForm.refillRequiredNodeTypes = refillRequiredNodeTypes.join(',')
  }

  const refillConfig = asRecord(diagnosticsBehavior?.refill)
    ?? asRecord(diagnosticsTargets?.refill)
    ?? asRecord(diagnosticsExecutionResolved?.refill)
  const refillChannel = readString(refillConfig?.channel)
  if (refillChannel !== null) {
    waterForm.refillPreferredChannel = refillChannel
  }

  const startup = asRecord(diagnosticsExecutionResolved?.startup)
  const startupCleanFillTimeoutSec = readNumber(startup?.clean_fill_timeout_sec)
  if (startupCleanFillTimeoutSec !== null) {
    waterForm.startupCleanFillTimeoutSeconds = clamp(Math.round(startupCleanFillTimeoutSec), 30, 86400)
  }
  const startupSolutionFillTimeoutSec = readNumber(startup?.solution_fill_timeout_sec)
  if (startupSolutionFillTimeoutSec !== null) {
    waterForm.startupSolutionFillTimeoutSeconds = clamp(Math.round(startupSolutionFillTimeoutSec), 30, 86400)
  }
  const startupPrepareRecirculationTimeoutSec = readNumber(startup?.prepare_recirculation_timeout_sec)
  if (startupPrepareRecirculationTimeoutSec !== null) {
    waterForm.startupPrepareRecirculationTimeoutSeconds = clamp(Math.round(startupPrepareRecirculationTimeoutSec), 30, 86400)
  }
  const startupCleanFillRetryCycles = readNumber(startup?.clean_fill_retry_cycles)
  if (startupCleanFillRetryCycles !== null) {
    waterForm.startupCleanFillRetryCycles = clamp(Math.round(startupCleanFillRetryCycles), 0, 20)
  }

  const prepareTolerance = asRecord(diagnosticsExecutionResolved?.prepare_tolerance)
  const prepareToleranceEcPct = readNumber(prepareTolerance?.ec_pct)
  if (prepareToleranceEcPct !== null) {
    waterForm.prepareToleranceEcPct = clamp(prepareToleranceEcPct, 0.1, 100)
  }
  const prepareTolerancePhPct = readNumber(prepareTolerance?.ph_pct)
  if (prepareTolerancePhPct !== null) {
    waterForm.prepareTolerancePhPct = clamp(prepareTolerancePhPct, 0.1, 100)
  }

  const correction = asRecord(diagnosticsExecutionResolved?.correction)
  const correctionMaxEcCorrectionAttempts = readNumber(correction?.max_ec_correction_attempts)
  if (correctionMaxEcCorrectionAttempts !== null) {
    waterForm.correctionMaxEcCorrectionAttempts = clamp(Math.round(correctionMaxEcCorrectionAttempts), 1, 50)
  }
  const correctionMaxPhCorrectionAttempts = readNumber(correction?.max_ph_correction_attempts)
  if (correctionMaxPhCorrectionAttempts !== null) {
    waterForm.correctionMaxPhCorrectionAttempts = clamp(Math.round(correctionMaxPhCorrectionAttempts), 1, 50)
  }
  const correctionPrepareRecirculationMaxAttempts = readNumber(correction?.prepare_recirculation_max_attempts)
  if (correctionPrepareRecirculationMaxAttempts !== null) {
    waterForm.correctionPrepareRecirculationMaxAttempts = clamp(
      Math.round(correctionPrepareRecirculationMaxAttempts),
      1,
      50
    )
  }
  const correctionPrepareRecirculationMaxCorrectionAttempts = readNumber(
    correction?.prepare_recirculation_max_correction_attempts
  )
  if (correctionPrepareRecirculationMaxCorrectionAttempts !== null) {
    waterForm.correctionPrepareRecirculationMaxCorrectionAttempts = clamp(
      Math.round(correctionPrepareRecirculationMaxCorrectionAttempts),
      1,
      500
    )
  }
  const correctionStabilizationSec = readNumber(correction?.stabilization_sec)
  if (correctionStabilizationSec !== null) {
    waterForm.correctionStabilizationSec = clamp(Math.round(correctionStabilizationSec), 0, 3600)
  }

  const irrigationRecovery = asRecord(diagnosticsExecutionResolved?.irrigation_recovery)
  const irrigationRecoveryMaxContinueAttempts = readNumber(irrigationRecovery?.max_continue_attempts)
  if (irrigationRecoveryMaxContinueAttempts !== null) {
    waterForm.irrigationRecoveryMaxContinueAttempts = clamp(
      Math.round(irrigationRecoveryMaxContinueAttempts),
      1,
      30
    )
  }
  const irrigationRecoveryTimeoutSec = readNumber(irrigationRecovery?.timeout_sec)
  if (irrigationRecoveryTimeoutSec !== null) {
    waterForm.irrigationRecoveryTimeoutSeconds = clamp(Math.round(irrigationRecoveryTimeoutSec), 30, 86400)
  }

  const twoTankCommands = asRecord(diagnosticsExecutionResolved?.two_tank_commands)
  const twoTankIrrigationStartSteps = readArrayLength(twoTankCommands?.irrigation_start)
  if (twoTankIrrigationStartSteps !== null) {
    waterForm.twoTankIrrigationStartSteps = clamp(twoTankIrrigationStartSteps, 1, 12)
  }
  const twoTankIrrigationStopSteps = readArrayLength(twoTankCommands?.irrigation_stop)
  if (twoTankIrrigationStopSteps !== null) {
    waterForm.twoTankIrrigationStopSteps = clamp(twoTankIrrigationStopSteps, 1, 12)
  }
  const twoTankCleanFillStartSteps = readArrayLength(twoTankCommands?.clean_fill_start)
  if (twoTankCleanFillStartSteps !== null) {
    waterForm.twoTankCleanFillStartSteps = clamp(twoTankCleanFillStartSteps, 1, 12)
  }
  const twoTankCleanFillStopSteps = readArrayLength(twoTankCommands?.clean_fill_stop)
  if (twoTankCleanFillStopSteps !== null) {
    waterForm.twoTankCleanFillStopSteps = clamp(twoTankCleanFillStopSteps, 1, 12)
  }
  const twoTankSolutionFillStartSteps = readArrayLength(twoTankCommands?.solution_fill_start)
  if (twoTankSolutionFillStartSteps !== null) {
    waterForm.twoTankSolutionFillStartSteps = clamp(twoTankSolutionFillStartSteps, 1, 12)
  }
  const twoTankSolutionFillStopSteps = readArrayLength(twoTankCommands?.solution_fill_stop)
  if (twoTankSolutionFillStopSteps !== null) {
    waterForm.twoTankSolutionFillStopSteps = clamp(twoTankSolutionFillStopSteps, 1, 12)
  }
  const twoTankPrepareRecirculationStartSteps = readArrayLength(twoTankCommands?.prepare_recirculation_start)
  if (twoTankPrepareRecirculationStartSteps !== null) {
    waterForm.twoTankPrepareRecirculationStartSteps = clamp(twoTankPrepareRecirculationStartSteps, 1, 12)
  }
  const twoTankPrepareRecirculationStopSteps = readArrayLength(twoTankCommands?.prepare_recirculation_stop)
  if (twoTankPrepareRecirculationStopSteps !== null) {
    waterForm.twoTankPrepareRecirculationStopSteps = clamp(twoTankPrepareRecirculationStopSteps, 1, 12)
  }
  const twoTankIrrigationRecoveryStartSteps = readArrayLength(twoTankCommands?.irrigation_recovery_start)
  if (twoTankIrrigationRecoveryStartSteps !== null) {
    waterForm.twoTankIrrigationRecoveryStartSteps = clamp(twoTankIrrigationRecoveryStartSteps, 1, 12)
  }
  const twoTankIrrigationRecoveryStopSteps = readArrayLength(twoTankCommands?.irrigation_recovery_stop)
  if (twoTankIrrigationRecoveryStopSteps !== null) {
    waterForm.twoTankIrrigationRecoveryStopSteps = clamp(twoTankIrrigationRecoveryStopSteps, 1, 12)
  }

  const solutionChange = asRecord(targets.solution_change)
  const solutionEnabled = readBoolean(solutionSubsystem?.enabled)
  if (solutionEnabled !== null) {
    waterForm.solutionChangeEnabled = solutionEnabled
  }

  const solutionIntervalSec = readNumber(solutionBehavior?.interval_sec, solutionTargets?.interval_sec, solutionChange?.interval_sec)
  if (solutionIntervalSec !== null) {
    waterForm.solutionChangeIntervalMinutes = clamp(Math.round(solutionIntervalSec / 60), 1, 1440)
  }

  const solutionDurationSec = readNumber(solutionBehavior?.duration_sec, solutionTargets?.duration_sec, solutionChange?.duration_sec)
  if (solutionDurationSec !== null) {
    waterForm.solutionChangeDurationSeconds = clamp(Math.round(solutionDurationSec), 1, 86400)
  }
}

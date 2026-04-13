/**
 * Парсер подсистемы irrigation из recipe automation targets.
 *
 * Извлечён из applyAutomationFromRecipe (zoneAutomationTargetsParser.ts).
 * Самая большая подсистема — читает 12 секций:
 * interval/duration, system_type+tanks, volumes, fill temperature, schedule,
 * correction tolerances, valve switching, decision strategy + config,
 * recovery policy, safety, drain control.
 */

import { clamp } from '@/services/automation/parsingUtils'
import {
  asArray,
  asRecord,
  readBoolean,
  readNumber,
  readString,
  toTimeHHmm,
  type Dictionary,
} from '@/services/automation/dictReaders'
import { syncSystemToTankLayout } from '@/services/automation/tankLayout'
import type { IrrigationSystem, WaterFormState } from '@/composables/zoneAutomationTypes'

function asIrrigationSystem(value: unknown): IrrigationSystem | null {
  if (value === 'drip' || value === 'substrate_trays' || value === 'nft') {
    return value
  }

  return null
}

export function applyIrrigationFromTargets(targets: Dictionary, waterForm: WaterFormState): void {
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
  const irrigation = asRecord(targets.irrigation)

  applyIntervalAndDuration(irrigationBehavior, irrigationTargets, irrigation, targets, waterForm)
  applySystemAndTanks(irrigationBehavior, irrigationTargets, waterForm)
  applyVolumes(irrigationBehavior, irrigationTargets, waterForm)
  applyFillTemperatureAndSchedule(irrigationBehavior, irrigationTargets, waterForm)
  applyCorrectionTolerances(irrigationBehavior, irrigationTargets, waterForm)
  applyToggles(irrigationBehavior, irrigationTargets, waterForm)
  applyDecision(irrigationDecision, irrigationDecisionConfig, waterForm)
  applyRecoveryAndSafety(irrigationRecoveryPolicy, irrigationSafety, waterForm)
  applyDrainControl(irrigationBehavior, irrigationTargets, waterForm)
}

function applyIntervalAndDuration(
  irrigationBehavior: Dictionary | null,
  irrigationTargets: Dictionary | null,
  irrigation: Dictionary | null,
  targets: Dictionary,
  waterForm: WaterFormState,
): void {
  const intervalSec = readNumber(
    irrigationBehavior?.interval_sec,
    irrigationBehavior?.interval_seconds,
    irrigationTargets?.interval_sec,
    irrigationTargets?.interval_seconds,
    irrigation?.interval_sec,
    targets.irrigation_interval_sec,
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
    targets.irrigation_duration_sec,
  )
  if (durationSec !== null) {
    waterForm.durationSeconds = clamp(Math.round(durationSec), 1, 3600)
  }
}

function applySystemAndTanks(
  irrigationBehavior: Dictionary | null,
  irrigationTargets: Dictionary | null,
  waterForm: WaterFormState,
): void {
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
}

function applyVolumes(
  irrigationBehavior: Dictionary | null,
  irrigationTargets: Dictionary | null,
  waterForm: WaterFormState,
): void {
  const cleanTankFill = readNumber(irrigationBehavior?.clean_tank_fill_l, irrigationTargets?.clean_tank_fill_l)
  if (cleanTankFill !== null) {
    waterForm.cleanTankFillL = clamp(Math.round(cleanTankFill), 10, 5000)
  }

  const nutrientTankTarget = readNumber(
    irrigationBehavior?.nutrient_tank_target_l,
    irrigationTargets?.nutrient_tank_target_l,
  )
  if (nutrientTankTarget !== null) {
    waterForm.nutrientTankTargetL = clamp(Math.round(nutrientTankTarget), 10, 5000)
  }

  const irrigationBatch = readNumber(irrigationBehavior?.irrigation_batch_l, irrigationTargets?.irrigation_batch_l)
  if (irrigationBatch !== null) {
    waterForm.irrigationBatchL = clamp(Math.round(irrigationBatch), 1, 500)
  }
}

function applyFillTemperatureAndSchedule(
  irrigationBehavior: Dictionary | null,
  irrigationTargets: Dictionary | null,
  waterForm: WaterFormState,
): void {
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
}

function applyCorrectionTolerances(
  irrigationBehavior: Dictionary | null,
  irrigationTargets: Dictionary | null,
  waterForm: WaterFormState,
): void {
  const correctionNode = asRecord(irrigationBehavior?.correction_node) ?? asRecord(irrigationTargets?.correction_node)
  const correctionTolerance = asRecord(correctionNode?.target_tolerance)

  const correctionPhPct = readNumber(
    correctionTolerance?.ph_pct,
    correctionNode?.ph_pct,
    irrigationBehavior?.ph_pct,
    irrigationTargets?.ph_pct,
  )
  const correctionEcPct = readNumber(
    correctionTolerance?.ec_pct,
    correctionNode?.ec_pct,
    irrigationBehavior?.ec_pct,
    irrigationTargets?.ec_pct,
  )

  if (correctionPhPct !== null) {
    waterForm.phPct = clamp(correctionPhPct, 1, 50)
  }
  if (correctionEcPct !== null) {
    waterForm.ecPct = clamp(correctionEcPct, 1, 50)
  }
}

function applyToggles(
  irrigationBehavior: Dictionary | null,
  irrigationTargets: Dictionary | null,
  waterForm: WaterFormState,
): void {
  const valveSwitching = readBoolean(
    irrigationBehavior?.valve_switching_enabled,
    irrigationTargets?.valve_switching_enabled,
  )
  if (valveSwitching !== null) {
    waterForm.valveSwitching = valveSwitching
  }

  const correctionDuringIrrigation = readBoolean(
    irrigationBehavior?.correction_during_irrigation,
    irrigationTargets?.correction_during_irrigation,
  )
  if (correctionDuringIrrigation !== null) {
    waterForm.correctionDuringIrrigation = correctionDuringIrrigation
  }
}

function applyDecision(
  irrigationDecision: Dictionary | null,
  irrigationDecisionConfig: Dictionary | null,
  waterForm: WaterFormState,
): void {
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
}

function applyRecoveryAndSafety(
  irrigationRecoveryPolicy: Dictionary | null,
  irrigationSafety: Dictionary | null,
  waterForm: WaterFormState,
): void {
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
}

function applyDrainControl(
  irrigationBehavior: Dictionary | null,
  irrigationTargets: Dictionary | null,
  waterForm: WaterFormState,
): void {
  const drainControl = asRecord(irrigationBehavior?.drain_control) ?? asRecord(irrigationTargets?.drain_control)
  const drainEnabled = readBoolean(drainControl?.enabled)
  const drainTarget = readNumber(drainControl?.target_percent)

  if (drainEnabled !== null) {
    waterForm.enableDrainControl = drainEnabled
  }
  if (drainTarget !== null) {
    waterForm.drainTargetPercent = clamp(drainTarget, 0, 100)
  }
}

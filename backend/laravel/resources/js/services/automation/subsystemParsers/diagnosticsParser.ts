/**
 * Парсер подсистемы diagnostics из recipe automation targets.
 *
 * Извлечён из applyAutomationFromRecipe (zoneAutomationTargetsParser.ts)
 * как изолированная единица: читает `targets.extensions.subsystems.diagnostics`
 * + плоский `targets.diagnostics` fallback и заполняет соответствующие поля
 * waterForm (diagnostics/refill/startup/failsafe/correction/recovery).
 */

import { clamp } from '@/services/automation/parsingUtils'
import {
  asRecord,
  readBoolean,
  readNumber,
  readString,
  readStringList,
  type Dictionary,
} from '@/services/automation/dictReaders'
import type { WaterFormState } from '@/composables/zoneAutomationTypes'

export function applyDiagnosticsFromTargets(targets: Dictionary, waterForm: WaterFormState): void {
  const extensions = asRecord(targets.extensions)
  const subsystems = asRecord(extensions?.subsystems)
  const diagnosticsSubsystem = asRecord(subsystems?.diagnostics)
  const diagnosticsExecution = asRecord(diagnosticsSubsystem?.execution)
  const diagnosticsTargets = asRecord(diagnosticsSubsystem?.targets)
  const diagnosticsBehavior = diagnosticsExecution ?? diagnosticsTargets
  const diagnostics = asRecord(targets.diagnostics)

  const diagnosticsEnabled = readBoolean(diagnosticsSubsystem?.enabled)
  if (diagnosticsEnabled !== null) {
    waterForm.diagnosticsEnabled = diagnosticsEnabled
  }

  const diagnosticsIntervalSec = readNumber(
    diagnosticsBehavior?.interval_sec,
    diagnosticsTargets?.interval_sec,
    diagnostics?.interval_sec,
  )
  if (diagnosticsIntervalSec !== null) {
    waterForm.diagnosticsIntervalMinutes = clamp(Math.round(diagnosticsIntervalSec / 60), 1, 1440)
  }

  const diagnosticsExecutionResolved = asRecord(diagnosticsBehavior?.execution) ?? diagnosticsBehavior
  const diagnosticsWorkflow = readString(
    diagnosticsBehavior?.workflow,
    diagnosticsTargets?.workflow,
    diagnosticsExecutionResolved?.workflow,
    asRecord(diagnostics?.execution)?.workflow,
  )
  if (
    diagnosticsWorkflow === 'startup'
    || diagnosticsWorkflow === 'cycle_start'
    || diagnosticsWorkflow === 'diagnostics'
  ) {
    waterForm.diagnosticsWorkflow = diagnosticsWorkflow
  }

  const cleanTankThreshold = readNumber(
    diagnosticsBehavior?.clean_tank_full_threshold,
    diagnosticsTargets?.clean_tank_full_threshold,
    diagnosticsExecutionResolved?.clean_tank_full_threshold,
  )
  if (cleanTankThreshold !== null) {
    waterForm.cleanTankFullThreshold = clamp(cleanTankThreshold, 0.05, 1)
  }

  const refillDurationSec = readNumber(
    diagnosticsBehavior?.refill_duration_sec,
    diagnosticsTargets?.refill_duration_sec,
    diagnosticsExecutionResolved?.refill_duration_sec,
    asRecord(diagnosticsExecutionResolved?.refill)?.duration_sec,
  )
  if (refillDurationSec !== null) {
    waterForm.refillDurationSeconds = clamp(Math.round(refillDurationSec), 1, 3600)
  }

  const refillTimeoutSec = readNumber(
    diagnosticsBehavior?.refill_timeout_sec,
    diagnosticsTargets?.refill_timeout_sec,
    diagnosticsExecutionResolved?.refill_timeout_sec,
    asRecord(diagnosticsExecutionResolved?.refill)?.timeout_sec,
  )
  if (refillTimeoutSec !== null) {
    waterForm.refillTimeoutSeconds = clamp(Math.round(refillTimeoutSec), 30, 86400)
  }

  const refillRequiredNodeTypes = readStringList(
    diagnosticsBehavior?.required_node_types,
    diagnosticsTargets?.required_node_types,
    diagnosticsExecutionResolved?.required_node_types,
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

  applyStartupSection(diagnosticsExecutionResolved, waterForm)
  applyFailSafeGuards(diagnosticsExecutionResolved, waterForm)
  applyCorrectionSection(diagnosticsExecutionResolved, waterForm)
  applyIrrigationRecoverySection(diagnosticsExecutionResolved, waterForm)
}

function applyStartupSection(diagnosticsExecutionResolved: Dictionary | null, waterForm: WaterFormState): void {
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
    waterForm.startupPrepareRecirculationTimeoutSeconds = clamp(
      Math.round(startupPrepareRecirculationTimeoutSec),
      30,
      86400,
    )
  }

  const startupCleanFillRetryCycles = readNumber(startup?.clean_fill_retry_cycles)
  if (startupCleanFillRetryCycles !== null) {
    waterForm.startupCleanFillRetryCycles = clamp(Math.round(startupCleanFillRetryCycles), 0, 20)
  }
}

function applyFailSafeGuards(diagnosticsExecutionResolved: Dictionary | null, waterForm: WaterFormState): void {
  const failSafeGuards = asRecord(diagnosticsExecutionResolved?.fail_safe_guards)

  const cleanFillMinCheckDelayMs = readNumber(failSafeGuards?.clean_fill_min_check_delay_ms)
  if (cleanFillMinCheckDelayMs !== null) {
    waterForm.cleanFillMinCheckDelayMs = clamp(Math.round(cleanFillMinCheckDelayMs), 0, 3600000)
  }

  const solutionFillCleanMinCheckDelayMs = readNumber(failSafeGuards?.solution_fill_clean_min_check_delay_ms)
  if (solutionFillCleanMinCheckDelayMs !== null) {
    waterForm.solutionFillCleanMinCheckDelayMs = clamp(Math.round(solutionFillCleanMinCheckDelayMs), 0, 3600000)
  }

  const solutionFillSolutionMinCheckDelayMs = readNumber(failSafeGuards?.solution_fill_solution_min_check_delay_ms)
  if (solutionFillSolutionMinCheckDelayMs !== null) {
    waterForm.solutionFillSolutionMinCheckDelayMs = clamp(Math.round(solutionFillSolutionMinCheckDelayMs), 0, 3600000)
  }

  const recirculationStopOnSolutionMin = readBoolean(failSafeGuards?.recirculation_stop_on_solution_min)
  if (recirculationStopOnSolutionMin !== null) {
    waterForm.recirculationStopOnSolutionMin = recirculationStopOnSolutionMin
  }

  const irrigationStopOnSolutionMinFailSafe = readBoolean(failSafeGuards?.irrigation_stop_on_solution_min)
  if (irrigationStopOnSolutionMinFailSafe !== null) {
    waterForm.stopOnSolutionMin = irrigationStopOnSolutionMinFailSafe
  }

  const estopDebounceMs = readNumber(failSafeGuards?.estop_debounce_ms)
  if (estopDebounceMs !== null) {
    waterForm.estopDebounceMs = clamp(Math.round(estopDebounceMs), 20, 5000)
  }
}

function applyCorrectionSection(diagnosticsExecutionResolved: Dictionary | null, waterForm: WaterFormState): void {
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
      50,
    )
  }

  const correctionPrepareRecirculationMaxCorrectionAttempts = readNumber(
    correction?.prepare_recirculation_max_correction_attempts,
  )
  if (correctionPrepareRecirculationMaxCorrectionAttempts !== null) {
    waterForm.correctionPrepareRecirculationMaxCorrectionAttempts = clamp(
      Math.round(correctionPrepareRecirculationMaxCorrectionAttempts),
      1,
      500,
    )
  }

  const correctionStabilizationSec = readNumber(correction?.stabilization_sec)
  if (correctionStabilizationSec !== null) {
    waterForm.correctionStabilizationSec = clamp(Math.round(correctionStabilizationSec), 0, 3600)
  }
}

function applyIrrigationRecoverySection(
  diagnosticsExecutionResolved: Dictionary | null,
  waterForm: WaterFormState,
): void {
  const irrigationRecovery = asRecord(diagnosticsExecutionResolved?.irrigation_recovery)

  const irrigationRecoveryMaxContinueAttempts = readNumber(irrigationRecovery?.max_continue_attempts)
  if (irrigationRecoveryMaxContinueAttempts !== null) {
    waterForm.irrigationRecoveryMaxContinueAttempts = clamp(Math.round(irrigationRecoveryMaxContinueAttempts), 1, 30)
  }

  const irrigationRecoveryTimeoutSec = readNumber(irrigationRecovery?.timeout_sec)
  if (irrigationRecoveryTimeoutSec !== null) {
    waterForm.irrigationRecoveryTimeoutSeconds = clamp(Math.round(irrigationRecoveryTimeoutSec), 30, 86400)
  }
}

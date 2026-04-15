export type IrrigationSystem = 'drip' | 'substrate_trays' | 'nft'

export interface ClimateFormState {
  enabled: boolean
  dayTemp: number
  nightTemp: number
  dayHumidity: number
  nightHumidity: number
  intervalMinutes: number
  dayStart: string
  nightStart: string
  ventMinPercent: number
  ventMaxPercent: number
  useExternalTelemetry: boolean
  outsideTempMin: number
  outsideTempMax: number
  outsideHumidityMax: number
  manualOverrideEnabled: boolean
  overrideMinutes: number
}

export interface WaterFormState {
  systemType: IrrigationSystem
  tanksCount: number
  cleanTankFillL: number
  nutrientTankTargetL: number
  irrigationBatchL: number
  intervalMinutes: number
  durationSeconds: number
  fillTemperatureC: number
  fillWindowStart: string
  fillWindowEnd: string
  targetPh: number
  targetEc: number
  phPct: number
  ecPct: number
  valveSwitching: boolean
  correctionDuringIrrigation: boolean
  enableDrainControl: boolean
  drainTargetPercent: number
  diagnosticsEnabled: boolean
  diagnosticsIntervalMinutes: number
  diagnosticsWorkflow?: 'startup' | 'cycle_start' | 'diagnostics'
  cleanTankFullThreshold: number
  refillDurationSeconds: number
  refillTimeoutSeconds: number
  startupCleanFillTimeoutSeconds?: number
  startupSolutionFillTimeoutSeconds?: number
  startupPrepareRecirculationTimeoutSeconds?: number
  startupCleanFillRetryCycles?: number
  cleanFillMinCheckDelayMs?: number
  solutionFillCleanMinCheckDelayMs?: number
  solutionFillSolutionMinCheckDelayMs?: number
  recirculationStopOnSolutionMin?: boolean
  estopDebounceMs?: number
  irrigationDecisionStrategy?: 'task' | 'smart_soil_v1'
  irrigationDecisionLookbackSeconds?: number
  irrigationDecisionMinSamples?: number
  irrigationDecisionStaleAfterSeconds?: number
  irrigationDecisionHysteresisPct?: number
  irrigationDecisionSpreadAlertThresholdPct?: number
  irrigationRecoveryMaxContinueAttempts?: number
  irrigationRecoveryTimeoutSeconds?: number
  irrigationAutoReplayAfterSetup?: boolean
  irrigationMaxSetupReplays?: number
  stopOnSolutionMin?: boolean
  correctionMaxEcCorrectionAttempts?: number
  correctionMaxPhCorrectionAttempts?: number
  correctionPrepareRecirculationMaxAttempts?: number
  correctionPrepareRecirculationMaxCorrectionAttempts?: number
  correctionStabilizationSec?: number
  refillRequiredNodeTypes: string
  refillPreferredChannel: string
  solutionChangeEnabled: boolean
  solutionChangeIntervalMinutes: number
  solutionChangeDurationSeconds: number
  manualIrrigationSeconds: number
}

export interface LightingFormState {
  enabled: boolean
  luxDay: number
  luxNight: number
  hoursOn: number
  intervalMinutes: number
  scheduleStart: string
  scheduleEnd: string
  manualIntensity: number
  manualDurationHours: number
}

export interface ZoneClimateFormState {
  enabled: boolean
}

export interface ZoneAutomationForms {
  climateForm: ClimateFormState
  waterForm: WaterFormState
  lightingForm: LightingFormState
  zoneClimateForm?: ZoneClimateFormState
}

// ─── Zone Automation Section types ────────────────────────────────────────────

export interface ZoneAutomationSectionAssignments {
  irrigation: number | null
  ph_correction: number | null
  ec_correction: number | null
  light: number | null
  soil_moisture_sensor: number | null
  co2_sensor: number | null
  co2_actuator: number | null
  root_vent_actuator: number | null
}

export type ZoneAutomationBindRole =
  | 'irrigation'
  | 'ph_correction'
  | 'ec_correction'
  | 'light'
  | 'soil_moisture_sensor'
  | 'co2_sensor'
  | 'co2_actuator'
  | 'root_vent_actuator'

export type ZoneAutomationSectionSaveKey =
  | 'required_devices'
  | 'water_contour'
  | 'irrigation'
  | 'solution_correction'
  | 'lighting'
  | 'zone_climate'

// ─── Zone Automation Tab types ────────────────────────────────────────────────

import type { ZoneTargets as ZoneTargetsType, ZoneTelemetry } from '@/types'

export type PredictionTargets = Record<string, { min?: number; max?: number }>

export interface ZoneAutomationTabProps {
  zoneId: number | null
  targets: ZoneTargetsType | PredictionTargets
  telemetry?: ZoneTelemetry | null
  activeGrowCycle?: { id?: number | null; status?: string | null } | null
  currentRecipePhase?: unknown | null
  pumpCalibrationSaveSeq?: number
  pumpCalibrationRunSeq?: number
}

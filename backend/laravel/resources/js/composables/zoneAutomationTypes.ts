export type IrrigationSystem = 'drip' | 'substrate_trays' | 'nft'

export interface ClimateFormState {
  enabled: boolean
  controlMode?: 'auto' | 'semi' | 'manual'
  dayTemp: number
  nightTemp: number
  dayHumidity: number
  nightHumidity: number
  intervalMinutes: number
  emergencyIntervalSeconds?: number
  minCommandIntervalSeconds?: number
  dayStart: string
  nightStart: string
  daylightLuxThreshold?: number
  ventMinPercent: number
  ventMaxPercent: number
  minSafeOpenPercent?: number
  fallbackOpenPercent?: number
  weatherStaleMaxOpenPercent?: number
  emergencyOpenPercent?: number
  positionDeadbandPercent?: number
  nightBaseOpenPercent?: number
  nightMinOpenPercent?: number
  nightMaxOpenPercent?: number
  dayBaseOpenPercent?: number
  dayMinOpenPercent?: number
  dayMaxOpenPercent?: number
  tempFullOpenDeltaC?: number
  rhFullOpenDeltaPercent?: number
  insideTempSpreadAlertC?: number
  insideRhSpreadAlertPercent?: number
  coldGuardMarginC?: number
  coldGuardMaxOpenPercent?: number
  outsideHotterGain?: number
  outsideWetterGain?: number
  useExternalTelemetry: boolean
  outsideTempMin: number
  outsideTempMax: number
  outsideHumidityMax: number
  windReduceThresholdMs?: number
  windCloseThresholdMs?: number
  windReduceWindwardMaxPercent?: number
  windReduceLeewardMaxPercent?: number
  windStormWindwardMaxPercent?: number
  windStormLeewardMaxPercent?: number
  rainWindwardPositionPercent?: number
  rainLeewardPositionPercent?: number
  rainUnknownDirectionMaxPercent?: number
  overheatEmergencyTempC?: number
  sensorFreshnessSeconds?: number
  greenhouseOrientationDeg?: number | null
  leftRoofNormalDeg?: number | null
  rightRoofNormalDeg?: number | null
  targetPolicy?: 'greenhouse_targets' | 'primary_zone' | 'active_zones_strictest'
  primaryZoneId?: number | null
  manualOverrideEnabled: boolean
  manualEmergencyOverrideEnabled?: boolean
  overrideMinutes: number
  /** Макс. шаг открытия форточек за один tick (AE `execution.max_step_pct`, 1–100). */
  maxVentStepPct: number
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
  mainPumpFlowLpm: number
  cleanWaterFlowLpm: number
  workingTankL: number
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

import type { AutomationControlMode } from '@/types/Automation'
import type { ZoneTargets as ZoneTargetsType, ZoneTelemetry } from '@/types'

export type PredictionTargets = Record<string, { min?: number; max?: number }>

export interface ZoneAutomationTabProps {
  zoneId: number | null
  /** Inertia `zones.control_mode` — начальная гидратация UI до ответа AE. */
  zoneControlMode?: AutomationControlMode | null
  targets: ZoneTargetsType | PredictionTargets
  telemetry?: ZoneTelemetry | null
  activeGrowCycle?: { id?: number | null; status?: string | null } | null
  currentRecipePhase?: unknown | null
  pumpCalibrationSaveSeq?: number
  pumpCalibrationRunSeq?: number
  /** Инкремент после ack policy-managed алерта — форсирует refetch `/zones/{id}/state`. */
  automationStateRefreshSeq?: number
  /** true пока выполняется START_IRRIGATION/FORCE_IRRIGATION (общий индикатор кнопок полива). */
  irrigationActionLoading?: boolean
}

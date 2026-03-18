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
  irrigationRecoveryMaxContinueAttempts?: number
  irrigationRecoveryTimeoutSeconds?: number
  prepareToleranceEcPct?: number
  prepareTolerancePhPct?: number
  correctionMaxEcCorrectionAttempts?: number
  correctionMaxPhCorrectionAttempts?: number
  correctionPrepareRecirculationMaxAttempts?: number
  correctionPrepareRecirculationMaxCorrectionAttempts?: number
  correctionStabilizationSec?: number
  twoTankCleanFillStartSteps?: number
  twoTankCleanFillStopSteps?: number
  twoTankSolutionFillStartSteps?: number
  twoTankSolutionFillStopSteps?: number
  twoTankPrepareRecirculationStartSteps?: number
  twoTankPrepareRecirculationStopSteps?: number
  twoTankIrrigationRecoveryStartSteps?: number
  twoTankIrrigationRecoveryStopSteps?: number
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

// ─── Zone Automation Tab types ────────────────────────────────────────────────

import type { ZoneTargets as ZoneTargetsType, ZoneTelemetry } from '@/types'

export type PredictionTargets = Record<string, { min?: number; max?: number }>

export interface ZoneAutomationTabProps {
  zoneId: number | null
  targets: ZoneTargetsType | PredictionTargets
  telemetry?: ZoneTelemetry | null
  activeGrowCycle?: { status?: string | null } | null
}

// ─── Scheduler Task types ─────────────────────────────────────────────────────

export interface SchedulerTaskLifecycleItem {
  status: string
  at: string | null
  error?: string | null
  source?: string | null
}

export interface SchedulerTaskTimelineItem {
  event_id: string
  event_seq?: number | null
  event_type: string
  type?: string | null
  at: string | null
  task_id?: string | null
  correlation_id?: string | null
  task_type?: string | null
  action_required?: boolean | null
  decision?: string | null
  reason_code?: string | null
  reason?: string | null
  node_uid?: string | null
  channel?: string | null
  cmd?: string | null
  error_code?: string | null
  command_submitted?: boolean | null
  command_effect_confirmed?: boolean | null
  terminal_status?: string | null
  status?: string | null
  run_mode?: string | null
  retry_attempt?: number | null
  retry_max_attempts?: number | null
  retry_backoff_sec?: number | null
  next_due_at?: string | null
  executed_steps?: unknown[] | null
  safety_flags?: Record<string, unknown> | null
  measurements_before_after?: Record<string, unknown> | null
  source?: string | null
  details?: Record<string, unknown> | null
}

export interface SchedulerTaskProcessAction {
  event_type?: string | null
  reason_code?: string | null
  at?: string | null
}

export interface SchedulerTaskProcessState {
  status?: string | null
  status_label?: string | null
  phase?: string | null
  phase_label?: string | null
  is_setup_completed?: boolean | null
  is_work_mode?: boolean | null
  current_action?: SchedulerTaskProcessAction | null
}

export interface SchedulerTaskProcessStep {
  phase: string
  label: string
  status: string
  status_label?: string | null
  started_at?: string | null
  updated_at?: string | null
  last_reason_code?: string | null
  last_event_type?: string | null
}

export interface SchedulerTaskStatus {
  task_id: string
  zone_id: number
  task_type: string | null
  status: string | null
  created_at: string | null
  updated_at: string | null
  scheduled_for: string | null
  due_at?: string | null
  expires_at?: string | null
  correlation_id: string | null
  result?: Record<string, unknown> | null
  error?: string | null
  error_code?: string | null
  action_required?: boolean | null
  decision?: string | null
  reason_code?: string | null
  reason?: string | null
  manual_ack_required?: boolean | null
  command_submitted?: boolean | null
  command_effect_confirmed?: boolean | null
  commands_total?: number | null
  commands_effect_confirmed?: number | null
  commands_failed?: number | null
  source?: string | null
  lifecycle: SchedulerTaskLifecycleItem[]
  timeline?: SchedulerTaskTimelineItem[]
  process_state?: SchedulerTaskProcessState | null
  process_steps?: SchedulerTaskProcessStep[] | null
}

export type SchedulerTaskSlaVariant = 'success' | 'warning' | 'danger' | 'info' | 'secondary'

export interface SchedulerTaskSlaMeta {
  variant: SchedulerTaskSlaVariant
  label: string
  hint: string
}

export interface SchedulerTaskDoneMeta {
  variant: SchedulerTaskSlaVariant
  label: string
  hint: string
}

export type SchedulerTaskPreset = 'all' | 'failed' | 'deadline' | 'done_confirmed' | 'done_unconfirmed'

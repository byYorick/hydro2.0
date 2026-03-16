import { clamp, syncSystemToTankLayout } from './zoneAutomationTargetsParser'
import type { ZoneAutomationForms } from './zoneAutomationTypes'

function isValidTimeHHMM(value: string): boolean {
  if (!/^\d{2}:\d{2}$/.test(value)) return false
  const [h, m] = value.split(':').map(Number)
  return h >= 0 && h <= 23 && m >= 0 && m <= 59
}

function normalizeNumber(value: unknown, fallback: number): number {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }

  return fallback
}

function round(value: number, digits: number): number {
  const factor = 10 ** digits
  return Math.round(value * factor) / factor
}

type RelayCommand = {
  channel: string
  cmd: 'set_relay'
  params: { state: boolean }
}

const TWO_TANK_COMMAND_TEMPLATES: Record<string, RelayCommand[]> = {
  clean_fill_start: [{ channel: 'valve_clean_fill', cmd: 'set_relay', params: { state: true } }],
  clean_fill_stop: [{ channel: 'valve_clean_fill', cmd: 'set_relay', params: { state: false } }],
  solution_fill_start: [
    { channel: 'valve_clean_supply', cmd: 'set_relay', params: { state: true } },
    { channel: 'valve_solution_fill', cmd: 'set_relay', params: { state: true } },
    { channel: 'pump_main', cmd: 'set_relay', params: { state: true } },
  ],
  solution_fill_stop: [
    { channel: 'pump_main', cmd: 'set_relay', params: { state: false } },
    { channel: 'valve_solution_fill', cmd: 'set_relay', params: { state: false } },
    { channel: 'valve_clean_supply', cmd: 'set_relay', params: { state: false } },
  ],
  prepare_recirculation_start: [
    { channel: 'valve_solution_supply', cmd: 'set_relay', params: { state: true } },
    { channel: 'valve_solution_fill', cmd: 'set_relay', params: { state: true } },
    { channel: 'pump_main', cmd: 'set_relay', params: { state: true } },
  ],
  prepare_recirculation_stop: [
    { channel: 'pump_main', cmd: 'set_relay', params: { state: false } },
    { channel: 'valve_solution_fill', cmd: 'set_relay', params: { state: false } },
    { channel: 'valve_solution_supply', cmd: 'set_relay', params: { state: false } },
  ],
  irrigation_recovery_start: [
    { channel: 'valve_irrigation', cmd: 'set_relay', params: { state: false } },
    { channel: 'valve_solution_supply', cmd: 'set_relay', params: { state: true } },
    { channel: 'valve_solution_fill', cmd: 'set_relay', params: { state: true } },
    { channel: 'pump_main', cmd: 'set_relay', params: { state: true } },
  ],
  irrigation_recovery_stop: [
    { channel: 'pump_main', cmd: 'set_relay', params: { state: false } },
    { channel: 'valve_solution_fill', cmd: 'set_relay', params: { state: false } },
    { channel: 'valve_solution_supply', cmd: 'set_relay', params: { state: false } },
  ],
}

function normalizeStepCount(value: unknown, fallback: number): number {
  return clamp(Math.round(normalizeNumber(value, fallback)), 1, 12)
}

function cloneRelayCommand(command: RelayCommand): RelayCommand {
  return {
    channel: command.channel,
    cmd: command.cmd,
    params: {
      state: command.params.state,
    },
  }
}

function resizeCommandSteps(steps: RelayCommand[], requestedCount: number): RelayCommand[] {
  const normalizedCount = clamp(requestedCount, 1, 12)
  const base = steps.map(cloneRelayCommand)
  if (normalizedCount <= base.length) {
    return base.slice(0, normalizedCount)
  }

  const tail = base[base.length - 1]
  while (base.length < normalizedCount) {
    base.push(cloneRelayCommand(tail))
  }

  return base
}

export function validateForms(forms: Pick<ZoneAutomationForms, 'climateForm' | 'waterForm'>): string | null {
  const { climateForm, waterForm } = forms
  if (climateForm.ventMinPercent > climateForm.ventMaxPercent) {
    return 'Минимум открытия форточек не может быть больше максимума.'
  }

  if (waterForm.cleanTankFillL <= 0 || waterForm.nutrientTankTargetL <= 0) {
    return 'Укажите положительные объёмы баков.'
  }

  if (waterForm.tanksCount === 3 && waterForm.enableDrainControl && waterForm.drainTargetPercent <= 0) {
    return 'Для контроля дренажа задайте целевой процент больше 0.'
  }

  if (waterForm.cleanTankFullThreshold <= 0 || waterForm.cleanTankFullThreshold > 1) {
    return 'Порог полного бака должен быть в диапазоне (0;1].'
  }

  if (!isValidTimeHHMM(waterForm.fillWindowStart) || !isValidTimeHHMM(waterForm.fillWindowEnd)) {
    return 'Укажите корректное время окна заполнения (формат HH:MM, 00:00–23:59).'
  }

  return null
}

export function buildGrowthCycleConfigPayload(
  forms: ZoneAutomationForms,
  options?: { includeSystemType?: boolean }
): Record<string, unknown> {
  const { climateForm, waterForm, lightingForm } = forms
  const includeSystemType = options?.includeSystemType ?? true
  const phTarget = clamp(normalizeNumber(waterForm.targetPh, 5.8), 4, 9)
  const ecTarget = clamp(normalizeNumber(waterForm.targetEc, 1.6), 0.1, 10)

  const irrigationIntervalMinutes = clamp(Math.round(waterForm.intervalMinutes), 5, 1440)
  const irrigationDurationSeconds = clamp(Math.round(waterForm.durationSeconds), 1, 3600)
  const climateIntervalSec = clamp(Math.round(climateForm.intervalMinutes * 60), 60, 86400)
  const lightingIntervalSec = clamp(Math.round(lightingForm.intervalMinutes * 60), 60, 86400)
  const diagnosticsIntervalSec = clamp(Math.round(waterForm.diagnosticsIntervalMinutes * 60), 60, 86400)
  const solutionChangeIntervalSec = clamp(Math.round(waterForm.solutionChangeIntervalMinutes * 60), 60, 86400)
  const solutionChangeDurationSec = clamp(Math.round(waterForm.solutionChangeDurationSeconds), 1, 86400)
  const cleanTankFullThreshold = round(clamp(waterForm.cleanTankFullThreshold, 0.05, 1), 3)
  const isTwoTankTopology = waterForm.tanksCount === 2
  const derivedDiagnosticsWorkflow = waterForm.cycleStartWorkflowEnabled
    ? (isTwoTankTopology ? 'startup' : 'cycle_start')
    : 'diagnostics'
  const diagnosticsWorkflowCandidate = typeof waterForm.diagnosticsWorkflow === 'string'
    ? waterForm.diagnosticsWorkflow
    : derivedDiagnosticsWorkflow
  const diagnosticsWorkflow =
    diagnosticsWorkflowCandidate === 'startup' ||
    diagnosticsWorkflowCandidate === 'cycle_start' ||
    diagnosticsWorkflowCandidate === 'diagnostics'
      ? diagnosticsWorkflowCandidate
      : derivedDiagnosticsWorkflow
  const normalizedDiagnosticsWorkflow =
    isTwoTankTopology && diagnosticsWorkflow === 'cycle_start'
      ? 'startup'
      : !isTwoTankTopology && diagnosticsWorkflow === 'startup'
        ? 'cycle_start'
        : diagnosticsWorkflow
  const refillDurationSec = clamp(Math.round(waterForm.refillDurationSeconds), 1, 3600)
  const refillTimeoutSec = clamp(Math.round(waterForm.refillTimeoutSeconds), 30, 86400)
  const startupCleanFillTimeoutSec = clamp(
    Math.round(normalizeNumber(waterForm.startupCleanFillTimeoutSeconds, refillTimeoutSec)),
    30,
    86400
  )
  const startupSolutionFillTimeoutSec = clamp(
    Math.round(normalizeNumber(waterForm.startupSolutionFillTimeoutSeconds, startupCleanFillTimeoutSec * 1.5)),
    30,
    86400
  )
  const startupPrepareRecirculationTimeoutSec = clamp(
    Math.round(normalizeNumber(waterForm.startupPrepareRecirculationTimeoutSeconds, refillTimeoutSec)),
    30,
    86400
  )
  const startupCleanFillRetryCycles = clamp(
    Math.round(normalizeNumber(waterForm.startupCleanFillRetryCycles, 1)),
    0,
    20
  )
  const prepareToleranceEcPct = round(clamp(normalizeNumber(waterForm.prepareToleranceEcPct, 25), 0.1, 100), 1)
  const prepareTolerancePhPct = round(clamp(normalizeNumber(waterForm.prepareTolerancePhPct, 15), 0.1, 100), 1)
  const irrigationRecoveryMaxContinueAttempts = clamp(
    Math.round(normalizeNumber(waterForm.irrigationRecoveryMaxContinueAttempts, 5)),
    1,
    30
  )
  const irrigationRecoveryTimeoutSec = clamp(
    Math.round(normalizeNumber(waterForm.irrigationRecoveryTimeoutSeconds, 600)),
    30,
    86400
  )
  const correctionMaxEcCorrectionAttempts = clamp(
    Math.round(normalizeNumber(waterForm.correctionMaxEcCorrectionAttempts, 5)),
    1,
    50
  )
  const correctionMaxPhCorrectionAttempts = clamp(
    Math.round(normalizeNumber(waterForm.correctionMaxPhCorrectionAttempts, 5)),
    1,
    50
  )
  const correctionPrepareRecirculationMaxAttempts = clamp(
    Math.round(normalizeNumber(waterForm.correctionPrepareRecirculationMaxAttempts, 3)),
    1,
    50
  )
  const correctionPrepareRecirculationMaxCorrectionAttempts = clamp(
    Math.round(normalizeNumber(waterForm.correctionPrepareRecirculationMaxCorrectionAttempts, 20)),
    1,
    500
  )
  const correctionStabilizationSec = clamp(
    Math.round(normalizeNumber(waterForm.correctionStabilizationSec, 60)),
    0,
    3600
  )
  const twoTankCommandSteps = {
    clean_fill_start: normalizeStepCount(
      waterForm.twoTankCleanFillStartSteps,
      TWO_TANK_COMMAND_TEMPLATES.clean_fill_start.length
    ),
    clean_fill_stop: normalizeStepCount(
      waterForm.twoTankCleanFillStopSteps,
      TWO_TANK_COMMAND_TEMPLATES.clean_fill_stop.length
    ),
    solution_fill_start: normalizeStepCount(
      waterForm.twoTankSolutionFillStartSteps,
      TWO_TANK_COMMAND_TEMPLATES.solution_fill_start.length
    ),
    solution_fill_stop: normalizeStepCount(
      waterForm.twoTankSolutionFillStopSteps,
      TWO_TANK_COMMAND_TEMPLATES.solution_fill_stop.length
    ),
    prepare_recirculation_start: normalizeStepCount(
      waterForm.twoTankPrepareRecirculationStartSteps,
      TWO_TANK_COMMAND_TEMPLATES.prepare_recirculation_start.length
    ),
    prepare_recirculation_stop: normalizeStepCount(
      waterForm.twoTankPrepareRecirculationStopSteps,
      TWO_TANK_COMMAND_TEMPLATES.prepare_recirculation_stop.length
    ),
    irrigation_recovery_start: normalizeStepCount(
      waterForm.twoTankIrrigationRecoveryStartSteps,
      TWO_TANK_COMMAND_TEMPLATES.irrigation_recovery_start.length
    ),
    irrigation_recovery_stop: normalizeStepCount(
      waterForm.twoTankIrrigationRecoveryStopSteps,
      TWO_TANK_COMMAND_TEMPLATES.irrigation_recovery_stop.length
    ),
  }

  const requiredNodeTypes = waterForm.refillRequiredNodeTypes
    .split(',')
    .map((item) => item.trim())
    .filter((item) => item.length > 0)
  const refillPreferredChannel = waterForm.refillPreferredChannel.trim()

  const diagnosticsExecution: Record<string, unknown> = {
    workflow: normalizedDiagnosticsWorkflow,
    clean_tank_full_threshold: cleanTankFullThreshold,
    required_node_types: requiredNodeTypes,
    refill_duration_sec: refillDurationSec,
    refill_timeout_sec: refillTimeoutSec,
    refill: {
      duration_sec: refillDurationSec,
      timeout_sec: refillTimeoutSec,
      ...(refillPreferredChannel ? { channel: refillPreferredChannel } : {}),
    },
  }
  if (isTwoTankTopology) {
    diagnosticsExecution.topology = 'two_tank_drip_substrate_trays'
    diagnosticsExecution.startup = {
      required_node_types: requiredNodeTypes.length > 0 ? requiredNodeTypes : ['irrig'],
      clean_fill_timeout_sec: startupCleanFillTimeoutSec,
      solution_fill_timeout_sec: startupSolutionFillTimeoutSec,
      prepare_recirculation_timeout_sec: startupPrepareRecirculationTimeoutSec,
      level_poll_interval_sec: 60,
      clean_fill_retry_cycles: startupCleanFillRetryCycles,
      level_switch_on_threshold: 0.5,
      clean_max_sensor_labels: ['level_clean_max'],
      solution_max_sensor_labels: ['level_solution_max'],
    }
    diagnosticsExecution.target_ph = round(phTarget, 2)
    diagnosticsExecution.target_ec = round(ecTarget, 2)
    diagnosticsExecution.prepare_tolerance = {
      ec_pct: prepareToleranceEcPct,
      ph_pct: prepareTolerancePhPct,
    }
    diagnosticsExecution.correction = {
      max_ec_correction_attempts: correctionMaxEcCorrectionAttempts,
      max_ph_correction_attempts: correctionMaxPhCorrectionAttempts,
      prepare_recirculation_max_attempts: correctionPrepareRecirculationMaxAttempts,
      prepare_recirculation_max_correction_attempts: correctionPrepareRecirculationMaxCorrectionAttempts,
      stabilization_sec: correctionStabilizationSec,
    }
    diagnosticsExecution.irrigation_recovery = {
      max_continue_attempts: irrigationRecoveryMaxContinueAttempts,
      timeout_sec: irrigationRecoveryTimeoutSec,
      target_tolerance: {
        ec_pct: 10,
        ph_pct: 5,
      },
      degraded_tolerance: {
        ec_pct: 20,
        ph_pct: 10,
      },
    }
    diagnosticsExecution.two_tank_commands = {
      clean_fill_start: resizeCommandSteps(TWO_TANK_COMMAND_TEMPLATES.clean_fill_start, twoTankCommandSteps.clean_fill_start),
      clean_fill_stop: resizeCommandSteps(TWO_TANK_COMMAND_TEMPLATES.clean_fill_stop, twoTankCommandSteps.clean_fill_stop),
      solution_fill_start: resizeCommandSteps(TWO_TANK_COMMAND_TEMPLATES.solution_fill_start, twoTankCommandSteps.solution_fill_start),
      solution_fill_stop: resizeCommandSteps(TWO_TANK_COMMAND_TEMPLATES.solution_fill_stop, twoTankCommandSteps.solution_fill_stop),
      prepare_recirculation_start: resizeCommandSteps(
        TWO_TANK_COMMAND_TEMPLATES.prepare_recirculation_start,
        twoTankCommandSteps.prepare_recirculation_start
      ),
      prepare_recirculation_stop: resizeCommandSteps(
        TWO_TANK_COMMAND_TEMPLATES.prepare_recirculation_stop,
        twoTankCommandSteps.prepare_recirculation_stop
      ),
      irrigation_recovery_start: resizeCommandSteps(
        TWO_TANK_COMMAND_TEMPLATES.irrigation_recovery_start,
        twoTankCommandSteps.irrigation_recovery_start
      ),
      irrigation_recovery_stop: resizeCommandSteps(
        TWO_TANK_COMMAND_TEMPLATES.irrigation_recovery_stop,
        twoTankCommandSteps.irrigation_recovery_stop
      ),
    }
  } else if (waterForm.tanksCount === 3) {
    diagnosticsExecution.topology = 'three_tank_drip_substrate_trays'
  }

  return {
    mode: 'adjust',
    subsystems: {
      ph: {
        enabled: true,
        execution: {},
      },
      ec: {
        enabled: true,
        execution: {},
      },
      irrigation: {
        enabled: true,
        execution: {
          interval_minutes: irrigationIntervalMinutes,
          interval_sec: irrigationIntervalMinutes * 60,
          duration_seconds: irrigationDurationSeconds,
          duration_sec: irrigationDurationSeconds,
          ...(includeSystemType ? { system_type: waterForm.systemType } : {}),
          tanks_count: waterForm.tanksCount,
          fill_strategy: 'volume',
          correction_strategy: 'feedback_target',
          clean_tank_fill_l: clamp(Math.round(waterForm.cleanTankFillL), 10, 5000),
          nutrient_tank_target_l: clamp(Math.round(waterForm.nutrientTankTargetL), 10, 5000),
          irrigation_batch_l: clamp(Math.round(waterForm.irrigationBatchL), 1, 500),
          valve_switching_enabled: waterForm.valveSwitching,
          correction_during_irrigation: waterForm.correctionDuringIrrigation,
          fill_temperature_c: clamp(waterForm.fillTemperatureC, 5, 35),
          schedule: [
            {
              start: waterForm.fillWindowStart,
              end: waterForm.fillWindowEnd,
              action: 'fill_clean_tank_then_mix',
            },
          ],
          correction_node: {
            target_ph: round(phTarget, 2),
            target_ec: round(ecTarget, 2),
            sensors_location: 'correction_node',
          },
          drain_control: {
              enabled: waterForm.tanksCount === 3 ? waterForm.enableDrainControl : false,
              target_percent: waterForm.tanksCount === 3 ? clamp(waterForm.drainTargetPercent, 0, 100) : null,
            },
        }
      },
      climate: {
        enabled: climateForm.enabled,
        execution: {
          interval_sec: climateIntervalSec,
          temperature: {
            day: clamp(climateForm.dayTemp, 10, 35),
            night: clamp(climateForm.nightTemp, 10, 35),
          },
          humidity: {
            day: clamp(climateForm.dayHumidity, 30, 90),
            night: clamp(climateForm.nightHumidity, 30, 90),
          },
          vent_control: {
            role: 'vent',
            min_open_percent: clamp(Math.round(climateForm.ventMinPercent), 0, 100),
            max_open_percent: clamp(Math.round(climateForm.ventMaxPercent), 0, 100),
          },
          external_guard: {
            enabled: climateForm.useExternalTelemetry,
            temp_min: climateForm.outsideTempMin,
            temp_max: climateForm.outsideTempMax,
            humidity_max: climateForm.outsideHumidityMax,
          },
          limits: {
            strong_wind_mps: 10,
            low_outside_temp_c: clamp(climateForm.outsideTempMin, -30, 45),
          },
          schedule: [
            {
              start: climateForm.dayStart,
              end: climateForm.nightStart,
              profile: 'day',
            },
            {
              start: climateForm.nightStart,
              end: climateForm.dayStart,
              profile: 'night',
            },
          ],
          manual_override: {
            enabled: climateForm.manualOverrideEnabled,
            timeout_minutes: clamp(Math.round(climateForm.overrideMinutes), 5, 120),
          },
        }
      },
      lighting: {
        enabled: lightingForm.enabled,
        execution: {
          interval_sec: lightingIntervalSec,
          lux: {
            day: clamp(Math.round(lightingForm.luxDay), 0, 120000),
            night: clamp(Math.round(lightingForm.luxNight), 0, 120000),
          },
          photoperiod: {
            hours_on: clamp(lightingForm.hoursOn, 0, 24),
            hours_off: round(clamp(24 - lightingForm.hoursOn, 0, 24), 1),
          },
          schedule: [
            {
              start: lightingForm.scheduleStart,
              end: lightingForm.scheduleEnd,
            },
          ],
          future_metrics: {
            ppfd: null,
            dli: null,
            ready: true,
          },
        }
      },
      diagnostics: {
        enabled: waterForm.diagnosticsEnabled,
        execution: {
          interval_sec: diagnosticsIntervalSec,
          // Все остальные поля берутся из diagnosticsExecution: workflow, clean_tank_full_threshold,
          // required_node_types, refill_*, topology, startup, two_tank_commands (для 2-tank)
          ...diagnosticsExecution,
        },
      },
      solution_change: {
        enabled: waterForm.solutionChangeEnabled,
        execution: {
          interval_sec: solutionChangeIntervalSec,
          duration_sec: solutionChangeDurationSec,
        }
      },
    },
  }
}

export function resetToRecommended(forms: ZoneAutomationForms): void {
  const { climateForm, waterForm, lightingForm } = forms

  climateForm.enabled = true
  climateForm.dayTemp = 23
  climateForm.nightTemp = 20
  climateForm.dayHumidity = 62
  climateForm.nightHumidity = 70
  climateForm.intervalMinutes = 5
  climateForm.dayStart = '07:00'
  climateForm.nightStart = '19:00'
  climateForm.ventMinPercent = 15
  climateForm.ventMaxPercent = 85
  climateForm.useExternalTelemetry = true
  climateForm.outsideTempMin = 4
  climateForm.outsideTempMax = 34
  climateForm.outsideHumidityMax = 90
  climateForm.manualOverrideEnabled = true
  climateForm.overrideMinutes = 30

  waterForm.systemType = 'drip'
  waterForm.cleanTankFillL = 300
  waterForm.nutrientTankTargetL = 280
  waterForm.irrigationBatchL = 20
  waterForm.intervalMinutes = 30
  waterForm.durationSeconds = 120
  waterForm.fillTemperatureC = 20
  waterForm.fillWindowStart = '05:00'
  waterForm.fillWindowEnd = '07:00'
  waterForm.targetPh = 5.8
  waterForm.targetEc = 1.6
  waterForm.phPct = 5
  waterForm.ecPct = 10
  waterForm.valveSwitching = true
  waterForm.correctionDuringIrrigation = true
  waterForm.enableDrainControl = false
  waterForm.drainTargetPercent = 20
  waterForm.diagnosticsEnabled = true
  waterForm.diagnosticsIntervalMinutes = 15
  waterForm.cycleStartWorkflowEnabled = true
  waterForm.diagnosticsWorkflow = 'startup'
  waterForm.cleanTankFullThreshold = 0.95
  waterForm.refillDurationSeconds = 30
  waterForm.refillTimeoutSeconds = 600
  waterForm.startupCleanFillTimeoutSeconds = 900
  waterForm.startupSolutionFillTimeoutSeconds = 1350
  waterForm.startupPrepareRecirculationTimeoutSeconds = 900
  waterForm.startupCleanFillRetryCycles = 1
  waterForm.irrigationRecoveryMaxContinueAttempts = 5
  waterForm.irrigationRecoveryTimeoutSeconds = 600
  waterForm.prepareToleranceEcPct = 25
  waterForm.prepareTolerancePhPct = 15
  waterForm.correctionMaxEcCorrectionAttempts = 5
  waterForm.correctionMaxPhCorrectionAttempts = 5
  waterForm.correctionPrepareRecirculationMaxAttempts = 3
  waterForm.correctionPrepareRecirculationMaxCorrectionAttempts = 20
  waterForm.correctionEcMixWaitSec = 120
  waterForm.correctionPhMixWaitSec = 60
  waterForm.correctionStabilizationSec = 60
  waterForm.twoTankCleanFillStartSteps = 1
  waterForm.twoTankCleanFillStopSteps = 1
  waterForm.twoTankSolutionFillStartSteps = 3
  waterForm.twoTankSolutionFillStopSteps = 3
  waterForm.twoTankPrepareRecirculationStartSteps = 3
  waterForm.twoTankPrepareRecirculationStopSteps = 3
  waterForm.twoTankIrrigationRecoveryStartSteps = 4
  waterForm.twoTankIrrigationRecoveryStopSteps = 3
  waterForm.refillRequiredNodeTypes = 'irrig'
  waterForm.refillPreferredChannel = 'fill_valve'
  waterForm.solutionChangeEnabled = false
  waterForm.solutionChangeIntervalMinutes = 180
  waterForm.solutionChangeDurationSeconds = 120
  waterForm.manualIrrigationSeconds = 90

  lightingForm.enabled = true
  lightingForm.luxDay = 18000
  lightingForm.luxNight = 0
  lightingForm.hoursOn = 16
  lightingForm.intervalMinutes = 30
  lightingForm.scheduleStart = '06:00'
  lightingForm.scheduleEnd = '22:00'
  lightingForm.manualIntensity = 75
  lightingForm.manualDurationHours = 4

  syncSystemToTankLayout(waterForm, 'drip')
}

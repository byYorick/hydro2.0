import { describe, expect, it } from 'vitest'
import {
  applyAutomationFromRecipe,
  buildGrowthCycleConfigPayload,
  resetToRecommended,
  syncSystemToTankLayout,
  validateForms,
  type ZoneAutomationForms,
} from '@/composables/zoneAutomationFormLogic'

function createForms(): ZoneAutomationForms {
  return {
    climateForm: {
      enabled: true,
      dayTemp: 22,
      nightTemp: 19,
      dayHumidity: 60,
      nightHumidity: 66,
      intervalMinutes: 5,
      dayStart: '07:00',
      nightStart: '19:00',
      ventMinPercent: 10,
      ventMaxPercent: 80,
      useExternalTelemetry: true,
      outsideTempMin: 3,
      outsideTempMax: 35,
      outsideHumidityMax: 90,
      manualOverrideEnabled: true,
      overrideMinutes: 30,
    },
    waterForm: {
      systemType: 'drip',
      tanksCount: 2,
      cleanTankFillL: 300,
      nutrientTankTargetL: 280,
      irrigationBatchL: 20,
      intervalMinutes: 30,
      durationSeconds: 120,
      fillTemperatureC: 20,
      fillWindowStart: '05:00',
      fillWindowEnd: '07:00',
      targetPh: 5.8,
      targetEc: 1.6,
      phPct: 5,
      ecPct: 10,
      valveSwitching: true,
      correctionDuringIrrigation: true,
      enableDrainControl: false,
      drainTargetPercent: 20,
      diagnosticsEnabled: true,
      diagnosticsIntervalMinutes: 15,
      diagnosticsWorkflow: 'startup',
      cleanTankFullThreshold: 0.95,
      refillDurationSeconds: 30,
      refillTimeoutSeconds: 600,
      startupCleanFillTimeoutSeconds: 900,
      startupSolutionFillTimeoutSeconds: 1350,
      startupPrepareRecirculationTimeoutSeconds: 900,
      startupCleanFillRetryCycles: 1,
      irrigationRecoveryMaxContinueAttempts: 5,
      irrigationRecoveryTimeoutSeconds: 600,
      prepareToleranceEcPct: 25,
      prepareTolerancePhPct: 15,
      correctionMaxEcCorrectionAttempts: 5,
      correctionMaxPhCorrectionAttempts: 5,
      correctionPrepareRecirculationMaxAttempts: 3,
      correctionPrepareRecirculationMaxCorrectionAttempts: 20,
      correctionStabilizationSec: 60,
      twoTankCleanFillStartSteps: 1,
      twoTankCleanFillStopSteps: 1,
      twoTankSolutionFillStartSteps: 3,
      twoTankSolutionFillStopSteps: 3,
      twoTankPrepareRecirculationStartSteps: 3,
      twoTankPrepareRecirculationStopSteps: 3,
      twoTankIrrigationRecoveryStartSteps: 4,
      twoTankIrrigationRecoveryStopSteps: 3,
      refillRequiredNodeTypes: 'irrig,climate,light',
      refillPreferredChannel: 'fill_valve',
      solutionChangeEnabled: false,
      solutionChangeIntervalMinutes: 180,
      solutionChangeDurationSeconds: 120,
      manualIrrigationSeconds: 90,
    },
    lightingForm: {
      enabled: true,
      luxDay: 18000,
      luxNight: 0,
      hoursOn: 16,
      intervalMinutes: 30,
      scheduleStart: '06:00',
      scheduleEnd: '22:00',
      manualIntensity: 75,
      manualDurationHours: 4,
    },
  }
}

describe('zoneAutomationFormLogic', () => {
  it('syncSystemToTankLayout синхронизирует баки и дренаж', () => {
    const forms = createForms()

    forms.waterForm.enableDrainControl = true
    syncSystemToTankLayout(forms.waterForm, 'drip')
    expect(forms.waterForm.tanksCount).toBe(2)
    expect(forms.waterForm.enableDrainControl).toBe(false)

    syncSystemToTankLayout(forms.waterForm, 'nft')
    expect(forms.waterForm.tanksCount).toBe(3)
  })

  it('applyAutomationFromRecipe применяет targets из recipe payload', () => {
    const forms = createForms()
    const payload = {
      ph: { target: 5.7, min: 5.5, max: 6.1 },
      ec: { target: 2.2 },
      climate_request: {
        temp_air_target: 24,
        humidity_target: 68,
      },
      lighting: {
        photoperiod_hours: 18,
      },
      extensions: {
        subsystems: {
          irrigation: {
            enabled: true,
            targets: {
              interval_sec: 2400,
              duration_sec: 75,
              system_type: 'substrate_trays',
              tanks_count: 3,
              clean_tank_fill_l: 420,
              nutrient_tank_target_l: 390,
              irrigation_batch_l: 30,
              fill_temperature_c: 18,
              valve_switching_enabled: false,
              correction_during_irrigation: false,
              schedule: [{ start: '06:15:00', end: '08:20:00' }],
              correction_node: {
                target_ph: 6.3,
                target_ec: 2.4,
              },
              drain_control: {
                enabled: true,
                target_percent: 35,
              },
            },
          },
          climate: {
            enabled: true,
            targets: {
              interval_sec: 600,
              temperature: { day: 26, night: 21 },
              humidity: { day: 65, night: 72 },
              vent_control: { min_open_percent: 18, max_open_percent: 88 },
              external_guard: {
                enabled: true,
                temp_min: 5,
                temp_max: 33,
                humidity_max: 86,
              },
              schedule: [
                { profile: 'day', start: '08:00:00' },
                { profile: 'night', start: '20:30:00' },
              ],
              manual_override: {
                enabled: false,
                timeout_minutes: 45,
              },
            },
          },
          lighting: {
            enabled: true,
            targets: {
              interval_sec: 5400,
              lux: {
                day: 20000,
                night: 100,
              },
              photoperiod: {
                hours_on: 17,
              },
              schedule: [{ start: '06:30:00', end: '23:00:00' }],
            },
          },
          diagnostics: {
            enabled: false,
            targets: {
              interval_sec: 1800,
              workflow: 'cycle_start',
              clean_tank_full_threshold: 0.91,
              refill_duration_sec: 40,
              refill_timeout_sec: 700,
              required_node_types: ['irrig', 'climate'],
              refill: { channel: 'fill_valve' },
              startup: {
                clean_fill_timeout_sec: 930,
                solution_fill_timeout_sec: 1410,
                prepare_recirculation_timeout_sec: 960,
                clean_fill_retry_cycles: 2,
              },
              prepare_tolerance: {
                ec_pct: 18,
                ph_pct: 12,
              },
              irrigation_recovery: {
                max_continue_attempts: 7,
                timeout_sec: 800,
              },
              correction: {
                max_ec_correction_attempts: 6,
                max_ph_correction_attempts: 8,
                prepare_recirculation_max_attempts: 4,
                prepare_recirculation_max_correction_attempts: 150,
                stabilization_sec: 45,
              },
              two_tank_commands: {
                clean_fill_start: [{}, {}],
                clean_fill_stop: [{}],
                solution_fill_start: [{}, {}, {}, {}],
                solution_fill_stop: [{}, {}],
                prepare_recirculation_start: [{}, {}, {}],
                prepare_recirculation_stop: [{}, {}],
                irrigation_recovery_start: [{}, {}, {}, {}, {}],
                irrigation_recovery_stop: [{}, {}, {}],
              },
            },
          },
          solution_change: {
            enabled: true,
            targets: {
              interval_sec: 14400,
              duration_sec: 210,
            },
          },
        },
      },
    }

    applyAutomationFromRecipe(payload, forms)

    expect(forms.waterForm.systemType).toBe('substrate_trays')
    expect(forms.waterForm.tanksCount).toBe(3)
    expect(forms.waterForm.intervalMinutes).toBe(40)
    expect(forms.waterForm.durationSeconds).toBe(75)
    expect(forms.waterForm.fillWindowStart).toBe('06:15')
    expect(forms.waterForm.fillWindowEnd).toBe('08:20')
    expect(forms.waterForm.targetPh).toBe(5.7)
    expect(forms.waterForm.targetEc).toBe(2.2)
    expect(forms.waterForm.enableDrainControl).toBe(true)
    expect(forms.waterForm.drainTargetPercent).toBe(35)

    expect(forms.climateForm.dayTemp).toBe(26)
    expect(forms.climateForm.nightTemp).toBe(21)
    expect(forms.climateForm.intervalMinutes).toBe(10)
    expect(forms.climateForm.dayStart).toBe('08:00')
    expect(forms.climateForm.nightStart).toBe('20:30')
    expect(forms.climateForm.overrideMinutes).toBe(45)

    expect(forms.lightingForm.luxDay).toBe(20000)
    expect(forms.lightingForm.luxNight).toBe(100)
    expect(forms.lightingForm.hoursOn).toBe(17)
    expect(forms.lightingForm.intervalMinutes).toBe(90)
    expect(forms.lightingForm.scheduleStart).toBe('06:30')
    expect(forms.lightingForm.scheduleEnd).toBe('23:00')

    expect(forms.waterForm.diagnosticsEnabled).toBe(false)
    expect(forms.waterForm.diagnosticsIntervalMinutes).toBe(30)
    expect(forms.waterForm.diagnosticsWorkflow).toBe('cycle_start')
    expect(forms.waterForm.cleanTankFullThreshold).toBe(0.91)
    expect(forms.waterForm.refillDurationSeconds).toBe(40)
    expect(forms.waterForm.refillTimeoutSeconds).toBe(700)
    expect(forms.waterForm.startupCleanFillTimeoutSeconds).toBe(930)
    expect(forms.waterForm.startupSolutionFillTimeoutSeconds).toBe(1410)
    expect(forms.waterForm.startupPrepareRecirculationTimeoutSeconds).toBe(960)
    expect(forms.waterForm.startupCleanFillRetryCycles).toBe(2)
    expect(forms.waterForm.irrigationRecoveryMaxContinueAttempts).toBe(7)
    expect(forms.waterForm.irrigationRecoveryTimeoutSeconds).toBe(800)
    expect(forms.waterForm.prepareToleranceEcPct).toBe(18)
    expect(forms.waterForm.prepareTolerancePhPct).toBe(12)
    expect(forms.waterForm.correctionMaxEcCorrectionAttempts).toBe(6)
    expect(forms.waterForm.correctionMaxPhCorrectionAttempts).toBe(8)
    expect(forms.waterForm.correctionPrepareRecirculationMaxAttempts).toBe(4)
    expect(forms.waterForm.correctionPrepareRecirculationMaxCorrectionAttempts).toBe(150)
    expect(forms.waterForm.correctionStabilizationSec).toBe(45)
    expect(forms.waterForm.twoTankCleanFillStartSteps).toBe(2)
    expect(forms.waterForm.twoTankCleanFillStopSteps).toBe(1)
    expect(forms.waterForm.twoTankSolutionFillStartSteps).toBe(4)
    expect(forms.waterForm.twoTankSolutionFillStopSteps).toBe(2)
    expect(forms.waterForm.twoTankPrepareRecirculationStartSteps).toBe(3)
    expect(forms.waterForm.twoTankPrepareRecirculationStopSteps).toBe(2)
    expect(forms.waterForm.twoTankIrrigationRecoveryStartSteps).toBe(5)
    expect(forms.waterForm.twoTankIrrigationRecoveryStopSteps).toBe(3)
    expect(forms.waterForm.refillRequiredNodeTypes).toBe('irrig,climate')
    expect(forms.waterForm.refillPreferredChannel).toBe('fill_valve')
    expect(forms.waterForm.solutionChangeEnabled).toBe(true)
    expect(forms.waterForm.solutionChangeIntervalMinutes).toBe(240)
    expect(forms.waterForm.solutionChangeDurationSeconds).toBe(210)
  })

  it('buildGrowthCycleConfigPayload нормализует значения и выключает drain для 2 баков', () => {
    const forms = createForms()

    forms.waterForm.systemType = 'drip'
    forms.waterForm.tanksCount = 2
    forms.waterForm.targetPh = 10
    forms.waterForm.targetEc = -1
    forms.waterForm.intervalMinutes = 2
    forms.waterForm.durationSeconds = 7000
    forms.waterForm.drainTargetPercent = 70
    forms.waterForm.startupCleanFillTimeoutSeconds = 940
    forms.waterForm.startupSolutionFillTimeoutSeconds = 1300
    forms.waterForm.startupPrepareRecirculationTimeoutSeconds = 920
    forms.waterForm.startupCleanFillRetryCycles = 4
    forms.waterForm.irrigationRecoveryMaxContinueAttempts = 9
    forms.waterForm.irrigationRecoveryTimeoutSeconds = 650
    forms.waterForm.prepareToleranceEcPct = 19
    forms.waterForm.prepareTolerancePhPct = 11
    forms.waterForm.correctionMaxEcCorrectionAttempts = 11
    forms.waterForm.correctionMaxPhCorrectionAttempts = 13
    forms.waterForm.correctionPrepareRecirculationMaxAttempts = 6
    forms.waterForm.correctionPrepareRecirculationMaxCorrectionAttempts = 200
    forms.waterForm.correctionStabilizationSec = 50
    forms.waterForm.twoTankCleanFillStartSteps = 2
    forms.waterForm.twoTankSolutionFillStartSteps = 4
    forms.climateForm.ventMinPercent = -5
    forms.climateForm.ventMaxPercent = 140
    forms.lightingForm.hoursOn = 25

    const payload = buildGrowthCycleConfigPayload(forms) as any
    const targets = payload.subsystems.irrigation.execution

    expect(payload.subsystems.ph.targets).toBeUndefined()
    expect(payload.subsystems.ec.targets).toBeUndefined()
    expect(payload.subsystems.diagnostics.execution.target_ph).toBeUndefined()
    expect(payload.subsystems.diagnostics.execution.target_ec).toBeUndefined()
    expect(targets.interval_minutes).toBe(5)
    expect(targets.interval_sec).toBe(300)
    expect(targets.duration_seconds).toBe(3600)
    expect(targets.duration_sec).toBe(3600)
    expect(targets.correction_node.target_ph).toBeUndefined()
    expect(targets.correction_node.target_ec).toBeUndefined()
    expect(targets.drain_control.enabled).toBe(false)
    expect(targets.drain_control.target_percent).toBeNull()
    expect(payload.subsystems.climate.execution.vent_control.min_open_percent).toBe(0)
    expect(payload.subsystems.climate.execution.vent_control.max_open_percent).toBe(100)
    expect(payload.subsystems.climate.execution.interval_sec).toBe(300)
    expect(payload.subsystems.lighting.execution.interval_sec).toBe(1800)
    expect(payload.subsystems.diagnostics.execution.workflow).toBe('startup')
    expect(payload.subsystems.diagnostics.execution.topology).toBe('two_tank_drip_substrate_trays')
    expect(payload.subsystems.diagnostics.execution.startup.clean_fill_timeout_sec).toBe(940)
    expect(payload.subsystems.diagnostics.execution.startup.solution_fill_timeout_sec).toBe(1300)
    expect(payload.subsystems.diagnostics.execution.startup.prepare_recirculation_timeout_sec).toBe(920)
    expect(payload.subsystems.diagnostics.execution.startup.clean_fill_retry_cycles).toBe(4)
    expect(payload.subsystems.diagnostics.execution.irrigation_recovery.max_continue_attempts).toBe(9)
    expect(payload.subsystems.diagnostics.execution.irrigation_recovery.timeout_sec).toBe(650)
    expect(payload.subsystems.diagnostics.execution.prepare_tolerance.ec_pct).toBe(19)
    expect(payload.subsystems.diagnostics.execution.prepare_tolerance.ph_pct).toBe(11)
    expect(payload.subsystems.diagnostics.execution.correction.max_ec_correction_attempts).toBe(11)
    expect(payload.subsystems.diagnostics.execution.correction.max_ph_correction_attempts).toBe(13)
    expect(payload.subsystems.diagnostics.execution.correction.prepare_recirculation_max_attempts).toBe(6)
    expect(payload.subsystems.diagnostics.execution.correction.prepare_recirculation_max_correction_attempts).toBe(200)
    expect(payload.subsystems.diagnostics.execution.correction.ec_mix_wait_sec).toBeUndefined()
    expect(payload.subsystems.diagnostics.execution.correction.ph_mix_wait_sec).toBeUndefined()
    expect(payload.subsystems.diagnostics.execution.correction.stabilization_sec).toBe(50)
    expect(payload.subsystems.diagnostics.execution.irrigation_recovery.degraded_tolerance.ec_pct).toBe(20)
    expect(payload.subsystems.diagnostics.execution.two_tank_commands.clean_fill_start.length).toBe(2)
    expect(payload.subsystems.diagnostics.execution.two_tank_commands.clean_fill_start[0].channel).toBe('valve_clean_fill')
    expect(payload.subsystems.diagnostics.execution.two_tank_commands.solution_fill_start.length).toBe(4)
    expect(payload.subsystems.diagnostics.execution.two_tank_commands.prepare_recirculation_start[0].channel).toBe(
      'valve_solution_supply'
    )
    expect(payload.subsystems.solution_change.execution.duration_sec).toBe(120)
    expect(payload.subsystems.lighting.execution.photoperiod.hours_on).toBe(24)
  })

  it('не даёт урезать критические two-tank command plans ниже безопасного минимума', () => {
    const forms = createForms()

    forms.waterForm.systemType = 'drip'
    forms.waterForm.tanksCount = 2
    forms.waterForm.twoTankSolutionFillStartSteps = 1
    forms.waterForm.twoTankSolutionFillStopSteps = 1
    forms.waterForm.twoTankPrepareRecirculationStartSteps = 1
    forms.waterForm.twoTankPrepareRecirculationStopSteps = 1
    forms.waterForm.twoTankIrrigationRecoveryStartSteps = 1
    forms.waterForm.twoTankIrrigationRecoveryStopSteps = 1

    const payload = buildGrowthCycleConfigPayload(forms) as any
    const twoTankCommands = payload.subsystems.diagnostics.execution.two_tank_commands

    expect(twoTankCommands.solution_fill_start).toHaveLength(3)
    expect(twoTankCommands.solution_fill_stop).toHaveLength(3)
    expect(twoTankCommands.prepare_recirculation_start).toHaveLength(3)
    expect(twoTankCommands.prepare_recirculation_stop).toHaveLength(3)
    expect(twoTankCommands.irrigation_recovery_start).toHaveLength(4)
    expect(twoTankCommands.irrigation_recovery_stop).toHaveLength(3)
  })

  it('buildGrowthCycleConfigPayload может не отправлять system_type для активного цикла', () => {
    const forms = createForms()

    const payload = buildGrowthCycleConfigPayload(forms, { includeSystemType: false }) as any
    const targets = payload.subsystems.irrigation.execution

    expect(targets.system_type).toBeUndefined()
  })

  it('buildGrowthCycleConfigPayload маркирует 3-баковую топологию отдельным runtime-id', () => {
    const forms = createForms()
    forms.waterForm.tanksCount = 3
    forms.waterForm.systemType = 'nft'

    const payload = buildGrowthCycleConfigPayload(forms) as any
    expect(payload.subsystems.diagnostics.execution.workflow).toBe('cycle_start')
    expect(payload.subsystems.diagnostics.execution.topology).toBe('three_tank_drip_substrate_trays')
  })

  it('validateForms возвращает сообщение для некорректных значений', () => {
    const forms = createForms()

    forms.climateForm.ventMinPercent = 90
    forms.climateForm.ventMaxPercent = 10
    expect(validateForms(forms)).toBe('Минимум открытия форточек не может быть больше максимума.')

    forms.climateForm.ventMinPercent = 10
    forms.climateForm.ventMaxPercent = 90
    forms.waterForm.cleanTankFillL = 0
    expect(validateForms(forms)).toBe('Укажите положительные объёмы баков.')

    forms.waterForm.cleanTankFillL = 300
    forms.waterForm.nutrientTankTargetL = 280
    forms.waterForm.tanksCount = 3
    forms.waterForm.enableDrainControl = true
    forms.waterForm.drainTargetPercent = 0
    expect(validateForms(forms)).toBe('Для контроля дренажа задайте целевой процент больше 0.')
  })

  it('resetToRecommended восстанавливает рекомендуемые значения', () => {
    const forms = createForms()

    forms.waterForm.systemType = 'nft'
    forms.waterForm.tanksCount = 3
    forms.waterForm.enableDrainControl = true
    forms.climateForm.dayTemp = 30
    forms.lightingForm.hoursOn = 10

    resetToRecommended(forms)

    expect(forms.waterForm.systemType).toBe('drip')
    expect(forms.waterForm.tanksCount).toBe(2)
    expect(forms.waterForm.enableDrainControl).toBe(false)
    expect(forms.climateForm.dayTemp).toBe(23)
    expect(forms.lightingForm.hoursOn).toBe(16)
  })
})

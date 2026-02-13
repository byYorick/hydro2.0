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
      valveSwitching: true,
      correctionDuringIrrigation: true,
      enableDrainControl: false,
      drainTargetPercent: 20,
      diagnosticsEnabled: true,
      diagnosticsIntervalMinutes: 15,
      cycleStartWorkflowEnabled: true,
      cleanTankFullThreshold: 0.95,
      refillDurationSeconds: 30,
      refillTimeoutSeconds: 600,
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
      ph: { min: 5.5, max: 6.1 },
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
    expect(forms.waterForm.targetPh).toBe(6.3)
    expect(forms.waterForm.targetEc).toBe(2.4)
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
    expect(forms.waterForm.cycleStartWorkflowEnabled).toBe(true)
    expect(forms.waterForm.cleanTankFullThreshold).toBe(0.91)
    expect(forms.waterForm.refillDurationSeconds).toBe(40)
    expect(forms.waterForm.refillTimeoutSeconds).toBe(700)
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
    forms.climateForm.ventMinPercent = -5
    forms.climateForm.ventMaxPercent = 140
    forms.lightingForm.hoursOn = 25

    const payload = buildGrowthCycleConfigPayload(forms) as any
    const targets = payload.subsystems.irrigation.targets

    expect(payload.subsystems.ph.targets.target).toBe(9)
    expect(payload.subsystems.ec.targets.target).toBe(0.1)
    expect(targets.interval_minutes).toBe(5)
    expect(targets.interval_sec).toBe(300)
    expect(targets.duration_seconds).toBe(3600)
    expect(targets.duration_sec).toBe(3600)
    expect(targets.drain_control.enabled).toBe(false)
    expect(targets.drain_control.target_percent).toBeNull()
    expect(payload.subsystems.climate.targets.vent_control.min_open_percent).toBe(0)
    expect(payload.subsystems.climate.targets.vent_control.max_open_percent).toBe(100)
    expect(payload.subsystems.climate.targets.interval_sec).toBe(300)
    expect(payload.subsystems.lighting.targets.interval_sec).toBe(1800)
    expect(payload.subsystems.diagnostics.targets.execution.workflow).toBe('cycle_start')
    expect(payload.subsystems.solution_change.targets.duration_sec).toBe(120)
    expect(payload.subsystems.lighting.targets.photoperiod.hours_on).toBe(24)
  })

  it('buildGrowthCycleConfigPayload может не отправлять system_type для активного цикла', () => {
    const forms = createForms()

    const payload = buildGrowthCycleConfigPayload(forms, { includeSystemType: false }) as any
    const targets = payload.subsystems.irrigation.targets

    expect(targets.system_type).toBeUndefined()
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

import { describe, expect, it } from 'vitest'
import {
  syncFormsFromRecipePhase,
  type PhaseSyncTargets,
  type RecipePhaseLike,
} from '@/services/automation/recipePhaseSync'
import type {
  ClimateFormState,
  LightingFormState,
  WaterFormState,
} from '@/composables/zoneAutomationTypes'

function createWaterForm(): WaterFormState {
  return {
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
    irrigationDecisionStrategy: 'task',
    irrigationDecisionLookbackSeconds: 1800,
    irrigationDecisionMinSamples: 3,
    irrigationDecisionStaleAfterSeconds: 600,
    irrigationDecisionHysteresisPct: 2,
    irrigationDecisionSpreadAlertThresholdPct: 12,
    irrigationRecoveryMaxContinueAttempts: 5,
    irrigationRecoveryTimeoutSeconds: 600,
    irrigationAutoReplayAfterSetup: true,
    irrigationMaxSetupReplays: 1,
    stopOnSolutionMin: true,
    correctionMaxEcCorrectionAttempts: 5,
    correctionMaxPhCorrectionAttempts: 5,
    correctionPrepareRecirculationMaxAttempts: 3,
    correctionPrepareRecirculationMaxCorrectionAttempts: 20,
    correctionStabilizationSec: 60,
    refillRequiredNodeTypes: 'irrig,climate,light',
    refillPreferredChannel: 'fill_valve',
    solutionChangeEnabled: false,
    solutionChangeIntervalMinutes: 180,
    solutionChangeDurationSeconds: 120,
    manualIrrigationSeconds: 90,
  } as WaterFormState
}

function createClimateForm(): ClimateFormState {
  return {
    enabled: false,
    dayTemp: 22,
    nightTemp: 19,
    dayHumidity: 60,
    nightHumidity: 66,
    intervalMinutes: 5,
    dayStart: '07:00',
    nightStart: '19:00',
    ventMinPercent: 10,
    ventMaxPercent: 80,
    useExternalTelemetry: false,
    outsideTempMin: 3,
    outsideTempMax: 35,
    outsideHumidityMax: 90,
    manualOverrideEnabled: false,
    overrideMinutes: 30,
  }
}

function createLightingForm(): LightingFormState {
  return {
    enabled: true,
    luxDay: 18000,
    luxNight: 0,
    hoursOn: 16,
    intervalMinutes: 30,
    scheduleStart: '06:00',
    scheduleEnd: '22:00',
    manualIntensity: 75,
    manualDurationHours: 4,
  }
}

function createForms(): PhaseSyncTargets {
  return {
    waterForm: createWaterForm(),
    climateForm: createClimateForm(),
    lightingForm: createLightingForm(),
  }
}

describe('syncFormsFromRecipePhase', () => {
  it('подставляет pH/EC/climate цели в формы', () => {
    const forms = createForms()
    const phase: RecipePhaseLike = {
      ph_target: 6.123,
      ec_target: 1.858,
      temp_air_target: 23.67,
      humidity_target: 68.4,
    }

    syncFormsFromRecipePhase(phase, forms)

    expect(forms.waterForm.targetPh).toBe(6.12)
    expect(forms.waterForm.targetEc).toBe(1.86)
    expect(forms.climateForm.dayTemp).toBe(23.7)
    expect(forms.climateForm.dayHumidity).toBe(68)
  })

  it('не меняет форму, если фаза не содержит целей', () => {
    const forms = createForms()
    const originalPh = forms.waterForm.targetPh
    const originalEc = forms.waterForm.targetEc

    syncFormsFromRecipePhase({}, forms)

    expect(forms.waterForm.targetPh).toBe(originalPh)
    expect(forms.waterForm.targetEc).toBe(originalEc)
  })

  it('парсит числа из строк (toFiniteNumber)', () => {
    const forms = createForms()
    syncFormsFromRecipePhase({ ph_target: '6.3' as unknown as number }, forms)
    expect(forms.waterForm.targetPh).toBe(6.3)
  })

  it('читает day_night extensions при readDayNightExtensions=true', () => {
    const forms = createForms()
    const phase: RecipePhaseLike = {
      temp_air_target: 20,
      humidity_target: 50,
      extensions: {
        day_night: {
          temperature: { day: 25 },
          humidity: { day: 70 },
        },
      },
    }

    syncFormsFromRecipePhase(phase, forms, { readDayNightExtensions: true })

    expect(forms.climateForm.dayTemp).toBe(25)
    expect(forms.climateForm.dayHumidity).toBe(70)
  })

  it('игнорирует day_night extensions по умолчанию', () => {
    const forms = createForms()
    const phase: RecipePhaseLike = {
      temp_air_target: 20,
      humidity_target: 50,
      extensions: {
        day_night: {
          temperature: { day: 25 },
          humidity: { day: 70 },
        },
      },
    }

    syncFormsFromRecipePhase(phase, forms)

    expect(forms.climateForm.dayTemp).toBe(20)
    expect(forms.climateForm.dayHumidity).toBe(50)
  })

  it('fallback на плоские поля, если extensions не содержат day', () => {
    const forms = createForms()
    const phase: RecipePhaseLike = {
      temp_air_target: 21,
      humidity_target: 55,
      extensions: { day_night: {} },
    }

    syncFormsFromRecipePhase(phase, forms, { readDayNightExtensions: true })

    expect(forms.climateForm.dayTemp).toBe(21)
    expect(forms.climateForm.dayHumidity).toBe(55)
  })

  it('применяет минимальный интервал полива Growth (5 минут)', () => {
    const forms = createForms()
    syncFormsFromRecipePhase(
      { irrigation_interval_sec: 60 },
      forms,
      { minIntervalMinutes: 5 },
    )
    expect(forms.waterForm.intervalMinutes).toBe(5)
  })

  it('применяет минимальный интервал полива Setup (1 минута)', () => {
    const forms = createForms()
    syncFormsFromRecipePhase(
      { irrigation_interval_sec: 60 },
      forms,
      { minIntervalMinutes: 1 },
    )
    expect(forms.waterForm.intervalMinutes).toBe(1)
  })

  it('применяет минимальную длительность Growth (10 сек)', () => {
    const forms = createForms()
    syncFormsFromRecipePhase(
      { irrigation_duration_sec: 3 },
      forms,
      { minDurationSeconds: 10 },
    )
    expect(forms.waterForm.durationSeconds).toBe(10)
  })

  it('clamp hoursOn в диапазон [1, 24]', () => {
    const forms = createForms()

    syncFormsFromRecipePhase({ lighting_photoperiod_hours: 0 }, forms)
    expect(forms.lightingForm.hoursOn).toBe(1)

    syncFormsFromRecipePhase({ lighting_photoperiod_hours: 30 }, forms)
    expect(forms.lightingForm.hoursOn).toBe(24)

    syncFormsFromRecipePhase({ lighting_photoperiod_hours: 14.3 }, forms)
    expect(forms.lightingForm.hoursOn).toBe(14)
  })

  it('подставляет luxDay при syncLuxDayFromPhotoperiod (Setup)', () => {
    const forms = createForms()
    syncFormsFromRecipePhase(
      { lighting_photoperiod_hours: 16 },
      forms,
      { syncLuxDayFromPhotoperiod: true },
    )
    expect(forms.lightingForm.luxDay).toBe(16000)
  })

  it('не меняет luxDay по умолчанию (Growth)', () => {
    const forms = createForms()
    const originalLux = forms.lightingForm.luxDay
    syncFormsFromRecipePhase({ lighting_photoperiod_hours: 16 }, forms)
    expect(forms.lightingForm.luxDay).toBe(originalLux)
  })

  it('подставляет schedule start/end при syncLightingSchedule (Growth)', () => {
    const forms = createForms()
    syncFormsFromRecipePhase(
      { lighting_photoperiod_hours: 12, lighting_start_time: '08:00' },
      forms,
      { syncLightingSchedule: true },
    )
    expect(forms.lightingForm.scheduleStart).toBe('08:00')
    expect(forms.lightingForm.scheduleEnd).toBe('20:00')
  })

  it('при невалидном lighting_start_time использует дефолт 06:00', () => {
    const forms = createForms()
    syncFormsFromRecipePhase(
      { lighting_photoperiod_hours: 10, lighting_start_time: 'badformat' },
      forms,
      { syncLightingSchedule: true },
    )
    expect(forms.lightingForm.scheduleStart).toBe('06:00')
    expect(forms.lightingForm.scheduleEnd).toBe('16:00')
  })

  it('включает climate при enableClimateOnSync (Growth)', () => {
    const forms = createForms()
    forms.climateForm.enabled = false

    syncFormsFromRecipePhase({}, forms, { enableClimateOnSync: true })

    expect(forms.climateForm.enabled).toBe(true)
  })

  it('не включает climate по умолчанию (Setup)', () => {
    const forms = createForms()
    forms.climateForm.enabled = false

    syncFormsFromRecipePhase({}, forms)

    expect(forms.climateForm.enabled).toBe(false)
  })

  it('игнорирует ноль и отрицательные значения для irrigation', () => {
    const forms = createForms()
    const originalInterval = forms.waterForm.intervalMinutes
    const originalDuration = forms.waterForm.durationSeconds

    syncFormsFromRecipePhase(
      { irrigation_interval_sec: 0, irrigation_duration_sec: -5 },
      forms,
    )

    expect(forms.waterForm.intervalMinutes).toBe(originalInterval)
    expect(forms.waterForm.durationSeconds).toBe(originalDuration)
  })
})

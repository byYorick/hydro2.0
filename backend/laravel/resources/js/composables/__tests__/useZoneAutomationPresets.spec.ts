import { describe, expect, it } from 'vitest'
import {
  applyPresetToWaterForm,
  buildPresetFromWaterForm,
  isPresetModified,
} from '@/composables/useZoneAutomationPresets'
import type { ZoneAutomationPreset } from '@/types/ZoneAutomationPreset'
import type { WaterFormState } from '@/composables/zoneAutomationTypes'

function createWaterForm(overrides: Partial<WaterFormState> = {}): WaterFormState {
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
    ...overrides,
  } as WaterFormState
}

function createPreset(overrides: Partial<ZoneAutomationPreset> = {}): ZoneAutomationPreset {
  return {
    id: 1,
    name: 'DWC Balanced',
    slug: 'dwc-balanced',
    description: 'Test preset',
    scope: 'system',
    is_locked: true,
    tanks_count: 2,
    irrigation_system_type: 'dwc',
    correction_preset_id: null,
    correction_profile: 'balanced',
    config: {
      irrigation: {
        duration_sec: 300,
        interval_sec: 3600,
        correction_during_irrigation: true,
        correction_slack_sec: 30,
      },
      irrigation_decision: {
        strategy: 'task' as const,
      },
      startup: {
        clean_fill_timeout_sec: 1200,
        solution_fill_timeout_sec: 1800,
        prepare_recirculation_timeout_sec: 1200,
        level_poll_interval_sec: 60,
        clean_fill_retry_cycles: 1,
      },
      climate: null,
      lighting: null,
    },
    created_by: null,
    updated_by: null,
    created_at: null,
    updated_at: null,
    ...overrides,
  }
}

describe('applyPresetToWaterForm', () => {
  it('применяет irrigation параметры из пресета', () => {
    const form = createWaterForm()
    const preset = createPreset()

    const result = applyPresetToWaterForm(preset, form)

    expect(result.durationSeconds).toBe(300)
    expect(result.intervalMinutes).toBe(60)
    expect(result.correctionDuringIrrigation).toBe(true)
  })

  it('применяет startup таймауты', () => {
    const form = createWaterForm()
    const preset = createPreset()

    const result = applyPresetToWaterForm(preset, form)

    expect(result.startupCleanFillTimeoutSeconds).toBe(1200)
    expect(result.startupSolutionFillTimeoutSeconds).toBe(1800)
    expect(result.startupPrepareRecirculationTimeoutSeconds).toBe(1200)
    expect(result.startupCleanFillRetryCycles).toBe(1)
  })

  it('применяет tanks_count из пресета', () => {
    const form = createWaterForm({ tanksCount: 3 })
    const preset = createPreset({ tanks_count: 2 })

    const result = applyPresetToWaterForm(preset, form)

    expect(result.tanksCount).toBe(2)
  })

  it('применяет irrigation_decision strategy', () => {
    const form = createWaterForm({ irrigationDecisionStrategy: 'smart_soil_v1' })
    const preset = createPreset()

    const result = applyPresetToWaterForm(preset, form)

    expect(result.irrigationDecisionStrategy).toBe('task')
  })

  it('сохраняет поля формы, не затронутые пресетом', () => {
    const form = createWaterForm({
      targetPh: 6.2,
      targetEc: 2.0,
      cleanTankFillL: 500,
      diagnosticsEnabled: false,
    })
    const preset = createPreset()

    const result = applyPresetToWaterForm(preset, form)

    expect(result.targetPh).toBe(6.2)
    expect(result.targetEc).toBe(2.0)
    expect(result.cleanTankFillL).toBe(500)
    expect(result.diagnosticsEnabled).toBe(false)
  })

  it('применяет smart_soil_v1 decision config если есть', () => {
    const form = createWaterForm()
    const preset = createPreset({
      config: {
        ...createPreset().config,
        irrigation_decision: {
          strategy: 'smart_soil_v1' as const,
          config: {
            lookback_sec: 900,
            min_samples: 5,
            stale_after_sec: 300,
            hysteresis_pct: 3.0,
          },
        },
      },
    })

    const result = applyPresetToWaterForm(preset, form)

    expect(result.irrigationDecisionStrategy).toBe('smart_soil_v1')
    expect(result.irrigationDecisionLookbackSeconds).toBe(900)
    expect(result.irrigationDecisionMinSamples).toBe(5)
  })
})

describe('buildPresetFromWaterForm', () => {
  it('собирает корректный payload из формы', () => {
    const form = createWaterForm({
      durationSeconds: 300,
      intervalMinutes: 60,
      correctionDuringIrrigation: true,
      tanksCount: 2,
      startupCleanFillTimeoutSeconds: 1200,
      startupSolutionFillTimeoutSeconds: 1800,
      startupPrepareRecirculationTimeoutSeconds: 1200,
      startupCleanFillRetryCycles: 1,
    })

    const payload = buildPresetFromWaterForm(form, {
      name: 'My Preset',
      description: 'Test description',
      irrigationSystemType: 'dwc',
      correctionProfile: 'balanced',
    })

    expect(payload.name).toBe('My Preset')
    expect(payload.description).toBe('Test description')
    expect(payload.tanks_count).toBe(2)
    expect(payload.irrigation_system_type).toBe('dwc')
    expect(payload.correction_profile).toBe('balanced')
    expect(payload.config.irrigation.duration_sec).toBe(300)
    expect(payload.config.irrigation.interval_sec).toBe(3600)
    expect(payload.config.irrigation.correction_during_irrigation).toBe(true)
    expect(payload.config.startup.clean_fill_timeout_sec).toBe(1200)
    expect(payload.config.startup.solution_fill_timeout_sec).toBe(1800)
  })

  it('включает irrigation_decision config для smart_soil_v1', () => {
    const form = createWaterForm({
      irrigationDecisionStrategy: 'smart_soil_v1',
      irrigationDecisionLookbackSeconds: 900,
      irrigationDecisionMinSamples: 5,
    })

    const payload = buildPresetFromWaterForm(form, {
      name: 'Soil Preset',
      irrigationSystemType: 'drip_tape',
    })

    expect(payload.config.irrigation_decision.strategy).toBe('smart_soil_v1')
    expect(payload.config.irrigation_decision.config?.lookback_sec).toBe(900)
    expect(payload.config.irrigation_decision.config?.min_samples).toBe(5)
  })

  it('не включает irrigation_decision config для task strategy', () => {
    const form = createWaterForm({ irrigationDecisionStrategy: 'task' })

    const payload = buildPresetFromWaterForm(form, {
      name: 'Task Preset',
      irrigationSystemType: 'dwc',
    })

    expect(payload.config.irrigation_decision.strategy).toBe('task')
    expect(payload.config.irrigation_decision.config).toBeUndefined()
  })

  it('конвертирует intervalMinutes в interval_sec', () => {
    const form = createWaterForm({ intervalMinutes: 90 })

    const payload = buildPresetFromWaterForm(form, {
      name: 'Test',
      irrigationSystemType: 'nft',
    })

    expect(payload.config.irrigation.interval_sec).toBe(5400)
  })

  it('использует fallback для startup если undefined', () => {
    const form = createWaterForm({
      startupCleanFillTimeoutSeconds: undefined,
      startupSolutionFillTimeoutSeconds: undefined,
      startupPrepareRecirculationTimeoutSeconds: undefined,
      startupCleanFillRetryCycles: undefined,
    })

    const payload = buildPresetFromWaterForm(form, {
      name: 'Fallback',
      irrigationSystemType: 'dwc',
    })

    expect(payload.config.startup.clean_fill_timeout_sec).toBe(1200)
    expect(payload.config.startup.solution_fill_timeout_sec).toBe(1800)
    expect(payload.config.startup.prepare_recirculation_timeout_sec).toBe(1200)
    expect(payload.config.startup.clean_fill_retry_cycles).toBe(1)
  })
})

describe('isPresetModified', () => {
  it('возвращает false если форма соответствует пресету', () => {
    const preset = createPreset()
    const form = applyPresetToWaterForm(preset, createWaterForm())

    expect(isPresetModified(preset, form)).toBe(false)
  })

  it('возвращает true при изменении duration', () => {
    const preset = createPreset()
    const form = applyPresetToWaterForm(preset, createWaterForm())
    form.durationSeconds = 999

    expect(isPresetModified(preset, form)).toBe(true)
  })

  it('возвращает true при изменении interval', () => {
    const preset = createPreset()
    const form = applyPresetToWaterForm(preset, createWaterForm())
    form.intervalMinutes = 45

    expect(isPresetModified(preset, form)).toBe(true)
  })

  it('возвращает true при изменении strategy', () => {
    const preset = createPreset()
    const form = applyPresetToWaterForm(preset, createWaterForm())
    form.irrigationDecisionStrategy = 'smart_soil_v1'

    expect(isPresetModified(preset, form)).toBe(true)
  })

  it('возвращает true при изменении startup timeout', () => {
    const preset = createPreset()
    const form = applyPresetToWaterForm(preset, createWaterForm())
    form.startupCleanFillTimeoutSeconds = 9999

    expect(isPresetModified(preset, form)).toBe(true)
  })

  it('не реагирует на изменение полей вне пресета (targetPh)', () => {
    const preset = createPreset()
    const form = applyPresetToWaterForm(preset, createWaterForm())
    form.targetPh = 99

    expect(isPresetModified(preset, form)).toBe(false)
  })
})

describe('round-trip: apply → build → apply', () => {
  it('preset → form → payload → form сохраняет ключевые параметры', () => {
    const original = createPreset({
      config: {
        irrigation: {
          duration_sec: 450,
          interval_sec: 2700,
          correction_during_irrigation: false,
          correction_slack_sec: 45,
        },
        irrigation_decision: { strategy: 'task' as const },
        startup: {
          clean_fill_timeout_sec: 900,
          solution_fill_timeout_sec: 1500,
          prepare_recirculation_timeout_sec: 1100,
          level_poll_interval_sec: 45,
          clean_fill_retry_cycles: 2,
        },
        climate: null,
        lighting: null,
      },
    })

    const form1 = applyPresetToWaterForm(original, createWaterForm())
    const payload = buildPresetFromWaterForm(form1, {
      name: 'Roundtrip',
      irrigationSystemType: 'dwc',
    })
    const rebuilt = createPreset({ config: payload.config })
    const form2 = applyPresetToWaterForm(rebuilt, createWaterForm())

    expect(form2.durationSeconds).toBe(form1.durationSeconds)
    expect(form2.intervalMinutes).toBe(form1.intervalMinutes)
    expect(form2.correctionDuringIrrigation).toBe(form1.correctionDuringIrrigation)
    expect(form2.startupCleanFillTimeoutSeconds).toBe(form1.startupCleanFillTimeoutSeconds)
    expect(form2.startupSolutionFillTimeoutSeconds).toBe(form1.startupSolutionFillTimeoutSeconds)
    expect(form2.startupPrepareRecirculationTimeoutSeconds).toBe(form1.startupPrepareRecirculationTimeoutSeconds)
    expect(form2.startupCleanFillRetryCycles).toBe(form1.startupCleanFillRetryCycles)
  })
})

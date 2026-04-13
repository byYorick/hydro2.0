import { describe, expect, it } from 'vitest'
import { buildCreateGrowCyclePayload } from '@/services/automation/growCyclePayload'
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

describe('buildCreateGrowCyclePayload', () => {
  it('строит payload для 2-бакового drip контура с указанием объёмов', () => {
    const payload = buildCreateGrowCyclePayload({
      waterForm: createWaterForm({ tanksCount: 2 }),
      recipeRevisionId: 42,
      plantId: 7,
      plantingAt: '2026-04-01T10:00:00Z',
      expectedHarvestAt: '2026-06-01T10:00:00Z',
      startImmediately: true,
    })

    expect(payload).toEqual({
      recipe_revision_id: 42,
      plant_id: 7,
      planting_at: '2026-04-01T10:00:00Z',
      start_immediately: true,
      irrigation: {
        system_type: 'drip',
        interval_minutes: 30,
        duration_seconds: 120,
        clean_tank_fill_l: 300,
        nutrient_tank_target_l: 280,
        irrigation_batch_l: 20,
      },
      settings: {
        expected_harvest_at: '2026-06-01T10:00:00Z',
      },
    })
  })

  it('опускает объёмы баков для 3-бакового контура', () => {
    const payload = buildCreateGrowCyclePayload({
      waterForm: createWaterForm({ tanksCount: 3, systemType: 'nft' }),
      recipeRevisionId: 1,
      plantId: 1,
      startImmediately: false,
    })

    expect(payload.irrigation.clean_tank_fill_l).toBeUndefined()
    expect(payload.irrigation.nutrient_tank_target_l).toBeUndefined()
    expect(payload.irrigation.irrigation_batch_l).toBeUndefined()
    expect(payload.irrigation.system_type).toBe('nft')
    expect(payload.start_immediately).toBe(false)
  })

  it('нормализует пустую строку expected_harvest_at в undefined', () => {
    const payload = buildCreateGrowCyclePayload({
      waterForm: createWaterForm(),
      recipeRevisionId: 1,
      plantId: 1,
      expectedHarvestAt: '',
      startImmediately: true,
    })

    expect(payload.settings.expected_harvest_at).toBeUndefined()
  })

  it('передаёт planting_at только если указан', () => {
    const payload = buildCreateGrowCyclePayload({
      waterForm: createWaterForm(),
      recipeRevisionId: 1,
      plantId: 1,
      startImmediately: true,
    })

    expect(payload.planting_at).toBeUndefined()
  })

  it('передаёт interval_minutes и duration_seconds из формы напрямую', () => {
    const payload = buildCreateGrowCyclePayload({
      waterForm: createWaterForm({ intervalMinutes: 45, durationSeconds: 90 }),
      recipeRevisionId: 1,
      plantId: 1,
      startImmediately: true,
    })

    expect(payload.irrigation.interval_minutes).toBe(45)
    expect(payload.irrigation.duration_seconds).toBe(90)
  })
})

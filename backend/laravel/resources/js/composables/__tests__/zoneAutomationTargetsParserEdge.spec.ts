import { describe, expect, it } from 'vitest'
import { applyAutomationFromRecipe, syncSystemToTankLayout } from '@/composables/zoneAutomationTargetsParser'
import type { ZoneAutomationForms } from '@/composables/zoneAutomationTypes'

/**
 * Дополнительные edge-case тесты для applyAutomationFromRecipe.
 * Happy-path покрыт интеграционным тестом в zoneAutomationFormLogic.spec.ts —
 * здесь проверяются clamp-границы, execution/targets precedence, fallback
 * на плоские поля и устойчивость к null/invalid данным.
 */
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
    } as ZoneAutomationForms['waterForm'],
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

describe('applyAutomationFromRecipe — ранний возврат', () => {
  it('ничего не делает при null input', () => {
    const forms = createForms()
    const before = JSON.stringify(forms)
    applyAutomationFromRecipe(null, forms)
    expect(JSON.stringify(forms)).toBe(before)
  })

  it('ничего не делает при non-object input (строка, число, массив)', () => {
    const forms = createForms()
    const before = JSON.stringify(forms)
    applyAutomationFromRecipe('invalid', forms)
    applyAutomationFromRecipe(42, forms)
    applyAutomationFromRecipe([1, 2, 3], forms)
    expect(JSON.stringify(forms)).toBe(before)
  })

  it('не падает на пустом объекте', () => {
    const forms = createForms()
    expect(() => applyAutomationFromRecipe({}, forms)).not.toThrow()
  })
})

describe('applyAutomationFromRecipe — clamp границ', () => {
  it('clamp pH в [4, 9]', () => {
    const forms = createForms()
    applyAutomationFromRecipe({ ph: { target: 15 } }, forms)
    expect(forms.waterForm.targetPh).toBe(9)

    applyAutomationFromRecipe({ ph: { target: 1 } }, forms)
    expect(forms.waterForm.targetPh).toBe(4)
  })

  it('clamp EC в [0.1, 10]', () => {
    const forms = createForms()
    applyAutomationFromRecipe({ ec: { target: 99 } }, forms)
    expect(forms.waterForm.targetEc).toBe(10)

    applyAutomationFromRecipe({ ec: { target: -5 } }, forms)
    expect(forms.waterForm.targetEc).toBe(0.1)
  })

  it('clamp интервал полива в [5, 1440] минут', () => {
    const forms = createForms()
    applyAutomationFromRecipe(
      { extensions: { subsystems: { irrigation: { targets: { interval_sec: 60 } } } } },
      forms,
    )
    expect(forms.waterForm.intervalMinutes).toBe(5)

    applyAutomationFromRecipe(
      { extensions: { subsystems: { irrigation: { targets: { interval_sec: 200000 } } } } },
      forms,
    )
    expect(forms.waterForm.intervalMinutes).toBe(1440)
  })

  it('clamp длительность полива в [1, 3600] секунд', () => {
    const forms = createForms()
    applyAutomationFromRecipe(
      { extensions: { subsystems: { irrigation: { targets: { duration_sec: 99999 } } } } },
      forms,
    )
    expect(forms.waterForm.durationSeconds).toBe(3600)
  })

  it('clamp lux day/night в [0, 120000]', () => {
    const forms = createForms()
    applyAutomationFromRecipe(
      {
        extensions: {
          subsystems: {
            lighting: { targets: { lux: { day: 999999, night: -500 } } },
          },
        },
      },
      forms,
    )
    expect(forms.lightingForm.luxDay).toBe(120000)
    expect(forms.lightingForm.luxNight).toBe(0)
  })

  it('clamp hoursOn в [0, 24]', () => {
    const forms = createForms()
    applyAutomationFromRecipe(
      {
        extensions: {
          subsystems: { lighting: { targets: { photoperiod: { hours_on: 48 } } } },
        },
      },
      forms,
    )
    expect(forms.lightingForm.hoursOn).toBe(24)
  })

  it('clamp климатическую температуру в [10, 35]', () => {
    const forms = createForms()
    applyAutomationFromRecipe(
      {
        extensions: {
          subsystems: { climate: { targets: { temperature: { day: 50, night: 5 } } } },
        },
      },
      forms,
    )
    expect(forms.climateForm.dayTemp).toBe(35)
    expect(forms.climateForm.nightTemp).toBe(10)
  })

  it('clamp влажность в [30, 90]', () => {
    const forms = createForms()
    applyAutomationFromRecipe(
      {
        extensions: {
          subsystems: { climate: { targets: { humidity: { day: 100, night: 10 } } } },
        },
      },
      forms,
    )
    expect(forms.climateForm.dayHumidity).toBe(90)
    expect(forms.climateForm.nightHumidity).toBe(30)
  })
})

describe('applyAutomationFromRecipe — execution vs targets precedence', () => {
  it('execution.interval_sec переопределяет targets.interval_sec', () => {
    const forms = createForms()
    applyAutomationFromRecipe(
      {
        extensions: {
          subsystems: {
            irrigation: {
              execution: { interval_sec: 600 },
              targets: { interval_sec: 1800 },
            },
          },
        },
      },
      forms,
    )
    expect(forms.waterForm.intervalMinutes).toBe(10)
  })

  it('execution.duration_sec переопределяет targets.duration_sec', () => {
    const forms = createForms()
    applyAutomationFromRecipe(
      {
        extensions: {
          subsystems: {
            irrigation: {
              execution: { duration_sec: 90 },
              targets: { duration_sec: 200 },
            },
          },
        },
      },
      forms,
    )
    expect(forms.waterForm.durationSeconds).toBe(90)
  })
})

describe('applyAutomationFromRecipe — side effects', () => {
  it('systemType=drip форсирует tanksCount=2 и enableDrainControl=false', () => {
    const forms = createForms()
    forms.waterForm.tanksCount = 3
    forms.waterForm.enableDrainControl = true

    applyAutomationFromRecipe(
      { extensions: { subsystems: { irrigation: { targets: { system_type: 'drip' } } } } },
      forms,
    )

    expect(forms.waterForm.systemType).toBe('drip')
    expect(forms.waterForm.tanksCount).toBe(2)
    expect(forms.waterForm.enableDrainControl).toBe(false)
  })

  it('systemType=nft даёт tanksCount=3 через syncSystemToTankLayout', () => {
    const forms = createForms()

    applyAutomationFromRecipe(
      { extensions: { subsystems: { irrigation: { targets: { system_type: 'nft' } } } } },
      forms,
    )

    expect(forms.waterForm.systemType).toBe('nft')
    expect(forms.waterForm.tanksCount).toBe(3)
  })

  it('tanksCount=2 явно сбрасывает enableDrainControl', () => {
    const forms = createForms()
    forms.waterForm.enableDrainControl = true

    applyAutomationFromRecipe(
      { extensions: { subsystems: { irrigation: { targets: { tanks_count: 2 } } } } },
      forms,
    )

    expect(forms.waterForm.tanksCount).toBe(2)
    expect(forms.waterForm.enableDrainControl).toBe(false)
  })

  it('игнорирует tanks_count вне {2, 3}', () => {
    const forms = createForms()
    forms.waterForm.tanksCount = 3

    applyAutomationFromRecipe(
      { extensions: { subsystems: { irrigation: { targets: { tanks_count: 5 } } } } },
      forms,
    )

    expect(forms.waterForm.tanksCount).toBe(3)
  })
})

describe('applyAutomationFromRecipe — fallback на плоские поля', () => {
  it('использует targets.irrigation_interval_sec как fallback', () => {
    const forms = createForms()
    applyAutomationFromRecipe({ irrigation_interval_sec: 1200 }, forms)
    expect(forms.waterForm.intervalMinutes).toBe(20)
  })

  it('использует targets.irrigation_duration_sec как fallback', () => {
    const forms = createForms()
    applyAutomationFromRecipe({ irrigation_duration_sec: 150 }, forms)
    expect(forms.waterForm.durationSeconds).toBe(150)
  })

  it('использует targets.light_hours как fallback photoperiod', () => {
    const forms = createForms()
    applyAutomationFromRecipe({ light_hours: 14 }, forms)
    expect(forms.lightingForm.hoursOn).toBe(14)
  })

  it('использует climate_request.temp_air_target если нет subsystems.climate.temperature', () => {
    const forms = createForms()
    applyAutomationFromRecipe({ climate_request: { temp_air_target: 24 } }, forms)
    expect(forms.climateForm.dayTemp).toBe(24)
  })

  it('ночная температура падает обратно на дневную, если night не задан', () => {
    const forms = createForms()
    applyAutomationFromRecipe(
      {
        extensions: {
          subsystems: { climate: { targets: { temperature: { day: 28 } } } },
        },
      },
      forms,
    )
    expect(forms.climateForm.nightTemp).toBe(28)
  })
})

describe('applyAutomationFromRecipe — валидация значений', () => {
  it('игнорирует invalid systemType', () => {
    const forms = createForms()
    const before = forms.waterForm.systemType

    applyAutomationFromRecipe(
      { extensions: { subsystems: { irrigation: { targets: { system_type: 'bogus' } } } } },
      forms,
    )

    expect(forms.waterForm.systemType).toBe(before)
  })

  it('принимает только "task"/"smart_soil_v1" как decision strategy', () => {
    const forms = createForms()

    applyAutomationFromRecipe(
      { extensions: { subsystems: { irrigation: { decision: { strategy: 'unknown' } } } } },
      forms,
    )
    expect(forms.waterForm.irrigationDecisionStrategy).toBe('task')

    applyAutomationFromRecipe(
      { extensions: { subsystems: { irrigation: { decision: { strategy: 'smart_soil_v1' } } } } },
      forms,
    )
    expect(forms.waterForm.irrigationDecisionStrategy).toBe('smart_soil_v1')
  })

  it('принимает только три значения diagnostics workflow', () => {
    const forms = createForms()
    forms.waterForm.diagnosticsWorkflow = 'startup'

    applyAutomationFromRecipe(
      { extensions: { subsystems: { diagnostics: { targets: { workflow: 'bogus' } } } } },
      forms,
    )
    expect(forms.waterForm.diagnosticsWorkflow).toBe('startup')

    applyAutomationFromRecipe(
      { extensions: { subsystems: { diagnostics: { targets: { workflow: 'diagnostics' } } } } },
      forms,
    )
    expect(forms.waterForm.diagnosticsWorkflow).toBe('diagnostics')
  })

  it('игнорирует non-number в числовых полях', () => {
    const forms = createForms()
    const phBefore = forms.waterForm.targetPh

    applyAutomationFromRecipe({ ph: { target: 'not a number' } }, forms)

    expect(forms.waterForm.targetPh).toBe(phBefore)
  })
})

describe('applyAutomationFromRecipe — частичные подсистемы', () => {
  it('обновляет только irrigation, не трогая climate и lighting', () => {
    const forms = createForms()
    const climateSnapshot = { ...forms.climateForm }
    const lightingSnapshot = { ...forms.lightingForm }

    applyAutomationFromRecipe(
      { extensions: { subsystems: { irrigation: { targets: { duration_sec: 180 } } } } },
      forms,
    )

    expect(forms.waterForm.durationSeconds).toBe(180)
    expect(forms.climateForm).toEqual(climateSnapshot)
    expect(forms.lightingForm).toEqual(lightingSnapshot)
  })

  it('subsystems.solution принимается как alias для solution_change', () => {
    const forms = createForms()

    applyAutomationFromRecipe(
      {
        extensions: {
          subsystems: { solution: { enabled: true, targets: { interval_sec: 7200 } } },
        },
      },
      forms,
    )

    expect(forms.waterForm.solutionChangeEnabled).toBe(true)
    expect(forms.waterForm.solutionChangeIntervalMinutes).toBe(120)
  })
})

describe('applyAutomationFromRecipe — drain control', () => {
  it('обновляет drain независимо: enabled + target_percent', () => {
    const forms = createForms()

    applyAutomationFromRecipe(
      {
        extensions: {
          subsystems: {
            irrigation: {
              targets: {
                tanks_count: 3,
                drain_control: { enabled: true, target_percent: 45 },
              },
            },
          },
        },
      },
      forms,
    )

    expect(forms.waterForm.enableDrainControl).toBe(true)
    expect(forms.waterForm.drainTargetPercent).toBe(45)
  })

  it('clamp drainTargetPercent в [0, 100]', () => {
    const forms = createForms()

    applyAutomationFromRecipe(
      {
        extensions: {
          subsystems: {
            irrigation: { targets: { drain_control: { target_percent: 150 } } },
          },
        },
      },
      forms,
    )

    expect(forms.waterForm.drainTargetPercent).toBe(100)
  })
})

describe('syncSystemToTankLayout', () => {
  it('drip → 2 бака, drain отключён', () => {
    const forms = createForms()
    forms.waterForm.enableDrainControl = true
    syncSystemToTankLayout(forms.waterForm, 'drip')
    expect(forms.waterForm.tanksCount).toBe(2)
    expect(forms.waterForm.enableDrainControl).toBe(false)
  })

  it('nft → 3 бака', () => {
    const forms = createForms()
    syncSystemToTankLayout(forms.waterForm, 'nft')
    expect(forms.waterForm.tanksCount).toBe(3)
  })

  it('substrate_trays → 3 бака', () => {
    const forms = createForms()
    syncSystemToTankLayout(forms.waterForm, 'substrate_trays')
    expect(forms.waterForm.tanksCount).toBe(3)
  })
})

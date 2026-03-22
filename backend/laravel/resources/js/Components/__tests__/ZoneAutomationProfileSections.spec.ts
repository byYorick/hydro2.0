import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ZoneAutomationProfileSections from '@/Components/ZoneAutomationProfileSections.vue'

describe('ZoneAutomationProfileSections', () => {
  it('показывает уже привязанную ноду по binding_role в списке обязательных устройств', () => {
    const wrapper = mount(ZoneAutomationProfileSections, {
      props: {
        canConfigure: true,
        showNodeBindings: true,
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
          prepareToleranceEcPct: 10,
          prepareTolerancePhPct: 5,
          correctionMaxEcCorrectionAttempts: 8,
          correctionMaxPhCorrectionAttempts: 8,
          correctionPrepareRecirculationMaxAttempts: 6,
          correctionPrepareRecirculationMaxCorrectionAttempts: 24,
          correctionStabilizationSec: 30,
          enableDrainControl: false,
          drainTargetPercent: 0,
          diagnosticsEnabled: true,
          diagnosticsIntervalMinutes: 15,
          diagnosticsWorkflow: 'startup',
          cleanTankFullThreshold: 0.95,
          refillDurationSeconds: 30,
          refillTimeoutSeconds: 600,
          refillRequiredNodeTypes: 'irrig,climate,light',
          refillPreferredChannel: 'fill_valve',
          startupCleanFillTimeoutSeconds: 1800,
          startupSolutionFillTimeoutSeconds: 1800,
          startupPrepareRecirculationTimeoutSeconds: 900,
          startupCleanFillRetryCycles: 2,
          irrigationRecoveryMaxContinueAttempts: 3,
          irrigationRecoveryTimeoutSeconds: 600,
          solutionChangeEnabled: false,
          solutionChangeIntervalMinutes: 180,
          solutionChangeDurationSeconds: 120,
          manualIrrigationSeconds: 90,
          twoTankCleanFillStartSteps: 1,
          twoTankCleanFillStopSteps: 1,
          twoTankSolutionFillStartSteps: 1,
          twoTankSolutionFillStopSteps: 1,
          twoTankPrepareRecirculationStartSteps: 1,
          twoTankPrepareRecirculationStopSteps: 1,
          twoTankIrrigationRecoveryStartSteps: 1,
          twoTankIrrigationRecoveryStopSteps: 1,
        },
        lightingForm: {
          enabled: false,
          luxDay: 18000,
          luxNight: 0,
          hoursOn: 16,
          intervalMinutes: 30,
          scheduleStart: '06:00',
          scheduleEnd: '22:00',
          manualIntensity: 75,
          manualDurationHours: 4,
        },
        zoneClimateForm: {
          enabled: false,
        },
        assignments: {
          irrigation: 301,
          ph_correction: null,
          ec_correction: null,
          light: null,
          co2_sensor: null,
          co2_actuator: null,
          root_vent_actuator: null,
        },
        availableNodes: [
          {
            id: 301,
            uid: 'nd-irrig-bound',
            type: 'controller',
            channels: [{ binding_role: 'main_pump' }],
          },
        ],
      },
      global: {
        stubs: {
          Button: {
            template: '<button><slot /></button>',
          },
        },
      },
    })

    const irrigationSelect = wrapper.find('select')
    expect(irrigationSelect.exists()).toBe(true)
    expect(irrigationSelect.text()).toContain('nd-irrig-bound')
    expect((irrigationSelect.element as HTMLSelectElement).value).toBe('301')
  })
})

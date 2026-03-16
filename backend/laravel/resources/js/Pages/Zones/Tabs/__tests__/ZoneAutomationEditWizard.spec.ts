import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@/Components/Modal.vue', () => ({
  default: {
    name: 'Modal',
    props: ['open', 'title', 'size'],
    template: '<div v-if="open"><slot /><slot name="footer" /></div>',
  },
}))

vi.mock('@/Components/Button.vue', () => ({
  default: {
    name: 'Button',
    props: ['disabled', 'variant', 'type'],
    template: '<button :disabled="disabled" :type="type"><slot /></button>',
  },
}))

import ZoneAutomationEditWizard from '../ZoneAutomationEditWizard.vue'

function createProps() {
  return {
    open: true,
    isApplying: false,
    isSystemTypeLocked: false,
    climateForm: {
      enabled: true,
      dayTemp: 23,
      nightTemp: 20,
      dayHumidity: 62,
      nightHumidity: 70,
      intervalMinutes: 5,
      dayStart: '07:00',
      nightStart: '19:00',
      ventMinPercent: 15,
      ventMaxPercent: 85,
      useExternalTelemetry: true,
      outsideTempMin: 4,
      outsideTempMax: 34,
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
      cycleStartWorkflowEnabled: true,
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

describe('ZoneAutomationEditWizard.vue', () => {
  it('показывает пояснение про observe-window и отсутствие legacy wait state', async () => {
    const wrapper = mount(ZoneAutomationEditWizard, {
      props: createProps(),
    })

    const nextButton = wrapper.findAll('button').find((button) => button.text() === 'Далее')
    expect(nextButton).toBeTruthy()
    await nextButton!.trigger('click')

    expect(wrapper.text()).not.toContain('Legacy fallback hold для EC')
    expect(wrapper.text()).toContain('Observe-window после дозы больше не редактируется в этом wizard')
    expect(wrapper.text()).toContain('Legacy wait-поля больше не хранятся')
  })

  it('блокирует поле "Баков" для drip-системы', async () => {
    const wrapper = mount(ZoneAutomationEditWizard, {
      props: createProps(),
    })

    const nextButton = wrapper.findAll('button').find((button) => button.text() === 'Далее')
    expect(nextButton).toBeTruthy()
    await nextButton!.trigger('click')

    const tanksInput = wrapper.find('input[min="2"][max="3"]')
    expect(tanksInput.exists()).toBe(true)
    expect(tanksInput.attributes('disabled')).toBeDefined()
  })

  it('санитизирует payload waterForm перед emit apply', async () => {
    const wrapper = mount(ZoneAutomationEditWizard, {
      props: createProps(),
    })

    const vm = wrapper.vm as any
    vm.draftWaterForm.systemType = 'drip'
    vm.draftWaterForm.tanksCount = 3
    vm.draftWaterForm.enableDrainControl = true

    const nextButtons = () => wrapper.findAll('button').filter((button) => button.text() === 'Далее')
    await nextButtons()[0].trigger('click')
    await nextButtons()[0].trigger('click')

    const saveButton = wrapper.findAll('button').find((button) => button.text() === 'Сохранить')
    expect(saveButton).toBeTruthy()
    await saveButton!.trigger('click')

    const emitted = wrapper.emitted('apply')
    expect(emitted).toBeTruthy()
    const payload = emitted?.[0]?.[0] as any
    expect(payload.waterForm.systemType).toBe('drip')
    expect(payload.waterForm.tanksCount).toBe(2)
    expect(payload.waterForm.enableDrainControl).toBe(false)
  })
})

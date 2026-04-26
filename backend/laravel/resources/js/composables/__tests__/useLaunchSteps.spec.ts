import { beforeEach, describe, expect, it } from 'vitest'
import { computed, reactive, ref } from 'vue'
import { useLaunchSteps } from '../useLaunchSteps'
import {
  automationProfileDefaults,
  type AutomationProfile,
} from '@/schemas/automationProfile'
import type { LaunchFlowManifest } from '@/services/api/launchFlow'

function makeManifest(blockers: string[] = []): LaunchFlowManifest {
  return {
    zone_id: null,
    role: null,
    role_hints: {},
    readiness: {
      ready: blockers.length === 0,
      blockers: blockers.map((code, i) => ({
        code,
        message: code,
        severity: 'error',
      })),
      warnings: [],
    },
    steps: [
      { id: 'zone', title: 'Z', visible: true, required: true },
      { id: 'recipe', title: 'R', visible: true, required: true },
      { id: 'automation', title: 'A', visible: true, required: true },
      { id: 'calibration', title: 'C', visible: true, required: true },
      { id: 'preview', title: 'P', visible: true, required: true },
    ],
  }
}

describe('useLaunchSteps', () => {
  let state: Record<string, unknown>
  let automationProfile: ReturnType<typeof ref<AutomationProfile>>
  let manifest: ReturnType<typeof ref<LaunchFlowManifest | null>>
  let isFormValid: ReturnType<typeof ref<boolean>>
  let currentStep: ReturnType<typeof ref<string>>

  beforeEach(() => {
    state = reactive({})
    automationProfile = ref(structuredClone(automationProfileDefaults))
    manifest = ref(makeManifest())
    isFormValid = ref(true)
    currentStep = ref('zone')
  })

  function build() {
    return useLaunchSteps({
      state,
      manifest: computed(() => manifest.value),
      automationProfile: automationProfile as ReturnType<typeof ref<AutomationProfile>>,
      isFormValid: computed(() => isFormValid.value),
      currentStep,
    })
  }

  it('maps backend manifest steps to LaunchStep with labels', () => {
    const { stepperSteps } = build()
    expect(stepperSteps.value).toHaveLength(5)
    expect(stepperSteps.value[0]).toMatchObject({ id: 'zone', label: 'Зона' })
    expect(stepperSteps.value[4]).toMatchObject({ id: 'preview', label: 'Подтверждение' })
  })

  it('canProceedStep gating: zone requires zone_id', () => {
    const { canProceedStep } = build()
    expect(canProceedStep('zone')).not.toBe(true)
    state.zone_id = 5
    expect(canProceedStep('zone')).toBe(true)
  })

  it('canProceedStep gating: recipe requires triple recipe/plant/planting_at', () => {
    const { canProceedStep } = build()
    state.recipe_revision_id = 3
    expect(canProceedStep('recipe')).toMatchObject({ ok: false })
    state.plant_id = 1
    expect(canProceedStep('recipe')).toMatchObject({ ok: false })
    state.planting_at = '2026-04-25T12:00:00Z'
    expect(canProceedStep('recipe')).toBe(true)
  })

  it('canProceedStep gating: automation requires required bindings', () => {
    const { canProceedStep } = build()
    expect(canProceedStep('automation')).toMatchObject({ ok: false })

    automationProfile.value!.assignments.irrigation = 1
    automationProfile.value!.assignments.ph_correction = 2
    automationProfile.value!.assignments.ec_correction = 3
    expect(canProceedStep('automation')).toBe(true)
  })

  it('automation: lighting enabled requires light binding', () => {
    const { canProceedStep } = build()
    automationProfile.value!.assignments.irrigation = 1
    automationProfile.value!.assignments.ph_correction = 2
    automationProfile.value!.assignments.ec_correction = 3
    automationProfile.value!.lightingForm.enabled = true
    expect(canProceedStep('automation')).toMatchObject({ ok: false })
    automationProfile.value!.assignments.light = 4
    expect(canProceedStep('automation')).toBe(true)
  })

  it('canProceedStep gating: calibration blocked by manifest blockers', () => {
    manifest.value = makeManifest(['pump-blocker'])
    const { canProceedStep } = build()
    expect(canProceedStep('calibration')).toMatchObject({ ok: false })
    manifest.value = makeManifest([])
    expect(canProceedStep('calibration')).toBe(true)
  })

  it('canProceedStep gating: preview requires valid form + no blockers', () => {
    const { canProceedStep } = build()
    isFormValid.value = false
    expect(canProceedStep('preview')).toMatchObject({ ok: false, reason: expect.stringContaining('валиден') })
    isFormValid.value = true
    expect(canProceedStep('preview')).toBe(true)
    manifest.value = makeManifest(['x'])
    expect(canProceedStep('preview')).toMatchObject({ ok: false })
  })

  it('completion: marks current=current, prev failing=warn, prev passing=done', () => {
    const { completion } = build()
    currentStep.value = 'recipe'
    state.zone_id = 5
    expect(completion.value[0]).toBe('done') // zone passable
    expect(completion.value[1]).toBe('current')
    expect(completion.value[2]).toBe('todo')

    state.zone_id = undefined
    currentStep.value = 'preview'
    // zone не пройден → warn
    expect(completion.value[0]).toBe('warn')
  })

  it('canLaunch: only on preview when canProceed=true', () => {
    const { canLaunch } = build()
    currentStep.value = 'preview'
    isFormValid.value = true
    expect(canLaunch.value).toBe(true)

    currentStep.value = 'recipe'
    expect(canLaunch.value).toBe(false)
  })
})

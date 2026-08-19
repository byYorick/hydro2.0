/**
 * Launch wizard step navigation + validation logic.
 *
 * Извлечено из Pages/Launch/Index.vue для соблюдения file-size guard.
 * Содержит:
 *   - STEP_DEFS — labels/sub для LaunchStepper
 *   - canProceedStep(stepId) — gate-функция per step (forward navigation)
 *   - completion[] computed — состояние bullets в LaunchStepper
 *   - isRepeatPath — короткий линейный путь (рецепт → подтверждение) для готовой зоны
 */
import { computed, type ComputedRef, type Ref } from 'vue'
import type { LaunchStep, StepCompletion } from '@/Components/Launch/Shell/types'
import type { GrowCycleLaunchPayload } from '@/schemas/growCycleLaunch'
import type { AutomationProfile } from '@/schemas/automationProfile'
import type { LaunchFlowManifest } from '@/services/api/launchFlow'

export interface ProceedFailure {
  ok: false
  reason: string
}

export type ProceedVerdict = true | ProceedFailure

const STEP_DEFS: Record<string, { label: string; sub: string }> = {
  zone: { label: 'Зона', sub: 'теплица + зона' },
  recipe: { label: 'Рецепт', sub: 'культура + фазы' },
  automation: { label: 'Автоматика', sub: 'узлы и роли' },
  calibration: { label: 'Калибровка', sub: '5 подсистем' },
  preview: { label: 'Подтверждение', sub: 'diff + запуск' },
}

const LINEAR_REPEAT_STEP_IDS = new Set(['zone', 'recipe', 'preview'])

export interface UseLaunchStepsInput {
  state: Partial<GrowCycleLaunchPayload>
  manifest: ComputedRef<LaunchFlowManifest | null>
  automationProfile: Ref<AutomationProfile>
  isFormValid: ComputedRef<boolean>
  currentStep: Ref<string>
}

export interface UseLaunchStepsReturn {
  stepperSteps: ComputedRef<LaunchStep[]>
  allVisibleSteps: ComputedRef<LaunchStep[]>
  activeIndex: ComputedRef<number>
  completion: ComputedRef<StepCompletion[]>
  currentStepDef: ComputedRef<LaunchStep>
  canLaunch: ComputedRef<boolean>
  canProceedStep: (stepId: string) => ProceedVerdict
  isRepeatPath: ComputedRef<boolean>
  isAdvancedStep: ComputedRef<boolean>
}

export function useLaunchSteps(input: UseLaunchStepsInput): UseLaunchStepsReturn {
  function blockersReason(prefix: string): string {
    const blockers = input.manifest.value?.readiness.blockers ?? []
    if (blockers.length === 0) {
      return ''
    }

    const details = blockers
      .slice(0, 2)
      .map((b) => b.message || b.code)
      .filter((m) => m.length > 0)
      .join('; ')
    const suffix = blockers.length > 2 ? ` (+${blockers.length - 2})` : ''

    return details.length > 0
      ? `${prefix}: ${details}${suffix}`
      : `${prefix}: ${blockers.length}`
  }

  const visibleSteps = computed(
    () => (input.manifest.value?.steps ?? []).filter((s) => s.visible),
  )

  const isRepeatPath = computed(() => {
    if (input.state.zone_id == null) return false
    const manifest = input.manifest.value
    if (!manifest) return false
    const blockers = manifest.readiness?.blockers ?? []
    if (blockers.length > 0) return false
    const calibration = (manifest.steps ?? []).find((s) => s.id === 'calibration')
    return calibration?.required !== true
  })

  function toLaunchStep(s: { id: string; title?: string; description?: string }): LaunchStep {
    const recipeSub =
      isRepeatPath.value && s.id === 'recipe' ? 'культура + дата посадки' : undefined
    return {
      id: s.id,
      label: STEP_DEFS[s.id]?.label ?? s.title ?? s.id,
      sub: recipeSub ?? STEP_DEFS[s.id]?.sub ?? s.description ?? '',
    }
  }

  const allVisibleSteps = computed<LaunchStep[]>(() =>
    visibleSteps.value.map(toLaunchStep),
  )

  const stepperSteps = computed<LaunchStep[]>(() => {
    const source = isRepeatPath.value
      ? visibleSteps.value.filter((s) => LINEAR_REPEAT_STEP_IDS.has(s.id))
      : visibleSteps.value
    return source.map(toLaunchStep)
  })

  const isAdvancedStep = computed(
    () =>
      isRepeatPath.value &&
      input.currentStep.value !== '' &&
      !stepperSteps.value.some((s) => s.id === input.currentStep.value),
  )

  const activeIndex = computed(() => {
    const idx = stepperSteps.value.findIndex((s) => s.id === input.currentStep.value)
    return idx
  })

  function canProceedStep(stepId: string): ProceedVerdict {
    const state = input.state
    const profile = input.automationProfile.value

    if (stepId === 'zone') {
      return state.zone_id != null
        ? true
        : { ok: false, reason: 'Выберите зону' }
    }
    if (stepId === 'recipe') {
      if (!state.recipe_revision_id) return { ok: false, reason: 'Выберите ревизию рецепта' }
      if (!state.plant_id) return { ok: false, reason: 'Выберите растение' }
      if (!state.planting_at) return { ok: false, reason: 'Укажите дату посадки' }
      return true
    }
    if (stepId === 'automation') {
      const a = profile.assignments
      if (!a.irrigation) return { ok: false, reason: 'Не привязан irrigation канал' }
      if (!a.ph_correction) return { ok: false, reason: 'Не привязан pH-корректор' }
      if (!a.ec_correction) return { ok: false, reason: 'Не привязан EC-корректор' }
      if (profile.lightingForm.enabled && !a.light) {
        return { ok: false, reason: 'Свет включён — нужна привязка светового канала' }
      }
      if (profile.zoneClimateForm.enabled) {
        const hasClimateBinding = a.co2_sensor || a.co2_actuator || a.root_vent_actuator
        if (!hasClimateBinding) {
          return { ok: false, reason: 'Climate включён — нужна привязка CO₂/вентиляции' }
        }
      }
      return true
    }
    if (stepId === 'calibration') {
      const blockers = input.manifest.value?.readiness.blockers ?? []
      return blockers.length === 0
        ? true
        : { ok: false, reason: blockersReason('Остались блокеры') }
    }
    if (stepId === 'preview') {
      if (!input.isFormValid.value) return { ok: false, reason: 'Payload не валиден' }
      const blockers = input.manifest.value?.readiness.blockers ?? []
      if (blockers.length > 0) {
        return {
          ok: false,
          reason: `${blockersReason('Запуск заблокирован')}`,
        }
      }
      return true
    }
    return true
  }

  const completion = computed<StepCompletion[]>(() =>
    stepperSteps.value.map((s, i) => {
      if (i === activeIndex.value) return 'current'
      if (i < activeIndex.value) {
        return canProceedStep(s.id) === true ? 'done' : 'warn'
      }
      return 'todo'
    }),
  )

  const currentStepDef = computed<LaunchStep>(() => {
    if (activeIndex.value >= 0) {
      return stepperSteps.value[activeIndex.value] ?? { id: '', label: '', sub: '' }
    }
    return (
      allVisibleSteps.value.find((s) => s.id === input.currentStep.value) ?? {
        id: '',
        label: '',
        sub: '',
      }
    )
  })

  const canLaunch = computed(() => {
    if (input.currentStep.value !== 'preview') return false
    return canProceedStep('preview') === true
  })

  return {
    stepperSteps,
    allVisibleSteps,
    activeIndex,
    completion,
    currentStepDef,
    canLaunch,
    canProceedStep,
    isRepeatPath,
    isAdvancedStep,
  }
}

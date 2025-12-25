/**
 * useWizardState - управление состоянием визарда
 * 
 * Предоставляет реактивное состояние для многошаговых визардов:
 * - Текущий шаг
 * - Данные формы
 * - Валидация
 * - Навигация между шагами
 */
import { ref, computed, type Ref } from 'vue'

export interface WizardStep {
  id: string
  title: string
  description?: string
  component?: string
  canSkip?: boolean
  validate?: () => boolean | Promise<boolean>
}

export interface WizardState<T = Record<string, any>> {
  currentStep: Ref<number>
  steps: Ref<WizardStep[]>
  formData: Ref<T>
  errors: Ref<Record<string, string[]>>
  isValid: Ref<boolean>
  canGoNext: Ref<boolean>
  canGoPrev: Ref<boolean>
  isFirstStep: Ref<boolean>
  isLastStep: Ref<boolean>
  next: () => Promise<void>
  prev: () => void
  goToStep: (stepIndex: number) => void
  reset: () => void
  submit: () => Promise<void>
}

/**
 * Создает состояние визарда с управлением шагами
 * 
 * @param steps - Массив шагов визарда
 * @param initialData - Начальные данные формы
 * @param onSubmit - Callback для отправки формы
 * @returns Состояние визарда
 */
export function useWizardState<T extends Record<string, any> = Record<string, any>>(
  steps: WizardStep[],
  initialData: T = {} as T,
  onSubmit?: (data: T) => Promise<void> | void
): WizardState<T> {
  const currentStep = ref(0)
  const stepsRef = ref(steps)
  const formData = ref({ ...initialData }) as Ref<T>
  const errors = ref<Record<string, string[]>>({})

  // Вычисляемые свойства
  const isValid = computed(() => {
    return Object.keys(errors.value).length === 0
  })

  const canGoNext = computed(() => {
    if (currentStep.value >= stepsRef.value.length - 1) {
      return false
    }
    const currentStepData = stepsRef.value[currentStep.value]
    if (currentStepData?.canSkip) {
      return true
    }
    return isValid.value
  })

  const canGoPrev = computed(() => {
    return currentStep.value > 0
  })

  const isFirstStep = computed(() => {
    return currentStep.value === 0
  })

  const isLastStep = computed(() => {
    return currentStep.value === stepsRef.value.length - 1
  })

  // Валидация текущего шага
  const validateCurrentStep = async (): Promise<boolean> => {
    const step = stepsRef.value[currentStep.value]
    if (!step) {
      return false
    }

    // Если есть кастомная валидация, используем её
    if (step.validate) {
      try {
        const result = await step.validate()
        return result === true
      } catch (error) {
        // Используем logger вместо console.error для консистентности
        if (typeof window !== 'undefined') {
          import('@/utils/logger').then(({ logger }) => {
            logger.error('[useWizardState] Step validation error', { error })
          }).catch(() => {
            // Fallback к console.error если logger недоступен
            console.error('[useWizardState] Step validation error:', error)
          })
        }
        return false
      }
    }

    // Базовая валидация: проверяем, что нет ошибок
    return isValid.value
  }

  // Переход к следующему шагу
  const next = async (): Promise<void> => {
    if (!canGoNext.value) {
      return
    }

    // Валидируем текущий шаг перед переходом
    const isValidStep = await validateCurrentStep()
    if (!isValidStep && !stepsRef.value[currentStep.value]?.canSkip) {
      return
    }

    if (currentStep.value < stepsRef.value.length - 1) {
      currentStep.value++
    }
  }

  // Переход к предыдущему шагу
  const prev = (): void => {
    if (canGoPrev.value) {
      currentStep.value--
    }
  }

  // Переход к конкретному шагу
  const goToStep = (stepIndex: number): void => {
    if (stepIndex >= 0 && stepIndex < stepsRef.value.length) {
      currentStep.value = stepIndex
    }
  }

  // Сброс визарда
  const reset = (): void => {
    currentStep.value = 0
    formData.value = { ...initialData } as T
    errors.value = {}
  }

  // Отправка формы
  const submit = async (): Promise<void> => {
    if (!isValid.value) {
      return
    }

    // Валидируем последний шаг
    const isValidStep = await validateCurrentStep()
    if (!isValidStep) {
      return
    }

    if (onSubmit) {
      await onSubmit(formData.value)
    }
  }

  return {
    currentStep,
    steps: stepsRef,
    formData,
    errors,
    isValid,
    canGoNext,
    canGoPrev,
    isFirstStep,
    isLastStep,
    next,
    prev,
    goToStep,
    reset,
    submit,
  }
}


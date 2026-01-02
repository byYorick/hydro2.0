/**
 * useWizardValidation - валидация данных визарда
 * 
 * Предоставляет функции валидации для различных шагов визарда:
 * - Валидация выбора теплицы
 * - Валидация выбора/создания зоны
 * - Валидация выбора растения
 * - Валидация выбора/создания рецепта
 * - Валидация фаз рецепта
 */
import type { WizardState } from './useWizardState'

export interface GreenhouseData {
  id?: number
  name?: string
}

export interface ZoneData {
  id?: number
  name?: string
  greenhouse_id?: number
}

export interface PlantData {
  id?: number
  name?: string
}

export interface RecipeData {
  id?: number
  name?: string
  phases?: Array<{
    name: string
    duration_hours: number
  }>
}

export interface GrowCycleWizardData {
  greenhouseId?: number
  greenhouse?: GreenhouseData
  zoneId?: number
  zone?: ZoneData
  plantId?: number
  plant?: PlantData
  recipeId?: number
  recipe?: RecipeData
  plantingAt?: string
  batchLabel?: string
}

/**
 * Валидация шага выбора теплицы
 */
export function validateGreenhouseStep(data: GrowCycleWizardData): string[] {
  const errors: string[] = []
  
  if (!data.greenhouseId && !data.greenhouse) {
    errors.push('Необходимо выбрать или создать теплицу')
  }
  
  return errors
}

/**
 * Валидация шага выбора зоны
 */
export function validateZoneStep(data: GrowCycleWizardData): string[] {
  const errors: string[] = []
  
  if (!data.zoneId && !data.zone) {
    errors.push('Необходимо выбрать или создать зону')
  }
  
  if (data.zone && !data.zone.name) {
    errors.push('Необходимо указать название зоны')
  }
  
  if (data.zone && !data.zone.greenhouse_id && !data.greenhouseId) {
    errors.push('Необходимо указать теплицу для зоны')
  }
  
  return errors
}

/**
 * Валидация шага выбора растения
 */
export function validatePlantStep(data: GrowCycleWizardData): string[] {
  const errors: string[] = []
  
  if (!data.plantId && !data.plant) {
    errors.push('Необходимо выбрать или создать растение')
  }
  
  if (data.plant && !data.plant.name) {
    errors.push('Необходимо указать название растения')
  }
  
  return errors
}

/**
 * Валидация шага выбора рецепта
 */
export function validateRecipeStep(data: GrowCycleWizardData): string[] {
  const errors: string[] = []
  
  if (!data.recipeId && !data.recipe) {
    errors.push('Необходимо выбрать или создать рецепт')
  }
  
  if (data.recipe && !data.recipe.name) {
    errors.push('Необходимо указать название рецепта')
  }
  
  if (data.recipe && (!data.recipe.phases || data.recipe.phases.length === 0)) {
    errors.push('Рецепт должен содержать хотя бы одну фазу')
  }
  
  if (data.recipe?.phases) {
    data.recipe.phases.forEach((phase, index) => {
      if (!phase.name || phase.name.trim() === '') {
        errors.push(`Фаза ${index + 1}: необходимо указать название`)
      }
      if (!phase.duration_hours || phase.duration_hours <= 0) {
        errors.push(`Фаза ${index + 1}: необходимо указать длительность (больше 0 часов)`)
      }
    })
  }
  
  return errors
}

/**
 * Валидация шага старта цикла
 */
export function validateStartCycleStep(data: GrowCycleWizardData): string[] {
  const errors: string[] = []
  
  if (!data.zoneId) {
    errors.push('Необходимо выбрать зону')
  }
  
  if (!data.recipeId) {
    errors.push('Необходимо выбрать рецепт')
  }
  
  if (!data.plantingAt) {
    errors.push('Необходимо указать дату посадки')
  }
  
  return errors
}

/**
 * Создает валидатор для визарда создания цикла выращивания
 */
export function useWizardValidation(wizardState: WizardState<GrowCycleWizardData>) {
  const validateStep = async (stepIndex: number): Promise<boolean> => {
    const data = wizardState.formData.value
    let errors: string[] = []

    switch (stepIndex) {
      case 0: // Выбор теплицы
        errors = validateGreenhouseStep(data)
        break
      case 1: // Выбор зоны
        errors = validateZoneStep(data)
        break
      case 2: // Выбор растения
        errors = validatePlantStep(data)
        break
      case 3: // Выбор рецепта
        errors = validateRecipeStep(data)
        break
      case 4: // Старт цикла
        errors = validateStartCycleStep(data)
        break
      default:
        break
    }

    // Обновляем ошибки в состоянии визарда
    if (errors.length > 0) {
      wizardState.errors.value = {
        ...wizardState.errors.value,
        [`step_${stepIndex}`]: errors,
      }
      return false
    }

    // Очищаем ошибки шага при успешной валидации
    const stepErrors = { ...wizardState.errors.value }
    delete stepErrors[`step_${stepIndex}`]
    wizardState.errors.value = stepErrors

    return true
  }

  const validateAll = (): boolean => {
    const data = wizardState.formData.value
    const allErrors: string[] = [
      ...validateGreenhouseStep(data),
      ...validateZoneStep(data),
      ...validatePlantStep(data),
      ...validateRecipeStep(data),
      ...validateStartCycleStep(data),
    ]

    if (allErrors.length > 0) {
      wizardState.errors.value = {
        general: allErrors,
      }
      return false
    }

    return true
  }

  return {
    validateStep,
    validateAll,
  }
}

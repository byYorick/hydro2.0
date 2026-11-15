import type { RecipeEditorFormState } from '@/composables/recipeEditorShared'
import { getRecipePhaseTargetValidationError, isNutrientRatioValid } from '@/composables/recipeEditorShared'

export function recipeEditorValidationError(form: RecipeEditorFormState): string | null {
  if (!form.name.trim()) {
    return 'Введите название рецепта'
  }

  if (!form.plant_id) {
    return 'Выберите культуру'
  }

  if (form.phases.length === 0) {
    return 'Добавьте хотя бы одну фазу'
  }

  for (const phase of form.phases) {
    if (!phase.name.trim()) {
      return 'У каждой фазы должно быть название'
    }

    const phaseTargetError = getRecipePhaseTargetValidationError(phase)
    if (phaseTargetError) {
      const label = phase.name.trim() || `Фаза ${phase.phase_index + 1}`
      return `${phaseTargetError} (${label})`
    }

    if (!isNutrientRatioValid(phase)) {
      const label = phase.name.trim() || `Фаза ${phase.phase_index + 1}`
      return `Сумма nutrient ratio должна быть 100% (${label})`
    }

    const ratioMode = phase.nutrient_mode === 'ratio_ec_pid' || phase.nutrient_mode === 'delta_ec_by_k'
    const hasEcTarget = (phase.ec_target ?? 0) > 0
    const hasAllRatios = phase.nutrient_npk_ratio_pct != null
      && phase.nutrient_calcium_ratio_pct != null
      && phase.nutrient_magnesium_ratio_pct != null
      && phase.nutrient_micro_ratio_pct != null
    if (ratioMode && hasEcTarget && !hasAllRatios) {
      const label = phase.name.trim() || `Фаза ${phase.phase_index + 1}`
      return `Для режима ${phase.nutrient_mode} при EC > 0 обязательны все 4 доли компонентов (${label})`
    }
  }

  return null
}

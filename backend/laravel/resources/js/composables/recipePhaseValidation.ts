import type { RecipePhaseFormState } from './recipeEditorShared'
import { toNullableNumber, nullableDraftNumber } from './recipePhaseNumbers'

function validateBoundedTarget(
  label: string,
  target: number | null,
  min: number | null,
  max: number | null,
): string | null {
  if (target === null || min === null || max === null) {
    return `${label}: заполните target, min и max`
  }

  if (min > max) {
    return `${label}: нижняя граница не может быть больше верхней`
  }

  if (target < min || target > max) {
    return `${label}: цель должна находиться между нижней и верхней границами`
  }

  return null
}

function cropDayPhaseError(phase: RecipePhaseFormState): string | null {
  const min = nullableDraftNumber(phase.solution_temp_min)
  const max = nullableDraftNumber(phase.solution_temp_max)
  if (min !== null && max !== null && min > max) {
    return 'Температура раствора: нижняя граница не может быть больше верхней'
  }
  if (phase.solution_health_required === true && (min === null || max === null)) {
    return 'Для контроля температуры раствора заполните нижнюю и верхнюю границы'
  }
  return null
}

export function getRecipePhaseTargetValidationError(phase: RecipePhaseFormState): string | null {
  for (const [label, value] of [
    ['Длительность фазы', phase.duration_hours],
    ['Интервал полива', phase.irrigation_interval_sec],
    ['Длительность полива', phase.irrigation_duration_sec],
  ] as Array<[string, number | null]>) {
    if (value !== null && (!Number.isFinite(value) || !Number.isInteger(value) || value < 0)) {
      return `${label}: проверьте формат времени и допустимые значения минут, секунд или часов`
    }
  }

  for (const [profile, value] of Object.entries(phase.day_night.soil_moisture)) {
    if (value !== null && (typeof value !== 'number' || !Number.isFinite(value) || value < 0 || value > 100)) {
      return `Влажность субстрата (${profile === 'day' ? 'день' : 'ночь'}): укажите число от 0 до 100%`
    }
  }
  if (phase.irrigation_duration_sec !== null && phase.irrigation_duration_sec > 3600) {
    return 'Длительность полива: не более 60 минут (60:00) за один запуск'
  }
  if (phase.irrigation_interval_sec !== null && phase.irrigation_interval_sec > 86400) {
    return 'Интервал полива: не более 24 часов (24:00)'
  }
  return validateBoundedTarget(
    'pH',
    toNullableNumber(phase.ph_target),
    toNullableNumber(phase.ph_min),
    toNullableNumber(phase.ph_max),
  ) ?? validateBoundedTarget(
    'EC',
    toNullableNumber(phase.ec_target),
    toNullableNumber(phase.ec_min),
    toNullableNumber(phase.ec_max),
  ) ?? cropDayPhaseError(phase)
}

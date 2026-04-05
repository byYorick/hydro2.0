/**
 * Standalone validation utilities — не привязаны к Inertia-форме.
 * Могут использоваться в любых компонентах и composables.
 */

export function validateNumberRange(
  value: number | null | undefined,
  min: number,
  max: number,
  fieldName: string,
): string | null {
  if (value === null || value === undefined) {
    return `${fieldName}: обязательное поле`
  }
  if (value < min || value > max) {
    return `${fieldName}: допустимый диапазон ${min}–${max}`
  }
  return null
}

export function validateMinLength(
  value: string | null | undefined,
  minLength: number,
  fieldName: string,
): string | null {
  if (!value || value.length < minLength) {
    return `${fieldName} должен содержать минимум ${minLength} символов`
  }
  return null
}

export function validateEmail(email: string | null | undefined): string | null {
  if (!email) {
    return 'Email обязателен для заполнения'
  }
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
  if (!emailRegex.test(email)) {
    return 'Некорректный формат email'
  }
  return null
}

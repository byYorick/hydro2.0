export type FieldModelValue = string | number | boolean | null

export interface FieldModifiers {
  trim?: boolean
  number?: boolean
}

/**
 * Повторяет поведение нативных модификаторов Vue: trim обрезает строку,
 * number приводит к числу и оставляет исходное значение, если это не число.
 */
export function applyFieldModifiers(
  value: FieldModelValue,
  modifiers: FieldModifiers,
): FieldModelValue {
  let next = value
  if (modifiers.trim && typeof next === 'string') {
    next = next.trim()
  }
  if (modifiers.number) {
    if (next === '' || next === null) {
      return next
    }
    const numeric = typeof next === 'number' ? next : Number(next)
    return Number.isNaN(numeric) ? next : numeric
  }
  return next
}

/**
 * Общие утилиты парсинга и валидации для автоматики зоны.
 *
 * Используются в Setup Wizard и Growth Cycle Wizard для единообразной
 * обработки числовых значений, диапазонов и форматов времени.
 */

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

export function toFiniteNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }

  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) {
      return parsed
    }
  }

  return null
}

export function isValidHHMM(value: string): boolean {
  if (!/^\d{2}:\d{2}$/.test(value)) {
    return false
  }

  const [h, m] = value.split(':').map(Number)
  return Number.isFinite(h) && Number.isFinite(m) && h >= 0 && h <= 23 && m >= 0 && m <= 59
}

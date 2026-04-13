/**
 * Reader-утилиты для безопасного чтения значений из unknown-словарей.
 *
 * Используются парсерами автоматики (zoneAutomationTargetsParser и пр.),
 * где входные данные — произвольный JSON из API без гарантий формата.
 *
 * Все функции типобезопасны: возвращают null при невалидных значениях,
 * поддерживают лёгкое type coercion (строка→число, '1'/'0'/'true'/'false'→boolean).
 */

export type Dictionary = Record<string, unknown>

export function asRecord(value: unknown): Dictionary | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null
  }

  return value as Dictionary
}

export function asArray(value: unknown): unknown[] | null {
  if (!Array.isArray(value)) {
    return null
  }

  return value
}

/**
 * Возвращает первое финитное число из переданных значений.
 * Строки автоматически парсятся через Number().
 */
export function readNumber(...values: unknown[]): number | null {
  for (const value of values) {
    if (typeof value === 'number' && Number.isFinite(value)) {
      return value
    }

    if (typeof value === 'string' && value.trim() !== '') {
      const parsed = Number(value)
      if (Number.isFinite(parsed)) {
        return parsed
      }
    }
  }

  return null
}

/**
 * Возвращает первый валидный boolean. Принимает `true`/`false`, `1`/`0`,
 * строки `'1'`/`'0'`/`'true'`/`'false'`.
 */
export function readBoolean(...values: unknown[]): boolean | null {
  for (const value of values) {
    if (typeof value === 'boolean') {
      return value
    }
    if (value === 1 || value === '1' || value === 'true') {
      return true
    }
    if (value === 0 || value === '0' || value === 'false') {
      return false
    }
  }

  return null
}

/**
 * Возвращает первую непустую (после trim) строку.
 */
export function readString(...values: unknown[]): string | null {
  for (const value of values) {
    if (typeof value === 'string' && value.trim() !== '') {
      return value.trim()
    }
  }

  return null
}

/**
 * Парсит список строк. Принимает либо массив, либо CSV-строку.
 * Пустые элементы отбрасываются; возвращает null, если валидных нет.
 */
export function readStringList(...values: unknown[]): string[] | null {
  for (const value of values) {
    if (Array.isArray(value)) {
      const items = value
        .map((item) => (typeof item === 'string' ? item.trim() : String(item ?? '').trim()))
        .filter((item) => item.length > 0)
      if (items.length > 0) {
        return items
      }
      continue
    }

    if (typeof value === 'string' && value.trim() !== '') {
      const items = value
        .split(',')
        .map((item) => item.trim())
        .filter((item) => item.length > 0)
      if (items.length > 0) {
        return items
      }
    }
  }

  return null
}

/**
 * Нормализует строку времени к формату HH:MM.
 * Принимает '6:30', '06:30', '06:30:00' и т.п. Возвращает null для невалидных значений.
 */
export function toTimeHHmm(value: unknown): string | null {
  const raw = readString(value)
  if (!raw) {
    return null
  }

  const match = raw.match(/^(\d{1,2}):(\d{2})/)
  if (!match) {
    return null
  }

  const h = Number(match[1])
  const m = Number(match[2])
  if (h < 0 || h > 23 || m < 0 || m > 59) {
    return null
  }

  return `${match[1].padStart(2, '0')}:${match[2]}`
}

/**
 * Утилиты для работы с переменными окружения
 */

/**
 * Читает boolean значение из переменной окружения
 * @param key - Ключ переменной окружения
 * @param defaultValue - Значение по умолчанию
 * @returns Boolean значение
 */
export function readBooleanEnv(key: string, defaultValue: boolean = false): boolean {
  const value = import.meta.env[key]
  if (value === undefined || value === null) {
    return defaultValue
  }
  if (typeof value === 'boolean') {
    return value
  }
  if (typeof value === 'string') {
    const normalized = value.toLowerCase().trim()
    return normalized === 'true' || normalized === '1' || normalized === 'yes'
  }
  return defaultValue
}

/**
 * Читает строковое значение из переменной окружения
 * @param key - Ключ переменной окружения
 * @param defaultValue - Значение по умолчанию
 * @returns Строковое значение
 */
export function readStringEnv(key: string, defaultValue: string = ''): string {
  const value = import.meta.env[key]
  if (value === undefined || value === null) {
    return defaultValue
  }
  return String(value)
}

/**
 * Читает числовое значение из переменной окружения
 * @param key - Ключ переменной окружения
 * @param defaultValue - Значение по умолчанию
 * @returns Числовое значение
 */
export function readNumberEnv(key: string, defaultValue: number = 0): number {
  const value = import.meta.env[key]
  if (value === undefined || value === null) {
    return defaultValue
  }
  if (typeof value === 'number') {
    return value
  }
  if (typeof value === 'string') {
    const parsed = Number(value)
    return isNaN(parsed) ? defaultValue : parsed
  }
  return defaultValue
}


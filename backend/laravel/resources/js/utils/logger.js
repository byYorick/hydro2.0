/**
 * Утилита для условного логирования (только в dev режиме)
 */

const isDev = import.meta.env.DEV

/**
 * Логирует сообщение только в dev режиме
 * @param {...any} args - Аргументы для console.log
 */
export function log(...args) {
  if (isDev) {
    console.log(...args)
  }
}

/**
 * Логирует предупреждение только в dev режиме
 * @param {...any} args - Аргументы для console.warn
 */
export function warn(...args) {
  if (isDev) {
    console.warn(...args)
  }
}

/**
 * Всегда логирует ошибку (даже в production)
 * @param {...any} args - Аргументы для console.error
 */
export function error(...args) {
  console.error(...args)
}

/**
 * Экспорт объекта logger для удобства
 */
export const logger = {
  log,
  warn,
  error,
}


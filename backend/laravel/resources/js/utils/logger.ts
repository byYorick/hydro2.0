/**
 * Централизованная утилита для логирования
 * Автоматически отключает debug логи в production
 */

type LogLevel = 'debug' | 'info' | 'warn' | 'error'

const isDev = import.meta.env.DEV
const isProd = import.meta.env.PROD

/**
 * Проверяет, нужно ли логировать на данном уровне
 */
function shouldLog(level: LogLevel): boolean {
  if (level === 'error') return true // Ошибки всегда логируются
  if (level === 'warn') return true // Предупреждения всегда логируются
  if (level === 'info' || level === 'debug') return isDev // Info и debug только в dev
  return false
}

/**
 * Форматирует сообщение с префиксом уровня
 */
function formatMessage(level: LogLevel, ...args: unknown[]): unknown[] {
  const prefix = `[${level.toUpperCase()}]`
  return [prefix, ...args]
}

/**
 * Логирует debug сообщение (только в dev режиме)
 */
export function debug(...args: unknown[]): void {
  if (shouldLog('debug')) {
    console.log(...formatMessage('debug', ...args))
  }
}

/**
 * Логирует информационное сообщение (только в dev режиме)
 */
export function info(...args: unknown[]): void {
  if (shouldLog('info')) {
    console.log(...formatMessage('info', ...args))
  }
}

/**
 * Логирует предупреждение (всегда)
 */
export function warn(...args: unknown[]): void {
  if (shouldLog('warn')) {
    console.warn(...formatMessage('warn', ...args))
  }
}

/**
 * Логирует ошибку (всегда)
 */
export function error(...args: unknown[]): void {
  if (shouldLog('error')) {
    console.error(...formatMessage('error', ...args))
  }
}

/**
 * Группирует логи (только в dev)
 */
export function group(label: string): void {
  if (isDev) {
    console.group(label)
  }
}

/**
 * Закрывает группу логов (только в dev)
 */
export function groupEnd(): void {
  if (isDev) {
    console.groupEnd()
  }
}

/**
 * Группирует логи с коллапсом (только в dev)
 */
export function groupCollapsed(label: string): void {
  if (isDev) {
    console.groupCollapsed(label)
  }
}

/**
 * Логирует таблицу (только в dev)
 */
export function table(data: unknown): void {
  if (isDev) {
    console.table(data)
  }
}

/**
 * Логирует время выполнения (только в dev)
 */
export function time(label: string): void {
  if (isDev) {
    console.time(label)
  }
}

/**
 * Завершает логирование времени (только в dev)
 */
export function timeEnd(label: string): void {
  if (isDev) {
    console.timeEnd(label)
  }
}

/**
 * Объект logger для удобного использования
 */
export const logger = {
  debug,
  info,
  warn,
  error,
  group,
  groupEnd,
  groupCollapsed,
  table,
  time,
  timeEnd,
  /**
   * Проверяет, находится ли приложение в dev режиме
   */
  get isDev(): boolean {
    return isDev
  },
  /**
   * Проверяет, находится ли приложение в production режиме
   */
  get isProd(): boolean {
    return isProd
  },
}

// Экспорт по умолчанию для обратной совместимости
export default logger


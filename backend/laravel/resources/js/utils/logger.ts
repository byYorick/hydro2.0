/**
 * Централизованная утилита для логирования
 * Автоматически отключает debug логи в production
 * Поддерживает структурированное логирование с контекстом
 */

type LogLevel = 'debug' | 'info' | 'warn' | 'error'

const isDev = import.meta.env.DEV
const isProd = import.meta.env.PROD

// Runtime переключение уровня логирования через переменные окружения
const wsLogLevel = (import.meta.env.VITE_WS_LOG_LEVEL || '').toLowerCase() as LogLevel | ''
const wsLogSample = Number(import.meta.env.VITE_WS_LOG_SAMPLE || '1') // 1 = все, 0.1 = 10% и т.д.
const normalizedLogSample = Number.isFinite(wsLogSample) ? wsLogSample : 1

// Порядок уровней для сравнения
const logLevels: Record<LogLevel, number> = {
  debug: 0,
  info: 1,
  warn: 2,
  error: 3,
}

/**
 * Интерфейс для контекста логирования
 */
export interface LogContext {
  socketId?: string
  userId?: number | string
  channel?: string
  zoneId?: number
  componentTag?: string
  subscriptionId?: string
  attempt?: number
  duration?: number
  restoredCount?: number
  [key: string]: unknown
}

/**
 * Проверяет, нужно ли логировать на данном уровне
 */
function shouldLog(level: LogLevel): boolean {
  // ИСПРАВЛЕНО: Включаем жесткое логирование для диагностики
  // Проверяем переменную окружения для принудительного включения логирования
  const forceDebug = String((import.meta.env.VITE_FORCE_DEBUG_LOGS || 'false')).toLowerCase() === 'true'
  
  // Если задан уровень через переменную окружения, используем его
  if (wsLogLevel && logLevels[wsLogLevel] !== undefined) {
    return logLevels[level] >= logLevels[wsLogLevel]
  }
  
  // Если включено принудительное логирование, логируем все
  if (forceDebug) {
    return true
  }
  
  // По умолчанию: ошибки и предупреждения всегда, info/debug только в dev
  if (level === 'error') return true
  if (level === 'warn') return true
  if (level === 'info' || level === 'debug') return isDev
  return false
}

/**
 * Проверяет, нужно ли логировать с учетом выборки
 */
function shouldSample(level: LogLevel): boolean {
  if (level === 'warn' || level === 'error') return true

  if (normalizedLogSample >= 1) return true
  if (normalizedLogSample <= 0) return false

  return Math.random() < normalizedLogSample
}

/**
 * Форматирует сообщение с префиксом уровня и контекстом
 */
function formatMessage(level: LogLevel, message: string, context?: LogContext): unknown[] {
  const prefix = `[${level.toUpperCase()}]`
  
  // Если есть контекст, форматируем как JSON для структурированного логирования
  if (context && Object.keys(context).length > 0) {
    const jsonContext = safeStringify(context)
    if (isDev) {
      return [prefix, message, context]
    } else {
      // В проде выводим JSON для сопоставления с backend логами
      return [`${prefix} ${message}`, jsonContext]
    }
  }
  
  return [prefix, message]
}

function safeStringify(context: LogContext): string {
  try {
    return JSON.stringify(context, null, isDev ? 2 : 0)
  } catch (err) {
    const fallbackMessage = err instanceof Error ? err.message : 'Unable to serialize context'
    return JSON.stringify(
      {
        serializationError: fallbackMessage,
        contextKeys: Object.keys(context),
      },
      null,
      isDev ? 2 : 0
    )
  }
}

function writeToConsole(level: LogLevel, args: unknown[]): void {
  if (typeof console === 'undefined') return

  switch (level) {
    case 'warn':
      console.warn(...args)
      break
    case 'error':
      console.error(...args)
      break
    default:
      console.log(...args)
  }
}

function logWithLevel(
  level: LogLevel,
  message: string,
  context?: LogContext,
  err?: Error | unknown
): void {
  if (!shouldLog(level) || !shouldSample(level)) return

  const formattedMessage = formatMessage(level, message, context)
  writeToConsole(level, formattedMessage)

  if (level === 'error') {
    sendToErrorSink(level, message, context, err instanceof Error ? err : undefined)
  }
}

/**
 * Отправляет ошибку во внешний sink (Sentry/HTTP endpoint)
 */
function sendToErrorSink(level: LogLevel, message: string, context?: LogContext, error?: Error): void {
  // В будущем можно добавить отправку в Sentry или HTTP endpoint
  // const errorEndpoint = import.meta.env.VITE_ERROR_SINK_URL
  // if (errorEndpoint && level === 'error') {
  //   fetch(errorEndpoint, { method: 'POST', body: JSON.stringify({ message, context, error }) })
  // }
}

/**
 * Логирует debug сообщение (только в dev режиме)
 */
export function debug(message: string, context?: LogContext): void {
  logWithLevel('debug', message, context)
}

/**
 * Логирует информационное сообщение (только в dev режиме)
 */
export function info(message: string, context?: LogContext): void {
  logWithLevel('info', message, context)
}

/**
 * Логирует предупреждение (всегда)
 */
export function warn(message: string, context?: LogContext): void {
  logWithLevel('warn', message, context)
}

/**
 * Логирует ошибку (всегда)
 */
export function error(message: string, context?: LogContext, err?: Error | unknown): void {
  const errorDetails: LogContext = err instanceof Error
    ? {
        errorMessage: err.message,
        errorStack: err.stack,
        errorName: err.name,
      }
    : err !== undefined
      ? { error: err }
      : {}

  const errorContext: LogContext = {
    ...context,
    ...errorDetails,
  }

  logWithLevel('error', message, errorContext, err)
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
  /**
   * Устаревший метод для обратной совместимости (принимает любые аргументы)
   */
  log(...args: unknown[]): void {
    if (isDev) {
      console.log(...args)
    }
  },
}

// Экспорт по умолчанию для обратной совместимости
export default logger

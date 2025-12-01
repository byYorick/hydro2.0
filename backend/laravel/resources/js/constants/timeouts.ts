/**
 * Константы для таймаутов, задержек и длительностей в приложении
 */

/**
 * Таймауты для Toast уведомлений (в миллисекундах)
 */
export const TOAST_TIMEOUT = {
  SHORT: 2000,
  NORMAL: 3000,
  LONG: 5000,
  VERY_LONG: 8000,
} as const

/**
 * Задержки для debounce/throttle (в миллисекундах)
 */
export const DEBOUNCE_DELAY = {
  FAST: 100,
  NORMAL: 200,
  SLOW: 500,
  VERY_SLOW: 1000,
} as const

/**
 * Интервалы для polling/обновлений (в миллисекундах)
 */
export const POLLING_INTERVAL = {
  FAST: 1000,      // 1 секунда
  NORMAL: 5000,    // 5 секунд
  SLOW: 30000,     // 30 секунд
  VERY_SLOW: 60000, // 1 минута
} as const

/**
 * Таймауты для HTTP запросов (в миллисекундах)
 */
export const HTTP_TIMEOUT = {
  SHORT: 5000,     // 5 секунд
  NORMAL: 10000,   // 10 секунд
  LONG: 30000,     // 30 секунд
  VERY_LONG: 60000, // 1 минута
} as const

/**
 * Задержки для UI анимаций (в миллисекундах)
 */
export const ANIMATION_DELAY = {
  FAST: 100,
  NORMAL: 200,
  SLOW: 300,
  VERY_SLOW: 500,
} as const


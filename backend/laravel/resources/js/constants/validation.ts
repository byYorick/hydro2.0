/**
 * Константы для валидации форм
 */

/**
 * Диапазоны значений для различных полей
 */
export const VALIDATION_RANGES = {
  IRRIGATION_DURATION: { min: 1, max: 3600 },
  PH: { min: 4.0, max: 9.0 },
  EC: { min: 0.1, max: 10.0 },
  TEMPERATURE: { min: 10, max: 35 },
  HUMIDITY: { min: 30, max: 90 },
  LIGHTING_INTENSITY: { min: 0, max: 100 },
  LIGHTING_DURATION: { min: 0.5, max: 24 },
} as const

/**
 * Сообщения об ошибках валидации
 */
export const VALIDATION_MESSAGES = {
  IRRIGATION_DURATION: 'Длительность должна быть от 1 до 3600 секунд',
  PH: 'pH должен быть от 4.0 до 9.0',
  EC: 'EC должен быть от 0.1 до 10.0',
  TEMPERATURE: 'Температура должна быть от 10 до 35°C',
  HUMIDITY: 'Влажность должна быть от 30 до 90%',
  LIGHTING_INTENSITY: 'Интенсивность должна быть от 0 до 100%',
  LIGHTING_DURATION: 'Длительность должна быть от 0.5 до 24 часов',
} as const


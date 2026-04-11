/**
 * Утилиты для работы с API ответами
 */

type ApiResponseLike<T> = {
  data?: T | ApiResponseLike<T>
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function hasDataKey(value: unknown): value is ApiResponseLike<unknown> {
  return isRecord(value) && 'data' in value
}

/**
 * Признаки того, что значение — это пагинированный envelope, а не обёртка,
 * которую нужно ещё раз развернуть. Laravel resource отдаёт пагинированные
 * списки в форме `{ data: [...], current_page, last_page, per_page, total }`;
 * двойной unwrap такого объекта терял бы метаданные пагинации.
 */
const PAGINATION_KEYS = [
  'current_page',
  'last_page',
  'per_page',
  'total',
  'meta',
  'links',
] as const

function isPaginatedEnvelope(value: unknown): boolean {
  if (!isRecord(value)) return false
  return PAGINATION_KEYS.some((key) => key in value)
}

/**
 * Извлекает данные из API ответа.
 *
 * Поддерживает несколько форматов:
 * - `T` — прямой ответ
 * - `{ data: T }` — обернутый ответ
 * - `{ data: { data: T } }` — двойная обёртка (status-envelope поверх data)
 *
 * Защита от потери пагинации: если `response.data` выглядит как
 * `{ data: [...], current_page, last_page, ... }`, вложенный `data.data`
 * НЕ разворачивается, иначе теряются `current_page`/`last_page`/`meta`.
 *
 * @param response - Ответ от API
 * @returns Извлеченные данные или null
 */
export function extractData<T = unknown>(response: unknown): T | null {
  if (!response) {
    return null
  }

  // Если response уже является нужным типом
  if (isRecord(response) && !hasDataKey(response)) {
    return response as T
  }

  // Стандартный формат: { data: T }
  if (hasDataKey(response) && typeof response.data !== 'undefined') {
    // Проверяем, не является ли data тоже обернутым объектом
    // (НО не разворачиваем пагинированные envelope-ы — они тоже содержат `data`,
    //  но вместе с `current_page`/`last_page`/`meta`, и unwrap сломал бы пагинацию).
    if (hasDataKey(response.data) && !isPaginatedEnvelope(response.data)) {
      return response.data.data as T
    }
    return response.data as T
  }

  return response as T
}

/**
 * Нормализует ответ API к ожидаемому типу
 * 
 * @param response - Ответ от API
 * @param expectedType - Ожидаемый тип (для валидации)
 * @returns Нормализованные данные
 */
export function normalizeResponse<T = unknown>(
  response: unknown,
  expectedType?: 'array' | 'object' | 'primitive'
): T {
  const data = extractData<T>(response)
  
  if (data === null || data === undefined) {
    throw new Error('Response data is null or undefined')
  }
  
  if (expectedType === 'array' && !Array.isArray(data)) {
    throw new Error(`Expected array, got ${typeof data}`)
  }
  
  if (expectedType === 'object' && (typeof data !== 'object' || Array.isArray(data))) {
    throw new Error(`Expected object, got ${typeof data}`)
  }
  
  return data
}

/**
 * Извлекает данные из ответа с fallback значением
 * 
 * @param response - Ответ от API
 * @param fallback - Значение по умолчанию
 * @returns Извлеченные данные или fallback
 */
export function extractDataWithFallback<T = unknown>(response: unknown, fallback: T): T {
  const data = extractData<T>(response)
  return data !== null && data !== undefined ? data : fallback
}

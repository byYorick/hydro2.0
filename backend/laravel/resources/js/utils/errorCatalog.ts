import catalogJson from '@/constants/error_codes.json'

interface ErrorCatalogEntry {
  code: string
  title?: string
  message?: string
}

interface ErrorCatalogFile {
  codes?: ErrorCatalogEntry[]
}

export interface HumanErrorInput {
  code?: string | null
  message?: string | null
  humanMessage?: string | null
}

const catalog = (catalogJson as ErrorCatalogFile).codes ?? []

const ERROR_MESSAGE_BY_CODE = new Map<string, string>()
for (const entry of catalog) {
  const code = normalizeErrorCode(entry?.code)
  const message = typeof entry?.message === 'string' ? entry.message.trim() : ''
  if (code && message) {
    ERROR_MESSAGE_BY_CODE.set(code, message)
  }
}

const RAW_MESSAGE_TRANSLATIONS: Record<string, string> = {
  'Intent skipped: zone busy': 'Повторный запуск отклонён: по зоне уже есть активный intent или выполняемая задача.',
  'Task execution exceeded runtime timeout': 'Выполнение задачи превысило допустимый runtime timeout.',
  'Execution not found': 'Запрошенное выполнение не найдено.',
  'Command not found': 'Запрошенная команда не найдена.',
  'Access denied': 'У вас нет прав для доступа к этому объекту.',
  'Authentication required': 'Для выполнения действия нужно войти в систему.',
  Unauthorized: 'Для выполнения действия нужно войти в систему.',
  Forbidden: 'У вас нет прав для выполнения этого действия.',
  'Not found': 'Запрошенный объект не найден.',
  'Validation failed': 'Проверьте корректность переданных данных.',
  TIMEOUT: 'Превышено время ожидания выполнения команды.',
  SEND_FAILED: 'Команду не удалось отправить до узла.',
}

const RAW_MESSAGE_PATTERNS: Array<[RegExp, string]> = [
  [
    /^Zone (\d+) has no online actuator channels$/i,
    'В зоне нет ни одного онлайн-исполнительного канала. Проверьте привязки устройств и состояние нод.',
  ],
]

export function normalizeErrorCode(code?: string | null): string {
  const normalized = String(code ?? '').trim().toLowerCase()
  if (!normalized) return ''
  return normalized.replace(/[^a-z0-9_-]/g, '_')
}

export function isLocalizedErrorMessage(message?: string | null): boolean {
  return /[А-Яа-яЁё]/u.test(String(message ?? ''))
}

export function resolveHumanErrorMessage(input: HumanErrorInput, fallback?: string | null): string | null {
  const humanMessage = typeof input.humanMessage === 'string' ? input.humanMessage.trim() : ''
  if (humanMessage) {
    return humanMessage
  }

  const message = typeof input.message === 'string' ? input.message.trim() : ''
  if (message && isLocalizedErrorMessage(message)) {
    return message
  }

  const normalizedCode = normalizeErrorCode(input.code)
  if (normalizedCode && ERROR_MESSAGE_BY_CODE.has(normalizedCode)) {
    return ERROR_MESSAGE_BY_CODE.get(normalizedCode) ?? null
  }

  if (message && RAW_MESSAGE_TRANSLATIONS[message]) {
    return RAW_MESSAGE_TRANSLATIONS[message]
  }

  if (message) {
    for (const [pattern, translation] of RAW_MESSAGE_PATTERNS) {
      if (pattern.test(message)) {
        return translation
      }
    }
  }

  if (normalizedCode) {
    return `Внутренняя ошибка системы (код: ${normalizedCode}).`
  }

  if (message) {
    return fallback ?? 'Произошла ошибка сервиса. Проверьте логи и повторите попытку.'
  }

  return fallback ?? null
}

/**
 * Централизованные сообщения для приложения
 */

/**
 * Стандартные сообщения об ошибках
 */
export const ERROR_MESSAGES = {
  NETWORK: 'Ошибка сети. Проверьте подключение к интернету.',
  UNAUTHORIZED: 'Требуется авторизация. Пожалуйста, войдите в систему.',
  FORBIDDEN: 'Доступ запрещен. У вас нет прав для выполнения этого действия.',
  NOT_FOUND: 'Ресурс не найден.',
  SERVER_ERROR: 'Ошибка сервера. Попробуйте позже.',
  VALIDATION: 'Ошибка валидации. Проверьте введенные данные.',
  TIMEOUT: 'Превышено время ожидания. Попробуйте еще раз.',
  UNKNOWN: 'Произошла неизвестная ошибка.',
} as const

/**
 * Сообщения об успехе
 */
export const SUCCESS_MESSAGES = {
  SAVED: 'Изменения сохранены',
  CREATED: 'Создано успешно',
  UPDATED: 'Обновлено успешно',
  DELETED: 'Удалено успешно',
  SENT: 'Отправлено успешно',
} as const

/**
 * Сообщения-предупреждения
 */
export const WARNING_MESSAGES = {
  UNSAVED_CHANGES: 'У вас есть несохраненные изменения. Вы уверены, что хотите покинуть страницу?',
  CONFIRM_DELETE: 'Вы уверены, что хотите удалить этот элемент?',
  CONFIRM_ACTION: 'Вы уверены, что хотите выполнить это действие?',
} as const

/**
 * Сообщения-информация
 */
export const INFO_MESSAGES = {
  LOADING: 'Загрузка...',
  PROCESSING: 'Обработка...',
  NO_DATA: 'Нет данных для отображения',
  NO_RESULTS: 'Результаты не найдены',
} as const

/**
 * Получить сообщение об ошибке по статусу HTTP
 */
export function getErrorMessageByStatus(status: number): string {
  switch (status) {
    case 400:
      return ERROR_MESSAGES.VALIDATION
    case 401:
      return ERROR_MESSAGES.UNAUTHORIZED
    case 403:
      return ERROR_MESSAGES.FORBIDDEN
    case 404:
      return ERROR_MESSAGES.NOT_FOUND
    case 422:
      return ERROR_MESSAGES.VALIDATION
    case 500:
    case 502:
    case 503:
      return ERROR_MESSAGES.SERVER_ERROR
    default:
      return ERROR_MESSAGES.UNKNOWN
  }
}


/**
 * Утилиты для форматирования времени
 */

/**
 * Форматирует дату в относительное время или краткую дату
 * @param {string|Date|null} dateString - Дата в виде строки или объекта Date
 * @returns {string} Отформатированная дата (например, "только что", "5 мин назад", "15.11 10:30")
 */
export function formatTime(dateString) {
  if (!dateString) return ''
  
  const date = new Date(dateString)
  const now = new Date()
  const diffMs = now - date
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)
  
  if (diffMins < 1) return 'только что'
  if (diffMins < 60) return `${diffMins} мин назад`
  if (diffHours < 24) return `${diffHours} ч назад`
  if (diffDays < 7) return `${diffDays} дн назад`
  return date.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

/**
 * Форматирует timestamp в короткий формат для Cycles (час:минута день.месяц)
 * @param {string|Date|null} timestamp - Timestamp
 * @returns {string} Отформатированная дата или "-" если нет данных
 */
export function formatTimeShort(timestamp) {
  if (!timestamp) return '-'
  return new Date(timestamp).toLocaleString('ru-RU', { 
    hour: '2-digit', 
    minute: '2-digit',
    day: '2-digit',
    month: '2-digit',
  })
}

/**
 * Форматирует интервал времени для Cycles
 * @param {number|null} seconds - Интервал в секундах
 * @returns {string} Отформатированный интервал (например, "5 мин", "2 ч")
 */
export function formatInterval(seconds) {
  if (!seconds) return '-'
  if (seconds < 60) return `${seconds} сек`
  if (seconds < 3600) return `${Math.floor(seconds / 60)} мин`
  return `${Math.floor(seconds / 3600)} ч`
}


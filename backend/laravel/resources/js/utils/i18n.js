/**
 * Утилиты для локализации (перевод статусов, событий, ролей)
 */

/**
 * Переводит статус зоны/устройства на русский язык
 * @param {string} status - Статус (RUNNING, PAUSED, WARNING, ALARM, и т.д.)
 * @returns {string} Переведенный статус
 */
export function translateStatus(status) {
  const translations = {
    'RUNNING': 'Запущено',
    'PAUSED': 'Приостановлено',
    'WARNING': 'Предупреждение',
    'ALARM': 'Тревога',
    'NEW': 'Новая',
    'SETUP': 'Настройка',
    'OFFLINE': 'Офлайн',
    'ONLINE': 'Онлайн',
    'ACTIVE': 'Активно',
    'RESOLVED': 'Решено',
    'resolved': 'Решено',
    'active': 'Активно',
  }
  return translations[status] || status
}

/**
 * Классифицирует тип события в одну из категорий фильтра.
 * Реальные типы из БД (ALERT_CREATED, CYCLE_STARTED и т.д.) группируются
 * по смыслу, чтобы фильтры на фронтенде работали корректно.
 * @param {string} kind - Тип события из БД
 * @returns {'ALERT'|'WARNING'|'INFO'|'ACTION'}
 */
export function classifyEventKind(kind) {
  if (!kind) return 'INFO'
  if (kind === 'ALERT' || kind.startsWith('ALERT_') || kind === 'WATER_LEVEL_LOW') return 'ALERT'
  if (kind === 'WARNING' || kind.startsWith('WARNING_')) return 'WARNING'
  if (
    kind === 'ACTION' ||
    kind === 'ZONE_COMMAND' ||
    kind.startsWith('SCHEDULE_') ||
    kind.startsWith('SELF_TASK_')
  ) return 'ACTION'
  return 'INFO'
}

/**
 * Переводит тип события на русский язык
 * @param {string} kind - Тип события (ALERT_CREATED, CYCLE_STARTED и т.д.)
 * @returns {string} Переведенный тип события
 */
export function translateEventKind(kind) {
  const translations = {
    'ALERT': 'Тревога',
    'ALERT_CREATED': 'Тревога создана',
    'ALERT_UPDATED': 'Тревога обновлена',
    'ALERT_RESOLVED': 'Тревога закрыта',
    'WARNING': 'Предупреждение',
    'WATER_LEVEL_LOW': 'Низкий уровень воды',
    'INFO': 'Информация',
    'ACTION': 'Действие',
    'SENSOR': 'Датчик',
    'CYCLE_CREATED': 'Цикл создан',
    'CYCLE_STARTED': 'Цикл запущен',
    'CYCLE_PAUSED': 'Цикл приостановлен',
    'CYCLE_RESUMED': 'Цикл возобновлён',
    'CYCLE_HARVESTED': 'Урожай собран',
    'CYCLE_ABORTED': 'Цикл прерван',
    'CYCLE_ADJUSTED': 'Цикл скорректирован',
    'CYCLE_PHASE_ADVANCED': 'Переход фазы',
    'CYCLE_PHASE_SET': 'Фаза установлена',
    'CYCLE_RECIPE_REVISION_CHANGED': 'Смена ревизии',
    'CYCLE_CONFIG': 'Конфигурация цикла',
    'PHASE_TRANSITION': 'Смена фазы',
    'RECIPE_PHASE_CHANGED': 'Смена фазы',
    'ZONE_COMMAND': 'Команда зоны',
    'SCHEDULE_TASK_FAILED': 'Ошибка задачи',
    'SELF_TASK_DISPATCH_RETRY_SCHEDULED': 'Повтор задачи',
  }
  return translations[kind] || kind
}

/**
 * Переводит роль пользователя на русский язык
 * @param {string} role - Роль (admin, operator, viewer)
 * @returns {string} Переведенная роль
 */
export function translateRole(role) {
  const translations = {
    'admin': 'Администратор',
    'operator': 'Оператор',
    'viewer': 'Наблюдатель',
    'agronomist': 'Агроном',
    'engineer': 'Инженер',
  }
  return translations[role] || role
}

/**
 * Переводит тип цикла на русский язык
 * @param {string} cycleType - Тип цикла (PH_CONTROL, EC_CONTROL, IRRIGATION, LIGHTING, CLIMATE)
 * @returns {string} Переведенный тип цикла
 */
export function translateCycleType(cycleType) {
  const translations = {
    'PH_CONTROL': 'Контроль pH',
    'EC_CONTROL': 'Контроль EC',
    'IRRIGATION': 'Полив',
    'LIGHTING': 'Освещение',
    'CLIMATE': 'Климат',
  }
  return translations[cycleType] || cycleType
}

/**
 * Переводит стратегию цикла на русский язык
 * @param {string} strategy - Стратегия (periodic, event, hybrid)
 * @returns {string} Переведенная стратегия
 */
export function translateStrategy(strategy) {
  const translations = {
    'periodic': 'периодическая',
    'event': 'событийная',
    'hybrid': 'гибридная',
  }
  return translations[strategy] || strategy
}

/**
 * Переводит тип устройства на русский язык
 * @param {string} type - Тип устройства (sensor, actuator, controller)
 * @returns {string} Переведенный тип устройства
 */
export function translateDeviceType(type) {
  const translations = {
    'sensor': 'Датчик',
    'actuator': 'Актуатор',
    'controller': 'Контроллер',
  }
  return translations[type] || type
}

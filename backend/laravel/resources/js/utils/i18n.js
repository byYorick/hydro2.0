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

  // Коррекционные ACTION-события
  if (
    kind === 'PH_CORRECTED' ||
    kind === 'EC_DOSING' ||
    kind === 'PUMP_DOSE_SENT' ||
    kind === 'RELAY_AUTOTUNE_STARTED' ||
    kind === 'RELAY_AUTOTUNE_COMPLETE' ||
    kind === 'RELAY_AUTOTUNE_COMPLETED' ||
    kind === 'PUMP_CALIBRATION_SAVED' ||
    kind === 'PROCESS_CALIBRATION_SAVED' ||
    kind === 'DOSING'
  ) return 'ACTION'

  // Operator-visible skip/block warnings must win over generic CORRECTION_SKIPPED_* → INFO.
  if (
    kind === 'EQUIPMENT_ANOMALY_BLOCKED' ||
    kind === 'EQUIPMENT_ANOMALY_RELEASED' ||
    kind === 'CORRECTION_NO_EFFECT' ||
    kind === 'CORRECTION_ACTION_DEFERRED' ||
    kind === 'CORRECTION_SKIPPED_EMERGENCY_STOP' ||
    kind === 'CORRECTION_SKIPPED_BY_ALERT_BLOCK' ||
    kind === 'PUMP_CALIBRATION_MIRROR_MISMATCH' ||
    kind === 'PUMP_CALIBRATION_STALE' ||
    kind === 'RELAY_AUTOTUNE_TIMEOUT' ||
    kind.endsWith('_DOSING_BLOCKED_ANOMALY') ||
    kind.endsWith('_DOSE_NO_EFFECT')
  ) return 'WARNING'

  // Пропуски и служебные события коррекции — INFO
  if (
    kind === 'PID_OUTPUT' ||
    kind === 'PID_CONFIG_UPDATED' ||
    kind === 'CORRECTION_DECISION_MADE' ||
    kind === 'CORRECTION_OBSERVATION_EVALUATED' ||
    kind === 'CORRECTION_LIMIT_POLICY_APPLIED' ||
    kind === 'CORRECTION_ATTEMPT_CAP_IGNORED' ||
    kind === 'CORRECTION_INTERRUPTED_STAGE_COMPLETE' ||
    kind === 'CORRECTION_STATE_TRANSITION' ||
    kind.startsWith('CORRECTION_SKIPPED_') ||
    kind === 'CORRECTION_SKIPPED_WINDOW_NOT_READY' ||
    kind === 'PH_CORRECTION_SKIPPED' ||
    kind === 'EC_CORRECTION_SKIPPED' ||
    kind.endsWith('_CORRECTION_SKIPPED') ||
    kind.endsWith('_CORRECTION_SKIPPED_STALE_DATA') ||
    kind.endsWith('_CORRECTION_SKIPPED_BOUNDS') ||
    kind.endsWith('_CORRECTION_SKIPPED_ANOMALY')
  ) return 'INFO'

  if (kind === 'AE_TASK_STARTED') return 'INFO'

  // AE / irrigation workflow events
  if (
    kind === 'PUMP_CALIBRATION_FINISHED' ||
    kind === 'CLEAN_FILL_COMPLETED' ||
    kind === 'SOLUTION_FILL_COMPLETED' ||
    kind === 'AE_TASK_COMPLETED' ||
    kind === 'CORRECTION_COMPLETE' ||
    kind === 'IRRIGATION_CORRECTION_STARTED'
  ) return 'ACTION'

  if (
    kind === 'COMMAND_TIMEOUT' ||
    kind === 'AE_TASK_FAILED' ||
    kind === 'CORRECTION_EXHAUSTED' ||
    kind === 'EC_BATCH_PARTIAL_FAILURE'
  ) return 'WARNING'
  if (kind === 'command_status' || kind === 'COMMAND_STATUS') return 'ACTION'
  if (kind === 'IRR_STATE_SNAPSHOT' || kind === 'PUMP_CALIBRATION_RUN_SKIPPED') return 'INFO'

  // Lifecycle / zone events (WATER_LEVEL_LOW уже обрабатывается выше как ALERT)
  if (kind === 'ALERT_TRIGGERED') return 'ALERT'
  if (
    kind === 'NODE_DISCONNECTED' ||
    kind === 'MANUAL_INTERVENTION'
  ) return 'WARNING'
  if (
    kind === 'IRRIGATION_START' ||
    kind === 'IRRIGATION_STOP' ||
    kind.startsWith('IRRIGATION_CYCLE_') ||
    kind === 'IRRIGATION_EC_MULTI_DOSE' ||
    kind === 'IRRIGATION_CORRECTION_COMPLETED' ||
    kind.startsWith('IRRIGATION_DECISION_') ||
    kind === 'CALIBRATION_STARTED' ||
    kind === 'CALIBRATION_COMPLETED' ||
    kind === 'RECIPE_STARTED' ||
    kind === 'RECIPE_COMPLETED' ||
    kind === 'HARVEST_STARTED' ||
    kind === 'HARVEST_COMPLETED' ||
    kind === 'AUTO_MODE_ENABLED' ||
    kind === 'AUTO_MODE_DISABLED'
  ) return 'ACTION'
  if (
    kind === 'NODE_CONNECTED' ||
    kind === 'SETTINGS_CHANGED' ||
    kind === 'AUTOMATION_LOGIC_PROFILE_UPDATED' ||
    kind === 'PHASE_CHANGE'
  ) return 'INFO'

  return 'INFO'
}

/**
 * Словарь переводов типов zone_events на русский.
 * Используется бейджами/лентами событий; неизвестный kind возвращается как есть.
 */
export const EVENT_KIND_TRANSLATIONS = {
  'ALERT': 'Тревога',
  'ALERT_CREATED': 'Тревога создана',
  'ALERT_UPDATED': 'Тревога обновлена',
  'ALERT_RESOLVED': 'Тревога закрыта',
  'WARNING': 'Предупреждение',
  'WATER_LEVEL_LOW': 'Низкий уровень воды',
  'NO_FLOW': 'Нет потока',
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
  'CYCLE_RECIPE_REBASED': 'Рецепт цикла обновлён',
  'PHASE_TRANSITION': 'Смена фазы',
  'RECIPE_PHASE_CHANGED': 'Смена фазы',
  'ZONE_COMMAND': 'Команда зоны',
  'SCHEDULE_TASK_FAILED': 'Ошибка задачи',
  'SELF_TASK_DISPATCH_RETRY_SCHEDULED': 'Повтор задачи',

  // Коррекция pH/EC
  'PH_CORRECTED': 'pH скорректирован',
  'EC_DOSING': 'EC: подача питания',
  'EC_BATCH_PARTIAL_FAILURE': 'EC: частичный сбой batch',
  'PUMP_DOSE_SENT': 'Доза отправлена насосу',
  'PID_OUTPUT': 'PID: расчёт выхода',
  'PID_CONFIG_UPDATED': 'Конфиг PID обновлён',
  'CORRECTION_DECISION_MADE': 'Коррекция: выбран следующий шаг',
  'CORRECTION_OBSERVATION_EVALUATED': 'Коррекция: наблюдение оценено',
  'CORRECTION_LIMIT_POLICY_APPLIED': 'Коррекция: применена политика лимитов',
  'CORRECTION_ATTEMPT_CAP_IGNORED': 'Коррекция: лимит попыток проигнорирован',
  'CORRECTION_INTERRUPTED_STAGE_COMPLETE': 'Коррекция: стадия завершилась во время окна',
  'CORRECTION_INTERRUPTED_SOLUTION_LOW': 'Коррекция прервана: низкий уровень раствора',
  'CORRECTION_STATE_TRANSITION': 'Коррекция: переход состояния',
  'CORRECTION_COMPLETE': 'Коррекция завершена успешно',
  'CORRECTION_EXHAUSTED': 'Коррекция: попытки исчерпаны',
  'CORRECTION_SKIPPED_DEAD_ZONE': 'Коррекция: мёртвая зона PID',
  'CORRECTION_SKIPPED_COOLDOWN': 'Коррекция: кулдаун PID',
  'CORRECTION_SKIPPED_DOSE_DISCARDED': 'Коррекция: доза отброшена',
  'CORRECTION_SKIPPED_MISSING_ACTUATOR': 'Коррекция: нет насоса',
  'CORRECTION_SKIPPED_NO_CALIBRATION': 'Коррекция: нет калибровки',
  'CORRECTION_SKIPPED_WATER_LEVEL': 'Коррекция: мало воды',
  'CORRECTION_SKIPPED_FRESHNESS': 'Коррекция: устаревшие данные',
  'CORRECTION_SKIPPED_WINDOW_NOT_READY': 'Коррекция: окно наблюдения не готово',
  'CORRECTION_SKIPPED_ANOMALY_BLOCK': 'Коррекция: аномалия оборудования',
  'CORRECTION_PLANNER_CONFIG_INVALID': 'Коррекция: ошибка конфигурации planner',
  'CORRECTION_SKIPPED_EMERGENCY_STOP': 'Коррекция: E-STOP',
  'CORRECTION_SKIPPED_BY_ALERT_BLOCK': 'Коррекция: блок alert',
  'CORRECTION_ACTION_DEFERRED': 'Коррекция: действие отложено',
  'CORRECTION_NO_EFFECT': 'Коррекция: нет наблюдаемого эффекта',
  'CORRECTION_SENSOR_MODE_REACTIVATED': 'Коррекция: датчик реактивирован',
  'PUMP_CALIBRATION_MIRROR_MISMATCH': 'Коррекция: расхождение калибровки насоса',
  'PH_CORRECTION_SKIPPED': 'Коррекция pH: пропуск',
  'EC_CORRECTION_SKIPPED': 'Коррекция EC: пропуск',
  'PH_CORRECTION_SKIPPED_STALE_DATA': 'Коррекция pH: устаревшие данные',
  'EC_CORRECTION_SKIPPED_STALE_DATA': 'Коррекция EC: устаревшие данные',
  'PH_CORRECTION_SKIPPED_BOUNDS': 'Коррекция pH: ограничение safety bounds',
  'EC_CORRECTION_SKIPPED_BOUNDS': 'Коррекция EC: ограничение safety bounds',
  'PH_CORRECTION_SKIPPED_ANOMALY': 'Коррекция pH: блок аномалии оборудования',
  'EC_CORRECTION_SKIPPED_ANOMALY': 'Коррекция EC: блок аномалии оборудования',

  // Автотюнинг / калибровки
  'RELAY_AUTOTUNE_STARTED': 'Relay-автотюнинг запущен',
  'RELAY_AUTOTUNE_COMPLETE': 'Relay-автотюнинг завершён',
  'RELAY_AUTOTUNE_COMPLETED': 'Relay-автотюнинг завершён',
  'RELAY_AUTOTUNE_TIMEOUT': 'Relay-автотюнинг: таймаут',
  'PUMP_CALIBRATION_SAVED': 'Калибровка насоса сохранена',
  'PUMP_CALIBRATION_STARTED': 'Калибровка насоса запущена',
  'PUMP_CALIBRATION_FINISHED': 'Калибровка насоса завершена',
  'PUMP_CALIBRATION_RUN_SKIPPED': 'Калибровка насоса пропущена',
  'PUMP_CALIBRATION_STALE': 'Калибровка насоса устарела',
  'PROCESS_CALIBRATION_SAVED': 'Калибровка процесса сохранена',
  'CALIBRATION_STARTED': 'Калибровка запущена',
  'CALIBRATION_COMPLETED': 'Калибровка завершена',
  'PUMP_STOPPED': 'Насос остановлен',

  // Equipment anomaly
  'EQUIPMENT_ANOMALY_BLOCKED': 'Оборудование: блокировка (нет эффекта)',
  'EQUIPMENT_ANOMALY_RELEASED': 'Оборудование: блокировка снята',

  // Irrigation / AE workflow
  'IRR_STATE_SNAPSHOT': 'Снимок ирригации',
  'IRR_STATE_PROBE_DEFERRED': 'Ирригация: опрос состояния отложен',
  'IRR_STATE_PROBE_FAILED': 'Ирригация: ошибка опроса состояния',
  'IRR_STATE_PROBE_STREAK_EXHAUSTED': 'Ирригация: опрос состояния исчерпан',
  'IRRIGATION_DECISION_SNAPSHOT_LOCKED': 'Параметры полива зафиксированы',
  'IRRIGATION_DECISION_EVALUATED': 'Решение о поливе',
  'IRRIGATION_DECISION_APPLIED': 'Решение о поливе применено',
  'IRRIGATION_CORRECTION_STARTED': 'Полив: окно коррекции открыто',
  'IRRIGATION_CORRECTION_COMPLETED': 'Полив: коррекция завершена',
  'IRRIGATION_EC_MULTI_DOSE': 'Полив: многодозовая EC-коррекция',
  'IRRIGATION_START': 'Полив запущен',
  'IRRIGATION_STOP': 'Полив остановлен',
  'IRRIGATION_STARTED': 'Полив запущен',
  'IRRIGATION_FINISHED': 'Полив завершён',
  'IRRIGATION_STOPPED': 'Полив остановлен',
  'IRRIGATION_SKIPPED': 'Полив пропущен',
  'IRRIGATION_APPROVED': 'Полив разрешён',
  'IRRIGATION_READY': 'Раствор готов к поливу',
  'IRRIGATION_CHECK': 'Проверка полива',
  'IRRIGATION_LOW_SOLUTION': 'Полив остановлен: низкий уровень раствора',
  'IRRIGATION_SOLUTION_LOW': 'Полив: низкий уровень раствора',
  'IRRIGATION_SOLUTION_MIN_DETECTED': 'Полив: достигнут минимум раствора',
  'IRRIGATION_WAIT_READY_TIMEOUT': 'Полив: таймаут ожидания готовности',
  'IRRIGATION_BLOCKED_SETUP_PENDING': 'Полив заблокирован: нужна подготовка',
  'IRRIGATION_RECOVERY_STARTED': 'Recovery после полива запущен',
  'IRRIGATION_RECOVERY_COMPLETED': 'Recovery после полива завершён',
  'IRRIGATION_CYCLE_STARTED': 'Полив запущен',
  'IRRIGATION_CYCLE_FINISHED': 'Полив завершён',
  'IRRIGATION_CYCLE_STOPPED': 'Полив остановлен',
  'IRRIGATION_CYCLE_SKIPPED': 'Полив пропущен',

  // Two-tank fill / recirculation
  'CLEAN_FILL_STARTED': 'Чистая вода: заполнение запущено',
  'CLEAN_FILL_IN_PROGRESS': 'Чистая вода: заполнение',
  'CLEAN_FILL_SOURCE_EMPTY': 'Чистая вода: источник пуст',
  'CLEAN_FILL_COMPLETED': 'Чистая вода: заполнение завершено',
  'SOLUTION_FILL_STARTED': 'Раствор: заполнение запущено',
  'SOLUTION_FILL_IN_PROGRESS': 'Раствор: заполнение',
  'SOLUTION_FILL_CORRECTION': 'Раствор: коррекция при заполнении',
  'SOLUTION_FILL_SOURCE_EMPTY': 'Раствор: источник чистой воды пуст',
  'SOLUTION_FILL_LEAK_DETECTED': 'Раствор: провал нижнего уровня',
  'SOLUTION_FILL_COMPLETED': 'Раствор: заполнение завершено',
  'SOLUTION_FILL_TIMEOUT': 'Раствор: таймаут заполнения',
  'SOLUTION_CHANGE_GATE_PASSED': 'Смена раствора: проверка пройдена',
  'SOLUTION_CHANGE_COMPLETED': 'Смена раствора завершена',
  'SOLUTION_CHANGE_ABORTED': 'Смена раствора прервана',
  'SOLUTION_TOPUP_DONE': 'Долив раствора завершён',
  'SOLUTION_TANK_STARTUP_GUARD_TRIGGERED': 'Защита бака: запуск заблокирован',
  'SOLUTION_TANK_MIN_TRIGGERED': 'Бак: уровень раствора критически низкий',
  'RECIRC_STARTED': 'Рециркуляция запущена',
  'RECIRC_IN_PROGRESS': 'Рециркуляция',
  'RECIRC_COMPLETED': 'Рециркуляция завершена',
  'RECIRCULATION_SOLUTION_LOW': 'Рециркуляция: низкий уровень раствора',
  'RECIRCULATION_SOLUTION_LOW_TO_SETUP': 'Рециркуляция → подготовка раствора',
  'RECIRCULATION_STATE_CHANGED': 'Рециркуляция: изменение состояния',
  'PREPARE_RECIRCULATION_TIMEOUT': 'Таймаут подготовки рециркуляции',
  'WATER_CHANGE_STARTED': 'Смена воды запущена',
  'WATER_CHANGE_COMPLETED': 'Смена воды завершена',
  'READY': 'Готов к поливу',

  // AE runtime / control
  'AE_TASK_STARTED': 'Задача AE запущена',
  'AE_TASK_COMPLETED': 'Задача AE завершена',
  'AE_TASK_FAILED': 'Задача AE: ошибка',
  'AE_STARTUP_PROBE_TIMEOUT': 'AE: таймаут startup-probe',
  'AE_COMMAND_POLL_DEADLINE_EXCEEDED': 'AE: таймаут ожидания ответа команды',
  'AE_COMMAND_SEND_RETRY_SCHEDULED': 'AE: повтор отправки команды',
  'AE_COMMAND_SEND_RETRY_EXHAUSTED': 'AE: исчерпаны повторы отправки команды',
  'AE_SNAPSHOT_RETRY_SCHEDULED': 'AE: повтор опроса снимка состояния',
  'AE_SNAPSHOT_RETRY_EXHAUSTED': 'AE: исчерпаны повторы опроса снимка',
  'AE_WORKFLOW_STATE_SYNC_FAILED': 'AE: ошибка синхронизации workflow',
  'CONTROL_MODE_CHANGED': 'Режим управления изменён',
  'CONTROL_MODE_FLOW_STOPPED': 'Поток остановлен (control mode)',
  'FLOW_STOP_FAILED_HARDWARE_MAY_BE_ACTIVE': 'Ошибка остановки потока: оборудование может быть активно',
  'CONFIG_HOT_RELOADED': 'Конфиг горячо перезагружен',
  'CONFIG_MODE_AUTO_REVERTED': 'Режим конфига автоматически откатан',
  'COMMAND_ZONE_NODE_MISMATCH': 'Команда: несовпадение зоны и узла',
  'COMMAND_TIMEOUT': 'Таймаут команды',
  'command_status': 'Статус команды',
  'COMMAND_STATUS': 'Статус команды',
  'NODE_REBOOT_DETECTED': 'Обнаружена перезагрузка узла',
  'TELEMETRY_STALE': 'Телеметрия устарела',
  'EMERGENCY_STOP_ACTIVATED': 'Аварийный стоп активирован',
  'WATER_LEVEL_SENSOR_CHANGED': 'Датчик уровня воды: изменение',
  'LEVEL_SWITCH_CHANGED': 'Датчик уровня: изменение',
  'ZONE_AUTOMATION_STARTED': 'Автоматизация зоны запущена',
  'ZONE_AUTOMATION_STOPPED': 'Автоматизация зоны остановлена',
  'ZONE_WORKFLOW_STATE_RESET': 'Состояние workflow сброшено',
  'TWO_TANK_STARTUP_INITIATED': 'Two-tank: запуск подготовки',

  // Alerts / lifecycle
  'ALERT_TRIGGERED': 'Тревога сработала',
  'NODE_CONNECTED': 'Узел подключён',
  'NODE_DISCONNECTED': 'Узел отключён',
  'AUTO_MODE_ENABLED': 'Авторежим включён',
  'AUTO_MODE_DISABLED': 'Авторежим выключен',
  'MANUAL_INTERVENTION': 'Ручное вмешательство',
  'SETTINGS_CHANGED': 'Настройки изменены',
  'AUTOMATION_LOGIC_PROFILE_UPDATED': 'Профиль автоматики обновлён',
  'RECIPE_STARTED': 'Рецепт запущен',
  'RECIPE_COMPLETED': 'Рецепт завершён',
  'HARVEST_STARTED': 'Сбор урожая начат',
  'HARVEST_COMPLETED': 'Сбор урожая завершён',
  'PHASE_CHANGE': 'Смена фазы',
}

/**
 * Переводит тип события на русский язык
 * @param {string} kind - Тип события (ALERT_CREATED, CYCLE_STARTED и т.д.)
 * @returns {string} Переведенный тип события
 */
export function translateEventKind(kind) {
  if (typeof kind !== 'string' || kind.length === 0) return ''
  return EVENT_KIND_TRANSLATIONS[kind] || EVENT_KIND_TRANSLATIONS[kind.toUpperCase()] || kind
}

/**
 * Переводит стадию/фазу AE workflow на русский
 * @param {string} value - стадия или фаза (напр. irrigation_check, irrig_recirc)
 * @returns {string}
 */
export function translateWorkflowStage(value) {
  if (!value) return value
  const translations = {
    // Workflow phases
    'ready': 'Готов',
    'irrigating': 'Полив',
    'irrig_recirc': 'Рециркуляция',
    'startup': 'Запуск',
    'clean_fill': 'Заполнение чистой водой',
    'solution_fill': 'Заполнение раствором',
    'prepare_recirculation': 'Подготовка рециркуляции',
    'idle': 'Ожидание',
    'fault': 'Сбой',
    // Stages
    'await_ready': 'Ожидание готовности',
    'irrigation_start': 'Старт полива',
    'irrigation_check': 'Проверка полива',
    'irrigation_stop': 'Остановка полива',
    'irrigation_stop_to_ready': 'Завершение → готов',
    'completed_run': 'Цикл завершён',
    'decision_gate': 'Шлюз решения',
    'correction_window': 'Окно коррекции',
    'clean_fill_start': 'Старт заполнения водой',
    'solution_fill_start': 'Старт заполнения раствором',
    'recirculation_start': 'Старт рециркуляции',
    'recirculation_stop': 'Остановка рециркуляции',
  }
  return translations[value] ?? value
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

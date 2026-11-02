import { formatRelativeUtc } from '@/utils/manualSchedulePreview'

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return '—'

  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(parsed)
}

export function formatRelativeTrigger(value: string | null | undefined): string {
  if (!value) return '—'
  return formatRelativeUtc(value)
}

export function statusVariant(status: string | null | undefined): 'success' | 'warning' | 'danger' | 'info' | 'secondary' {
  const normalized = String(status ?? '').trim().toLowerCase()
  if (normalized === 'completed') return 'success'
  if (normalized === 'running' || normalized === 'accepted') return 'info'
  if (normalized === 'failed' || normalized === 'cancelled') return 'danger'
  return 'secondary'
}

export function controlModeLabel(controlMode: string | null | undefined): string {
  const normalized = String(controlMode ?? '').trim().toLowerCase()
  if (normalized === 'manual') return 'ручной'
  if (normalized === 'semi') return 'полуавто'
  return 'авто'
}

export function laneLabel(taskType: string | null | undefined): string {
  const normalized = String(taskType ?? '').trim().toLowerCase()
  if (normalized === 'irrigation') return 'Полив'
  if (normalized === 'lighting') return 'Свет'
  if (normalized === 'climate' || normalized === 'ventilation') return 'Климат'
  if (normalized === 'solution_change') return 'Смена раствора'
  if (normalized === 'diagnostics') return 'Диагностика'
  if (normalized === 'mist') return 'Туман'
  return normalized || '—'
}

export function decisionLabel(outcome: string | null | undefined, degraded: boolean | null | undefined): string {
  const normalized = String(outcome ?? '').trim().toLowerCase()
  if (normalized === 'skip') return 'Пропуск'
  if (normalized === 'degraded_run' || (normalized === 'run' && degraded)) return 'Деградированный запуск'
  if (normalized === 'run') return 'Запуск'
  if (normalized === 'fail') return 'Сбой decision-controller'
  return normalized || 'Decision'
}

export function statusLabel(status: string | null | undefined): string {
  const normalized = String(status ?? '').trim().toLowerCase()
  const labels: Record<string, string> = {
    running: 'Выполняется',
    completed: 'Завершён',
    failed: 'Ошибка',
    cancelled: 'Отменён',
    pending: 'Ожидает',
    claimed: 'Занят',
    waiting_command: 'Ожидает команды',
    idle: 'Ожидание',
    accepted: 'Принят',
    skipped: 'Пропущен',
    unknown: 'Неизвестно',
  }
  return labels[normalized] ?? status ?? '—'
}

export function workflowStageLabel(stage: string | null | undefined): string | null {
  const raw = asNonEmptyString(stage)
  if (!raw) return null
  const normalized = raw.toLowerCase()
  const labels: Record<string, string> = {
    // Общие
    startup: 'Запуск',
    idle: 'Ожидание',
    waiting: 'Ожидание',
    ready: 'Готов',
    complete_ready: 'Готовность',
    cycle_start: 'Запуск цикла',
    decision_gate: 'Шлюз решения',
    apply: 'Применение',
    await_ready: 'Ожидание готовности',
    unknown: 'Неизвестно',
    completed_run: 'Выполнение завершено',
    completed_skip: 'Пропуск завершён',
    // Заполнение чистой водой
    clean_fill: 'Заполнение чистой водой',
    clean_fill_start: 'Запуск заполнения (чистая вода)',
    clean_fill_check: 'Проверка заполнения',
    clean_fill_cycle: 'Цикл заполнения',
    clean_fill_stop_to_solution: 'Заполнение → раствор',
    clean_fill_retry_stop: 'Повтор заполнения — стоп',
    clean_fill_source_empty_stop: 'Источник пуст — стоп',
    clean_fill_timeout_stop: 'Таймаут заполнения — стоп',
    // Заполнение раствором
    solution_fill: 'Заполнение раствором',
    solution_fill_start: 'Запуск заполнения (раствор)',
    solution_fill_check: 'Проверка заполнения раствором',
    solution_fill_stop_to_prepare: 'Заполнение → подготовка',
    solution_fill_stop_to_ready: 'Заполнение → готовность',
    solution_fill_leak_stop: 'Утечка — стоп',
    solution_fill_source_empty_stop: 'Источник пуст — стоп',
    solution_fill_timeout_stop: 'Таймаут — стоп',
    // Рециркуляция
    prepare_recirculation: 'Подготовка рециркуляции',
    prepare_recirculation_check: 'Проверка рециркуляции',
    prepare_recirculation_start: 'Запуск рециркуляции',
    prepare_recirculation_stop_to_ready: 'Остановка рециркуляции',
    prepare_recirculation_window_exhausted: 'Окно рециркуляции исчерпано',
    prepare_recirculation_solution_low_stop: 'Низкий уровень — стоп',
    irrig_recirc: 'Полив с рециркуляцией',
    tank_recirc: 'Рециркуляция бака',
    tank_filling: 'Заполнение бака',
    // Полив
    irrigation_check: 'Проверка полива',
    irrigating: 'Полив',
    irrigation_start: 'Запуск полива',
    irrigation_stop_to_ready: 'Полив → готовность',
    irrigation_stop_to_recovery: 'Полив → восстановление',
    irrigation_stop_to_setup: 'Полив → настройка',
    irrigation_recovery_check: 'Проверка восстановления',
    irrigation_recovery_start: 'Запуск восстановления',
    irrigation_recovery_stop_to_ready: 'Восстановление → готовность',
    // Коррекция
    exit_correction: 'Выход из коррекции',
    pre_dose_reactivation: 'Реактивация перед дозой',
    corr_return_stage_success: 'Коррекция: возврат успешен',
    corr_return_stage_fail: 'Коррекция: возврат неудачен',
    corr_step: 'Шаг коррекции',
    correction: 'Коррекция',
    dose: 'Дозирование',
    dosing: 'Дозирование',
    flush: 'Промывка',
    drain: 'Слив',
    fill: 'Заполнение',
  }
  return labels[normalized] ?? raw
}

export function asNonEmptyString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() !== '' ? value.trim() : null
}

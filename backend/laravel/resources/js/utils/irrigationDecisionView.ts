import type { IrrigationDecisionEvidence } from '@/types/Automation'

export function irrigationStrategyLabel(value: unknown): string {
  if (value === 'smart_soil_v1') return 'По влажности субстрата'
  if (value === 'task') return 'По расписанию'
  return 'Условие полива не определено'
}

export function irrigationOutcomeLabel(value: unknown): string {
  if (value === 'run' || value === 'degraded_run') return 'Полив разрешён'
  if (value === 'skip') return 'Полив пропущен'
  if (value === 'fail') return 'Полив не разрешён: ошибка'
  if (value == null || value === '') return 'Решение ещё не принято'
  return 'Результат решения неизвестен'
}

const REASONS: Record<string, { explanation: string; action: string | null }> = {
  irrigation_task_strategy_run: { explanation: 'Наступило время полива по расписанию. Влажность субстрата в этом режиме не проверяется.', action: null },
  irrigation_force_mode: { explanation: 'Оператор запросил полив без проверки влажности. Остальные ограничения безопасности продолжают действовать.', action: null },
  smart_soil_below_min: { explanation: 'Средняя влажность ниже нижней границы с учётом запаса. Условие для полива выполнено.', action: null },
  smart_soil_above_max: { explanation: 'Средняя влажность выше верхней границы. Дополнительный полив сейчас не требуется.', action: null },
  smart_soil_within_band: { explanation: 'Средняя влажность ещё не опустилась ниже порога запуска. Система дождётся следующей проверки.', action: null },
  smart_soil_target_missing: { explanation: 'В активной фазе рецепта не задана цель влажности.', action: 'Укажите влажность субстрата в рецепте действующего цикла.' },
  smart_soil_target_invalid: { explanation: 'Цель влажности содержит недопустимое значение, единицу или порядок границ.', action: 'Проверьте диапазон 0–100% и нижнюю/верхнюю границы в рецепте.' },
  smart_soil_telemetry_missing_or_stale: { explanation: 'Нет свежих корректных измерений хотя бы одного активного датчика влажности. Полив пропущен.', action: 'Проверьте связь, калибровку, единицы и время последнего измерения всех активных датчиков.' },
  irrigation_timezone_invalid: { explanation: 'Не удалось определить дневную или ночную цель из-за часового пояса теплицы.', action: 'Проверьте часовой пояс теплицы и время начала дня в рецепте.' },
  irrigation_decision_strategy_unknown: { explanation: 'Сохранено неизвестное условие разрешения полива.', action: 'Выберите полив по расписанию или по влажности и сохраните профиль.' },
  irrigation_decision_invalid_outcome: { explanation: 'Контроллер вернул неизвестный результат. Запуск не разрешён.', action: 'Откройте технические данные и передайте код ошибки инженеру.' },
  solution_temp_out_of_band: { explanation: 'Измерения подтвердили слишком низкую температуру раствора в течение выдержки.', action: 'Проверьте температуру раствора и нижнюю границу в рецепте. Следующая проверка будет выполнена по расписанию.' },
  solution_temp_hot_stop: { explanation: 'Измерения подтвердили аварийно высокую температуру раствора в течение выдержки. Новый полив пропущен.', action: 'Проверьте датчик и охлаждение раствора. Не снимайте ограничение, пока причина перегрева не устранена.' },
  solution_temp_hot_warn: { explanation: 'Раствор нагрет до порога предупреждения. Это предупреждение само по себе не запрещает полив.', action: 'Проверьте охлаждение раствора и наблюдайте за температурой.' },
  solution_temp_unavailable: { explanation: 'Нет свежего измерения температуры. По текущей политике это предупреждение не запрещает полив.', action: 'Проверьте датчик температуры раствора и время последнего измерения.' },
}

export function irrigationReasonPresentation(value: unknown) {
  const code = typeof value === 'string' ? value.replace('smart_soil_degraded_', 'smart_soil_') : ''
  return REASONS[code] ?? {
    explanation: code ? 'Причина решения не распознана.' : 'Проверка условий полива ещё не завершена.',
    action: code ? 'Откройте технические данные и проверьте код причины.' : null,
  }
}

export function decisionNumber(value: unknown): number | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null
  return value
}

export function irrigationDecisionFacts(decision: IrrigationDecisionEvidence): Array<{ label: string; value: string }> {
  const details = decision.details ?? {}
  const facts: Array<{ label: string; value: string }> = []
  const add = (key: string, label: string, unit = '') => {
    const value = decisionNumber(details[key])
    if (value !== null) facts.push({ label, value: `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(value)}${unit}` })
  }
  add('zone_average_pct', 'Средняя влажность', '%')
  add('run_below_pct', 'Полив при влажности ниже', '%')
  add('target_min_pct', 'Нижняя граница цели', '%')
  add('target_max_pct', 'Верхняя граница цели', '%')
  add('sensor_count', 'Датчиков с данными')
  add('active_sensor_count', 'Всего активных датчиков')
  add('missing_sensor_count', 'Датчиков без корректных данных')
  add('samples', details.hold_sec != null ? 'Измерений температуры' : 'Принято измерений влажности')
  add('soil_samples', 'Принято измерений влажности')
  add('rejected_samples', 'Отброшено измерений')
  add('spread_pct', 'Разброс датчиков', ' п.п.')
  add('max_sensor_sample_age_sec', 'Максимальный возраст последних данных', ' сек')
  const freshnessLimit = decisionNumber(decision.config?.stale_after_sec)
  if (freshnessLimit !== null) facts.push({ label: 'Допустимый возраст данных', value: `${freshnessLimit} сек` })
  add('latest_c', 'Температура раствора', ' °C')
  add('hold_sec', 'Требуемая выдержка', ' сек')
  add('observed_span_sec', 'Длительность наблюдения', ' сек')
  add('requested_duration_sec', 'Запрошенная длительность подачи', ' сек')
  if (typeof details.target_profile === 'string' && details.target_profile) {
    facts.push({ label: 'Профиль цели', value: details.target_profile === 'day' ? 'Дневной' : details.target_profile === 'night' ? 'Ночной' : details.target_profile })
  }
  if (typeof details.timezone === 'string' && details.timezone) {
    facts.push({ label: 'Часовой пояс цели', value: details.timezone })
  }
  if (typeof details.hold_covered === 'boolean') {
    facts.push({ label: 'Выдержка подтверждена измерениями', value: details.hold_covered ? 'Да' : 'Нет' })
  }
  return facts
}

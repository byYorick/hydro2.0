/**
 * Дескрипторы low-level runtime параметров Automation Engine.
 * Используются для отображения в вкладке «Автоматизация» → секция «Настройки AE».
 */

export interface AutomationEngineSettingItem {
  key: string
  label: string
  value: unknown
  unit?: string
  description?: string
}

export interface AutomationEngineSettingDescriptor {
  key: string
  group: 'startup' | 'correction' | 'solution_change'
  label: string
  unit?: string
  description: string
}

export const AUTOMATION_ENGINE_SETTING_DESCRIPTORS: AutomationEngineSettingDescriptor[] = [
  {
    key: 'subsystems.diagnostics.execution.workflow',
    group: 'startup',
    label: 'diagnostics.workflow',
    description: 'Режим запуска диагностики: startup (2 бака), cycle_start (3 бака) или diagnostics (только диагностика).',
  },
  {
    key: 'subsystems.diagnostics.execution.refill.duration_sec',
    group: 'startup',
    label: 'refill.duration_sec',
    unit: 'sec',
    description: 'Рабочая длительность импульса долива/набора при диагностике.',
  },
  {
    key: 'subsystems.diagnostics.execution.refill.timeout_sec',
    group: 'startup',
    label: 'refill.timeout_sec',
    unit: 'sec',
    description: 'Максимальное время ожидания завершения refill до фиксации timeout.',
  },
  {
    key: 'subsystems.diagnostics.execution.startup.clean_fill_timeout_sec',
    group: 'startup',
    label: 'startup.clean_fill_timeout_sec',
    unit: 'sec',
    description: 'Таймаут фазы заполнения бака чистой водой в startup.',
  },
  {
    key: 'subsystems.diagnostics.execution.startup.solution_fill_timeout_sec',
    group: 'startup',
    label: 'startup.solution_fill_timeout_sec',
    unit: 'sec',
    description: 'Таймаут фазы заполнения бака раствором в startup.',
  },
  {
    key: 'subsystems.diagnostics.execution.startup.prepare_recirculation_timeout_sec',
    group: 'startup',
    label: 'startup.prepare_recirculation_timeout_sec',
    unit: 'sec',
    description: 'Таймаут подготовки рециркуляции перед переходом в рабочий режим.',
  },
  {
    key: 'subsystems.diagnostics.execution.startup.clean_fill_retry_cycles',
    group: 'startup',
    label: 'startup.clean_fill_retry_cycles',
    description: 'Количество разрешённых повторов clean_fill при неуспешном наборе.',
  },
  {
    key: 'subsystems.diagnostics.execution.irrigation_recovery.max_continue_attempts',
    group: 'startup',
    label: 'irrigation_recovery.max_continue_attempts',
    description: 'Максимум попыток продолжить полив в сценарии recovery.',
  },
  {
    key: 'subsystems.diagnostics.execution.irrigation_recovery.timeout_sec',
    group: 'startup',
    label: 'irrigation_recovery.timeout_sec',
    unit: 'sec',
    description: 'Таймаут сценария восстановления irrigation_recovery.',
  },
  {
    key: 'subsystems.diagnostics.execution.prepare_tolerance.ec_pct',
    group: 'startup',
    label: 'prepare_tolerance.ec_pct',
    unit: '%',
    description: 'Допуск по EC для признания фазы подготовки раствора успешной.',
  },
  {
    key: 'subsystems.diagnostics.execution.prepare_tolerance.ph_pct',
    group: 'startup',
    label: 'prepare_tolerance.ph_pct',
    unit: '%',
    description: 'Допуск по pH для признания фазы подготовки раствора успешной.',
  },
  {
    key: 'subsystems.diagnostics.execution.correction.max_ec_correction_attempts',
    group: 'correction',
    label: 'correction.max_ec_correction_attempts',
    description: 'Максимум попыток EC-коррекции в одном correction cycle.',
  },
  {
    key: 'subsystems.diagnostics.execution.correction.max_ph_correction_attempts',
    group: 'correction',
    label: 'correction.max_ph_correction_attempts',
    description: 'Максимум попыток pH-коррекции в одном correction cycle.',
  },
  {
    key: 'subsystems.diagnostics.execution.correction.prepare_recirculation_max_attempts',
    group: 'correction',
    label: 'correction.prepare_recirculation_max_attempts',
    description: 'Сколько окон рециркуляции допускается до terminal fail.',
  },
  {
    key: 'subsystems.diagnostics.execution.correction.prepare_recirculation_max_correction_attempts',
    group: 'correction',
    label: 'correction.prepare_recirculation_max_correction_attempts',
    description: 'Верхний общий лимит шагов коррекции внутри окон рециркуляции.',
  },
  {
    key: 'subsystems.diagnostics.execution.correction.stabilization_sec',
    group: 'correction',
    label: 'correction.stabilization_sec',
    unit: 'sec',
    description: 'Stage-level stabilization перед первым corr_check; не заменяет observe-window после дозы.',
  },
  {
    key: 'subsystems.solution_change.execution.interval_sec',
    group: 'solution_change',
    label: 'solution_change.interval_sec',
    unit: 'sec',
    description: 'Период запуска процедуры полной смены раствора.',
  },
  {
    key: 'subsystems.solution_change.execution.duration_sec',
    group: 'solution_change',
    label: 'solution_change.duration_sec',
    unit: 'sec',
    description: 'Длительность одного цикла смены раствора.',
  },
]

export const AUTOMATION_ENGINE_SETTING_GROUP_META: Record<
  AutomationEngineSettingDescriptor['group'],
  { label: string; description: string }
> = {
  startup: {
    label: 'Startup, refill и recovery',
    description:
      'Низкоуровневые лимиты фаз запуска, refill и recovery-path, которые не являются частью пользовательского профиля климата/полива.',
  },
  correction: {
    label: 'Correction loop guards',
    description: 'Лимиты correction cycle и stage-level guard-параметры AE.',
  },
  solution_change: {
    label: 'Solution change runtime',
    description: 'Периодичность и длительность процедуры полной смены раствора.',
  },
}

export function formatAutomationEngineSettingValue(item: AutomationEngineSettingItem): string {
  const { value, unit } = item

  if (value === null || value === undefined) {
    return '—'
  }

  let rendered: string
  if (typeof value === 'boolean') {
    rendered = value ? 'true' : 'false'
  } else if (Array.isArray(value)) {
    rendered = value.length > 0 ? value.map((entry) => String(entry)).join(', ') : '[]'
  } else if (typeof value === 'object') {
    rendered = JSON.stringify(value)
  } else {
    rendered = String(value)
  }

  return unit ? `${rendered} ${unit}` : rendered
}

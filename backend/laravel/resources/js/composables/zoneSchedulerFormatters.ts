/**
 * zoneSchedulerFormatters.ts
 *
 * Чистые функции форматирования и label-хелперы для scheduler-задач.
 * Не содержат реактивного состояния — импортируются напрямую там, где нужны.
 */
import { parseIsoDate, formatRelativeMs } from '@/composables/zoneAutomationUtils'
import type {
  SchedulerTaskStatus,
  SchedulerTaskTimelineItem,
  SchedulerTaskPreset,
  SchedulerTaskSlaVariant,
  SchedulerTaskSlaMeta,
  SchedulerTaskDoneMeta,
} from '@/composables/zoneAutomationTypes'

// ─── Constants ────────────────────────────────────────────────────────────────

const TARGET_SCHEDULER_STATUSES = ['accepted', 'running', 'completed', 'failed', 'rejected', 'expired'] as const
type TargetSchedulerStatus = (typeof TARGET_SCHEDULER_STATUSES)[number]

export const CLEAN_FILL_REASON_CODES = new Set([
  'clean_fill_started',
  'clean_fill_in_progress',
  'clean_fill_completed',
  'clean_fill_timeout',
  'clean_fill_retry_started',
  'tank_refill_started',
  'tank_refill_in_progress',
  'tank_refill_completed',
  'tank_refill_timeout',
  'tank_refill_required',
  'tank_refill_not_required',
])
export const SOLUTION_FILL_REASON_CODES = new Set([
  'solution_fill_started',
  'solution_fill_in_progress',
  'solution_fill_completed',
  'solution_fill_timeout',
])
export const PARALLEL_CORRECTION_REASON_CODES = new Set([
  'prepare_recirculation_started',
  'prepare_targets_not_reached',
  'prepare_npk_ph_target_not_reached',
  'tank_to_tank_correction_started',
  'online_correction_failed',
  'irrigation_recovery_started',
  'irrigation_recovery_recovered',
  'irrigation_recovery_failed',
  'irrigation_recovery_degraded',
])
export const SETUP_TRANSITION_REASON_CODES = new Set([
  'prepare_targets_reached',
  'setup_completed',
  'setup_finished',
  'setup_to_working',
  'working_mode_activated',
])

// ─── Internal types ───────────────────────────────────────────────────────────

export interface SchedulerTasksResponse {
  status: string
  data?: SchedulerTaskStatus[]
}

export interface SchedulerTaskResponse {
  status: string
  data?: SchedulerTaskStatus
}

// ─── Private helpers ──────────────────────────────────────────────────────────

export type SchedulerTaskProcessStatus = 'pending' | 'running' | 'completed' | 'failed'

export function normalizeTargetSchedulerStatus(status: string | null | undefined): TargetSchedulerStatus | null {
  const normalized = String(status ?? '').trim().toLowerCase()
  if (normalized === 'done') return 'completed'
  if (normalized === 'pending' || normalized === 'claimed') return 'accepted'
  if (normalized === 'cancelled' || normalized === 'canceled') return 'rejected'
  if (TARGET_SCHEDULER_STATUSES.includes(normalized as TargetSchedulerStatus)) {
    return normalized as TargetSchedulerStatus
  }
  return null
}

export function normalizeProcessStatus(status: string | null | undefined): SchedulerTaskProcessStatus {
  const normalized = String(status ?? '').trim().toLowerCase()
  if (normalized === 'running') return 'running'
  if (normalized === 'completed') return 'completed'
  if (normalized === 'failed') return 'failed'
  return 'pending'
}

export function normalizeOptionalBool(value: unknown): boolean | null {
  if (typeof value === 'boolean') return value
  if (typeof value === 'number') {
    if (value === 1) return true
    if (value === 0) return false
    return null
  }
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase()
    if (normalized === 'true' || normalized === '1') return true
    if (normalized === 'false' || normalized === '0') return false
  }
  return null
}

export function resolveTaskCommandSubmitted(task: SchedulerTaskStatus | null | undefined): boolean | null {
  if (!task) return null
  const fromRoot = normalizeOptionalBool(task.command_submitted)
  if (fromRoot !== null) return fromRoot
  const fromResult = normalizeOptionalBool(task.result?.command_submitted)
  return fromResult
}

export function resolveTaskCommandEffectConfirmed(task: SchedulerTaskStatus | null | undefined): boolean | null {
  if (!task) return null
  const fromRoot = normalizeOptionalBool(task.command_effect_confirmed)
  if (fromRoot !== null) return fromRoot
  const fromResult = normalizeOptionalBool(task.result?.command_effect_confirmed)
  return fromResult
}

export function resolveTaskCommandsTotal(task: SchedulerTaskStatus | null | undefined): number | null {
  const toFinite = (v: unknown): number | null => {
    const n = Number(v)
    return Number.isFinite(n) ? n : null
  }
  const direct = toFinite(task?.commands_total ?? null)
  if (direct !== null) return Math.max(0, Math.round(direct))
  const fromResult = toFinite(task?.result?.commands_total)
  if (fromResult !== null) return Math.max(0, Math.round(fromResult))
  return null
}

export function resolveTaskCommandsEffectConfirmed(task: SchedulerTaskStatus | null | undefined): number | null {
  const toFinite = (v: unknown): number | null => {
    const n = Number(v)
    return Number.isFinite(n) ? n : null
  }
  const direct = toFinite(task?.commands_effect_confirmed ?? null)
  if (direct !== null) return Math.max(0, Math.round(direct))
  const fromResult = toFinite(task?.result?.commands_effect_confirmed)
  if (fromResult !== null) return Math.max(0, Math.round(fromResult))
  return null
}

// ─── Exported formatters ──────────────────────────────────────────────────────

export function schedulerTaskStatusVariant(
  status: string | null | undefined
): 'success' | 'warning' | 'danger' | 'info' | 'secondary' {
  const normalized = normalizeTargetSchedulerStatus(status)
  if (normalized === 'completed') return 'success'
  if (normalized === 'failed' || normalized === 'rejected' || normalized === 'expired') return 'danger'
  if (normalized === 'running') return 'warning'
  if (normalized === 'accepted') return 'info'
  return 'secondary'
}

export function schedulerTaskStatusLabel(status: string | null | undefined): string {
  const normalized = normalizeTargetSchedulerStatus(status)
  if (normalized === 'accepted') return 'Принята'
  if (normalized === 'running') return 'Выполняется'
  if (normalized === 'completed') return 'Выполнена'
  if (normalized === 'failed') return 'Ошибка'
  if (normalized === 'rejected') return 'Отклонена'
  if (normalized === 'expired') return 'Просрочена'
  return 'Неизвестно'
}

export function schedulerTaskProcessStatusVariant(status: string | null | undefined): SchedulerTaskSlaVariant {
  const normalized = normalizeProcessStatus(status)
  if (normalized === 'running') return 'warning'
  if (normalized === 'completed') return 'success'
  if (normalized === 'failed') return 'danger'
  return 'secondary'
}

export function schedulerTaskProcessStatusLabel(
  status: string | null | undefined,
  fallbackLabel?: string | null
): string {
  if (typeof fallbackLabel === 'string' && fallbackLabel.trim() !== '') {
    return fallbackLabel
  }
  const normalized = normalizeProcessStatus(status)
  if (normalized === 'running') return 'Выполняется'
  if (normalized === 'completed') return 'Выполнено'
  if (normalized === 'failed') return 'Ошибка'
  return 'Ожидание'
}

export function schedulerTaskEventLabel(eventType: string | null | undefined): string {
  const normalized = String(eventType ?? '').toUpperCase()
  if (normalized === 'TASK_RECEIVED') return 'Задача получена'
  if (normalized === 'TASK_STARTED') return 'Выполнение начато'
  if (normalized === 'DECISION_MADE') return 'Решение принято'
  if (normalized === 'COMMAND_DISPATCHED') return 'Команда отправлена'
  if (normalized === 'COMMAND_FAILED') return 'Ошибка отправки команды'
  if (normalized === 'COMMAND_EFFECT_NOT_CONFIRMED') return 'Команда не подтверждена нодой (не DONE)'
  if (normalized === 'TASK_FINISHED') return 'Задача завершена'
  if (normalized === 'SCHEDULE_TASK_EXECUTION_STARTED') return 'Automation-engine: запуск выполнения'
  if (normalized === 'SCHEDULE_TASK_EXECUTION_FINISHED') return 'Automation-engine: выполнение завершено'
  if (normalized === 'DIAGNOSTICS_SERVICE_UNAVAILABLE') return 'Diagnostics service недоступен'
  if (normalized === 'CYCLE_START_INITIATED') return 'Запуск цикла инициирован'
  if (normalized === 'NODES_AVAILABILITY_CHECKED') return 'Проверена доступность нод'
  if (normalized === 'TANK_LEVEL_CHECKED') return 'Проверен уровень бака'
  if (normalized === 'TANK_LEVEL_STALE') return 'Телеметрия бака устарела'
  if (normalized === 'TANK_REFILL_STARTED') return 'Запущено наполнение бака'
  if (normalized === 'TANK_REFILL_COMPLETED') return 'Наполнение бака завершено'
  if (normalized === 'TANK_REFILL_TIMEOUT') return 'Таймаут наполнения бака'
  if (normalized === 'CLEAN_FILL_STARTED') return 'Запущено наполнение бака чистой воды'
  if (normalized === 'CLEAN_FILL_COMPLETED') return 'Наполнение бака чистой воды завершено'
  if (normalized === 'SOLUTION_FILL_STARTED') return 'Запущено наполнение бака раствора'
  if (normalized === 'SOLUTION_FILL_COMPLETED') return 'Наполнение бака раствора завершено'
  if (normalized === 'SELF_TASK_ENQUEUED') return 'Запланирована отложенная проверка'
  if (normalized === 'SELF_TASK_DISPATCHED') return 'Отложенная задача отправлена'
  if (normalized === 'SELF_TASK_DISPATCH_FAILED') return 'Отложенная задача не отправлена'
  if (normalized === 'SELF_TASK_EXPIRED') return 'Отложенная задача просрочена'
  if (normalized === 'SCHEDULE_TASK_ACCEPTED') return 'Scheduler: задача принята'
  if (normalized === 'SCHEDULE_TASK_COMPLETED') return 'Scheduler: задача завершена'
  if (normalized === 'SCHEDULE_TASK_FAILED') return 'Scheduler: задача завершилась с ошибкой'
  if (normalized === 'AUTOMATION_CONTROL_MODE_UPDATED') return 'Режим управления автоматикой обновлён'
  if (normalized === 'MANUAL_STEP_ACCEPTED') return 'Ручной шаг принят'
  if (normalized === 'MANUAL_STEP_REQUESTED') return 'Ручной шаг запрошен'
  if (normalized === 'MANUAL_STEP_EXECUTED') return 'Ручной шаг выполнен'
  return eventType ? String(eventType) : 'Событие'
}

export function schedulerTaskTimelineStageLabel(step: SchedulerTaskTimelineItem | null | undefined): string | null {
  if (!step) return null

  const eventType = String(step.event_type ?? '').trim().toUpperCase()
  const reasonCode = String(step.reason_code ?? '').trim().toLowerCase()
  const runMode = String(step.run_mode ?? '').trim().toLowerCase()

  if (
    CLEAN_FILL_REASON_CODES.has(reasonCode) ||
    eventType === 'TANK_REFILL_STARTED' ||
    eventType === 'TANK_REFILL_COMPLETED' ||
    eventType === 'TANK_REFILL_TIMEOUT'
  ) {
    return 'Этап: набор бака с чистой водой'
  }

  if (SOLUTION_FILL_REASON_CODES.has(reasonCode)) {
    return 'Этап: набор бака с раствором'
  }

  if (
    SETUP_TRANSITION_REASON_CODES.has(reasonCode) ||
    ((eventType === 'SCHEDULE_TASK_EXECUTION_FINISHED' || eventType === 'TASK_FINISHED') && runMode === 'working')
  ) {
    return 'Этап: завершение setup и переход в рабочий режим'
  }

  if (PARALLEL_CORRECTION_REASON_CODES.has(reasonCode)) {
    return 'Этап: параллельная коррекция pH/EC'
  }

  return null
}

export function schedulerTaskTimelineStepLabel(step: SchedulerTaskTimelineItem | null | undefined): string {
  if (!step) return 'Событие'

  const stageLabel = schedulerTaskTimelineStageLabel(step)
  if (stageLabel) {
    const eventType = String(step.event_type ?? '').trim().toUpperCase()
    const stagePrefix = stageLabel.replace('Этап: ', '')
    const preferEventLabelForStage = new Set([
      'COMMAND_DISPATCHED',
      'CLEAN_FILL_STARTED',
      'CLEAN_FILL_COMPLETED',
      'SOLUTION_FILL_STARTED',
      'SOLUTION_FILL_COMPLETED',
      'TASK_FINISHED',
      'SCHEDULE_TASK_COMPLETED',
      'SCHEDULE_TASK_EXECUTION_FINISHED',
    ])

    if (preferEventLabelForStage.has(eventType)) {
      return `${stagePrefix}: ${schedulerTaskEventLabel(step.event_type)}`
    }

    if (step.reason_code) {
      return `${stagePrefix}: ${schedulerTaskReasonLabel(step.reason_code, step.reason)}`
    }
    if (step.error_code) {
      return `${stagePrefix}: ${schedulerTaskErrorLabel(step.error_code)}`
    }
    const eventLabel = schedulerTaskEventLabel(step.event_type)
    return `${stagePrefix}: ${eventLabel}`
  }

  return schedulerTaskEventLabel(step.event_type)
}

export function schedulerTaskTimelineItems(task: SchedulerTaskStatus | null | undefined): SchedulerTaskTimelineItem[] {
  const rawTimeline = Array.isArray(task?.timeline) ? task.timeline : []
  if (rawTimeline.length <= 1) return rawTimeline

  const hasSchedulerCompleted = rawTimeline.some(
    (item) => String(item?.event_type ?? '').trim().toUpperCase() === 'SCHEDULE_TASK_COMPLETED'
  )
  const filteredTimeline = hasSchedulerCompleted
    ? rawTimeline.filter((item) => {
        const eventType = String(item?.event_type ?? '').trim().toUpperCase()
        if (eventType !== 'TASK_FINISHED' && eventType !== 'SCHEDULE_TASK_EXECUTION_FINISHED') {
          return true
        }

        const itemTaskId = String(item?.task_id ?? task?.task_id ?? '').trim()
        return !rawTimeline.some((candidate) => {
          const candidateType = String(candidate?.event_type ?? '').trim().toUpperCase()
          if (candidateType !== 'SCHEDULE_TASK_COMPLETED') return false
          if (!itemTaskId) return true
          const candidateTaskId = String(candidate?.task_id ?? task?.task_id ?? '').trim()
          return candidateTaskId === '' || candidateTaskId === itemTaskId
        })
      })
    : rawTimeline

  const dedupedTimeline: SchedulerTaskTimelineItem[] = []
  const seenSignatures = new Set<string>()
  for (const item of filteredTimeline) {
    const signature = [
      String(item?.event_type ?? '').trim().toUpperCase(),
      String(item?.at ?? '').trim(),
      String(item?.task_id ?? task?.task_id ?? '').trim(),
      String(item?.correlation_id ?? '').trim(),
      String(item?.reason_code ?? '').trim().toLowerCase(),
      String(item?.error_code ?? '').trim().toLowerCase(),
      String(item?.decision ?? '').trim().toLowerCase(),
      String(item?.run_mode ?? '').trim().toLowerCase(),
      String(item?.node_uid ?? '').trim(),
      String(item?.channel ?? '').trim(),
      String(item?.cmd ?? '').trim(),
      String(item?.status ?? '').trim().toLowerCase(),
    ].join('|')

    if (seenSignatures.has(signature)) {
      continue
    }

    seenSignatures.add(signature)
    dedupedTimeline.push(item)
  }

  return dedupedTimeline
}

export function schedulerTaskDecisionLabel(decision: string | null | undefined): string {
  const normalized = String(decision ?? '').toLowerCase()
  if (normalized === 'run' || normalized === 'execute') return 'Выполнить'
  if (normalized === 'skip') return 'Пропустить'
  if (normalized === 'retry') return 'Повторить'
  if (normalized === 'fail') return 'Завершить с ошибкой'
  return decision ? String(decision) : '-'
}

export function schedulerTaskReasonLabel(reasonCode: string | null | undefined, reasonText?: string | null): string {
  const normalized = String(reasonCode ?? '').trim().toLowerCase()
  if (!normalized) return reasonText ? String(reasonText) : '-'

  const reasonMap: Record<string, string> = {
    already_running: 'Операция уже выполняется',
    outside_window: 'Задача вызвана вне окна выполнения',
    safety_blocked: 'Выполнение заблокировано safety-политикой',
    target_already_met: 'Целевое состояние уже достигнуто',
    nodes_unavailable: 'Недоступны обязательные ноды',
    low_water: 'Недостаточный уровень воды/раствора',
    climate_external_nodes_unavailable: 'Внешние climate-ноды недоступны, включён fallback',
    irrigation_required: 'Требуется выполнение полива',
    task_due_deadline_exceeded: 'Задача отклонена: пропущен дедлайн due_at',
    task_expired: 'Задача просрочена: превышен expires_at',
    command_bus_unavailable: 'CommandBus недоступен',
    execution_exception: 'Исключение во время исполнения',
    task_execution_failed: 'Исполнение завершилось с ошибкой',
    required_nodes_checked: 'Проверка обязательных нод выполнена',
    tank_level_checked: 'Проверка уровня бака выполнена',
    tank_refill_required: 'Требуется наполнение бака',
    tank_refill_started: 'Наполнение бака запущено',
    automation_control_mode_updated: 'Режим управления автоматикой обновлён',
    manual_step_requested: 'Ручной шаг запрошен',
    manual_step_executed: 'Ручной шаг выполнен',
    manual_step_failed: 'Ручной шаг завершился ошибкой',
    manual_step_command_plan_missing: 'Не найден command plan для ручного шага',
    manual_step_unsupported: 'Неподдерживаемый ручной шаг',
    manual_step_forbidden_in_auto_mode: 'Ручной шаг запрещён в auto-режиме',
    manual_step_topology_not_supported: 'Ручной шаг поддерживается только для 2-баковой топологии',
    tank_refill_in_progress: 'Наполнение бака в процессе',
    tank_refill_completed: 'Наполнение бака завершено',
    tank_refill_not_required: 'Наполнение бака не требуется',
    cycle_start_blocked_nodes_unavailable: 'Старт цикла заблокирован: недоступны обязательные ноды',
    cycle_start_tank_level_unavailable: 'Старт цикла заблокирован: нет данных уровня бака',
    cycle_start_tank_level_stale: 'Старт цикла заблокирован: телеметрия уровня бака устарела',
    cycle_start_refill_timeout: 'Таймаут наполнения бака',
    cycle_start_refill_command_failed: 'Ошибка отправки команды наполнения бака',
    cycle_start_self_task_enqueue_failed: 'Не удалось запланировать отложенную проверку',
    online_correction_failed: 'Online-коррекция в поливе не достигла целевых параметров',
    tank_to_tank_correction_started: 'Запущена баковая коррекция (tank-to-tank)',
    clean_fill_started: 'Запущено наполнение бака чистой воды',
    clean_fill_in_progress: 'Наполнение бака чистой воды продолжается',
    clean_fill_completed: 'Наполнение бака чистой воды завершено',
    clean_fill_timeout: 'Таймаут наполнения бака чистой воды',
    clean_fill_retry_started: 'Запущен повторный цикл наполнения бака чистой воды',
    solution_fill_started: 'Запущено наполнение бака рабочего раствора',
    solution_fill_in_progress: 'Наполнение бака рабочего раствора продолжается',
    solution_fill_completed: 'Наполнение бака рабочего раствора завершено',
    solution_fill_timeout: 'Таймаут наполнения бака рабочего раствора',
    prepare_recirculation_started: 'Запущена рециркуляция подготовки раствора',
    prepare_targets_reached: 'Подготовка раствора достигла целевых EC/pH',
    prepare_targets_not_reached: 'Подготовка раствора не достигла цели до таймаута',
    wind_blocked: 'Вентиляция заблокирована: превышен порог скорости ветра',
    outside_temp_blocked: 'Вентиляция заблокирована: наружная температура ниже порога',
    irrigation_recovery_started: 'Запущен recovery-контур полива',
    irrigation_recovery_recovered: 'Recovery-контур полива достиг цели',
    irrigation_recovery_failed: 'Recovery-контур полива завершился неуспешно',
    irrigation_recovery_degraded: 'Recovery-контур завершён в degraded tolerance',
    irrigation_correction_attempts_exhausted_continue_irrigation: 'Лимит коррекций исчерпан, полив продолжается по расписанию',
    manual_ack_required_after_retries: 'Требуется ручное подтверждение после автопопыток',
    irr_state_unavailable: 'Снимок состояния irr-ноды недоступен',
    irr_state_stale: 'Снимок состояния irr-ноды устарел',
    irr_state_mismatch: 'Состояние irr-ноды не совпадает с ожидаемым',
    lighting_already_in_target_state: 'Свет уже в целевом состоянии',
  }
  if (reasonMap[normalized]) return reasonMap[normalized]
  if (normalized.endsWith('_not_required')) return 'Действие не требуется'
  if (normalized.endsWith('_required')) return 'Действие требуется'
  if (reasonText && String(reasonText).trim() !== '') return String(reasonText)
  return 'Неизвестная причина'
}

export function schedulerTaskErrorLabel(errorCode: string | null | undefined, errorText?: string | null): string {
  const normalized = String(errorCode ?? '').trim().toLowerCase()
  if (!normalized) return errorText ? String(errorText) : '-'

  const errorMap: Record<string, string> = {
    task_due_deadline_exceeded: 'Превышен дедлайн due_at',
    task_expired: 'Превышен срок expires_at',
    command_publish_failed: 'Ошибка отправки команды',
    command_send_failed: 'Команда не отправлена',
    command_timeout: 'Таймаут ожидания DONE от ноды',
    command_error: 'Нода вернула ошибку',
    command_invalid: 'Нода отклонила команду',
    command_busy: 'Нода занята',
    command_no_effect: 'Нода не подтвердила выполнение команды',
    command_tracker_unavailable: 'Невозможно подтвердить DONE: tracker недоступен',
    command_effect_not_confirmed: 'Нода не подтвердила DONE',
    mapping_not_found: 'Конфигурация команды не найдена',
    no_online_nodes: 'Нет online-нод для выполнения',
    cycle_start_required_nodes_unavailable: 'Недоступны обязательные ноды для старта цикла',
    cycle_start_tank_level_unavailable: 'Нет телеметрии уровня бака',
    cycle_start_tank_level_stale: 'Телеметрия бака устарела',
    cycle_start_refill_timeout: 'Таймаут наполнения бака',
    cycle_start_refill_node_not_found: 'Не найден узел для наполнения бака',
    cycle_start_refill_command_failed: 'Команда наполнения бака не отправлена',
    cycle_start_self_task_enqueue_failed: 'Не удалось запланировать self-task',
    clean_tank_not_filled_timeout: 'Таймаут наполнения бака чистой воды',
    solution_tank_not_filled_timeout: 'Таймаут наполнения бака рабочего раствора',
    two_tank_level_unavailable: 'Нет данных датчиков уровня для 2-баковой схемы',
    two_tank_level_stale: 'Телеметрия датчиков уровня для 2-баковой схемы устарела',
    two_tank_command_failed: 'Не удалось отправить команды для 2-баковой схемы',
    two_tank_enqueue_failed: 'Не удалось запланировать self-task для 2-баковой схемы',
    two_tank_channel_not_found: 'Не найден канал для команды 2-баковой схемы',
    two_tank_irr_state_unavailable: 'Нет snapshot состояния irr-ноды для критической проверки',
    two_tank_irr_state_stale: 'Snapshot состояния irr-ноды устарел для критической проверки',
    two_tank_irr_state_mismatch: 'Состояние irr-ноды не совпадает с ожидаемым на critical этапе',
    sensor_state_inconsistent: 'Обнаружена несовместимая комбинация датчиков уровня',
    prepare_npk_ph_target_not_reached: 'Подготовка раствора (NPK + pH) не достигла цели',
    irrigation_recovery_attempts_exceeded: 'Превышено число попыток recovery-контурa полива',
    command_bus_unavailable: 'CommandBus недоступен',
    execution_exception: 'Исключение во время выполнения задачи',
    task_execution_failed: 'Задача завершилась с ошибкой',
  }
  if (errorMap[normalized]) return errorMap[normalized]
  if (errorText && String(errorText).trim() !== '') return String(errorText)
  return 'Неизвестная ошибка'
}

export function schedulerTaskDoneMeta(task: SchedulerTaskStatus | null | undefined): SchedulerTaskDoneMeta {
  if (!task) {
    return { variant: 'secondary', label: 'DONE не определен', hint: 'Нет данных task status' }
  }

  const status = normalizeTargetSchedulerStatus(task.status)
  const actionRequired = normalizeOptionalBool(task.action_required ?? task.result?.action_required)
  const submitted = resolveTaskCommandSubmitted(task)
  const effectConfirmed = resolveTaskCommandEffectConfirmed(task)
  const commandsTotal = resolveTaskCommandsTotal(task)
  const commandsConfirmed = resolveTaskCommandsEffectConfirmed(task)

  if (actionRequired === false || String(task.decision ?? task.result?.decision ?? '').toLowerCase() === 'skip') {
    return {
      variant: 'info',
      label: 'Команды не требовались',
      hint: 'Decision layer вернул skip/action_required=false',
    }
  }

  if (status !== 'completed') {
    return {
      variant: 'secondary',
      label: 'Ожидание terminal DONE',
      hint: 'Подтверждение эффекта доступно после terminal статуса',
    }
  }

  if (commandsTotal === 0) {
    return {
      variant: 'info',
      label: 'Команды не отправлялись',
      hint: 'Для этой задачи commands_total=0, подтверждение DONE не требуется',
    }
  }

  if (submitted === false) {
    return {
      variant: 'danger',
      label: 'Команда не отправлена',
      hint: 'command_submitted=false (SEND_FAILED или transport failure)',
    }
  }

  if (effectConfirmed === true) {
    if (commandsTotal !== null && commandsConfirmed !== null) {
      return {
        variant: 'success',
        label: 'DONE подтвержден',
        hint: `Подтверждено ${commandsConfirmed}/${commandsTotal} команд`,
      }
    }
    return {
      variant: 'success',
      label: 'DONE подтвержден',
      hint: 'Нода вернула terminal статус DONE',
    }
  }

  return {
    variant: 'danger',
    label: 'DONE не подтвержден',
    hint: 'Команда завершилась неуспешным terminal-статусом или подтверждение отсутствует',
  }
}

export function formatSchedulerDateTime(value: string | null): string {
  const parsed = parseIsoDate(value)
  if (!parsed) return '-'
  return parsed.toLocaleString('ru-RU')
}

export function schedulerTaskSlaMeta(task: SchedulerTaskStatus | null | undefined): SchedulerTaskSlaMeta {
  if (!task) {
    return { variant: 'secondary', label: 'SLA не определен', hint: 'Нет данных задачи' }
  }

  const status = normalizeTargetSchedulerStatus(task.status)
  const dueAt = parseIsoDate(task.due_at)
  const expiresAt = parseIsoDate(task.expires_at)
  const updatedAt = parseIsoDate(task.updated_at)
  const scheduledFor = parseIsoDate(task.scheduled_for)
  const now = new Date()

  const windowParts: string[] = []
  if (scheduledFor) windowParts.push(`scheduled: ${formatSchedulerDateTime(task.scheduled_for ?? null)}`)
  if (dueAt) windowParts.push(`due: ${formatSchedulerDateTime(task.due_at ?? null)}`)
  if (expiresAt) windowParts.push(`expires: ${formatSchedulerDateTime(task.expires_at ?? null)}`)
  const windowHint = windowParts.join(' · ')

  if (!dueAt && !expiresAt) {
    return {
      variant: 'secondary',
      label: 'SLA не задан',
      hint: windowHint || 'В payload задачи нет due_at/expires_at',
    }
  }

  if (status === 'expired') {
    return {
      variant: 'danger',
      label: 'SLA нарушен: expires_at',
      hint: windowHint || 'Задача завершена статусом expired',
    }
  }

  if (status === 'rejected') {
    return {
      variant: 'danger',
      label: 'SLA нарушен: due_at',
      hint: windowHint || 'Задача завершена статусом rejected',
    }
  }

  if (status === 'completed') {
    if (dueAt && updatedAt && updatedAt.getTime() > dueAt.getTime()) {
      return {
        variant: 'warning',
        label: 'SLA пограничный: завершена после due_at',
        hint: windowHint || 'Проверьте интервал dispatch->execute',
      }
    }
    return {
      variant: 'success',
      label: 'SLA выполнен',
      hint: windowHint || 'Задача завершена в SLA-окне',
    }
  }

  if (status === 'failed') {
    return {
      variant: 'danger',
      label: 'SLA риск: task failed',
      hint: windowHint || 'Задача завершена ошибкой',
    }
  }

  if (expiresAt && now.getTime() > expiresAt.getTime()) {
    return {
      variant: 'danger',
      label: 'SLA нарушен: expires_at',
      hint: windowHint || 'Текущее время больше expires_at',
    }
  }

  if (dueAt && now.getTime() > dueAt.getTime()) {
    return {
      variant: 'danger',
      label: 'SLA нарушен: due_at',
      hint: windowHint || 'Текущее время больше due_at',
    }
  }

  if (dueAt) {
    const msLeft = dueAt.getTime() - now.getTime()
    if (msLeft <= 30_000) {
      return {
        variant: 'warning',
        label: 'SLA: дедлайн близко',
        hint: `До due_at: ${formatRelativeMs(msLeft)}${windowHint ? ` · ${windowHint}` : ''}`,
      }
    }
    return {
      variant: 'info',
      label: 'SLA-окно активно',
      hint: `До due_at: ${formatRelativeMs(msLeft)}${windowHint ? ` · ${windowHint}` : ''}`,
    }
  }

  return {
    variant: 'info',
    label: 'SLA-окно активно',
    hint: windowHint || 'Ожидание исполнения задачи',
  }
}

export function taskMatchesPreset(task: SchedulerTaskStatus, preset: SchedulerTaskPreset): boolean {
  if (preset === 'all') return true

  const status = normalizeTargetSchedulerStatus(task.status)
  const reasonCode = String(task.reason_code ?? task.result?.reason_code ?? '').toLowerCase()
  const errorCode = String(task.error_code ?? task.result?.error_code ?? '').toLowerCase()
  const effectConfirmed = resolveTaskCommandEffectConfirmed(task)
  const commandsTotal = resolveTaskCommandsTotal(task)
  const actionRequired = normalizeOptionalBool(task.action_required ?? task.result?.action_required)

  if (preset === 'failed') {
    return status === 'failed' || status === 'rejected' || status === 'expired'
  }

  if (preset === 'deadline') {
    if (status === 'rejected' || status === 'expired') return true
    return (
      reasonCode === 'task_due_deadline_exceeded' ||
      reasonCode === 'task_expired' ||
      errorCode === 'task_due_deadline_exceeded' ||
      errorCode === 'task_expired'
    )
  }

  if (preset === 'done_confirmed') {
    return status === 'completed' && commandsTotal !== 0 && effectConfirmed === true
  }

  if (preset === 'done_unconfirmed') {
    return status === 'completed' && commandsTotal !== 0 && actionRequired !== false && effectConfirmed !== true
  }

  return true
}

export function taskMatchesSearch(task: SchedulerTaskStatus, rawQuery: string): boolean {
  const query = rawQuery.trim().toLowerCase()
  if (!query) return true

  const haystack = [
    task.task_id,
    task.task_type,
    task.status,
    task.decision,
    task.reason_code,
    task.error_code,
    task.reason,
    task.error,
  ]
    .map((item) => String(item ?? '').toLowerCase())
    .join(' ')

  return haystack.includes(query)
}

import { computed, ref } from 'vue'
import { logger } from '@/utils/logger'
import { resolveHumanErrorMessage } from '@/utils/errorCatalog'
import { api } from '@/services/api'
import type { ToastHandler } from '@/services/api'
import type { ZoneAutomationTabProps } from '@/composables/zoneAutomationTypes'
import type { AutomationState } from '@/types/Automation'
import type {
  ExecutionFailureSummary,
  ExecutionResponse,
  ExecutionRun,
  PlanLane,
  PlanWindow,
  SchedulerDiagnostics,
  SchedulerDiagnosticsResponse,
  ScheduleWorkspace,
  ScheduleWorkspaceResponse,
} from '@/composables/zoneScheduleWorkspaceTypes'

export interface ZoneScheduleWorkspaceDeps {
  showToast: ToastHandler
}

export interface TimelineDisplayItem {
  key: string
  event_type: string
  at: string | null
  label: string
  detail: string | null
  grouped?: boolean
  _count?: number
}

interface DecisionDescriptorInput {
  outcome?: string | null
  degraded?: boolean | null
  reasonCode?: string | null
  reason?: string | null
  errorCode?: string | null
  details?: Record<string, unknown> | null
}

export function useZoneScheduleWorkspace(props: ZoneAutomationTabProps, _deps: ZoneScheduleWorkspaceDeps) {
  const horizon = ref<'24h' | '7d'>('24h')
  const workspace = ref<ScheduleWorkspace | null>(null)
  const automationState = ref<AutomationState | null>(null)
  const selectedExecution = ref<ExecutionRun | null>(null)
  const diagnostics = ref<SchedulerDiagnostics | null>(null)
  const loading = ref(false)
  const detailLoading = ref(false)
  const diagnosticsLoading = ref(false)
  const error = ref<string | null>(null)
  const diagnosticsError = ref<string | null>(null)
  const updatedAt = ref<string | null>(null)

  let pollTimer: ReturnType<typeof setTimeout> | null = null

  /**
   * `apiGet` уже снимает status-envelope `{status, data: ...}` через `extractData`,
   * поэтому в норме сюда приходит уже inner-payload. Но если бэкенд (или тест-mock)
   * вдруг вернул wrapped-форму — корректно вытащим вложенный `.data`.
   */
  function unwrapEnvelope<T>(response: T | { data?: T } | null | undefined): T | null {
    if (response === null || response === undefined) return null
    if (
      typeof response === 'object'
      && response !== null
      && 'data' in (response as Record<string, unknown>)
      && (response as { data?: T }).data !== undefined
      && (response as { data?: T }).data !== null
    ) {
      return (response as { data: T }).data
    }
    return response as T
  }

  const lanes = computed<PlanLane[]>(() => workspace.value?.plan?.lanes ?? [])
  const windows = computed<PlanWindow[]>(() => workspace.value?.plan?.windows ?? [])
  const recentRuns = computed<ExecutionRun[]>(() => workspace.value?.execution?.recent_runs ?? [])
  const activeRun = computed<ExecutionRun | null>(() => workspace.value?.execution?.active_run ?? null)
  const latestFailure = computed<ExecutionFailureSummary | null>(() => workspace.value?.execution?.latest_failure ?? null)
  const executionCounters = computed(() => workspace.value?.execution?.counters ?? {
    active: 0,
    completed_24h: 0,
    failed_24h: 0,
  })
  const executableTaskTypes = computed<string[]>(() => workspace.value?.capabilities?.executable_task_types ?? [])
  const nextExecutableWindows = computed<PlanWindow[]>(() => {
    const executable = new Set(executableTaskTypes.value)

    return windows.value
      .filter((window) => executable.has(String(window.task_type ?? '').trim()))
      .slice(0, 3)
  })
  const configOnlyLanes = computed<PlanLane[]>(() => lanes.value.filter((lane) => !lane.executable))
  const activeProcessLabels = computed<string[]>(() => {
    const current = automationState.value?.active_processes
    if (!current) return []

    const labels: string[] = []
    if (current.pump_in) labels.push('Насос набора')
    if (current.circulation_pump) labels.push('Рециркуляционный насос')
    if (current.ph_correction) labels.push('Коррекция pH')
    if (current.ec_correction) labels.push('Коррекция EC')

    return labels
  })
  const attentionItems = computed(() => {
    const items: Array<{ tone: 'danger' | 'warning' | 'info', title: string, detail: string | null }> = []

    if (latestFailure.value) {
      const failureMessage = resolveHumanErrorMessage({
        code: latestFailure.value.error_code,
        message: latestFailure.value.error_message,
        humanMessage: latestFailure.value.human_error_message,
      }, 'Неизвестная ошибка') || 'Неизвестная ошибка'
      const failureDetail = latestFailure.value.at
        ? `Зафиксировано ${formatDateTime(latestFailure.value.at)}`
        : null
      items.push({
        tone: 'danger',
        title: `Последняя ошибка: ${laneLabel(latestFailure.value.task_type)} · ${failureMessage}`,
        detail: failureDetail,
      })
    }

    const runtime = String(workspace.value?.control?.automation_runtime ?? '').trim().toLowerCase()
    if (runtime === 'ae3') {
      const caps = workspace.value?.capabilities
      const nonExecRaw = caps?.non_executable_planned_task_types
      const hasTypedList = Array.isArray(nonExecRaw)
      const nonExec = hasTypedList ? nonExecRaw : []
      const showLimit = (hasTypedList && nonExec.length > 0) || (!hasTypedList && configOnlyLanes.value.length > 0)

      if (showLimit) {
        const typesHint = nonExec.length > 0 ? nonExec.join(', ') : null
        const autoHint = executableTaskTypes.value.length > 0
          ? `Сейчас автодиспатч scheduler покрывает: ${executableTaskTypes.value.join(', ')}.`
          : ''
        items.push({
          tone: 'warning',
          title: 'Не все типы расписания запускаются автоматически (AE3)',
          detail: typesHint
            ? `${autoHint ? `${autoHint} ` : ''}Не диспатчатся из scheduler: ${typesHint}. Окна в графике отражают конфигурацию effective targets.`.trim()
            : `${autoHint ? `${autoHint} ` : ''}Часть дорожек в графике относится к подсистемам без автоматического dispatch из этого планировщика (см. подписи дорожек).`.trim(),
        })
      }
    }

    if (executionCounters.value.failed_24h > 0) {
      const latestFailureCode = asNonEmptyString(latestFailure.value?.error_code)
      items.push({
        tone: latestFailure.value ? 'warning' : 'danger',
        title: `Ошибок за 24ч: ${executionCounters.value.failed_24h}`,
        detail: latestFailureCode === 'start_cycle_zone_busy'
          ? 'Повторные старты полива отклоняются, пока зона занята активным intent.'
          : 'Есть неуспешные scheduler/AE исполнения, которые требуют внимания.',
      })
    }

    if (activeRun.value && automationState.value?.state_label) {
      items.push({
        tone: 'info',
        title: `Сейчас выполняется: ${automationState.value.state_label}`,
        detail: activeRun.value.current_stage || automationState.value.current_stage || null,
      })
    }

    return items.slice(0, 4)
  })
  const condensedTimeline = computed<TimelineDisplayItem[]>(() => collapseTimeline(selectedExecution.value?.timeline ?? []))

  const laneWindows = computed<Record<string, PlanWindow[]>>(() => {
    const grouped: Record<string, PlanWindow[]> = {}
    for (const window of windows.value) {
      const key = String(window.task_type ?? '').trim()
      if (key === '') continue
      if (!grouped[key]) {
        grouped[key] = []
      }
      grouped[key].push(window)
    }
    return grouped
  })

  async function fetchWorkspace(): Promise<void> {
    if (!props.zoneId) {
      workspace.value = null
      selectedExecution.value = null
      updatedAt.value = null
      loading.value = false
      return
    }

    loading.value = true
    error.value = null

    try {
      const response = await api.zones.scheduleWorkspace<ScheduleWorkspace | ScheduleWorkspaceResponse>(
        props.zoneId,
        { horizon: horizon.value },
      )
      workspace.value = unwrapEnvelope<ScheduleWorkspace>(response)
      updatedAt.value = new Date().toISOString()

      const nextSelectedExecutionId = selectedExecution.value?.execution_id?.trim()
      if (nextSelectedExecutionId) {
        await fetchExecution(nextSelectedExecutionId, { silent: true })
      } else if (activeRun.value?.execution_id) {
        await fetchExecution(activeRun.value.execution_id, { silent: true })
      } else if (recentRuns.value[0]?.execution_id) {
        await fetchExecution(recentRuns.value[0].execution_id, { silent: true })
      } else {
        selectedExecution.value = null
      }
    } catch (fetchError) {
      logger.warn('[ZoneSchedulerTab] Failed to fetch schedule workspace', { fetchError, zoneId: props.zoneId })
      error.value = 'Не удалось получить workspace планировщика.'
    } finally {
      loading.value = false
    }
  }

  async function fetchAutomationState(options?: { silent?: boolean }): Promise<void> {
    if (!props.zoneId) {
      automationState.value = null
      return
    }

    try {
      const response = await api.zones.getState<AutomationState | { data?: AutomationState }>(props.zoneId)
      automationState.value = unwrapEnvelope<AutomationState>(response)
    } catch (fetchError) {
      logger.warn('[ZoneSchedulerTab] Failed to fetch automation state', { fetchError, zoneId: props.zoneId })
      if (!options?.silent && !error.value) {
        error.value = 'Не удалось получить состояние зоны.'
      }
    }
  }

  async function fetchExecution(executionId: string, options?: { silent?: boolean }): Promise<void> {
    const normalizedExecutionId = String(executionId ?? '').trim()
    if (!props.zoneId || normalizedExecutionId === '') {
      return
    }

    if (!options?.silent) {
      detailLoading.value = true
    }

    try {
      const response = await api.zones.getExecution<ExecutionRun | ExecutionResponse>(props.zoneId, normalizedExecutionId)
      selectedExecution.value = unwrapEnvelope<ExecutionRun>(response)
    } catch (fetchError) {
      logger.warn('[ZoneSchedulerTab] Failed to fetch execution detail', { fetchError, zoneId: props.zoneId, executionId: normalizedExecutionId })
      if (!options?.silent) {
        error.value = 'Не удалось получить детали выполнения.'
      }
    } finally {
      if (!options?.silent) {
        detailLoading.value = false
      }
    }
  }

  async function fetchDiagnostics(options?: { silent?: boolean }): Promise<void> {
    if (!props.zoneId) {
      diagnostics.value = null
      diagnosticsError.value = null
      diagnosticsLoading.value = false
      return
    }

    if (!options?.silent) {
      diagnosticsLoading.value = true
    }

    diagnosticsError.value = null

    try {
      const response = await api.zones.schedulerDiagnostics<SchedulerDiagnostics | SchedulerDiagnosticsResponse>(props.zoneId)
      diagnostics.value = unwrapEnvelope<SchedulerDiagnostics>(response)
    } catch (fetchError) {
      logger.warn('[ZoneSchedulerTab] Failed to fetch scheduler diagnostics', { fetchError, zoneId: props.zoneId })
      diagnostics.value = null
      diagnosticsError.value = 'Не удалось получить инженерную диагностику.'
    } finally {
      if (!options?.silent) {
        diagnosticsLoading.value = false
      }
    }
  }

  function setHorizon(nextHorizon: '24h' | '7d'): void {
    horizon.value = nextHorizon
  }

  function clearDiagnostics(): void {
    diagnostics.value = null
    diagnosticsError.value = null
    diagnosticsLoading.value = false
  }

  function clearPollTimer(): void {
    if (pollTimer !== null) {
      clearTimeout(pollTimer)
      pollTimer = null
    }
  }

  function schedulePoll(): void {
    clearPollTimer()
    const delay = activeRun.value ? 3000 : 15000
    pollTimer = window.setTimeout(() => {
      void pollCycle()
    }, delay)
  }

  async function pollCycle(): Promise<void> {
    await Promise.all([
      fetchWorkspace(),
      fetchAutomationState({ silent: true }),
    ])
    if (typeof document !== 'undefined' && document.visibilityState === 'hidden') {
      return
    }
    schedulePoll()
  }

  function handleVisibilityChange(): void {
    if (typeof document === 'undefined') return
    if (document.visibilityState === 'visible') {
      void pollCycle()
      return
    }
    clearPollTimer()
  }

  function formatDateTime(value: string | null | undefined): string {
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

  function formatRelativeTrigger(value: string | null | undefined): string {
    if (!value) return '—'
    const parsed = new Date(value)
    if (Number.isNaN(parsed.getTime())) return '—'
    const diffMinutes = Math.round((parsed.getTime() - Date.now()) / 60000)
    if (diffMinutes <= 0) return 'сейчас'
    if (diffMinutes < 60) return `через ${diffMinutes} мин`
    const diffHours = Math.floor(diffMinutes / 60)
    const remainMinutes = diffMinutes % 60
    if (remainMinutes === 0) return `через ${diffHours} ч`
    return `через ${diffHours} ч ${remainMinutes} мин`
  }

  function statusVariant(status: string | null | undefined): 'success' | 'warning' | 'danger' | 'info' | 'secondary' {
    const normalized = String(status ?? '').trim().toLowerCase()
    if (normalized === 'completed') return 'success'
    if (normalized === 'running' || normalized === 'accepted') return 'info'
    if (normalized === 'failed' || normalized === 'cancelled') return 'danger'
    return 'secondary'
  }

  function controlModeLabel(controlMode: string | null | undefined): string {
    const normalized = String(controlMode ?? '').trim().toLowerCase()
    if (normalized === 'manual') return 'ручной'
    if (normalized === 'semi') return 'полуавто'
    return 'авто'
  }

  function laneLabel(taskType: string | null | undefined): string {
    const normalized = String(taskType ?? '').trim().toLowerCase()
    if (normalized === 'irrigation') return 'Полив'
    if (normalized === 'lighting') return 'Свет'
    if (normalized === 'climate') return 'Климат'
    if (normalized === 'solution_change') return 'Смена раствора'
    if (normalized === 'diagnostics') return 'Диагностика'
    if (normalized === 'mist') return 'Туман'
    return normalized || '—'
  }

  function decisionLabel(outcome: string | null | undefined, degraded: boolean | null | undefined): string {
    const normalized = String(outcome ?? '').trim().toLowerCase()
    if (normalized === 'skip') return 'Пропуск'
    if (normalized === 'degraded_run' || (normalized === 'run' && degraded)) return 'Деградированный запуск'
    if (normalized === 'run') return 'Запуск'
    if (normalized === 'fail') return 'Сбой decision-controller'
    return normalized || 'Decision'
  }

  function statusLabel(status: string | null | undefined): string {
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

  function modeLabel(mode: string | null | undefined): string {
    const normalized = String(mode ?? '').trim().toLowerCase()
    const labels: Record<string, string> = {
      time: 'по расписанию',
      smart: 'умный',
      force: 'принудительно',
      task: 'задача',
      manual: 'вручную',
      auto: 'авто',
    }
    return labels[normalized] ?? mode ?? '—'
  }

  function workflowStageLabel(stage: string | null | undefined): string | null {
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

  function eventTypeLabel(eventType: string | null | undefined): string {
    const raw = String(eventType ?? '').trim()
    const labels: Record<string, string> = {
      // Задачи AE
      AE_TASK_STARTED: 'Переход стадии',
      AE_TASK_COMPLETED: 'Задача завершена',
      AE_TASK_FAILED: 'Ошибка задачи',
      // Коррекция (общие)
      CORRECTION_OBSERVATION_EVALUATED: 'Оценка наблюдения',
      CORRECTION_DECISION_MADE: 'Решение о коррекции',
      CORRECTION_SENSOR_MODE_REACTIVATED: 'Реактивация датчика',
      CORRECTION_WINDOW_OPENED: 'Окно коррекции открыто',
      CORRECTION_WINDOW_CLOSED: 'Окно коррекции закрыто',
      CORRECTION_COMPLETE: 'Коррекция завершена',
      CORRECTION_CHECK: 'Проверка коррекции',
      CORRECTION_STANDALONE: 'Автономная коррекция',
      CORRECTION_EXHAUSTED: 'Попытки коррекции исчерпаны',
      CORRECTION_NO_EFFECT: 'Коррекция без эффекта',
      CORRECTION_ACTION_DEFERRED: 'Коррекция отложена',
      CORRECTION_INTERRUPTED_STAGE_COMPLETE: 'Коррекция прервана',
      CORRECTION_LIMIT_POLICY_APPLIED: 'Лимит коррекций',
      CORRECTION_ATTEMPT_CAP_IGNORED: 'Лимит попыток',
      CORRECTION_PLANNER_CONFIG_INVALID: 'Ошибка конфигурации',
      // Коррекция (пропуски)
      CORRECTION_SKIPPED: 'Коррекция пропущена',
      CORRECTION_SKIPPED_COOLDOWN: 'Пропуск: откат',
      CORRECTION_SKIPPED_DEAD_ZONE: 'Пропуск: мёртвая зона',
      CORRECTION_SKIPPED_DOSE_DISCARDED: 'Пропуск: доза сброшена',
      CORRECTION_SKIPPED_FRESHNESS: 'Пропуск: устаревшие данные',
      CORRECTION_SKIPPED_WATER_LEVEL: 'Пропуск: уровень воды',
      CORRECTION_SKIPPED_WINDOW_NOT_READY: 'Пропуск: окно не готово',
      // pH / EC
      PH_CORRECTED: 'pH скорректирован',
      EC_CORRECTED: 'EC скорректирован',
      EC_DOSING: 'Дозирование EC',
      // Полив
      IRRIGATION_APPROVED: 'Полив разрешён',
      IRRIGATION_SKIPPED: 'Полив пропущен',
      IRRIGATION_STARTED: 'Полив начат',
      IRRIGATION_STOPPED: 'Полив остановлен',
      IRRIGATION_READY: 'Полив готов',
      IRRIGATION_DECISION_EVALUATED: 'Решение о поливе',
      IRRIGATION_DECISION_SNAPSHOT_LOCKED: 'Параметры полива зафиксированы',
      IRRIGATION_EC_MULTI_DOSE: 'Мульти-доза EC',
      IRRIGATION_CORRECTION_STARTED: 'Коррекция полива начата',
      IRRIGATION_CORRECTION_COMPLETED: 'Коррекция полива завершена',
      IRRIGATION_LOW_SOLUTION: 'Низкий уровень раствора',
      IRRIGATION_SOLUTION_LOW: 'Раствор на минимуме',
      IRRIGATION_SOLUTION_MIN_DETECTED: 'Обнаружен минимум раствора',
      IRRIGATION_WAIT_READY_TIMEOUT: 'Таймаут ожидания готовности',
      IRRIGATION_RECOVERY_STARTED: 'Восстановление начато',
      IRRIGATION_RECOVERY_COMPLETED: 'Восстановление завершено',
      // Дозы и команды
      DOSE_DISPATCHED: 'Доза отправлена',
      COMMAND_SENT: 'Команда отправлена',
      COMMAND_ACKNOWLEDGED: 'Команда подтверждена',
      COMMAND_RESPONSE_RECEIVED: 'Ответ на команду',
      COMMAND_TIMEOUT: 'Таймаут команды',
      // Датчики и аварии
      LEVEL_SWITCH_CHANGED: 'Датчик уровня изменился',
      WATER_LEVEL_SWITCH: 'Датчик уровня воды',
      EMERGENCY_STOP_ACTIVATED: 'Аварийная остановка',
      // Освещение
      LIGHTING_STARTED: 'Освещение включено',
      LIGHTING_COMPLETED: 'Освещение выключено',
      // Прочее
      ZONE_EVENT: 'Событие зоны',
      CORRECTION_FAILED: 'Ошибка коррекции',
    }
    return labels[raw] ?? raw.replace(/_/g, ' ').toLowerCase()
  }

  function decisionReasonLabel(reasonCode: string | null | undefined): string | null {
    const normalized = String(reasonCode ?? '').trim().toLowerCase()
    if (normalized === '') return null

    const labels: Record<string, string> = {
      irrigation_task_strategy_run: 'Стратегия task разрешила запуск по расписанию.',
      irrigation_force_mode: 'Force path обходит decision-controller.',
      smart_soil_target_missing: 'Целевой диапазон soil moisture не настроен, поэтому используется degraded path.',
      smart_soil_telemetry_missing_or_stale: 'Нет свежей soil telemetry, поэтому используется degraded path.',
      smart_soil_below_min: 'Средняя влажность ниже нижней границы.',
      smart_soil_above_max: 'Средняя влажность выше верхней границы.',
      smart_soil_within_band: 'Средняя влажность уже внутри целевого диапазона.',
      irrigation_decision_strategy_unknown: 'Указана неизвестная стратегия decision-controller.',
    }

    return labels[normalized] ?? normalized.replace(/_/g, ' ')
  }

  function timelinePrimaryLabel(step: ExecutionRun['timeline'][number] | null | undefined): string {
    if (!step) return 'событие'

    const decision = asNonEmptyString(step.decision)
    if (decision) {
      return decisionLabel(decision, decision === 'degraded_run')
    }

    if (step.event_type === 'AE_TASK_STARTED') {
      const rawStage = asNonEmptyString(step.stage)
      return rawStage ? (workflowStageLabel(rawStage) ?? rawStage) : 'Переход стадии'
    }

    if (step.event_type === 'AE_TASK_FAILED') {
      return 'Ошибка выполнения'
    }

    const details = isRecord(step.details) ? step.details : null
    const humanErrorCode = resolveHumanErrorMessage({ code: step.error_code }, null)
    const candidates: Array<string | null | undefined> = [
      workflowStageLabel(step.reason_code),
      workflowStageLabel(asNonEmptyString(details?.stage)),
      workflowStageLabel(asNonEmptyString(details?.current_stage)),
      humanErrorCode,
      step.reason,
    ]

    for (const candidate of candidates) {
      const normalized = asNonEmptyString(candidate)
      if (normalized) return normalized
    }

    return 'событие'
  }

  function describeDecision(input: DecisionDescriptorInput): string | null {
    const details = isRecord(input.details) ? input.details : null
    const result = isRecord(details?.result) ? details.result : null
    const reasonLabel = decisionReasonLabel(input.reasonCode)
    const explicitReason = asNonEmptyString(input.reason)
    const errorCode = asNonEmptyString(input.errorCode)

    const infoParts: string[] = []
    if (reasonLabel) {
      infoParts.push(reasonLabel)
    }
    if (explicitReason && explicitReason !== reasonLabel) {
      infoParts.push(explicitReason)
    }

    const zoneAverage = readDecisionNumber(details, result, ['zone_average_pct'])
    if (zoneAverage !== null) {
      infoParts.push(`Средняя влажность ${zoneAverage.toFixed(1)}%.`)
    }

    const spreadPct = readDecisionNumber(details, result, ['spread_pct'])
    if (spreadPct !== null) {
      infoParts.push(`Разбег сенсоров ${spreadPct.toFixed(1)}%.`)
    }

    const sensorCount = readDecisionNumber(details, result, ['sensor_count'])
    const samples = readDecisionNumber(details, result, ['samples'])
    if (sensorCount !== null || samples !== null) {
      const telemetryBits: string[] = []
      if (sensorCount !== null) telemetryBits.push(`сенсоров ${Math.round(sensorCount)}`)
      if (samples !== null) telemetryBits.push(`замеров ${Math.round(samples)}`)
      infoParts.push(`Телеметрия: ${telemetryBits.join(', ')}.`)
    }

    if (readDecisionBool(details, result, ['spread_alert']) === true) {
      infoParts.push('Разбег сенсоров выше alert-порога.')
    }

    const requestedDurationSec = readDecisionNumber(details, result, ['requested_duration_sec'])
    if (requestedDurationSec !== null) {
      infoParts.push(`Запрошенная длительность ${Math.round(requestedDurationSec)} с.`)
    }

    const strategy = readDecisionString(details, result, ['strategy'])
    if (strategy) {
      infoParts.push(`Стратегия: ${strategy}.`)
    }

    if (!reasonLabel && errorCode) {
      const resolvedError = resolveHumanErrorMessage({ code: errorCode }, errorCode) || errorCode
      infoParts.push(resolvedError)
    }

    return infoParts.length > 0 ? infoParts.join(' ') : null
  }

  function collapseTimeline(items: ExecutionRun['timeline'] = []): TimelineDisplayItem[] {
    const result: TimelineDisplayItem[] = []

    for (const step of items) {
      const label = timelinePrimaryLabel(step)
      const detail = timelineDetail(step, label)
      const previous = result[result.length - 1]

      if (step.event_type === 'AE_TASK_STARTED' && previous?.event_type === 'AE_TASK_STARTED') {
        previous.grouped = true
        previous.at = step.at
        previous.label = previous.label === label ? label : `${previous.label} → ${label}`
        previous.detail = detail ?? previous.detail ?? 'Переходы стадий'
        continue
      }

      if (
        step.event_type === 'IRRIGATION_DECISION_SNAPSHOT_LOCKED' &&
        previous?.event_type === 'IRRIGATION_DECISION_SNAPSHOT_LOCKED'
      ) {
        const prevCount = previous._count ?? 1
        const newCount = prevCount + 1
        previous._count = newCount
        previous.grouped = true
        previous.at = step.at
        previous.detail = detail ?? previous.detail
        previous.label = `${label} ×${newCount}`
        continue
      }

      result.push({
        key: String(step.event_id ?? `${step.event_type}-${step.at ?? result.length}`),
        event_type: step.event_type,
        at: step.at,
        label,
        detail,
      })
    }

    return result.slice(-8)
  }

  function timelineDetail(step: ExecutionRun['timeline'][number] | null | undefined, label: string): string | null {
    if (!step) return null

    const details = isRecord(step.details) ? step.details : null

    // Специфичная обработка по event_type
    if (step.event_type === 'IRRIGATION_DECISION_SNAPSHOT_LOCKED') {
      const parts: string[] = []
      const strategy = asNonEmptyString(details?.strategy)
      if (strategy) parts.push(`Стратегия: ${modeLabel(strategy)}`)
      const phaseName = asNonEmptyString(details?.phase_name)
      if (phaseName) parts.push(`Фаза рецепта: ${phaseName}`)
      const bundleRevision = asNonEmptyString(details?.bundle_revision)
      if (bundleRevision) parts.push(`Ревизия: ${String(bundleRevision).slice(0, 12)}`)
      return parts.length > 0 ? parts.join(' · ') : 'Параметры полива зафиксированы'
    }

    if (step.event_type === 'IRRIGATION_DECISION_EVALUATED') {
      const outcome = asNonEmptyString(details?.outcome ?? step.decision)
      const degraded = details?.degraded === true
      const reasonCode = asNonEmptyString(details?.reason_code ?? step.reason_code)
      if (!outcome) return null
      const outcomeLabel = decisionLabel(outcome, degraded)
      return reasonCode ? `${outcomeLabel} · ${reasonCode}` : outcomeLabel
    }

    if (step.event_type === 'IRRIGATION_CORRECTION_COMPLETED') {
      const success = typeof details?.success === 'boolean' ? details.success : null
      if (success === true) return 'Коррекция достигла цели.'
      if (success === false) return 'Коррекция не достигла цели.'
      return null
    }

    if (step.event_type === 'IRRIGATION_EC_MULTI_DOSE') {
      const topology = asNonEmptyString(details?.topology)
      return topology ? `Топология: ${topology}` : null
    }

    // Общий путь: decision field → reason → reason_code → error_code
    const decision = asNonEmptyString(step.decision)
    if (decision) {
      return describeDecision({
        outcome: decision,
        degraded: decision === 'degraded_run',
        reasonCode: step.reason_code,
        reason: step.reason,
        errorCode: step.error_code,
        details: step.details,
      })
    }

    const reason = asNonEmptyString(step.reason)
    if (reason && reason !== label) return reason

    const reasonLabel = decisionReasonLabel(step.reason_code)
    if (reasonLabel && reasonLabel !== label) return reasonLabel

    const errorCode = asNonEmptyString(step.error_code)
    if (errorCode && errorCode !== label) {
      return resolveHumanErrorMessage({ code: errorCode }, errorCode) || errorCode
    }

    return null
  }

  function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === 'object' && value !== null && !Array.isArray(value)
  }

  function asNonEmptyString(value: unknown): string | null {
    return typeof value === 'string' && value.trim() !== '' ? value.trim() : null
  }

  function readDecisionNumber(
    details: Record<string, unknown> | null,
    result: Record<string, unknown> | null,
    keys: string[],
  ): number | null {
    for (const key of keys) {
      const value = details?.[key] ?? result?.[key]
      if (typeof value === 'number' && Number.isFinite(value)) return value
      if (typeof value === 'string' && value.trim() !== '') {
        const parsed = Number(value)
        if (Number.isFinite(parsed)) return parsed
      }
    }

    return null
  }

  function readDecisionBool(
    details: Record<string, unknown> | null,
    result: Record<string, unknown> | null,
    keys: string[],
  ): boolean | null {
    for (const key of keys) {
      const value = details?.[key] ?? result?.[key]
      if (typeof value === 'boolean') return value
      if (typeof value === 'number') return value !== 0
      if (typeof value === 'string') {
        const normalized = value.trim().toLowerCase()
        if (['true', '1', 'yes', 'on'].includes(normalized)) return true
        if (['false', '0', 'no', 'off'].includes(normalized)) return false
      }
    }

    return null
  }

  function readDecisionString(
    details: Record<string, unknown> | null,
    result: Record<string, unknown> | null,
    keys: string[],
  ): string | null {
    for (const key of keys) {
      const value = asNonEmptyString(details?.[key] ?? result?.[key])
      if (value) return value
    }

    return null
  }

  return {
    horizon,
    workspace,
    automationState,
    selectedExecution,
    diagnostics,
    loading,
    detailLoading,
    diagnosticsLoading,
    error,
    diagnosticsError,
    updatedAt,
    lanes,
    windows,
    laneWindows,
    recentRuns,
    activeRun,
    latestFailure,
    executionCounters,
    nextExecutableWindows,
    configOnlyLanes,
    activeProcessLabels,
    attentionItems,
    condensedTimeline,
    fetchWorkspace,
    fetchAutomationState,
    fetchExecution,
    fetchDiagnostics,
    setHorizon,
    clearDiagnostics,
    clearPollTimer,
    schedulePoll,
    pollCycle,
    handleVisibilityChange,
    formatDateTime,
    formatRelativeTrigger,
    statusVariant,
    statusLabel,
    modeLabel,
    eventTypeLabel,
    controlModeLabel,
    laneLabel,
    workflowStageLabel,
    decisionLabel,
    decisionReasonLabel,
    describeDecision,
  }
}

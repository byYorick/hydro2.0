import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import type {
  AutomationState,
  AutomationStateType,
  AutomationTimelineEvent,
  IrrNodeState,
  WorkflowStageCode,
  WorkflowStageStatus,
  WorkflowStageView,
} from '@/types/Automation'
import type { IrrigationSystem } from '@/composables/zoneAutomationTypes'
import { readBooleanEnv } from '@/utils/env'
import { getConnectionState, onWsStateChange } from '@/utils/echoClient'
import { logger } from '@/utils/logger'
import type { WsEventPayload } from '@/ws/subscriptionTypes'
import { subscribeManagedChannelEvents } from '@/ws/managedChannelEvents'
import { api } from '@/services/api'
import { useZonesStore } from '@/stores/zones'
import {
  normalizeAutomationControlMode,
  normalizeAutomationControlModes,
  normalizeAutomationManualSteps,
} from '@/composables/zoneAutomationUtils'

// ─── Constants ────────────────────────────────────────────────────────────────

const WS_COMMAND_EVENT_NAMES = [
  '.CommandStatusUpdated',
  '.App\\Events\\CommandStatusUpdated',
  '.CommandFailed',
  '.App\\Events\\CommandFailed',
] as const

const AUTOMATION_EVENT_LABELS: Record<string, string> = {
  SCHEDULE_TASK_ACCEPTED: 'Scheduler: задача принята',
  SCHEDULE_TASK_COMPLETED: 'Scheduler: задача завершена',
  SCHEDULE_TASK_FAILED: 'Scheduler: задача с ошибкой',
  SCHEDULE_TASK_EXECUTION_STARTED: 'Automation-engine: запуск выполнения',
  SCHEDULE_TASK_EXECUTION_FINISHED: 'Automation-engine: выполнение завершено',
  TASK_RECEIVED: 'Automation-engine: задача получена',
  TASK_STARTED: 'Automation-engine: выполнение начато',
  DECISION_MADE: 'Automation-engine: решение принято',
  COMMAND_DISPATCHED: 'Команда отправлена узлу',
  COMMAND_FAILED: 'Ошибка отправки команды',
  TASK_FINISHED: 'Automation-engine: задача завершена',
  CLEAN_FILL_COMPLETED: 'Бак чистой воды заполнен',
  SOLUTION_FILL_COMPLETED: 'Бак рабочего раствора заполнен',
  CLEAN_FILL_RETRY_STARTED: 'Запущен повторный цикл clean-fill',
  PREPARE_TARGETS_REACHED: 'Целевые pH/EC достигнуты',
  TWO_TANK_STARTUP_INITIATED: 'Запущен старт 2-баковой схемы',
  AUTOMATION_CONTROL_MODE_UPDATED: 'Режим управления автоматикой обновлён',
  MANUAL_STEP_ACCEPTED: 'Ручной шаг принят',
  MANUAL_STEP_REQUESTED: 'Запрошен ручной шаг',
  MANUAL_STEP_EXECUTED: 'Ручной шаг выполнен',
  WORKFLOW_RECOVERY_STALE_STOPPED: 'Залипшая фаза сброшена (авто-восстановление)',
  WORKFLOW_RECOVERY_ENQUEUED: 'Workflow возобновлён после рестарта AE',
  WORKFLOW_RECOVERY_WORKFLOW_FALLBACK: 'Workflow переключён на резервный',
}

const AUTOMATION_REASON_LABELS: Record<string, string> = {
  clean_fill_started: 'Запущено наполнение бака чистой воды',
  clean_fill_in_progress: 'Идёт наполнение бака чистой воды',
  clean_fill_completed: 'Бак чистой воды наполнен',
  clean_fill_timeout: 'Таймаут набора чистой воды',
  solution_fill_started: 'Запущено наполнение бака раствора',
  solution_fill_in_progress: 'Идёт наполнение бака раствора',
  solution_fill_completed: 'Бак раствора наполнен',
  solution_fill_timeout: 'Таймаут набора бака раствора',
  prepare_recirculation_started: 'Запущена рециркуляция и коррекция',
  prepare_targets_reached: 'Целевые pH/EC достигнуты',
  prepare_targets_not_reached: 'Цели pH/EC не достигнуты',
  prepare_npk_ph_target_not_reached: 'Цели подготовки раствора не достигнуты',
  setup_completed: 'Setup завершен',
  setup_to_working: 'Переход в рабочий режим',
  working_mode_activated: 'Рабочий режим активирован',
  stale_safety_reset: 'Сработал stale safety reset',
  manual_step_requested: 'Ручной шаг запрошен',
  manual_step_executed: 'Ручной шаг выполнен',
  automation_control_mode_updated: 'Режим управления изменён',
}

const WORKFLOW_STAGE_LABELS: Record<WorkflowStageCode, string> = {
  tank_filling: 'Наполнение баков',
  tank_recirc: 'Рециркуляция раствора',
  ready: 'Раствор готов',
  irrigating: 'Полив',
  irrig_recirc: 'Рециркуляция после полива',
}

const WORKFLOW_STAGE_ORDER: WorkflowStageCode[] = [
  'tank_filling',
  'tank_recirc',
  'ready',
  'irrigating',
  'irrig_recirc',
]

const WS_MIN_REFRESH_INTERVAL_MS = 1200
const FALLBACK_POLL_INTERVAL_MS = 30000
const FLOW_TICK_INTERVAL_MS = 80

// ─── Props interface ──────────────────────────────────────────────────────────

export interface AutomationPanelProps {
  zoneId: number | null
  fallbackTanksCount?: number
  fallbackSystemType?: IrrigationSystem
}

// ─── Helper functions ─────────────────────────────────────────────────────────

function clampPercent(value: unknown): number {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return 0
  return Math.max(0, Math.min(100, parsed))
}

function toOptionalBoolean(value: unknown): boolean | null {
  if (typeof value === 'boolean') return value
  if (typeof value === 'number') {
    if (value === 1) return true
    if (value === 0) return false
    return null
  }
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase()
    if (normalized === '1' || normalized === 'true') return true
    if (normalized === '0' || normalized === 'false') return false
  }
  return null
}

function normalizeIrrNodeState(raw: unknown): IrrNodeState | null {
  if (!raw || typeof raw !== 'object') return null
  const state = raw as Record<string, unknown>

  return {
    clean_level_max: toOptionalBoolean(state.clean_level_max),
    clean_level_min: toOptionalBoolean(state.clean_level_min),
    solution_level_max: toOptionalBoolean(state.solution_level_max),
    solution_level_min: toOptionalBoolean(state.solution_level_min),
    valve_clean_fill: toOptionalBoolean(state.valve_clean_fill),
    valve_clean_supply: toOptionalBoolean(state.valve_clean_supply),
    valve_solution_fill: toOptionalBoolean(state.valve_solution_fill),
    valve_solution_supply: toOptionalBoolean(state.valve_solution_supply),
    valve_irrigation: toOptionalBoolean(state.valve_irrigation),
    pump_main: toOptionalBoolean(state.pump_main),
    updated_at: typeof state.updated_at === 'string' ? state.updated_at : null,
  }
}

function formatDuration(rawSeconds: number | null | undefined): string {
  if (!rawSeconds || rawSeconds <= 0) return '00:00'
  const total = Math.floor(rawSeconds)
  const mm = Math.floor(total / 60)
  const ss = total % 60
  return `${String(mm).padStart(2, '0')}:${String(ss).padStart(2, '0')}`
}

function normalizeReasonCode(reasonCode: string): string {
  return reasonCode.trim().toLowerCase().replace(/\s+/g, '_')
}

function extractReasonCodeFromEventLabel(label: string): string | null {
  const match = label.match(/\(([^()]+)\)\s*$/)
  if (!match || !match[1]) return null
  return normalizeReasonCode(match[1])
}

function automationStateToWorkflowIndex(state: AutomationStateType): number {
  const order: Record<AutomationStateType, number> = {
    IDLE: -1,
    TANK_FILLING: 0,
    TANK_RECIRC: 1,
    READY: 2,
    IRRIGATING: 3,
    IRRIG_RECIRC: 4,
  }
  return order[state]
}

function deriveWorkflowStages(state: AutomationStateType, hasFailedState: boolean): WorkflowStageView[] {
  const currentStageIndex = automationStateToWorkflowIndex(state)

  return WORKFLOW_STAGE_ORDER.map((code, index) => {
    let status: WorkflowStageStatus = 'pending'

    if (currentStageIndex >= 0) {
      if (index < currentStageIndex) {
        status = 'completed'
      } else if (index === currentStageIndex) {
        status = hasFailedState ? 'failed' : 'running'
      }
    }

    return {
      code,
      label: WORKFLOW_STAGE_LABELS[code],
      status,
    }
  })
}

function stagePrefixForEvent(eventCode: string, reasonCode: string | null): string | null {
  const normalizedEvent = eventCode.trim().toUpperCase()
  const normalizedReason = reasonCode ? normalizeReasonCode(reasonCode) : null

  if (normalizedReason !== null && (normalizedReason.startsWith('clean_fill_') || normalizedReason.startsWith('tank_refill_') || normalizedEvent === 'CLEAN_FILL_COMPLETED')) {
    return 'Набор чистой воды'
  }
  if (normalizedReason !== null && (normalizedReason.startsWith('solution_fill_') || normalizedEvent === 'SOLUTION_FILL_COMPLETED')) {
    return 'Набор раствора'
  }
  if (normalizedReason !== null && (normalizedReason.startsWith('prepare_') || normalizedReason.includes('correction') || normalizedEvent === 'PREPARE_TARGETS_REACHED')) {
    return 'Параллельная коррекция'
  }
  if (normalizedReason !== null && (normalizedReason.startsWith('setup_') || normalizedReason.includes('working_mode') || normalizedReason.includes('setup_to_working'))) {
    return 'Переход в рабочий режим'
  }
  return null
}

function formatTimelineLabel(event: AutomationTimelineEvent): string {
  const eventCode = String(event.event ?? '').trim().toUpperCase()
  const sourceLabel = String(event.label ?? '').trim()
  const reasonFromLabel = extractReasonCodeFromEventLabel(sourceLabel)
  const baseFromLabel = sourceLabel.replace(/\s*\([^()]+\)\s*$/, '').trim()
  const baseLabel = baseFromLabel || AUTOMATION_EVENT_LABELS[eventCode] || eventCode || 'Событие'
  const reasonLabel = reasonFromLabel ? (AUTOMATION_REASON_LABELS[reasonFromLabel] ?? reasonFromLabel) : null
  const stagePrefix = stagePrefixForEvent(eventCode, reasonFromLabel)
  const suppressReasonForEvent =
    eventCode === 'COMMAND_DISPATCHED'
    || eventCode === 'COMMAND_FAILED'
    || eventCode === 'COMMAND_EFFECT_NOT_CONFIRMED'

  let formatted = baseLabel
  if (
    reasonLabel
    && !suppressReasonForEvent
    && baseLabel.trim().toLowerCase() !== reasonLabel.trim().toLowerCase()
  ) {
    formatted = `${formatted} — ${reasonLabel}`
  }
  if (stagePrefix) {
    formatted = `${stagePrefix}: ${formatted}`
  }
  return formatted
}

// ─── Composable ───────────────────────────────────────────────────────────────

export function useAutomationPanel(
  props: AutomationPanelProps,
  emit: {
    (e: 'state-change', state: AutomationStateType): void
    (e: 'state-snapshot', snapshot: AutomationState): void
  }
) {
  const zonesStore = useZonesStore()
  const wsEnabled = readBooleanEnv('VITE_ENABLE_WS', true)

  // ─── State ────────────────────────────────────────────────────────────────

  const automationState = ref<AutomationState | null>(null)
  const errorMessage = ref<string | null>(null)
  const connectivityWarning = ref<string | null>(null)
  const flowOffset = ref(0)

  let fetchInFlight = false
  let fetchQueued = false

  // ─── Timer / channel vars ─────────────────────────────────────────────────

  let flowTimer: ReturnType<typeof setInterval> | null = null
  let fallbackPollingTimer: ReturnType<typeof setInterval> | null = null
  let wsRefreshTimer: ReturnType<typeof setTimeout> | null = null
  let wsStateListenerCleanup: (() => void) | null = null
  let stopCommandsRealtimeSubscription: (() => void) | null = null
  let lastRealtimeRefreshAt = 0

  // ─── Normalize ────────────────────────────────────────────────────────────

  function normalizeState(raw: unknown): AutomationState {
    const source = (raw && typeof raw === 'object' ? raw : {}) as Partial<AutomationState>
    const sourceAny = source as Record<string, unknown>
    const state = String(source.state || 'IDLE') as AutomationStateType
    const tanksRaw = Number(source.system_config?.tanks_count ?? props.fallbackTanksCount ?? 2)
    const tanksCount: 2 | 3 = tanksRaw === 3 ? 3 : 2

    const irrNodeStateRaw =
      sourceAny.irr_node_state
      ?? sourceAny.irrState
      ?? sourceAny.irrigation_node_state
      ?? (sourceAny.process_state && typeof sourceAny.process_state === 'object'
        ? (sourceAny.process_state as Record<string, unknown>).irr_node_state
        : undefined)
    const irrNodeState = normalizeIrrNodeState(irrNodeStateRaw)

    const rawDecision = sourceAny.decision && typeof sourceAny.decision === 'object'
      ? sourceAny.decision as Record<string, unknown>
      : null

    return {
      zone_id: Number(source.zone_id ?? props.zoneId ?? 0),
      state,
      state_label: String(source.state_label || ''),
      state_details: {
        started_at: source.state_details?.started_at ?? null,
        elapsed_sec: Number(source.state_details?.elapsed_sec ?? 0),
        progress_percent: clampPercent(source.state_details?.progress_percent ?? 0),
        failed: Boolean(source.state_details?.failed ?? false),
        error_code: (source.state_details as Record<string, unknown> | undefined)?.error_code as string | null ?? null,
        error_message: (source.state_details as Record<string, unknown> | undefined)?.error_message as string | null ?? null,
        human_error_message: (source.state_details as Record<string, unknown> | undefined)?.human_error_message as string | null ?? null,
      },
      workflow_phase: (sourceAny.workflow_phase as string | null | undefined) ?? null,
      current_stage: (sourceAny.current_stage as string | null | undefined) ?? null,
      current_stage_label: (sourceAny.current_stage_label as string | null | undefined) ?? null,
      system_config: {
        tanks_count: tanksCount,
        system_type: (source.system_config?.system_type as IrrigationSystem) || props.fallbackSystemType || 'drip',
        clean_tank_capacity_l: source.system_config?.clean_tank_capacity_l ?? null,
        nutrient_tank_capacity_l: source.system_config?.nutrient_tank_capacity_l ?? null,
      },
      current_levels: {
        clean_tank_level_percent: clampPercent(source.current_levels?.clean_tank_level_percent ?? 0),
        nutrient_tank_level_percent: clampPercent(source.current_levels?.nutrient_tank_level_percent ?? 0),
        buffer_tank_level_percent: source.current_levels?.buffer_tank_level_percent ?? null,
        ph: source.current_levels?.ph ?? null,
        ec: source.current_levels?.ec ?? null,
      },
      active_processes: {
        pump_in: Boolean(source.active_processes?.pump_in),
        circulation_pump: Boolean(source.active_processes?.circulation_pump),
        ph_correction: Boolean(source.active_processes?.ph_correction),
        ec_correction: Boolean(source.active_processes?.ec_correction),
      },
      timeline: Array.isArray(source.timeline) ? source.timeline : [],
      next_state: source.next_state ?? null,
      estimated_completion_sec: source.estimated_completion_sec ?? null,
      irr_node_state: irrNodeState,
      control_mode: normalizeAutomationControlMode(sourceAny.control_mode),
      control_mode_available: normalizeAutomationControlModes(sourceAny.control_mode_available),
      allowed_manual_steps: normalizeAutomationManualSteps(sourceAny.allowed_manual_steps),
      state_meta: sourceAny.state_meta && typeof sourceAny.state_meta === 'object'
        ? {
            source: String((sourceAny.state_meta as Record<string, unknown>).source ?? ''),
            is_stale: Boolean((sourceAny.state_meta as Record<string, unknown>).is_stale),
            served_at: String((sourceAny.state_meta as Record<string, unknown>).served_at ?? ''),
          }
        : null,
      decision: rawDecision
        ? {
            outcome: (rawDecision.outcome as string | null | undefined) ?? null,
            reason_code: (rawDecision.reason_code as string | null | undefined) ?? null,
            strategy: (rawDecision.strategy as string | null | undefined) ?? null,
            config: (rawDecision.config as Record<string, unknown> | null | undefined) ?? null,
            bundle_revision: (rawDecision.bundle_revision as string | null | undefined) ?? null,
            degraded: (rawDecision.degraded as boolean | null | undefined) ?? null,
          }
        : null,
    }
  }

  // ─── Fetch ────────────────────────────────────────────────────────────────

  async function fetchAutomationState(): Promise<void> {
    if (!props.zoneId) return

    if (fetchInFlight) {
      fetchQueued = true
      return
    }

    const requestedZoneId = props.zoneId
    fetchInFlight = true
    try {
      const response = await api.zones.getState<unknown>(requestedZoneId)
      if (props.zoneId !== requestedZoneId) return
      const normalized = normalizeState(response)
      automationState.value = normalized
      errorMessage.value = null
      connectivityWarning.value = null
    } catch (error) {
      if (props.zoneId !== requestedZoneId) return
      const message = error instanceof Error ? error.message : 'unknown_error'
      if (automationState.value) {
        errorMessage.value = null
        connectivityWarning.value = `Связь с automation-engine нестабильна (${message}). Показано последнее полученное состояние.`
      } else {
        connectivityWarning.value = null
        errorMessage.value = `Не удалось получить состояние автоматизации (${message}).`
      }
    } finally {
      fetchInFlight = false
      if (fetchQueued) {
        fetchQueued = false
        void fetchAutomationState()
      }
    }
  }

  // ─── WS / Polling ─────────────────────────────────────────────────────────

  function clearWsRefreshTimer(): void {
    if (wsRefreshTimer !== null) {
      clearTimeout(wsRefreshTimer)
      wsRefreshTimer = null
    }
  }

  function stopFallbackPolling(): void {
    if (fallbackPollingTimer !== null) {
      clearInterval(fallbackPollingTimer)
      fallbackPollingTimer = null
    }
  }

  function startFallbackPolling(): void {
    if (fallbackPollingTimer !== null || !props.zoneId) return
    fallbackPollingTimer = setInterval(() => {
      void fetchAutomationState()
    }, FALLBACK_POLL_INTERVAL_MS)
  }

  function scheduleRealtimeRefresh(): void {
    const elapsed = Date.now() - lastRealtimeRefreshAt
    const waitMs = Math.max(0, WS_MIN_REFRESH_INTERVAL_MS - elapsed)

    if (waitMs === 0) {
      lastRealtimeRefreshAt = Date.now()
      void fetchAutomationState()
      return
    }

    if (wsRefreshTimer !== null) return

    wsRefreshTimer = setTimeout(() => {
      wsRefreshTimer = null
      lastRealtimeRefreshAt = Date.now()
      void fetchAutomationState()
    }, waitMs)
  }

  function cleanupRealtimeChannels(): void {
    if (stopCommandsRealtimeSubscription) {
      stopCommandsRealtimeSubscription()
      stopCommandsRealtimeSubscription = null
    }
  }

  function subscribeRealtimeChannels(): boolean {
    if (!wsEnabled || !props.zoneId) return false

    cleanupRealtimeChannels()

    try {
      const commandsChannelName = `hydro.commands.${props.zoneId}`

      stopCommandsRealtimeSubscription = subscribeManagedChannelEvents({
        channelName: commandsChannelName,
        componentTag: `AutomationProcessPanel:commands:${props.zoneId}`,
        eventHandlers: Object.fromEntries(
          WS_COMMAND_EVENT_NAMES.map((eventName) => [
            eventName,
            () => { scheduleRealtimeRefresh() },
          ])
        ) as Record<string, (payload: WsEventPayload) => void>,
      })

      logger.debug('[AutomationProcessPanel] Realtime subscriptions started', {
        zoneId: props.zoneId,
        commandsChannel: commandsChannelName,
      })

      return true
    } catch (error) {
      logger.warn('[AutomationProcessPanel] Failed to subscribe realtime channels', {
        zoneId: props.zoneId,
        error: error instanceof Error ? error.message : String(error),
      })
      cleanupRealtimeChannels()
      return false
    }
  }

  // ─── Computed ─────────────────────────────────────────────────────────────

  const stateCode = computed<AutomationStateType>(() => automationState.value?.state ?? 'IDLE')

  const stateLabel = computed(() => {
    const details = automationState.value?.state_details
    if (details?.failed) {
      const human = details.human_error_message?.trim()
      if (human) return human
      const raw = details.error_message?.trim()
      if (raw) return raw
    }
    if (automationState.value?.state_label) return automationState.value.state_label
    const labels: Record<AutomationStateType, string> = {
      IDLE: 'Система в ожидании',
      TANK_FILLING: 'Набор бака с раствором',
      TANK_RECIRC: 'Рециркуляция бака',
      READY: 'Раствор готов к поливу',
      IRRIGATING: 'Полив',
      IRRIG_RECIRC: 'Рециркуляция после полива',
    }
    return labels[stateCode.value]
  })

  const stateVariant = computed<'neutral' | 'info' | 'warning' | 'success' | 'danger'>(() => {
    if (automationState.value?.state_details?.failed) return 'danger'
    const map: Record<AutomationStateType, 'neutral' | 'info' | 'warning' | 'success'> = {
      IDLE: 'neutral',
      TANK_FILLING: 'info',
      TANK_RECIRC: 'warning',
      READY: 'success',
      IRRIGATING: 'info',
      IRRIG_RECIRC: 'warning',
    }
    return map[stateCode.value]
  })

  const isProcessActive = computed(() => stateCode.value !== 'IDLE' && stateCode.value !== 'READY')
  const irrNodeState = computed(() => automationState.value?.irr_node_state ?? null)
  const cleanTankLevel = computed(() => {
    const state = irrNodeState.value
    // max=true — бак точно заполнен до верхней отметки
    if (state?.clean_level_max === true) return 100
    // оба false — уровень ниже нижней отметки (бак пустой или почти пустой)
    if (state?.clean_level_max === false && state?.clean_level_min === false) return 0
    // min=true без max — выше нижней отметки, точное значение неизвестно; используем raw %
    return automationState.value?.current_levels.clean_tank_level_percent ?? 0
  })
  const nutrientTankLevel = computed(() => {
    const state = irrNodeState.value
    if (state?.solution_level_max === true) return 100
    if (state?.solution_level_max === false && state?.solution_level_min === false) return 0
    return automationState.value?.current_levels.nutrient_tank_level_percent ?? 0
  })
  const bufferTankLevel = computed(() => clampPercent(automationState.value?.current_levels.buffer_tank_level_percent ?? 0))
  const isPumpInActive = computed(() => {
    const fromIrr = irrNodeState.value?.pump_main
    if (fromIrr !== null && fromIrr !== undefined) return fromIrr
    return Boolean(automationState.value?.active_processes.pump_in)
  })
  const isCirculationActive = computed(() => Boolean(automationState.value?.active_processes.circulation_pump))
  const isPhCorrectionActive = computed(() => Boolean(automationState.value?.active_processes.ph_correction))
  const isEcCorrectionActive = computed(() => Boolean(automationState.value?.active_processes.ec_correction))
  const progressPercent = computed(() => clampPercent(automationState.value?.state_details.progress_percent ?? 0))

  const isWaterInletActive = computed(() => {
    const fromIrr = irrNodeState.value?.valve_clean_fill
    if (fromIrr !== null && fromIrr !== undefined) return fromIrr
    return stateCode.value === 'TANK_FILLING'
  })

  const isTankRefillActive = computed(() => {
    const fromIrr = irrNodeState.value
    if (fromIrr) {
      const solutionFill = fromIrr.valve_solution_fill
      const solutionSupply = fromIrr.valve_solution_supply
      if (solutionFill !== null || solutionSupply !== null) {
        return Boolean(solutionFill) || Boolean(solutionSupply)
      }
    }
    return stateCode.value === 'TANK_FILLING' || stateCode.value === 'TANK_RECIRC'
  })

  const isIrrigationActive = computed(() => {
    const fromIrr = irrNodeState.value?.valve_irrigation
    if (fromIrr !== null && fromIrr !== undefined) return fromIrr
    return stateCode.value === 'IRRIGATING' || stateCode.value === 'IRRIG_RECIRC'
  })

  const hasFailedState = computed(() => {
    if (automationState.value?.state_details.failed) return true
    // Fallback: только terminal-события провала всего процесса.
    // Намеренно НЕ проверяем COMMAND_FAILED и *_TIMEOUT — они могут идти с retry и не означают
    // гибель процесса целиком.
    const timeline = automationState.value?.timeline ?? []
    const latest = timeline[timeline.length - 1]
    if (!latest) return false
    const eventCode = String(latest.event ?? '').toUpperCase()
    return eventCode === 'SCHEDULE_TASK_FAILED' || eventCode === 'TASK_FAILED'
  })

  const workflowStages = computed<WorkflowStageView[]>(() => {
    return deriveWorkflowStages(stateCode.value, hasFailedState.value)
  })

  const currentWorkflowStageLabel = computed(() => {
    const running = workflowStages.value.find((stage) => stage.status === 'running')
    if (running) return running.label

    const failed = workflowStages.value.find((stage) => stage.status === 'failed')
    if (failed) return `${failed.label} (ошибка)`

    if (workflowStages.value.every((stage) => stage.status === 'completed')) {
      return 'Workflow завершён, система в рабочем режиме'
    }

    const pending = workflowStages.value.find((stage) => stage.status === 'pending')
    return pending?.label ?? 'Ожидание данных процесса'
  })

  const progressSummary = computed(() => {
    const elapsed = formatDuration(automationState.value?.state_details.elapsed_sec ?? 0)
    const eta = automationState.value?.estimated_completion_sec
    if (eta && eta > 0) {
      return `${Math.round(progressPercent.value)}% · ${elapsed} · ~${formatDuration(eta)}`
    }
    return `${Math.round(progressPercent.value)}% · ${elapsed}`
  })

  const timelineEvents = computed<AutomationTimelineEvent[]>(() => {
    const timeline = automationState.value?.timeline ?? []
    return timeline.slice(-12).map((event) => ({
      ...event,
      label: formatTimelineLabel(event),
    }))
  })

  // ─── Flow animation ───────────────────────────────────────────────────────

  function tickFlow(): void {
    if (!(isPumpInActive.value || isCirculationActive.value)) return
    flowOffset.value += 0.03
    if (flowOffset.value > 1) flowOffset.value = 0
  }

  // ─── Watchers ─────────────────────────────────────────────────────────────

  watch(stateCode, (value) => {
    emit('state-change', value)
  })

  watch(automationState, (value) => {
    if (!value) return
    emit('state-snapshot', value)
  })

  // Зональные события (GrowCycleUpdated, EventCreated, zone:updated, финальные команды)
  // нотифицируют через zonesStore.zoneEventSeq — единственная подписка в useZonePageState,
  // без дублирования на hydro.zones.{id}.
  watch(
    () => props.zoneId ? (zonesStore.zoneEventSeq[props.zoneId] ?? 0) : 0,
    () => {
      if (props.zoneId) {
        scheduleRealtimeRefresh()
      }
    }
  )

  watch(() => props.zoneId, (newZoneId, oldZoneId) => {
    if (newZoneId === oldZoneId) return

    clearWsRefreshTimer()
    cleanupRealtimeChannels()
    stopFallbackPolling()

    if (!newZoneId) {
      automationState.value = null
      errorMessage.value = null
      connectivityWarning.value = null
      return
    }

    void fetchAutomationState()

    if (wsEnabled) {
      const subscribed = subscribeRealtimeChannels()
      if (subscribed && getConnectionState().state === 'connected') {
        stopFallbackPolling()
        scheduleRealtimeRefresh()
        return
      }
    }

    startFallbackPolling()
  })

  // ─── Lifecycle ────────────────────────────────────────────────────────────

  onMounted(() => {
    void fetchAutomationState()

    if (wsEnabled) {
      const subscribed = subscribeRealtimeChannels()
      if (subscribed && getConnectionState().state === 'connected') {
        stopFallbackPolling()
        scheduleRealtimeRefresh()
      } else {
        startFallbackPolling()
      }

      wsStateListenerCleanup = onWsStateChange((state) => {
        if (state === 'connected') {
          stopFallbackPolling()
          scheduleRealtimeRefresh()
          return
        }

        if (state === 'disconnected' || state === 'unavailable' || state === 'failed') {
          clearWsRefreshTimer()
          startFallbackPolling()
        }
      })
    } else {
      startFallbackPolling()
    }

    flowTimer = setInterval(() => {
      tickFlow()
    }, FLOW_TICK_INTERVAL_MS)
  })

  onUnmounted(() => {
    if (wsStateListenerCleanup) {
      wsStateListenerCleanup()
      wsStateListenerCleanup = null
    }
    cleanupRealtimeChannels()
    clearWsRefreshTimer()
    stopFallbackPolling()
    if (flowTimer !== null) {
      clearInterval(flowTimer)
      flowTimer = null
    }
  })

  return {
    automationState,
    errorMessage,
    connectivityWarning,
    flowOffset,
    stateCode,
    stateLabel,
    stateVariant,
    isProcessActive,
    cleanTankLevel,
    nutrientTankLevel,
    bufferTankLevel,
    isPumpInActive,
    isCirculationActive,
    isPhCorrectionActive,
    isEcCorrectionActive,
    isWaterInletActive,
    isTankRefillActive,
    isIrrigationActive,
    workflowStages,
    currentWorkflowStageLabel,
    progressSummary,
    timelineEvents,
    irrNodeState,
  }
}

import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import type {
  AutomationControlMode,
  AutomationManualStep,
  AutomationState,
  AutomationStateType,
  AutomationTimelineEvent,
  IrrNodeState,
  SetupStageCode,
  SetupStageStatus,
  SetupStageView,
} from '@/types/Automation'
import type { IrrigationSystem } from '@/composables/zoneAutomationTypes'
import { readBooleanEnv } from '@/utils/env'
import { getEchoInstance, onWsStateChange } from '@/utils/echoClient'
import { logger } from '@/utils/logger'
import type { EchoChannelLike, WsEventPayload } from '@/ws/subscriptionTypes'
import { useApi } from '@/composables/useApi'

// ─── Constants ────────────────────────────────────────────────────────────────

const WS_ZONE_EVENT_NAMES = [
  '.telemetry.batch.updated',
  '.App\\Events\\TelemetryBatchUpdated',
  '.node.telemetry.updated',
  '.App\\Events\\NodeTelemetryUpdated',
  '.GrowCycleUpdated',
  '.App\\Events\\GrowCycleUpdated',
  '.ZoneUpdated',
  '.App\\Events\\ZoneUpdated',
] as const

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
  manual_step_requested: 'Ручной шаг запрошен',
  manual_step_executed: 'Ручной шаг выполнен',
  automation_control_mode_updated: 'Режим управления изменён',
}

const WS_MIN_REFRESH_INTERVAL_MS = 1200
const FALLBACK_POLL_INTERVAL_MS = 30000
const FLOW_TICK_INTERVAL_MS = 80

// ─── Props interface ──────────────────────────────────────────────────────────

export interface AutomationPanelProps {
  zoneId: number | null
  fallbackTanksCount?: number
  fallbackSystemType?: IrrigationSystem
}

const AUTOMATION_MANUAL_STEPS_SET = new Set<AutomationManualStep>([
  'clean_fill_start',
  'clean_fill_stop',
  'solution_fill_start',
  'solution_fill_stop',
  'prepare_recirculation_start',
  'prepare_recirculation_stop',
  'irrigation_recovery_start',
  'irrigation_recovery_stop',
])

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

function pickFirstDefined(source: Record<string, unknown>, keys: string[]): unknown {
  for (const key of keys) {
    if (Object.prototype.hasOwnProperty.call(source, key)) {
      return source[key]
    }
  }
  return undefined
}

function normalizeControlMode(value: unknown): AutomationControlMode {
  const normalized = String(value ?? '').trim().toLowerCase()
  if (normalized === 'semi' || normalized === 'manual') return normalized
  return 'auto'
}

function normalizeManualSteps(value: unknown): AutomationManualStep[] {
  if (!Array.isArray(value)) return []
  return value
    .map((item) => String(item ?? '').trim().toLowerCase())
    .filter((item): item is AutomationManualStep => AUTOMATION_MANUAL_STEPS_SET.has(item as AutomationManualStep))
}

function normalizeIrrNodeState(raw: unknown): IrrNodeState | null {
  if (!raw || typeof raw !== 'object') return null
  const state = raw as Record<string, unknown>

  return {
    clean_level_max: toOptionalBoolean(pickFirstDefined(state, ['clean_level_max', 'level_clean_max', 'clean_max'])),
    clean_level_min: toOptionalBoolean(pickFirstDefined(state, ['clean_level_min', 'level_clean_min', 'clean_min'])),
    solution_level_max: toOptionalBoolean(pickFirstDefined(state, ['solution_level_max', 'level_solution_max', 'solution_max'])),
    solution_level_min: toOptionalBoolean(pickFirstDefined(state, ['solution_level_min', 'level_solution_min', 'solution_min'])),
    valve_clean_fill: toOptionalBoolean(pickFirstDefined(state, ['valve_clean_fill'])),
    valve_clean_supply: toOptionalBoolean(pickFirstDefined(state, ['valve_clean_supply'])),
    valve_solution_fill: toOptionalBoolean(pickFirstDefined(state, ['valve_solution_fill'])),
    valve_solution_supply: toOptionalBoolean(pickFirstDefined(state, ['valve_solution_supply'])),
    valve_irrigation: toOptionalBoolean(pickFirstDefined(state, ['valve_irrigation'])),
    pump_main: toOptionalBoolean(pickFirstDefined(state, ['pump_main', 'pump'])),
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

function setupStageCodeFromReason(reasonCode: string | null): SetupStageCode | null {
  if (!reasonCode) return null

  if (reasonCode.startsWith('clean_fill_') || reasonCode.startsWith('tank_refill_')) {
    return 'clean_fill'
  }
  if (reasonCode.startsWith('solution_fill_')) {
    return 'solution_fill'
  }
  if (
    reasonCode.startsWith('prepare_')
    || reasonCode.includes('correction')
    || reasonCode.startsWith('irrigation_recovery_')
  ) {
    return 'parallel_correction'
  }
  if (
    reasonCode.startsWith('setup_')
    || reasonCode.includes('working_mode')
    || reasonCode.includes('setup_to_working')
  ) {
    return 'setup_transition'
  }

  return null
}

function setupStageCodeFromEvent(eventCode: string): SetupStageCode | null {
  const normalized = eventCode.trim().toUpperCase()
  if (normalized === 'CLEAN_FILL_COMPLETED') return 'clean_fill'
  if (normalized === 'SOLUTION_FILL_COMPLETED') return 'solution_fill'
  if (normalized === 'PREPARE_TARGETS_REACHED') return 'parallel_correction'
  return null
}

function isRunningReasonCode(reasonCode: string | null): boolean {
  if (!reasonCode) return false

  return (
    reasonCode.endsWith('_started')
    || reasonCode.endsWith('_in_progress')
    || reasonCode.endsWith('_retry_started')
    || reasonCode.endsWith('_check')
    || reasonCode.includes('not_reached')
    || reasonCode.includes('recovery')
  )
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

  let formatted = baseLabel
  if (reasonLabel && baseLabel.trim().toLowerCase() !== reasonLabel.trim().toLowerCase()) {
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
  const { get } = useApi()
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
  let zoneChannel: EchoChannelLike | null = null
  let commandsChannel: EchoChannelLike | null = null
  let zoneChannelName: string | null = null
  let commandsChannelName: string | null = null
  let lastRealtimeRefreshAt = 0

  const zoneEventHandlers = new Map<string, (payload: WsEventPayload) => void>()
  const commandEventHandlers = new Map<string, (payload: WsEventPayload) => void>()

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

    return {
      zone_id: Number(source.zone_id ?? props.zoneId ?? 0),
      state,
      state_label: String(source.state_label || ''),
      state_details: {
        started_at: source.state_details?.started_at ?? null,
        elapsed_sec: Number(source.state_details?.elapsed_sec ?? 0),
        progress_percent: clampPercent(source.state_details?.progress_percent ?? 0),
        failed: Boolean(source.state_details?.failed ?? false),
      },
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
      control_mode: normalizeControlMode(sourceAny.control_mode),
      control_mode_available: ['auto', 'semi', 'manual'],
      allowed_manual_steps: normalizeManualSteps(sourceAny.allowed_manual_steps),
      state_meta: sourceAny.state_meta && typeof sourceAny.state_meta === 'object'
        ? {
            source: String((sourceAny.state_meta as Record<string, unknown>).source ?? ''),
            is_stale: Boolean((sourceAny.state_meta as Record<string, unknown>).is_stale),
            served_at: String((sourceAny.state_meta as Record<string, unknown>).served_at ?? ''),
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

    fetchInFlight = true
    try {
      const response = await get(`/api/zones/${props.zoneId}/state`)
      const normalized = normalizeState(response.data)
      automationState.value = normalized
      errorMessage.value = null
      connectivityWarning.value = null
    } catch (error) {
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
    const echo = getEchoInstance()

    if (zoneChannel) {
      zoneEventHandlers.forEach((handler, eventName) => {
        zoneChannel?.stopListening(eventName, handler)
      })
      zoneEventHandlers.clear()
    }

    if (commandsChannel) {
      commandEventHandlers.forEach((handler, eventName) => {
        commandsChannel?.stopListening(eventName, handler)
      })
      commandEventHandlers.clear()
    }

    if (echo && zoneChannelName) echo.leave?.(zoneChannelName)
    if (echo && commandsChannelName) echo.leave?.(commandsChannelName)

    zoneChannel = null
    commandsChannel = null
    zoneChannelName = null
    commandsChannelName = null
  }

  function subscribeRealtimeChannels(): boolean {
    if (!wsEnabled || !props.zoneId) return false

    const echo = getEchoInstance()
    if (!echo) return false

    cleanupRealtimeChannels()

    try {
      zoneChannelName = `hydro.zones.${props.zoneId}`
      zoneChannel = echo.private(zoneChannelName)

      WS_ZONE_EVENT_NAMES.forEach((eventName) => {
        const handler = () => { scheduleRealtimeRefresh() }
        zoneEventHandlers.set(eventName, handler)
        zoneChannel?.listen(eventName, handler)
      })

      commandsChannelName = `commands.${props.zoneId}`
      commandsChannel = echo.private(commandsChannelName)

      WS_COMMAND_EVENT_NAMES.forEach((eventName) => {
        const handler = () => { scheduleRealtimeRefresh() }
        commandEventHandlers.set(eventName, handler)
        commandsChannel?.listen(eventName, handler)
      })

      logger.debug('[AutomationProcessPanel] Realtime subscriptions started', {
        zoneId: props.zoneId,
        zoneChannel: zoneChannelName,
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

  const stateVariant = computed<'neutral' | 'info' | 'warning' | 'success'>(() => {
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
    if (state?.clean_level_max === true) return 100
    if (state?.clean_level_min === true) return 50
    if (state?.clean_level_max === false && state?.clean_level_min === false) return 0
    return automationState.value?.current_levels.clean_tank_level_percent ?? 0
  })
  const nutrientTankLevel = computed(() => {
    const state = irrNodeState.value
    if (state?.solution_level_max === true) return 100
    if (state?.solution_level_min === true) return 50
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
    // Fallback: проверяем последнее событие таймлайна (для обратной совместимости)
    const timeline = automationState.value?.timeline ?? []
    const latest = timeline[timeline.length - 1]
    if (!latest) return false
    const eventCode = String(latest.event ?? '').toUpperCase()
    return eventCode.includes('FAILED') || eventCode.includes('TIMEOUT')
  })

  const hasSetupTransitionCompleted = computed(() => {
    return stateCode.value === 'READY' || stateCode.value === 'IRRIGATING' || stateCode.value === 'IRRIG_RECIRC'
  })

  const activeSetupStageCode = computed<SetupStageCode | null>(() => {
    if (hasSetupTransitionCompleted.value) return null

    const timeline = automationState.value?.timeline ?? []
    for (let index = timeline.length - 1; index >= 0; index -= 1) {
      const event = timeline[index]
      const eventCode = String(event?.event ?? '').trim()
      const label = String(event?.label ?? '')
      const reasonCode = extractReasonCodeFromEventLabel(label)
      const stageByReason = setupStageCodeFromReason(reasonCode)
      if (stageByReason && isRunningReasonCode(reasonCode)) {
        return stageByReason
      }
      const stageByEvent = setupStageCodeFromEvent(eventCode)
      if (stageByEvent && isRunningReasonCode(reasonCode)) {
        return stageByEvent
      }
    }

    if (stateCode.value === 'TANK_RECIRC') return 'parallel_correction'
    if (stateCode.value === 'TANK_FILLING') {
      const cleanDone = cleanTankLevel.value >= 90
      return cleanDone ? 'solution_fill' : 'clean_fill'
    }
    return null
  })

  const setupStages = computed<SetupStageView[]>(() => {
    const stageOrder: SetupStageCode[] = ['clean_fill', 'solution_fill', 'parallel_correction', 'setup_transition']
    const doneByStage: Record<SetupStageCode, boolean> = {
      clean_fill: cleanTankLevel.value >= 90 || stateCode.value === 'TANK_RECIRC' || hasSetupTransitionCompleted.value,
      solution_fill: nutrientTankLevel.value >= 90 || stateCode.value === 'TANK_RECIRC' || hasSetupTransitionCompleted.value,
      parallel_correction: hasSetupTransitionCompleted.value,
      setup_transition: hasSetupTransitionCompleted.value,
    }

    const statuses: Record<SetupStageCode, SetupStageStatus> = {
      clean_fill: 'pending',
      solution_fill: 'pending',
      parallel_correction: 'pending',
      setup_transition: 'pending',
    }

    const activeStage = activeSetupStageCode.value
    const activeIndex = activeStage ? stageOrder.indexOf(activeStage) : -1

    stageOrder.forEach((stageCode, index) => {
      if (hasFailedState.value) {
        if (activeIndex >= 0) {
          if (index < activeIndex || doneByStage[stageCode]) {
            statuses[stageCode] = 'completed'
          } else if (index === activeIndex) {
            statuses[stageCode] = 'failed'
          } else {
            statuses[stageCode] = 'pending'
          }
          return
        }
        statuses[stageCode] = doneByStage[stageCode] ? 'completed' : 'failed'
        return
      }

      if (hasSetupTransitionCompleted.value) {
        statuses[stageCode] = 'completed'
        return
      }

      if (activeIndex >= 0) {
        if (index < activeIndex || doneByStage[stageCode]) {
          statuses[stageCode] = 'completed'
        } else if (index === activeIndex) {
          statuses[stageCode] = 'running'
        } else {
          statuses[stageCode] = 'pending'
        }
        return
      }

      statuses[stageCode] = doneByStage[stageCode] ? 'completed' : 'pending'
    })

    return [
      { code: 'clean_fill', label: 'Набор бака с чистой водой', status: statuses.clean_fill },
      { code: 'solution_fill', label: 'Набор бака с раствором', status: statuses.solution_fill },
      { code: 'parallel_correction', label: 'Параллельная коррекция pH/EC', status: statuses.parallel_correction },
      { code: 'setup_transition', label: 'Завершение setup и переход в рабочий режим', status: statuses.setup_transition },
    ]
  })

  const currentSetupStageLabel = computed(() => {
    const running = setupStages.value.find((stage) => stage.status === 'running')
    if (running) return running.label

    const failed = setupStages.value.find((stage) => stage.status === 'failed')
    if (failed) return `${failed.label} (ошибка)`

    if (setupStages.value.every((stage) => stage.status === 'completed')) {
      return 'Setup завершен, система в рабочем режиме'
    }

    const pending = setupStages.value.find((stage) => stage.status === 'pending')
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
      if (subscribed) {
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
      if (subscribed) {
        scheduleRealtimeRefresh()
      } else {
        startFallbackPolling()
      }

      wsStateListenerCleanup = onWsStateChange((state) => {
        if (state === 'connected') {
          const resubscribed = subscribeRealtimeChannels()
          if (resubscribed) {
            stopFallbackPolling()
            scheduleRealtimeRefresh()
          } else {
            startFallbackPolling()
          }
          return
        }

        if (state === 'disconnected' || state === 'unavailable' || state === 'failed') {
          clearWsRefreshTimer()
          cleanupRealtimeChannels()
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
    setupStages,
    currentSetupStageLabel,
    progressSummary,
    timelineEvents,
    irrNodeState,
  }
}

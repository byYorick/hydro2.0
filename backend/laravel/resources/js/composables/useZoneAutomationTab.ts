import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { usePage } from '@inertiajs/vue3'
import { useCommands } from '@/composables/useCommands'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { logger } from '@/utils/logger'
import type { ZoneTargets as ZoneTargetsType, ZoneTelemetry } from '@/types'
import {
  applyAutomationFromRecipe,
  buildGrowthCycleConfigPayload,
  clamp,
  resetToRecommended as resetFormsToRecommended,
  syncSystemToTankLayout,
  type ClimateFormState,
  type IrrigationSystem,
  type LightingFormState,
  validateForms,
  type WaterFormState,
} from '@/composables/zoneAutomationFormLogic'

export type PredictionTargets = Record<string, { min?: number; max?: number }>

export interface ZoneAutomationTabProps {
  zoneId: number | null
  targets: ZoneTargetsType | PredictionTargets
  telemetry?: ZoneTelemetry | null
  activeGrowCycle?: { status?: string | null } | null
}

export interface SchedulerTaskLifecycleItem {
  status: string
  at: string | null
  error?: string | null
  source?: string | null
}

export interface SchedulerTaskTimelineItem {
  event_id: string
  event_seq?: number | null
  event_type: string
  type?: string | null
  at: string | null
  task_id?: string | null
  correlation_id?: string | null
  task_type?: string | null
  action_required?: boolean | null
  decision?: string | null
  reason_code?: string | null
  reason?: string | null
  node_uid?: string | null
  channel?: string | null
  cmd?: string | null
  error_code?: string | null
  command_submitted?: boolean | null
  command_effect_confirmed?: boolean | null
  terminal_status?: string | null
  source?: string | null
  details?: Record<string, unknown> | null
}

export interface SchedulerTaskStatus {
  task_id: string
  zone_id: number
  task_type: string | null
  status: string | null
  created_at: string | null
  updated_at: string | null
  scheduled_for: string | null
  due_at?: string | null
  expires_at?: string | null
  correlation_id: string | null
  result?: Record<string, unknown> | null
  error?: string | null
  error_code?: string | null
  action_required?: boolean | null
  decision?: string | null
  reason_code?: string | null
  reason?: string | null
  command_submitted?: boolean | null
  command_effect_confirmed?: boolean | null
  commands_total?: number | null
  commands_effect_confirmed?: number | null
  commands_failed?: number | null
  source?: string | null
  lifecycle: SchedulerTaskLifecycleItem[]
  timeline?: SchedulerTaskTimelineItem[]
}

interface SchedulerTasksResponse {
  status: string
  data?: SchedulerTaskStatus[]
}

interface SchedulerTaskResponse {
  status: string
  data?: SchedulerTaskStatus
}

type SchedulerTaskSlaVariant = 'success' | 'warning' | 'danger' | 'info' | 'secondary'

interface SchedulerTaskSlaMeta {
  variant: SchedulerTaskSlaVariant
  label: string
  hint: string
}

interface SchedulerTaskDoneMeta {
  variant: SchedulerTaskSlaVariant
  label: string
  hint: string
}

type SchedulerTaskPreset = 'all' | 'failed' | 'deadline' | 'done_confirmed' | 'done_unconfirmed'

function toFiniteNumber(value: unknown): number | null {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : null
  }

  if (typeof value === 'string') {
    const normalized = value.trim()
    if (normalized === '') return null

    const parsed = Number(normalized)
    return Number.isFinite(parsed) ? parsed : null
  }

  return null
}

const TARGET_SCHEDULER_STATUSES = ['accepted', 'running', 'completed', 'failed', 'rejected', 'expired'] as const
type TargetSchedulerStatus = (typeof TARGET_SCHEDULER_STATUSES)[number]

function normalizeTargetSchedulerStatus(status: string | null | undefined): TargetSchedulerStatus | null {
  const normalized = String(status ?? '').trim().toLowerCase()
  if (normalized === 'done') return 'completed'
  if (TARGET_SCHEDULER_STATUSES.includes(normalized as TargetSchedulerStatus)) {
    return normalized as TargetSchedulerStatus
  }
  return null
}

function toBoolean(value: unknown, fallback: boolean): boolean {
  if (typeof value === 'boolean') return value
  if (value === 1 || value === '1' || value === 'true') return true
  if (value === 0 || value === '0' || value === 'false') return false
  return fallback
}

function toNumber(value: unknown, fallback: number): number {
  const parsed = toFiniteNumber(value)
  return parsed === null ? fallback : parsed
}

function toRoundedNumber(value: unknown, fallback: number): number {
  return Math.round(toNumber(value, fallback))
}

function toTimeHHmm(value: unknown, fallback: string): string {
  if (typeof value !== 'string') return fallback
  const match = value.trim().match(/^(\d{1,2}):(\d{2})/)
  if (!match) return fallback
  const hours = Number(match[1])
  const minutes = Number(match[2])
  if (!Number.isInteger(hours) || !Number.isInteger(minutes) || hours < 0 || hours > 23 || minutes < 0 || minutes > 59) {
    return fallback
  }
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`
}

function toIrrigationSystem(value: unknown, fallback: IrrigationSystem): IrrigationSystem {
  if (value === 'drip' || value === 'substrate_trays' || value === 'nft') {
    return value
  }
  return fallback
}

function sanitizeClimateForm(raw: Partial<ClimateFormState> | undefined, fallback: ClimateFormState): ClimateFormState {
  return {
    enabled: toBoolean(raw?.enabled, fallback.enabled),
    dayTemp: clamp(toNumber(raw?.dayTemp, fallback.dayTemp), 10, 35),
    nightTemp: clamp(toNumber(raw?.nightTemp, fallback.nightTemp), 10, 35),
    dayHumidity: clamp(toNumber(raw?.dayHumidity, fallback.dayHumidity), 30, 90),
    nightHumidity: clamp(toNumber(raw?.nightHumidity, fallback.nightHumidity), 30, 90),
    dayStart: toTimeHHmm(raw?.dayStart, fallback.dayStart),
    nightStart: toTimeHHmm(raw?.nightStart, fallback.nightStart),
    ventMinPercent: clamp(toRoundedNumber(raw?.ventMinPercent, fallback.ventMinPercent), 0, 100),
    ventMaxPercent: clamp(toRoundedNumber(raw?.ventMaxPercent, fallback.ventMaxPercent), 0, 100),
    useExternalTelemetry: toBoolean(raw?.useExternalTelemetry, fallback.useExternalTelemetry),
    outsideTempMin: clamp(toNumber(raw?.outsideTempMin, fallback.outsideTempMin), -30, 45),
    outsideTempMax: clamp(toNumber(raw?.outsideTempMax, fallback.outsideTempMax), -30, 45),
    outsideHumidityMax: clamp(toRoundedNumber(raw?.outsideHumidityMax, fallback.outsideHumidityMax), 20, 100),
    manualOverrideEnabled: toBoolean(raw?.manualOverrideEnabled, fallback.manualOverrideEnabled),
    overrideMinutes: clamp(toRoundedNumber(raw?.overrideMinutes, fallback.overrideMinutes), 5, 120),
  }
}

function sanitizeWaterForm(raw: Partial<WaterFormState> | undefined, fallback: WaterFormState): WaterFormState {
  const systemType = toIrrigationSystem(raw?.systemType, fallback.systemType)
  const tanksRaw = toRoundedNumber(raw?.tanksCount, fallback.tanksCount)
  const tanksCount = tanksRaw === 3 ? 3 : 2

  const sanitized: WaterFormState = {
    systemType,
    tanksCount,
    cleanTankFillL: clamp(toRoundedNumber(raw?.cleanTankFillL, fallback.cleanTankFillL), 10, 5000),
    nutrientTankTargetL: clamp(toRoundedNumber(raw?.nutrientTankTargetL, fallback.nutrientTankTargetL), 10, 5000),
    irrigationBatchL: clamp(toRoundedNumber(raw?.irrigationBatchL, fallback.irrigationBatchL), 1, 500),
    intervalMinutes: clamp(toRoundedNumber(raw?.intervalMinutes, fallback.intervalMinutes), 5, 1440),
    durationSeconds: clamp(toRoundedNumber(raw?.durationSeconds, fallback.durationSeconds), 1, 3600),
    fillTemperatureC: clamp(toNumber(raw?.fillTemperatureC, fallback.fillTemperatureC), 5, 35),
    fillWindowStart: toTimeHHmm(raw?.fillWindowStart, fallback.fillWindowStart),
    fillWindowEnd: toTimeHHmm(raw?.fillWindowEnd, fallback.fillWindowEnd),
    targetPh: clamp(toNumber(raw?.targetPh, fallback.targetPh), 4, 9),
    targetEc: clamp(toNumber(raw?.targetEc, fallback.targetEc), 0.1, 10),
    valveSwitching: toBoolean(raw?.valveSwitching, fallback.valveSwitching),
    correctionDuringIrrigation: toBoolean(raw?.correctionDuringIrrigation, fallback.correctionDuringIrrigation),
    enableDrainControl: toBoolean(raw?.enableDrainControl, fallback.enableDrainControl),
    drainTargetPercent: clamp(toRoundedNumber(raw?.drainTargetPercent, fallback.drainTargetPercent), 0, 100),
    manualIrrigationSeconds: clamp(
      toRoundedNumber(raw?.manualIrrigationSeconds, fallback.manualIrrigationSeconds),
      1,
      3600
    ),
  }

  syncSystemToTankLayout(sanitized, sanitized.systemType)
  sanitized.tanksCount = sanitized.systemType === 'drip' ? 2 : tanksCount
  if (sanitized.tanksCount === 2) {
    sanitized.enableDrainControl = false
  }
  return sanitized
}

function sanitizeLightingForm(raw: Partial<LightingFormState> | undefined, fallback: LightingFormState): LightingFormState {
  return {
    enabled: toBoolean(raw?.enabled, fallback.enabled),
    luxDay: clamp(toRoundedNumber(raw?.luxDay, fallback.luxDay), 0, 120000),
    luxNight: clamp(toRoundedNumber(raw?.luxNight, fallback.luxNight), 0, 120000),
    hoursOn: clamp(toNumber(raw?.hoursOn, fallback.hoursOn), 0, 24),
    scheduleStart: toTimeHHmm(raw?.scheduleStart, fallback.scheduleStart),
    scheduleEnd: toTimeHHmm(raw?.scheduleEnd, fallback.scheduleEnd),
    manualIntensity: clamp(toRoundedNumber(raw?.manualIntensity, fallback.manualIntensity), 0, 100),
    manualDurationHours: clamp(toNumber(raw?.manualDurationHours, fallback.manualDurationHours), 0.5, 24),
  }
}

export function useZoneAutomationTab(props: ZoneAutomationTabProps) {
  const page = usePage<{ auth?: { user?: { role?: string } } }>()
  const { showToast } = useToast()
  const { sendZoneCommand } = useCommands(showToast)
  const { get } = useApi(showToast)

  const role = computed(() => page.props.auth?.user?.role ?? 'viewer')
  const canConfigureAutomation = computed(() => role.value === 'agronomist' || role.value === 'admin')
  const canOperateAutomation = computed(
    () => role.value === 'agronomist' || role.value === 'admin' || role.value === 'operator' || role.value === 'engineer'
  )
  const isSystemTypeLocked = computed(() => {
    const status = String(props.activeGrowCycle?.status ?? '').toUpperCase()
    return status === 'RUNNING' || status === 'PAUSED' || status === 'PLANNED'
  })

  const climateForm = reactive<ClimateFormState>({
    enabled: true,
    dayTemp: 23,
    nightTemp: 20,
    dayHumidity: 62,
    nightHumidity: 70,
    dayStart: '07:00',
    nightStart: '19:00',
    ventMinPercent: 15,
    ventMaxPercent: 85,
    useExternalTelemetry: true,
    outsideTempMin: 4,
    outsideTempMax: 34,
    outsideHumidityMax: 90,
    manualOverrideEnabled: true,
    overrideMinutes: 30,
  })

  const waterForm = reactive<WaterFormState>({
    systemType: 'drip' as IrrigationSystem,
    tanksCount: 2,
    cleanTankFillL: 300,
    nutrientTankTargetL: 280,
    irrigationBatchL: 20,
    intervalMinutes: 30,
    durationSeconds: 120,
    fillTemperatureC: 20,
    fillWindowStart: '05:00',
    fillWindowEnd: '07:00',
    targetPh: 5.8,
    targetEc: 1.6,
    valveSwitching: true,
    correctionDuringIrrigation: true,
    enableDrainControl: false,
    drainTargetPercent: 20,
    manualIrrigationSeconds: 90,
  })

  const lightingForm = reactive<LightingFormState>({
    enabled: true,
    luxDay: 18000,
    luxNight: 0,
    hoursOn: 16,
    scheduleStart: '06:00',
    scheduleEnd: '22:00',
    manualIntensity: 75,
    manualDurationHours: 4,
  })

  const quickActions = reactive({
    irrigation: false,
    climate: false,
    lighting: false,
    ph: false,
    ec: false,
  })

  const isApplyingProfile = ref(false)
  const isHydratingProfile = ref(false)
  const lastAppliedAt = ref<string | null>(null)
  const schedulerTaskIdInput = ref('')
  const schedulerTaskLookupLoading = ref(false)
  const schedulerTaskListLoading = ref(false)
  const schedulerTaskError = ref<string | null>(null)
  const schedulerTaskStatus = ref<SchedulerTaskStatus | null>(null)
  const recentSchedulerTasks = ref<SchedulerTaskStatus[]>([])
  const schedulerTaskSearch = ref('')
  const schedulerTaskPreset = ref<SchedulerTaskPreset>('all')
  const schedulerTasksUpdatedAt = ref<string | null>(null)
  const pendingTargetsSyncForZoneChange = ref(false)
  let schedulerTasksPollTimer: ReturnType<typeof setTimeout> | null = null
  let schedulerTaskListRequestVersion = 0
  let schedulerTaskLookupRequestVersion = 0

  const schedulerTaskPresetOptions: Array<{ value: SchedulerTaskPreset; label: string }> = [
    { value: 'all', label: 'Все' },
    { value: 'failed', label: 'Ошибки' },
    { value: 'deadline', label: 'Дедлайны' },
    { value: 'done_confirmed', label: 'DONE подтвержден' },
    { value: 'done_unconfirmed', label: 'DONE не подтвержден' },
  ]

  const predictionTargets = computed<PredictionTargets>(() => {
    const targets = props.targets
    if (!targets || typeof targets !== 'object') return {}

    if ('ph_min' in targets || 'ec_min' in targets || 'temp_min' in targets || 'humidity_min' in targets) {
      const legacy = targets as ZoneTargetsType
      return {
        ph: { min: legacy.ph_min, max: legacy.ph_max },
        ec: { min: legacy.ec_min, max: legacy.ec_max },
        temp_air: { min: legacy.temp_min, max: legacy.temp_max },
        humidity_air: { min: legacy.humidity_min, max: legacy.humidity_max },
      }
    }

    return targets as PredictionTargets
  })

  const telemetryLabel = computed(() => {
    const temperature = toFiniteNumber(props.telemetry?.temperature)
    const humidity = toFiniteNumber(props.telemetry?.humidity)

    if (temperature === null || humidity === null) {
      return 'нет данных'
    }

    return `${temperature.toFixed(1)}°C / ${humidity.toFixed(0)}%`
  })

  const waterTopologyLabel = computed(() => {
    if (waterForm.tanksCount === 2) {
      return 'Чистая вода + раствор'
    }

    return 'Чистая вода + раствор + дренаж'
  })

  const profileStorageKey = computed(() => {
    return props.zoneId ? `zone:${props.zoneId}:automation-profile:v2` : null
  })

  function normalizeTaskId(rawValue?: string): string {
    const source = typeof rawValue === 'string' ? rawValue : schedulerTaskIdInput.value
    return source.trim()
  }

  function schedulerTaskStatusVariant(status: string | null | undefined): 'success' | 'warning' | 'danger' | 'info' | 'secondary' {
    const normalized = normalizeTargetSchedulerStatus(status)
    if (normalized === 'completed') return 'success'
    if (normalized === 'failed' || normalized === 'rejected' || normalized === 'expired') return 'danger'
    if (normalized === 'running') return 'warning'
    if (normalized === 'accepted') return 'info'

    return 'secondary'
  }

  function schedulerTaskStatusLabel(status: string | null | undefined): string {
    const normalized = normalizeTargetSchedulerStatus(status)
    if (normalized === 'accepted') return 'Принята'
    if (normalized === 'running') return 'Выполняется'
    if (normalized === 'completed') return 'Выполнена'
    if (normalized === 'failed') return 'Ошибка'
    if (normalized === 'rejected') return 'Отклонена'
    if (normalized === 'expired') return 'Просрочена'

    return 'Неизвестно'
  }

  function schedulerTaskEventLabel(eventType: string | null | undefined): string {
    const normalized = String(eventType ?? '').toUpperCase()
    if (normalized === 'TASK_RECEIVED') return 'Задача получена'
    if (normalized === 'TASK_STARTED') return 'Выполнение начато'
    if (normalized === 'DECISION_MADE') return 'Решение принято'
    if (normalized === 'COMMAND_DISPATCHED') return 'Команда отправлена'
    if (normalized === 'COMMAND_FAILED') return 'Ошибка отправки команды'
    if (normalized === 'COMMAND_EFFECT_NOT_CONFIRMED') return 'Команда не подтверждена нодой (не DONE)'
    if (normalized === 'TASK_FINISHED') return 'Задача завершена'
    if (normalized === 'SCHEDULE_TASK_EXECUTION_STARTED') return 'Automation-engine: execution started'
    if (normalized === 'SCHEDULE_TASK_EXECUTION_FINISHED') return 'Automation-engine: execution finished'
    if (normalized === 'DIAGNOSTICS_SERVICE_UNAVAILABLE') return 'Diagnostics service недоступен'
    if (normalized === 'CYCLE_START_INITIATED') return 'Запуск цикла инициирован'
    if (normalized === 'NODES_AVAILABILITY_CHECKED') return 'Проверена доступность нод'
    if (normalized === 'TANK_LEVEL_CHECKED') return 'Проверен уровень бака'
    if (normalized === 'TANK_LEVEL_STALE') return 'Телеметрия бака устарела'
    if (normalized === 'TANK_REFILL_STARTED') return 'Запущено наполнение бака'
    if (normalized === 'TANK_REFILL_COMPLETED') return 'Наполнение бака завершено'
    if (normalized === 'TANK_REFILL_TIMEOUT') return 'Таймаут наполнения бака'
    if (normalized === 'SELF_TASK_ENQUEUED') return 'Запланирована отложенная проверка'
    if (normalized === 'SELF_TASK_DISPATCHED') return 'Отложенная задача отправлена'
    if (normalized === 'SELF_TASK_DISPATCH_FAILED') return 'Отложенная задача не отправлена'
    if (normalized === 'SELF_TASK_EXPIRED') return 'Отложенная задача просрочена'
    if (normalized === 'SCHEDULE_TASK_ACCEPTED') return 'Scheduler: задача принята'
    if (normalized === 'SCHEDULE_TASK_COMPLETED') return 'Scheduler: задача завершена'
    if (normalized === 'SCHEDULE_TASK_FAILED') return 'Scheduler: задача завершилась с ошибкой'

    return eventType ? String(eventType) : 'Событие'
  }

  function schedulerTaskDecisionLabel(decision: string | null | undefined): string {
    const normalized = String(decision ?? '').toLowerCase()
    if (normalized === 'execute') return 'Выполнить'
    if (normalized === 'skip') return 'Пропустить'
    return decision ? String(decision) : '-'
  }

  function schedulerTaskReasonLabel(reasonCode: string | null | undefined, reasonText?: string | null): string {
    const normalized = String(reasonCode ?? '').trim().toLowerCase()
    if (!normalized) return reasonText ? String(reasonText) : '-'

    const reasonMap: Record<string, string> = {
      task_due_deadline_exceeded: 'Задача отклонена: пропущен дедлайн due_at',
      task_expired: 'Задача просрочена: превышен expires_at',
      command_bus_unavailable: 'CommandBus недоступен',
      execution_exception: 'Исключение во время исполнения',
      task_execution_failed: 'Исполнение завершилось с ошибкой',
      required_nodes_checked: 'Проверка обязательных нод выполнена',
      tank_level_checked: 'Проверка уровня бака выполнена',
      tank_refill_required: 'Требуется наполнение бака',
      tank_refill_started: 'Наполнение бака запущено',
      tank_refill_in_progress: 'Наполнение бака в процессе',
      tank_refill_completed: 'Наполнение бака завершено',
      tank_refill_not_required: 'Наполнение бака не требуется',
      cycle_start_blocked_nodes_unavailable: 'Старт цикла заблокирован: недоступны обязательные ноды',
      cycle_start_tank_level_unavailable: 'Старт цикла заблокирован: нет данных уровня бака',
      cycle_start_tank_level_stale: 'Старт цикла заблокирован: телеметрия уровня бака устарела',
      cycle_start_refill_timeout: 'Таймаут наполнения бака',
      cycle_start_refill_command_failed: 'Ошибка отправки команды наполнения бака',
      cycle_start_self_task_enqueue_failed: 'Не удалось запланировать отложенную проверку',
      lighting_already_in_target_state: 'Свет уже в целевом состоянии',
    }
    if (reasonMap[normalized]) return `${reasonMap[normalized]} (${normalized})`
    if (normalized.endsWith('_not_required')) return `Действие не требуется (${normalized})`
    if (normalized.endsWith('_required')) return `Действие требуется (${normalized})`
    return reasonText ? `${reasonText} (${normalized})` : normalized
  }

  function schedulerTaskErrorLabel(errorCode: string | null | undefined, errorText?: string | null): string {
    const normalized = String(errorCode ?? '').trim().toLowerCase()
    if (!normalized) return errorText ? String(errorText) : '-'

    const errorMap: Record<string, string> = {
      task_due_deadline_exceeded: 'Превышен дедлайн due_at',
      task_expired: 'Превышен срок expires_at',
      command_publish_failed: 'Ошибка отправки команды',
      command_send_failed: 'Команда не отправлена',
      command_timeout: 'Таймаут ожидания DONE от ноды',
      command_error: 'Нода вернула ERROR',
      command_invalid: 'Нода вернула INVALID',
      command_busy: 'Нода вернула BUSY',
      command_no_effect: 'Нода вернула NO_EFFECT',
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
      command_bus_unavailable: 'CommandBus недоступен',
      execution_exception: 'Исключение во время выполнения задачи',
      task_execution_failed: 'Задача завершилась с ошибкой',
    }
    if (errorMap[normalized]) return `${errorMap[normalized]} (${normalized})`
    return errorText ? `${errorText} (${normalized})` : normalized
  }

  function normalizeOptionalBool(value: unknown): boolean | null {
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

  function resolveTaskCommandSubmitted(task: SchedulerTaskStatus | null | undefined): boolean | null {
    if (!task) return null
    const fromRoot = normalizeOptionalBool(task.command_submitted)
    if (fromRoot !== null) return fromRoot
    const fromResult = normalizeOptionalBool(task.result?.command_submitted)
    return fromResult
  }

  function resolveTaskCommandEffectConfirmed(task: SchedulerTaskStatus | null | undefined): boolean | null {
    if (!task) return null
    const fromRoot = normalizeOptionalBool(task.command_effect_confirmed)
    if (fromRoot !== null) return fromRoot
    const fromResult = normalizeOptionalBool(task.result?.command_effect_confirmed)
    return fromResult
  }

  function resolveTaskCommandsTotal(task: SchedulerTaskStatus | null | undefined): number | null {
    const direct = toFiniteNumber(task?.commands_total ?? null)
    if (direct !== null) return Math.max(0, Math.round(direct))
    const fromResult = toFiniteNumber(task?.result?.commands_total)
    if (fromResult !== null) return Math.max(0, Math.round(fromResult))
    return null
  }

  function resolveTaskCommandsEffectConfirmed(task: SchedulerTaskStatus | null | undefined): number | null {
    const direct = toFiniteNumber(task?.commands_effect_confirmed ?? null)
    if (direct !== null) return Math.max(0, Math.round(direct))
    const fromResult = toFiniteNumber(task?.result?.commands_effect_confirmed)
    if (fromResult !== null) return Math.max(0, Math.round(fromResult))
    return null
  }

  function normalizeIsoInput(rawValue: string): string {
    const raw = rawValue.trim()
    if (!raw) return raw

    const hasTimezone = /(?:Z|z|[+-]\d{2}:\d{2})$/.test(raw)
    const looksIsoDateTime = /^\d{4}-\d{2}-\d{2}T/.test(raw)
    if (looksIsoDateTime && !hasTimezone) {
      return `${raw}Z`
    }
    return raw
  }

  function schedulerTaskDoneMeta(task: SchedulerTaskStatus | null | undefined): SchedulerTaskDoneMeta {
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

  function parseIsoDate(value: string | null | undefined): Date | null {
    const raw = normalizeIsoInput(String(value ?? ''))
    if (!raw) return null
    const parsed = new Date(raw)
    return Number.isNaN(parsed.getTime()) ? null : parsed
  }

  function formatRelativeMs(ms: number): string {
    const totalSeconds = Math.max(0, Math.round(ms / 1000))
    const minutes = Math.floor(totalSeconds / 60)
    const seconds = totalSeconds % 60
    if (minutes <= 0) return `${seconds}с`
    if (minutes < 60) return `${minutes}м ${seconds}с`
    const hours = Math.floor(minutes / 60)
    const restMinutes = minutes % 60
    return `${hours}ч ${restMinutes}м`
  }

  function schedulerTaskSlaMeta(task: SchedulerTaskStatus | null | undefined): SchedulerTaskSlaMeta {
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
    if (scheduledFor) windowParts.push(`scheduled: ${formatDateTime(task.scheduled_for ?? null)}`)
    if (dueAt) windowParts.push(`due: ${formatDateTime(task.due_at ?? null)}`)
    if (expiresAt) windowParts.push(`expires: ${formatDateTime(task.expires_at ?? null)}`)
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

  function taskMatchesPreset(task: SchedulerTaskStatus, preset: SchedulerTaskPreset): boolean {
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

  function taskMatchesSearch(task: SchedulerTaskStatus, rawQuery: string): boolean {
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

  const filteredRecentSchedulerTasks = computed(() => {
    return recentSchedulerTasks.value.filter((task) => {
      return taskMatchesPreset(task, schedulerTaskPreset.value) && taskMatchesSearch(task, schedulerTaskSearch.value)
    })
  })

  watch(
    () => waterForm.systemType,
    (value) => syncSystemToTankLayout(waterForm, value),
    { immediate: true }
  )

  function saveProfileToStorage(): void {
    if (isHydratingProfile.value) return
    if (typeof window === 'undefined' || !profileStorageKey.value) return

    const payload = {
      climate: { ...climateForm },
      water: { ...waterForm },
      lighting: { ...lightingForm },
      lastAppliedAt: lastAppliedAt.value,
    }

    window.localStorage.setItem(profileStorageKey.value, JSON.stringify(payload))
  }

  function loadProfileFromStorage(): void {
    if (typeof window === 'undefined' || !profileStorageKey.value) return

    const raw = window.localStorage.getItem(profileStorageKey.value)
    if (!raw) return

    try {
      const parsed = JSON.parse(raw) as {
        climate?: Partial<ClimateFormState>
        water?: Partial<WaterFormState>
        lighting?: Partial<LightingFormState>
        lastAppliedAt?: string | null
      }

      if (parsed.climate) {
        Object.assign(climateForm, sanitizeClimateForm(parsed.climate, climateForm))
      }
      if (parsed.water) {
        Object.assign(waterForm, sanitizeWaterForm(parsed.water, waterForm))
      }
      if (parsed.lighting) {
        Object.assign(lightingForm, sanitizeLightingForm(parsed.lighting, lightingForm))
      }

      const parsedLastAppliedAt = parseIsoDate(parsed.lastAppliedAt ?? null)
      lastAppliedAt.value = parsedLastAppliedAt ? parsedLastAppliedAt.toISOString() : null
    } catch (error) {
      logger.warn('[ZoneAutomationTab] Failed to parse stored automation profile', { error })
    }
  }

  watch(climateForm, saveProfileToStorage, { deep: true })
  watch(waterForm, saveProfileToStorage, { deep: true })
  watch(lightingForm, saveProfileToStorage, { deep: true })
  watch(lastAppliedAt, saveProfileToStorage)

  function hydrateAutomationProfileFromCurrentZone(options?: { includeTargets?: boolean }): void {
    const includeTargets = options?.includeTargets ?? true
    isHydratingProfile.value = true
    try {
      resetFormsToRecommended({ climateForm, waterForm, lightingForm })
      lastAppliedAt.value = null
      loadProfileFromStorage()
      if (includeTargets) {
        applyAutomationFromRecipe(props.targets, { climateForm, waterForm, lightingForm })
      }
    } finally {
      isHydratingProfile.value = false
    }
  }

  onMounted(() => {
    hydrateAutomationProfileFromCurrentZone({ includeTargets: true })
    void fetchRecentSchedulerTasks()
    if (import.meta.env.MODE !== 'test') {
      void pollSchedulerTasksCycle()
      if (typeof document !== 'undefined') {
        document.addEventListener('visibilitychange', handleVisibilityChange)
      }
    }
  })

  onUnmounted(() => {
    clearSchedulerTasksPollTimer()
    if (typeof document !== 'undefined') {
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  })

  watch(
    () => props.zoneId,
    () => {
      pendingTargetsSyncForZoneChange.value = true
      schedulerTaskListRequestVersion += 1
      schedulerTaskLookupRequestVersion += 1
      schedulerTaskIdInput.value = ''
      schedulerTaskStatus.value = null
      recentSchedulerTasks.value = []
      schedulerTaskError.value = null
      schedulerTasksUpdatedAt.value = null
      schedulerTaskListLoading.value = false
      schedulerTaskLookupLoading.value = false
      hydrateAutomationProfileFromCurrentZone({ includeTargets: false })
      void fetchRecentSchedulerTasks()
      scheduleSchedulerTasksPoll()
    }
  )

  watch(
    () => props.targets,
    (targets) => {
      applyAutomationFromRecipe(targets, { climateForm, waterForm, lightingForm })
      pendingTargetsSyncForZoneChange.value = false
    },
    { deep: true }
  )

  async function fetchRecentSchedulerTasks(): Promise<void> {
    if (!props.zoneId) {
      recentSchedulerTasks.value = []
      schedulerTasksUpdatedAt.value = null
      schedulerTaskListLoading.value = false
      return
    }

    const requestZoneId = props.zoneId
    const requestVersion = ++schedulerTaskListRequestVersion
    schedulerTaskListLoading.value = true
    schedulerTaskError.value = null
    try {
      const response = await get<SchedulerTasksResponse>(`/api/zones/${requestZoneId}/scheduler-tasks`, {
        params: { limit: 20 },
      })

      if (requestVersion !== schedulerTaskListRequestVersion || requestZoneId !== props.zoneId) {
        return
      }

      const items = Array.isArray(response.data?.data) ? response.data.data : []
      recentSchedulerTasks.value = items
      schedulerTasksUpdatedAt.value = new Date().toISOString()
    } catch (error) {
      if (requestVersion !== schedulerTaskListRequestVersion || requestZoneId !== props.zoneId) {
        return
      }
      logger.warn('[ZoneAutomationTab] Failed to fetch scheduler tasks', { error, zoneId: props.zoneId })
      schedulerTaskError.value = 'Не удалось получить список scheduler-задач.'
    } finally {
      if (requestVersion === schedulerTaskListRequestVersion && requestZoneId === props.zoneId) {
        schedulerTaskListLoading.value = false
      }
    }
  }

  async function lookupSchedulerTask(taskIdRaw?: string): Promise<void> {
    if (!props.zoneId) return

    const taskId = normalizeTaskId(taskIdRaw)
    if (!taskId) {
      schedulerTaskStatus.value = null
      schedulerTaskError.value = 'Укажите task_id вида st-...'
      return
    }

    const requestZoneId = props.zoneId
    const requestVersion = ++schedulerTaskLookupRequestVersion
    schedulerTaskLookupLoading.value = true
    schedulerTaskError.value = null
    try {
      const response = await get<SchedulerTaskResponse>(`/api/zones/${requestZoneId}/scheduler-tasks/${encodeURIComponent(taskId)}`)

      if (requestVersion !== schedulerTaskLookupRequestVersion || requestZoneId !== props.zoneId) {
        return
      }

      schedulerTaskStatus.value = response.data?.data ?? null
      schedulerTaskIdInput.value = taskId
    } catch (error: any) {
      if (requestVersion !== schedulerTaskLookupRequestVersion || requestZoneId !== props.zoneId) {
        return
      }
      logger.warn('[ZoneAutomationTab] Failed to lookup scheduler task', { error, zoneId: props.zoneId, taskId })
      schedulerTaskStatus.value = null
      schedulerTaskError.value = error?.response?.data?.message ?? 'Не удалось получить статус задачи.'
    } finally {
      if (requestVersion === schedulerTaskLookupRequestVersion && requestZoneId === props.zoneId) {
        schedulerTaskLookupLoading.value = false
        scheduleSchedulerTasksPoll()
      }
    }
  }

  async function applyAutomationProfile(): Promise<boolean> {
    if (!props.zoneId || isApplyingProfile.value) return false

    if (!canConfigureAutomation.value) {
      showToast('Изменение профиля доступно только агроному.', 'warning')
      return false
    }

    const validationError = validateForms({ climateForm, waterForm })
    if (validationError) {
      showToast(validationError, 'error')
      return false
    }

    isApplyingProfile.value = true

    try {
      const payload = buildGrowthCycleConfigPayload(
        { climateForm, waterForm, lightingForm },
        { includeSystemType: !isSystemTypeLocked.value }
      )
      await sendZoneCommand(props.zoneId, 'GROWTH_CYCLE_CONFIG', payload)
      lastAppliedAt.value = new Date().toISOString()
      showToast('Профиль автоматики отправлен в scheduler.', 'success')
      return true
    } catch (error) {
      logger.error('[ZoneAutomationTab] Failed to apply automation profile', { error })
      return false
    } finally {
      isApplyingProfile.value = false
    }
  }

  function resetToRecommended(): void {
    resetFormsToRecommended({ climateForm, waterForm, lightingForm })
  }

  async function withQuickAction(key: keyof typeof quickActions, callback: () => Promise<void>): Promise<void> {
    if (quickActions[key]) return

    if (!canOperateAutomation.value) {
      showToast('Команды выполнения доступны оператору и агроному.', 'warning')
      return
    }

    quickActions[key] = true
    try {
      await callback()
    } catch (error) {
      logger.error('[ZoneAutomationTab] Quick action failed', { key, error })
    } finally {
      quickActions[key] = false
    }
  }

  async function runManualIrrigation(): Promise<void> {
    if (!props.zoneId) return

    await withQuickAction('irrigation', async () => {
      await sendZoneCommand(props.zoneId as number, 'FORCE_IRRIGATION', {
        duration_sec: clamp(Math.round(waterForm.manualIrrigationSeconds), 1, 3600),
      })
    })
  }

  async function runManualClimate(): Promise<void> {
    if (!props.zoneId) return

    await withQuickAction('climate', async () => {
      await sendZoneCommand(props.zoneId as number, 'FORCE_CLIMATE', {
        target_temp: clamp(climateForm.dayTemp, 10, 35),
        target_humidity: clamp(climateForm.dayHumidity, 30, 90),
      })
    })
  }

  async function runManualLighting(): Promise<void> {
    if (!props.zoneId) return

    await withQuickAction('lighting', async () => {
      await sendZoneCommand(props.zoneId as number, 'FORCE_LIGHTING', {
        intensity: clamp(Math.round(lightingForm.manualIntensity), 0, 100),
        duration_hours: clamp(lightingForm.manualDurationHours, 0.5, 24),
      })
    })
  }

  async function runManualPh(): Promise<void> {
    if (!props.zoneId) return

    await withQuickAction('ph', async () => {
      await sendZoneCommand(props.zoneId as number, 'FORCE_PH_CONTROL', {
        target_ph: clamp(waterForm.targetPh, 4, 9),
      })
    })
  }

  async function runManualEc(): Promise<void> {
    if (!props.zoneId) return

    await withQuickAction('ec', async () => {
      await sendZoneCommand(props.zoneId as number, 'FORCE_EC_CONTROL', {
        target_ec: clamp(waterForm.targetEc, 0.1, 10),
      })
    })
  }

  function formatDateTime(value: string | null): string {
    const parsed = parseIsoDate(value)
    if (!parsed) return '-'
    return parsed.toLocaleString('ru-RU')
  }

  function clearSchedulerTasksPollTimer(): void {
    if (schedulerTasksPollTimer) {
      clearTimeout(schedulerTasksPollTimer)
      schedulerTasksPollTimer = null
    }
  }

  function hasActiveSchedulerTask(): boolean {
    const isActive = (status: string | null | undefined): boolean => {
      const normalized = normalizeTargetSchedulerStatus(status)
      return normalized === 'accepted' || normalized === 'running'
    }

    if (isActive(schedulerTaskStatus.value?.status)) return true
    return recentSchedulerTasks.value.some((task) => isActive(task.status))
  }

  function getSchedulerPollDelayMs(): number {
    return hasActiveSchedulerTask() ? 3000 : 15000
  }

  function scheduleSchedulerTasksPoll(): void {
    if (import.meta.env.MODE === 'test') return
    if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return

    clearSchedulerTasksPollTimer()
    schedulerTasksPollTimer = setTimeout(() => {
      void pollSchedulerTasksCycle()
    }, getSchedulerPollDelayMs())
  }

  async function pollSchedulerTasksCycle(): Promise<void> {
    await fetchRecentSchedulerTasks()
    scheduleSchedulerTasksPoll()
  }

  function handleVisibilityChange(): void {
    if (typeof document === 'undefined') return
    if (document.visibilityState === 'visible') {
      void pollSchedulerTasksCycle()
      return
    }
    clearSchedulerTasksPollTimer()
  }

  return {
    role,
    canConfigureAutomation,
    canOperateAutomation,
    isSystemTypeLocked,
    climateForm,
    waterForm,
    lightingForm,
    quickActions,
    isApplyingProfile,
    lastAppliedAt,
    predictionTargets,
    telemetryLabel,
    waterTopologyLabel,
    applyAutomationProfile,
    resetToRecommended,
    runManualIrrigation,
    runManualClimate,
    runManualLighting,
    runManualPh,
    runManualEc,
    schedulerTaskIdInput,
    schedulerTaskLookupLoading,
    schedulerTaskListLoading,
    schedulerTaskError,
    schedulerTaskStatus,
    recentSchedulerTasks,
    filteredRecentSchedulerTasks,
    schedulerTaskSearch,
    schedulerTaskPreset,
    schedulerTaskPresetOptions,
    schedulerTasksUpdatedAt,
    fetchRecentSchedulerTasks,
    lookupSchedulerTask,
    schedulerTaskStatusVariant,
    schedulerTaskStatusLabel,
    schedulerTaskEventLabel,
    schedulerTaskDecisionLabel,
    schedulerTaskReasonLabel,
    schedulerTaskErrorLabel,
    schedulerTaskSlaMeta,
    schedulerTaskDoneMeta,
    formatDateTime,
  }
}

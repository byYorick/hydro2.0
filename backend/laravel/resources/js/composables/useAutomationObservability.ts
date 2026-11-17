import { computed, onMounted, onUnmounted, ref } from 'vue'
import { router } from '@inertiajs/vue3'
import type { AutomationObservability, AutomationState } from '@/types/Automation'
import {
  formatActiveDosesLabel,
  formatObservabilityDuration,
  observabilityHealthLabel,
  isSkipStillBlocking,
  resolveCorrectionDosingDiagnostics,
  resolveObservability,
} from '@/utils/automationObservability'
import { resolveAutomationFailureDiagnostics } from '@/utils/automationFailureDiagnostics'
import { processStageLabel as stageDiagnosticLabel, processComponentLabel } from '@/utils/automationProcessLabels'
import { statusLabel } from '@/utils/schedulerLabels'


export function useAutomationObservability(props: { automationState: AutomationState | null }) {
const tickMs = ref(Date.now())
let tickTimer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  tickTimer = setInterval(() => {
    tickMs.value = Date.now()
  }, 1000)
})

onUnmounted(() => {
  if (tickTimer) {
    clearInterval(tickTimer)
    tickTimer = null
  }
})

function parseIsoMs(value: string | null | undefined): number | null {
  if (!value) return null
  const ms = Date.parse(value)
  return Number.isFinite(ms) ? ms : null
}


const observability = computed<AutomationObservability | null>(() => resolveObservability(props.automationState))

const failureDiagnostics = computed(() => resolveAutomationFailureDiagnostics(
  props.automationState,
  observability.value,
))

function toPositiveId(value: unknown): number | null {
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null
}

const causalStrip = computed(() => {
  const runtime = observability.value?.runtime
  const correction = observability.value?.correction
  const zoneId = toPositiveId(props.automationState?.zone_id ?? runtime?.zone_id)
  const normalizedTaskId = toPositiveId(
    runtime?.task_id
    ?? props.automationState?.state_details?.failed_task_id
    ?? props.automationState?.last_terminal_failure?.task_id,
  )
  const correctionStep = typeof runtime?.correction_step === 'string' && runtime.correction_step.trim() !== ''
    ? runtime.correction_step.trim()
    : null
  const skipRaw = correction?.latest_skip ?? null
  const skip = isSkipStillBlocking(skipRaw) ? skipRaw : null
  const skipType = typeof skip?.event_type === 'string' ? skip.event_type : null
  const skipEventId = toPositiveId(skip?.event_id)
  const phNoEffect = correction?.last_dose?.ph?.no_effect_count
  const ecNoEffect = correction?.last_dose?.ec?.no_effect_count
  const waiting = runtime?.waiting_command === true
  const taskStatus = typeof runtime?.task_status === 'string' ? runtime.task_status : null

  const hasSignal = normalizedTaskId != null
    || correctionStep != null
    || skipType != null
    || (typeof phNoEffect === 'number' && Number.isFinite(phNoEffect) && phNoEffect > 0)
    || (typeof ecNoEffect === 'number' && Number.isFinite(ecNoEffect) && ecNoEffect > 0)
  if (!hasSignal) {
    return null
  }

  const chain: string[] = []
  if (normalizedTaskId != null) {
    chain.push(`Задача №${normalizedTaskId}`)
  }
  if (taskStatus) {
    const alreadyWaiting = taskStatus === 'waiting_command'
    chain.push(waiting && !alreadyWaiting ? `${statusLabel(taskStatus)} · ожидание ответа устройства` : statusLabel(taskStatus))
  }
  if (correctionStep) {
    chain.push(stageDiagnosticLabel(correctionStep))
  }
  if (skipType) {
    chain.push('Коррекция отложена')
  }

  const details: string[] = []
  if (taskStatus) details.push(`task_status=${taskStatus}`)
  if (correctionStep) details.push(`correction_step=${correctionStep}`)
  if (skipType) details.push(`skip_type=${skipType}`)
  if (skipEventId != null) {
    details.push(`skip_event_id=${skipEventId}`)
  }
  if (skip?.age_sec != null) {
    details.push(`skip_age=${formatObservabilityDuration(skip.age_sec)}`)
  }
  if (typeof phNoEffect === 'number') {
    details.push(`ph_no_effect=${phNoEffect}`)
  }
  if (typeof ecNoEffect === 'number') {
    details.push(`ec_no_effect=${ecNoEffect}`)
  }

  return {
    zoneId,
    taskId: normalizedTaskId,
    summary: chain.length > 0 ? chain.join(' → ') : 'Контекст коррекции',
    details,
  }
})

function openTaskEvents(zoneId: number, taskId: number): void {
  router.visit(`/zones/${zoneId}?tab=events&task_id=${taskId}`)
}

const hangHints = computed(() => observability.value?.hang_hints ?? [])

const correctionDosing = computed(() => resolveCorrectionDosingDiagnostics(
  props.automationState,
  observability.value,
))

const activeDosesLabel = computed(() => formatActiveDosesLabel(correctionDosing.value?.activeDoses))

const prepareBaseline = computed(() => observability.value?.correction?.prepare_baseline ?? null)
const correctionPipeline = computed(() => observability.value?.correction?.pipeline ?? null)

const ratioSummary = computed(() => formatComponentMap(prepareBaseline.value?.ratios ?? null))
const targetSummary = computed(() => {
  const fromBaseline = formatComponentMap(prepareBaseline.value?.component_targets ?? null)
  if (fromBaseline) {
    return fromBaseline
  }
  return formatComponentMap(correctionPipeline.value?.component_targets ?? null)
})

function formatNullableNumber(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) {
    return '—'
  }
  return Number.isInteger(value) ? String(value) : value.toFixed(3)
}

function formatComponentMap(map: Record<string, number> | null | undefined): string | null {
  if (!map) {
    return null
  }
  const parts = Object.entries(map)
    .filter(([, value]) => Number.isFinite(value))
    .map(([key, value]) => `${processComponentLabel(key)}: ${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 3 }).format(value)}`)
  return parts.length > 0 ? parts.join(' · ') : null
}

const correctionDosingClass = computed(() => {
  const severity = correctionDosing.value?.severity ?? 'neutral'
  if (severity === 'danger') {
    return 'border-[color:var(--badge-danger-border)] bg-[color:var(--badge-danger-bg)] text-[color:var(--badge-danger-text)]'
  }
  if (severity === 'warning') {
    return 'border-[color:var(--badge-warning-border)] bg-[color:var(--badge-warning-bg)] text-[color:var(--badge-warning-text)]'
  }
  if (severity === 'info') {
    return 'border-[color:var(--badge-info-border)] bg-[color:var(--badge-info-bg)] text-[color:var(--badge-info-text)]'
  }
  return 'border-[color:var(--border-muted)]/70 bg-[color:var(--bg-elevated)]/55 text-[color:var(--text-primary)]'
})

const healthLabel = computed(() => {
  if (failureDiagnostics.value) {
    return failureDiagnostics.value.isActiveFailure ? 'Сбой' : 'Последний сбой'
  }
  return observabilityHealthLabel(observability.value?.overall_health)
})

const healthBadgeVariant = computed<'neutral' | 'info' | 'warning' | 'danger' | 'success'>(() => {
  if (failureDiagnostics.value) {
    return failureDiagnostics.value.isActiveFailure ? 'danger' : 'warning'
  }
  const health = observability.value?.overall_health
  if (health === 'critical') return 'danger'
  if (health === 'warning') return 'warning'
  if (health === 'active') return 'info'
  return 'neutral'
})

const stageLabel = computed(() => {
  const runtime = observability.value?.runtime
  if (runtime?.task_status === 'failed' && !runtime?.task_is_active) {
    const failedStage = runtime.failed_stage
      ?? props.automationState?.current_stage
      ?? null
    if (failedStage) {
      return `${stageDiagnosticLabel(failedStage)} (сбой)`
    }
    return '—'
  }
  return stageDiagnosticLabel(
    runtime?.current_stage
    ?? props.automationState?.current_stage_label
    ?? props.automationState?.current_stage,
  )
})

const taskStatusLabel = computed(() => {
  const runtime = observability.value?.runtime
  if (!runtime?.task_status) {
    return runtime?.task_is_active === true ? 'Активна по снимку' : runtime?.task_is_active === false && runtime?.source !== 'client_fallback' ? 'Нет активной задачи по снимку' : 'Статус задачи не получен'
  }
  if (runtime.waiting_command) {
    return 'Ожидание подтверждения команды оборудованием'
  }
  return ({ pending: 'Ожидает запуска', claimed: 'Принята к выполнению', running: 'Выполняется', completed: 'Завершена', failed: 'Завершена с ошибкой', cancelled: 'Отменена' } as Record<string, string>)[runtime.task_status] ?? 'Статус неизвестен'
})

const stageElapsedLabel = computed(() => {
  void tickMs.value
  const runtime = observability.value?.runtime
  if (runtime?.task_status === 'failed' || props.automationState?.state_details?.failed === true) {
    const elapsed = runtime?.stage_elapsed_sec
    return elapsed != null && elapsed >= 0 ? formatObservabilityDuration(elapsed) : '—'
  }
  if (!runtime?.task_is_active || props.automationState?.state_meta?.is_stale) return formatObservabilityDuration(runtime?.stage_elapsed_sec)
  const enteredMs = parseIsoMs(runtime?.stage_entered_at ?? null)
  if (enteredMs != null) {
    const liveElapsed = Math.max(0, Math.floor((tickMs.value - enteredMs) / 1000))
    return formatObservabilityDuration(liveElapsed)
  }
  return formatObservabilityDuration(runtime?.stage_elapsed_sec)
})

const deadlineLabel = computed(() => {
  void tickMs.value
  const runtime = observability.value?.runtime
  if (runtime?.task_status === 'failed' || props.automationState?.state_details?.failed === true) {
    return '—'
  }
  if (!runtime?.task_is_active) return '—'
  if (props.automationState?.state_meta?.is_stale) return 'Нет актуальных данных'
  const deadlineMs = parseIsoMs(runtime?.stage_deadline_at ?? null)
  if (deadlineMs != null) {
    const remaining = Math.floor((deadlineMs - tickMs.value) / 1000)
    if (remaining < 0) {
      return `просрочен на ${formatObservabilityDuration(Math.abs(remaining))}`
    }
    return `осталось ${formatObservabilityDuration(remaining)}`
  }
  const recorded = runtime?.stage_deadline_remaining_sec
  const servedMs = parseIsoMs(props.automationState?.state_meta?.served_at)
  const remaining = recorded == null ? null : recorded - (servedMs == null ? 0 : Math.max(0, Math.floor((tickMs.value - servedMs) / 1000)))
  if (remaining === null || remaining === undefined) {
    return '—'
  }
  if (remaining < 0) {
    return `просрочен на ${formatObservabilityDuration(Math.abs(remaining))}`
  }
  return `осталось ${formatObservabilityDuration(remaining)}`
})

const correctionStep = computed(() => {
  if (observability.value?.runtime?.task_status === 'failed') {
    return null
  }
  return observability.value?.runtime?.correction_step ?? null
})

const topologyLabel = computed(() => {
  const topology = observability.value?.runtime?.topology
  if (typeof topology !== 'string' || topology.trim() === '') {
    return null
  }
  if (topology.startsWith('two_tank')) return 'Двухбаковая система'
  if (topology.startsWith('single_tank')) return 'Однобаковая система'
  if (topology.startsWith('three_tank')) return 'Трёхбаковая система'
  return 'Схема не распознана'
})

const pendingManualStepLabel = computed(() => {
  const step = observability.value?.runtime?.pending_manual_step
  if (typeof step !== 'string' || step.trim() === '') {
    return null
  }
  return stageDiagnosticLabel(step.trim())
})

const taskIdLabel = computed(() => {
  const taskId = observability.value?.runtime?.task_id
  if (taskId === null || taskId === undefined) {
    return null
  }
  return `#${taskId}`
})

const offlineNodes = computed(() => observability.value?.nodes?.offline_required ?? [])

const dataSourceLabel = computed(() => {
  if (props.automationState?.compatibility?.source === 'ae3_control_mode_fallback') return 'Резервные сведения о режиме управления и задаче; показания контура недоступны'
  if (props.automationState?.state_meta?.is_stale) {
    return 'сохранённые данные; актуальность не подтверждена'
  }
  const source = observability.value?.runtime?.source
  if (source === 'laravel_db_fallback') {
    return 'БД Laravel (fallback)'
  }
  if (source === 'client_fallback') {
    return 'локальная оценка UI'
  }
  return source === 'ae3' || source === 'automation_engine' ? 'Служба выполнения' : props.automationState?.state_meta?.source === 'live' ? 'Ответ службы выполнения' : 'Источник не указан'
})

const schedulerSummary = computed(() => {
  const scheduler = observability.value?.scheduler
  if (!scheduler) {
    return null
  }
  const pending = scheduler.pending_count
  const active = scheduler.active_count
  const latest = scheduler.latest_intent
  if (active === 0 && pending === 0) {
    return 'Нет ожидающих запросов в этой зоне'
  }
  const parts = [`Запросов в обработке: ${active ?? '—'}`, `ожидают приёма: ${pending ?? '—'}`]
  if (latest?.intent_type) {
    parts.push(`последний запрос: ${statusLabel(latest.status ?? '')}`)
  }
  if (latest?.age_sec != null) {
    parts.push(`возраст ${formatObservabilityDuration(latest.age_sec)}`)
  }
  return parts.join(' · ')
})

function readinessBoolLabel(value: boolean): string {
  return value ? 'да' : 'нет'
}

function hintClass(severity: string): string {
  if (severity === 'critical') {
    return 'border-[color:var(--badge-danger-border)] bg-[color:var(--badge-danger-bg)] text-[color:var(--badge-danger-text)]'
  }
  return 'border-[color:var(--badge-warning-border)] bg-[color:var(--badge-warning-bg)] text-[color:var(--badge-warning-text)]'
}

function hintDetailLines(hint: { details?: Record<string, unknown> }): string[] {
  const details = hint.details
  if (!details || typeof details !== 'object') {
    return []
  }

  const lines: string[] = []
  if (details.intent_id != null) {
    lines.push(`intent_id=${String(details.intent_id)}`)
  }
  if (typeof details.intent_type === 'string' && details.intent_type !== '') {
    lines.push(`intent_type=${details.intent_type}`)
  }
  if (details.age_sec != null) {
    lines.push(`age_sec=${String(details.age_sec)}`)
  }
  if (details.waiting_elapsed_sec != null) {
    lines.push(`waiting_elapsed_sec=${String(details.waiting_elapsed_sec)}`)
  }
  if (typeof details.current_stage === 'string' && details.current_stage !== '') {
    lines.push(`stage=${details.current_stage}`)
  }
  if (details.overdue_sec != null) {
    lines.push(`overdue_sec=${String(details.overdue_sec)}`)
  }
  if (typeof details.task_status === 'string' && details.task_status !== '') {
    lines.push(`task_status=${details.task_status}`)
  }
  if (typeof details.intent_status === 'string' && details.intent_status !== '') {
    lines.push(`intent_status=${details.intent_status}`)
  }
  if (typeof details.idempotency_key === 'string' && details.idempotency_key !== '') {
    lines.push(`idempotency_key=${details.idempotency_key}`)
  }
  if (Array.isArray(details.nodes) && details.nodes.length > 0) {
    lines.push(`nodes=${details.nodes.map((n) => String(n)).join(',')}`)
  }

  return lines
}

return { observability, failureDiagnostics, causalStrip, hangHints, correctionDosing, activeDosesLabel, prepareBaseline, correctionPipeline, ratioSummary, targetSummary, correctionDosingClass, healthLabel, healthBadgeVariant, stageLabel, taskStatusLabel, stageElapsedLabel, deadlineLabel, correctionStep, topologyLabel, pendingManualStepLabel, taskIdLabel, offlineNodes, dataSourceLabel, schedulerSummary, parseIsoMs, toPositiveId, openTaskEvents, formatNullableNumber, formatComponentMap, readinessBoolLabel, hintClass, hintDetailLines }
}

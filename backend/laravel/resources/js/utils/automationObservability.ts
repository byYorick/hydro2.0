import type {
  AutomationHangHint,
  AutomationObservability,
  AutomationObservabilityCorrection,
  AutomationObservabilityCorrectionSkip,
  AutomationObservabilityHealth,
  AutomationState,
  CorrectionDosingDiagnostics,
} from '@/types/Automation'
import { translateEventKind } from '@/utils/i18n'

const HEALTH_LABELS: Record<AutomationObservabilityHealth, string> = {
  idle: 'Ожидание',
  active: 'Выполняется',
  warning: 'Возможное зависание',
  critical: 'Критично',
}

const STAGE_LABELS: Record<string, string> = {
  startup: 'Инициализация',
  clean_fill_start: 'Запуск clean fill',
  clean_fill_check: 'Наполнение чистой водой',
  solution_fill_start: 'Запуск solution fill',
  solution_fill_check: 'Наполнение раствором',
  prepare_recirculation_start: 'Запуск рециркуляции',
  prepare_recirculation_check: 'Подготовка рециркуляции',
  irrigation_start: 'Запуск полива',
  irrigation_check: 'Полив',
  irrigation_recovery_check: 'Recovery после полива',
  complete_ready: 'Готов к поливу',
  await_ready: 'Ожидание готовности',
  decision_gate: 'Решение о поливе',
}

export function normalizeObservability(raw: unknown): AutomationObservability | null {
  if (!raw || typeof raw !== 'object') {
    return null
  }

  const source = raw as Record<string, unknown>
  const hangHints = Array.isArray(source.hang_hints)
    ? source.hang_hints
      .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object')
      .map(normalizeHangHint)
    : []

  return {
    runtime: normalizeRuntime(source.runtime),
    nodes: normalizeNodes(source.nodes),
    scheduler: normalizeScheduler(source.scheduler),
    hang_hints: hangHints,
    overall_health: normalizeHealth(source.overall_health),
    correction: normalizeCorrection(source.correction),
  }
}

function normalizeHangHint(raw: Record<string, unknown>): AutomationHangHint {
  const severityRaw = String(raw.severity ?? 'warning')
  const severity = severityRaw === 'critical' || severityRaw === 'info' ? severityRaw : 'warning'

  return {
    code: String(raw.code ?? 'unknown'),
    severity,
    message: String(raw.message ?? ''),
    recommendation: typeof raw.recommendation === 'string' ? raw.recommendation : null,
    details: raw.details && typeof raw.details === 'object'
      ? raw.details as Record<string, unknown>
      : undefined,
  }
}

function normalizeRuntime(raw: unknown): AutomationObservability['runtime'] {
  if (!raw || typeof raw !== 'object') {
    return undefined
  }
  const source = raw as Record<string, unknown>
  return {
    zone_id: Number(source.zone_id ?? 0),
    task_id: source.task_id != null ? Number(source.task_id) : null,
    task_status: typeof source.task_status === 'string' ? source.task_status : null,
    task_is_active: Boolean(source.task_is_active),
    current_stage: typeof source.current_stage === 'string' ? source.current_stage : null,
    workflow_phase: typeof source.workflow_phase === 'string' ? source.workflow_phase : null,
    stage_entered_at: typeof source.stage_entered_at === 'string' ? source.stage_entered_at : null,
    stage_elapsed_sec: Number(source.stage_elapsed_sec ?? 0),
    stage_deadline_at: typeof source.stage_deadline_at === 'string' ? source.stage_deadline_at : null,
    stage_deadline_remaining_sec: source.stage_deadline_remaining_sec != null
      ? Number(source.stage_deadline_remaining_sec)
      : null,
    waiting_command: Boolean(source.waiting_command),
    waiting_elapsed_sec: Number(source.waiting_elapsed_sec ?? 0),
    task_updated_age_sec: source.task_updated_age_sec != null
      ? Number(source.task_updated_age_sec)
      : null,
    correction_step: typeof source.correction_step === 'string' ? source.correction_step : null,
    pending_manual_step: typeof source.pending_manual_step === 'string' ? source.pending_manual_step : null,
    topology: typeof source.topology === 'string' ? source.topology : null,
    workflow_snapshot_updated_at: typeof source.workflow_snapshot_updated_at === 'string'
      ? source.workflow_snapshot_updated_at
      : null,
    workflow_snapshot_age_sec: source.workflow_snapshot_age_sec != null
      ? Number(source.workflow_snapshot_age_sec)
      : null,
    source: typeof source.source === 'string' ? source.source : null,
    failed_stage: typeof source.failed_stage === 'string' ? source.failed_stage : null,
  }
}

function normalizeNodes(raw: unknown): AutomationObservability['nodes'] {
  if (!raw || typeof raw !== 'object') {
    return undefined
  }
  const source = raw as Record<string, unknown>
  const nodes = Array.isArray(source.nodes)
    ? source.nodes
      .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object')
      .map((node) => ({
        uid: typeof node.uid === 'string' ? node.uid : null,
        type: typeof node.type === 'string' ? node.type : null,
        status: typeof node.status === 'string' ? node.status : null,
        last_seen_age_sec: node.last_seen_age_sec != null ? Number(node.last_seen_age_sec) : null,
        required: Boolean(node.required),
        healthy: Boolean(node.healthy),
      }))
    : []

  return {
    nodes,
    offline_required: Array.isArray(source.offline_required)
      ? source.offline_required.map((item) => String(item))
      : [],
    persistent_offline: Boolean(source.persistent_offline),
  }
}

function normalizeScheduler(raw: unknown): AutomationObservability['scheduler'] {
  if (!raw || typeof raw !== 'object') {
    return undefined
  }
  const source = raw as Record<string, unknown>
  const latest = source.latest_intent && typeof source.latest_intent === 'object'
    ? source.latest_intent as Record<string, unknown>
    : null

  return {
    pending_count: Number(source.pending_count ?? 0),
    active_count: Number(source.active_count ?? 0),
    latest_intent: latest
      ? {
          id: latest.id != null ? Number(latest.id) : undefined,
          status: typeof latest.status === 'string' ? latest.status : undefined,
          intent_type: typeof latest.intent_type === 'string' ? latest.intent_type : undefined,
          not_before: typeof latest.not_before === 'string' ? latest.not_before : null,
          created_at: typeof latest.created_at === 'string' ? latest.created_at : null,
          updated_at: typeof latest.updated_at === 'string' ? latest.updated_at : null,
          age_sec: latest.age_sec != null ? Number(latest.age_sec) : null,
        }
      : null,
  }
}

function normalizeHealth(raw: unknown): AutomationObservabilityHealth {
  const value = String(raw ?? 'idle')
  if (value === 'active' || value === 'warning' || value === 'critical') {
    return value
  }
  return 'idle'
}

function normalizeCorrection(raw: unknown): AutomationObservabilityCorrection | undefined {
  if (!raw || typeof raw !== 'object') {
    return undefined
  }

  const source = raw as Record<string, unknown>
  const lastDoseRaw = source.last_dose
  const lastDose: Record<string, { last_dose_at?: string | null, last_dose_age_sec?: number | null, no_effect_count?: number }> = {}

  if (lastDoseRaw && typeof lastDoseRaw === 'object') {
    for (const [pidType, entry] of Object.entries(lastDoseRaw as Record<string, unknown>)) {
      if (!entry || typeof entry !== 'object') {
        continue
      }
      const dose = entry as Record<string, unknown>
      lastDose[pidType] = {
        last_dose_at: typeof dose.last_dose_at === 'string' ? dose.last_dose_at : null,
        last_dose_age_sec: dose.last_dose_age_sec != null ? Number(dose.last_dose_age_sec) : null,
        no_effect_count: dose.no_effect_count != null ? Number(dose.no_effect_count) : 0,
      }
    }
  }

  const latestSkipRaw = source.latest_skip
  const latestSkip = latestSkipRaw && typeof latestSkipRaw === 'object'
    ? normalizeCorrectionSkip(latestSkipRaw as Record<string, unknown>)
    : null

  const readinessRaw = source.readiness
  const readiness = readinessRaw && typeof readinessRaw === 'object'
    ? normalizeCorrectionReadiness(readinessRaw as Record<string, unknown>)
    : null

  return {
    last_dose: Object.keys(lastDose).length > 0 ? lastDose : undefined,
    latest_skip: latestSkip,
    readiness,
  }
}

function normalizeCorrectionSkip(raw: Record<string, unknown>): AutomationObservabilityCorrection['latest_skip'] {
  return {
    event_id: raw.event_id != null ? Number(raw.event_id) : null,
    event_type: typeof raw.event_type === 'string' ? raw.event_type : null,
    occurred_at: typeof raw.occurred_at === 'string' ? raw.occurred_at : null,
    age_sec: raw.age_sec != null ? Number(raw.age_sec) : null,
    payload: raw.payload && typeof raw.payload === 'object'
      ? raw.payload as Record<string, unknown>
      : undefined,
  }
}

function normalizeCorrectionReadiness(raw: Record<string, unknown>): AutomationObservabilityCorrection['readiness'] {
  return {
    event_id: raw.event_id != null ? Number(raw.event_id) : null,
    event_type: typeof raw.event_type === 'string' ? raw.event_type : null,
    occurred_at: typeof raw.occurred_at === 'string' ? raw.occurred_at : null,
    targets_in_tolerance: typeof raw.targets_in_tolerance === 'boolean' ? raw.targets_in_tolerance : null,
    workflow_ready: typeof raw.workflow_ready === 'boolean' ? raw.workflow_ready : null,
  }
}

const CORRECTION_STEP_LABELS: Record<string, string> = {
  corr_wait_stable: 'Стабилизация перед наблюдением',
  corr_check: 'Окно наблюдения / решение',
  corr_dose_ec: 'Дозирование EC',
  corr_dose_ph: 'Дозирование pH',
  corr_dose_ph_up: 'Дозирование pH (вверх)',
  corr_dose_ph_down: 'Дозирование pH (вниз)',
  corr_wait_ec: 'Ожидание реакции EC',
  corr_wait_ph: 'Ожидание реакции pH',
}

const ACTIVE_DOSE_STEPS = new Set([
  'corr_dose_ec',
  'corr_dose_ph',
  'corr_dose_ph_up',
  'corr_dose_ph_down',
])

/** Skip events older than this are ignored by the dosing card (seconds). */
const SKIP_EVENT_MAX_AGE_SEC = 1800

/** Terminal/hard-fail skip kinds that stay visible even while dosing is active. */
const HARD_FAIL_SKIP_KINDS = new Set([
  'CORRECTION_SKIPPED_EMERGENCY_STOP',
  'EC_BATCH_PARTIAL_FAILURE',
  'CORRECTION_EXHAUSTED',
  'CORRECTION_NO_EFFECT',
  'CORRECTION_PLANNER_CONFIG_INVALID',
])

function correctionStepLabel(step: string | null | undefined): string | null {
  if (!step) {
    return null
  }
  const key = step.trim().toLowerCase()
  return CORRECTION_STEP_LABELS[key] ?? step
}

function isFreshSkip(
  skip: AutomationObservabilityCorrectionSkip | null | undefined,
): boolean {
  if (!skip?.event_type) {
    return false
  }
  if (skip.age_sec != null && Number.isFinite(skip.age_sec)) {
    return Number(skip.age_sec) <= SKIP_EVENT_MAX_AGE_SEC
  }
  // Missing age → treat as fresh (backend always sets age_sec when present).
  return true
}

function isSkipStillBlocking(
  skip: AutomationObservabilityCorrectionSkip | null | undefined,
): boolean {
  if (!isFreshSkip(skip)) {
    return false
  }
  const retrySec = skip?.payload?.retry_after_sec
  if (retrySec != null && Number.isFinite(Number(retrySec))) {
    const age = skip?.age_sec != null ? Number(skip.age_sec) : 0
    // Cooldown/window-not-ready: hide after retry window elapsed.
    if (age > Number(retrySec)) {
      return HARD_FAIL_SKIP_KINDS.has(String(skip?.event_type ?? ''))
    }
  }
  return true
}

function formatSkipDetail(payload: Record<string, unknown> | undefined): string | null {
  if (!payload) {
    return null
  }

  const parts: string[] = []
  const retrySec = payload.retry_after_sec
  if (retrySec != null && Number.isFinite(Number(retrySec))) {
    parts.push(`повтор через ${formatObservabilityDuration(Number(retrySec))}`)
  }

  const reason = typeof payload.reason === 'string' ? payload.reason.trim() : ''
  if (reason !== '') {
    parts.push(reason)
  }

  const phReason = typeof payload.ph_reason === 'string' ? payload.ph_reason.trim() : ''
  const ecReason = typeof payload.ec_reason === 'string' ? payload.ec_reason.trim() : ''
  if (phReason === 'sensor_out_of_bounds' || ecReason === 'sensor_out_of_bounds') {
    parts.push('сенсор вне допустимых bounds')
  }

  const failedComponent = typeof payload.failed_component === 'string' ? payload.failed_component : ''
  if (failedComponent !== '') {
    parts.push(`сбой компонента ${failedComponent}`)
  }

  const deferredAction = typeof payload.deferred_action === 'string' ? payload.deferred_action : ''
  if (deferredAction !== '') {
    parts.push(`отложено: ${deferredAction}`)
  }

  return parts.length > 0 ? parts.join(' · ') : null
}

function buildLastDoseSummary(correction: AutomationObservabilityCorrection | undefined): string | null {
  const lastDose = correction?.last_dose
  if (!lastDose) {
    return null
  }

  const parts: string[] = []
  for (const pidType of ['ec', 'ph']) {
    const entry = lastDose[pidType]
    if (!entry?.last_dose_at) {
      continue
    }
    const age = entry.last_dose_age_sec != null
      ? formatObservabilityDuration(entry.last_dose_age_sec)
      : '—'
    const noEffect = entry.no_effect_count != null && entry.no_effect_count > 0
      ? `, no-effect×${entry.no_effect_count}`
      : ''
    parts.push(`${pidType.toUpperCase()} ${age} назад${noEffect}`)
  }

  return parts.length > 0 ? parts.join(' · ') : null
}

export function resolveCorrectionDosingDiagnostics(
  state: AutomationState | null,
  observability: AutomationObservability | null,
): CorrectionDosingDiagnostics | null {
  if (!state && !observability) {
    return null
  }

  const correction = observability?.correction
  const corrStep = observability?.runtime?.task_status === 'failed'
    ? null
    : (observability?.runtime?.correction_step ?? null)
  const corrStepLabel = correctionStepLabel(corrStep)
  const controlMode = state?.control_mode ?? 'auto'
  const workflowPhase = (observability?.runtime?.workflow_phase ?? state?.workflow_phase ?? '').toLowerCase()
  const activeCorrectionProcess = Boolean(
    state?.active_processes?.ph_correction || state?.active_processes?.ec_correction,
  )
  // Do not open the card solely from stale skip/readiness events.
  const inCorrectionPhase = Boolean(corrStep)
    || activeCorrectionProcess
    || ['irrigating', 'irrig_recirc', 'tank_recirc'].includes(workflowPhase)

  if (!inCorrectionPhase) {
    return null
  }

  const isDosingActive = corrStep != null && ACTIVE_DOSE_STEPS.has(corrStep.toLowerCase())
  const latestSkipRaw = correction?.latest_skip ?? null
  const latestSkip = isSkipStillBlocking(latestSkipRaw) ? latestSkipRaw : null
  const readiness = correction?.readiness ?? null
  const hangHints = observability?.hang_hints ?? []
  const nodesOffline = hangHints.some((hint) => hint.code === 'nodes_offline')
  const hardFailSkip = latestSkip?.event_type != null
    && HARD_FAIL_SKIP_KINDS.has(latestSkip.event_type)

  let reason: string | null = null
  let detail: string | null = null
  let severity: CorrectionDosingDiagnostics['severity'] = 'neutral'

  // Priority: hard-fail skip → active dosing → control_mode → soft skip → offline → wait/check.
  if (hardFailSkip && latestSkip?.event_type) {
    reason = translateEventKind(latestSkip.event_type)
    detail = formatSkipDetail(latestSkip.payload)
    severity = 'danger'
  } else if (isDosingActive) {
    reason = 'Дозирование выполняется'
    severity = 'info'
  } else if (controlMode !== 'auto' && (corrStep || activeCorrectionProcess)) {
    reason = controlMode === 'manual'
      ? 'Ручной режим — автодозирование заблокировано'
      : 'Полуавтоматический режим — flow-path удержан'
    severity = 'warning'
    if (latestSkip?.event_type) {
      detail = `${translateEventKind(latestSkip.event_type)}${formatSkipDetail(latestSkip.payload) ? ` · ${formatSkipDetail(latestSkip.payload)}` : ''}`
    }
  } else if (latestSkip?.event_type) {
    reason = translateEventKind(latestSkip.event_type)
    detail = formatSkipDetail(latestSkip.payload)
    severity = 'warning'
  } else if (nodesOffline) {
    reason = 'Обязательные узлы offline или stale'
    severity = 'warning'
  } else if (corrStep === 'corr_check' || corrStep === 'corr_wait_stable') {
    reason = 'Окно наблюдения — доза ещё не выбрана'
    severity = 'info'
  } else if (corrStep === 'corr_wait_ec' || corrStep === 'corr_wait_ph') {
    reason = 'Ожидание реакции после дозы'
    severity = 'info'
  } else if (!corrStep) {
    reason = 'Коррекция не активна на текущем этапе'
    severity = 'neutral'
  }

  const cooldownLabel = latestSkip?.payload?.retry_after_sec != null
    ? formatObservabilityDuration(Number(latestSkip.payload.retry_after_sec))
    : null

  return {
    visible: true,
    corrStep,
    corrStepLabel,
    reason,
    detail,
    lastDoseSummary: buildLastDoseSummary(correction),
    cooldownLabel,
    targetsInTolerance: readiness?.targets_in_tolerance ?? null,
    workflowReady: readiness?.workflow_ready ?? null,
    severity,
    isDosingActive,
  }
}

export function observabilityHealthLabel(health: AutomationObservabilityHealth | null | undefined): string {
  if (!health) {
    return HEALTH_LABELS.idle
  }
  return HEALTH_LABELS[health] ?? HEALTH_LABELS.idle
}

export function stageDiagnosticLabel(stage: string | null | undefined): string {
  if (!stage) {
    return '—'
  }
  const key = stage.trim().toLowerCase()
  return STAGE_LABELS[key] ?? stage
}

export function formatObservabilityDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(Number(seconds))) {
    return '—'
  }
  const total = Math.max(0, Math.floor(Number(seconds)))
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const secs = total % 60
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
  }
  return `${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
}

export function resolveObservability(state: AutomationState | null): AutomationObservability | null {
  if (!state) {
    return null
  }

  const fromPayload = state.observability ?? null
  if (fromPayload) {
    if (state.state_meta?.is_stale) {
      return appendStaleSnapshotHint(fromPayload)
    }

    return fromPayload
  }

  return buildClientFallbackObservability(state)
}

function appendStaleSnapshotHint(observability: AutomationObservability): AutomationObservability {
  const hints = observability.hang_hints ?? []
  if (hints.some((hint) => hint.code === 'state_snapshot_stale')) {
    return observability
  }

  const staleHint: AutomationHangHint = {
    code: 'state_snapshot_stale',
    severity: 'warning',
    message: 'Снимок автоматики из кэша — AE3 может быть недоступен',
    recommendation: 'Проверьте automation-engine и обновите страницу.',
  }

  return {
    ...observability,
    hang_hints: [...hints, staleHint],
    overall_health: observability.overall_health === 'critical' ? 'critical' : 'warning',
  }
}

function buildClientFallbackObservability(state: AutomationState): AutomationObservability {
  const elapsed = Number(state.state_details?.elapsed_sec ?? 0)
  const workflowPhase = state.workflow_phase ?? 'idle'
  const taskIsActive = Boolean(
    state.state_details?.failed !== true
    && elapsed > 0
    && workflowPhase !== 'idle',
  )

  const hints: AutomationHangHint[] = []
  if (state.state_meta?.is_stale) {
    hints.push({
      code: 'state_snapshot_stale',
      severity: 'warning',
      message: 'Снимок автоматики из кэша — AE3 может быть недоступен',
      recommendation: 'Проверьте automation-engine и обновите страницу.',
    })
  }

  return {
    runtime: {
      zone_id: state.zone_id,
      task_is_active: taskIsActive,
      current_stage: state.current_stage,
      workflow_phase: workflowPhase,
      stage_elapsed_sec: elapsed,
      waiting_command: false,
      waiting_elapsed_sec: 0,
      source: 'client_fallback',
    },
    hang_hints: hints,
    overall_health: hints.length > 0 ? 'warning' : (taskIsActive ? 'active' : 'idle'),
  }
}

export function hasHangHints(state: AutomationState | null): boolean {
  return (state?.observability?.hang_hints?.length ?? 0) > 0
}

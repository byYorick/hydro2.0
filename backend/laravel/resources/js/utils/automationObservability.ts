import type {
  AutomationHangHint,
  AutomationObservability,
  AutomationObservabilityHealth,
  AutomationState,
} from '@/types/Automation'

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

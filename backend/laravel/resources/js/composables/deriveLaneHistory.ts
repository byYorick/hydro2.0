import type {
  ExecutionRun,
  LaneHistory,
  LaneHistoryPoint,
  LaneHistoryStatus,
} from '@/composables/zoneScheduleWorkspaceTypes'

export type LaneHistoryHorizon = '24h' | '7d'

const HORIZON_HOURS: Record<LaneHistoryHorizon, number> = {
  '24h': 24,
  '7d': 24 * 7,
}

const HORIZON_HALF_MS: Record<LaneHistoryHorizon, number> = {
  '24h': (24 / 2) * 60 * 60 * 1000,
  '7d': ((24 * 7) / 2) * 60 * 60 * 1000,
}

function pickRunStart(run: ExecutionRun): Date | null {
  const candidates = [run.scheduled_for, run.accepted_at, run.created_at, run.updated_at]
  for (const candidate of candidates) {
    if (!candidate) continue
    const date = new Date(candidate)
    if (!Number.isNaN(date.getTime())) return date
  }
  return null
}

function laneKey(run: ExecutionRun): string {
  return run.schedule_task_type ?? run.task_type ?? 'other'
}

function runStatusToHistoryStatus(run: ExecutionRun): LaneHistoryStatus {
  const normalized = String(run.status ?? '').toLowerCase()
  if (run.is_active || normalized === 'running' || normalized === 'claimed') return 'run'
  if (normalized === 'failed' || normalized === 'fail' || normalized === 'error') return 'err'
  if (normalized === 'skipped' || normalized === 'skip') return 'skip'
  const decision = String(run.decision_outcome ?? '').toLowerCase()
  if (decision === 'skip') return 'skip'
  if (decision === 'fail') return 'err'
  if (run.decision_degraded) return 'warn'
  return 'ok'
}

/**
 * Строит bucket-представление истории lanes для swimlane-ленты.
 *
 * `now` — опциональная точка отсчёта (передавать для детерминизма в тестах).
 * Горизонт — окно [now - H/2 … now + H/2]. `t` — процентная позиция точки
 * внутри этого окна. Runs вне окна отбрасываются.
 *
 * Функция используется как фронтовый fallback до Фазы 2, когда бэк начнёт
 * возвращать `workspace.lanes_history` напрямую.
 */
export function deriveLaneHistory(
  runs: ExecutionRun[],
  horizon: LaneHistoryHorizon,
  now: Date = new Date(),
): LaneHistory[] {
  const halfMs = HORIZON_HALF_MS[horizon] ?? HORIZON_HALF_MS['24h']
  const nowMs = now.getTime()
  const start = nowMs - halfMs
  const end = nowMs + halfMs
  const windowMs = end - start

  const lanes = new Map<string, LaneHistoryPoint[]>()

  for (const run of runs) {
    const at = pickRunStart(run)
    if (!at) continue
    const atMs = at.getTime()
    if (atMs < start || atMs > end) continue

    const t = ((atMs - start) / windowMs) * 100
    const clamped = Math.min(100, Math.max(0, t))

    const key = laneKey(run)
    const bucket = lanes.get(key) ?? []
    bucket.push({ t: Number(clamped.toFixed(2)), s: runStatusToHistoryStatus(run) })
    lanes.set(key, bucket)
  }

  for (const bucket of lanes.values()) {
    bucket.sort((a, b) => a.t - b.t)
  }

  return Array.from(lanes.entries()).map(([lane, runs]) => ({ lane, runs }))
}

export function laneHistoryHorizonHours(horizon: LaneHistoryHorizon): number {
  return HORIZON_HOURS[horizon] ?? HORIZON_HOURS['24h']
}

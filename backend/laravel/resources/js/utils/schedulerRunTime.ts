import type { ExecutionRun } from '@/composables/zoneScheduleWorkspaceTypes'

function parseIso(value: string | null | undefined): Date | null {
  if (!value) return null
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

export function readRunDurationSec(run: ExecutionRun): number | null {
  if (typeof run.requested_duration_sec === 'number' && Number.isFinite(run.requested_duration_sec) && run.requested_duration_sec > 0) {
    return run.requested_duration_sec
  }

  const config = run.decision_config as Record<string, unknown> | null | undefined
  if (!config || typeof config !== 'object') {
    return null
  }

  const candidates: unknown[] = [
    config.requested_duration_sec,
    config.duration_sec,
  ]

  for (const candidate of candidates) {
    if (typeof candidate === 'number' && Number.isFinite(candidate) && candidate > 0) {
      return candidate
    }
  }

  return null
}

export function deriveRunEndAt(run: ExecutionRun): Date | null {
  // due_at in AE3 is the next stage wake deadline, not end-of-run — prefer duration.
  const durationSec = readRunDurationSec(run)
  const startAt =
    parseIso(run.accepted_at) ??
    parseIso(run.scheduled_for) ??
    parseIso(run.created_at) ??
    parseIso(run.updated_at)

  if (durationSec !== null && startAt) {
    return new Date(startAt.getTime() + durationSec * 1000)
  }

  return null
}

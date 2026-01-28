function clampPercent(value: number): number {
  return Math.min(100, Math.max(0, value))
}

function toDate(value: string | Date | null | undefined): Date | null {
  if (!value) return null
  const date = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(date.getTime())) return null
  return date
}

export function normalizeDurationHours(
  durationHours?: number | null,
  durationDays?: number | null
): number | null {
  if (typeof durationHours === 'number' && durationHours > 0) {
    return durationHours
  }
  if (typeof durationDays === 'number' && durationDays > 0) {
    return durationDays * 24
  }
  return null
}

export function calculateProgressBetween(
  startAt: string | Date | null | undefined,
  endAt: string | Date | null | undefined,
  now: Date = new Date()
): number | null {
  const start = toDate(startAt)
  const end = toDate(endAt)
  if (!start || !end) return null

  const totalMs = end.getTime() - start.getTime()
  if (totalMs <= 0) return null

  const elapsedMs = now.getTime() - start.getTime()
  if (elapsedMs <= 0) return 0
  if (elapsedMs >= totalMs) return 100

  return clampPercent((elapsedMs / totalMs) * 100)
}

export function calculateProgressFromDuration(
  startAt: string | Date | null | undefined,
  durationHours?: number | null,
  durationDays?: number | null,
  now: Date = new Date()
): number | null {
  const start = toDate(startAt)
  const hours = normalizeDurationHours(durationHours ?? null, durationDays ?? null)
  if (!start || !hours) return null

  const end = new Date(start.getTime() + hours * 60 * 60 * 1000)
  return calculateProgressBetween(start, end, now)
}

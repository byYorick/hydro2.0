function asRecord(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === 'object') {
    return value as Record<string, unknown>
  }
  return null
}

export function extractZoneActiveCycleStatus(zone: unknown): string | null {
  const zoneRecord = asRecord(zone)
  if (!zoneRecord) {
    return null
  }

  const activeCycle =
    asRecord(zoneRecord.active_grow_cycle)
    ?? asRecord(zoneRecord.activeGrowCycle)
    ?? null

  if (!activeCycle) {
    return null
  }

  const status = activeCycle.status
  if (typeof status !== 'string' || status.trim().length === 0) {
    return null
  }

  return status.trim().toUpperCase()
}

export function isZoneCycleBlocking(status: string | null | undefined): boolean {
  if (!status) {
    return false
  }

  const normalized = status.trim().toUpperCase()
  return normalized === 'PLANNED' || normalized === 'RUNNING' || normalized === 'PAUSED'
}

export function zoneCycleStatusLabel(status: string | null | undefined): string {
  const normalized = status?.trim().toUpperCase() ?? ''
  if (normalized === 'PLANNED') {
    return 'PLANNED (запланирован)'
  }
  if (normalized === 'RUNNING') {
    return 'RUNNING (выполняется)'
  }
  if (normalized === 'PAUSED') {
    return 'PAUSED (на паузе)'
  }

  return normalized || 'UNKNOWN'
}

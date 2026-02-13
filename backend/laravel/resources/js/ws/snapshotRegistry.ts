import type { ZoneSnapshot, SnapshotHandler } from '@/types/reconciliation'

const zoneSnapshots = new Map<number, ZoneSnapshot>()
const snapshotHandlers = new Map<number, SnapshotHandler>()

export function hasZoneSnapshot(zoneId: number): boolean {
  return zoneSnapshots.has(zoneId)
}

export function getZoneSnapshot(zoneId: number): ZoneSnapshot | undefined {
  return zoneSnapshots.get(zoneId)
}

export function setZoneSnapshot(zoneId: number, snapshot: ZoneSnapshot): void {
  zoneSnapshots.set(zoneId, snapshot)
}

export function registerSnapshotHandler(zoneId: number, handler: SnapshotHandler): void {
  snapshotHandlers.set(zoneId, handler)
}

export function removeSnapshotHandler(zoneId: number): void {
  snapshotHandlers.delete(zoneId)
}

export function getSnapshotHandler(zoneId: number): SnapshotHandler | undefined {
  return snapshotHandlers.get(zoneId)
}

export function isStaleSnapshotEvent(
  zoneId: number | null | undefined,
  eventServerTs: number | null | undefined
): boolean {
  if (!zoneId || eventServerTs === null || typeof eventServerTs === 'undefined') {
    return false
  }

  const snapshot = zoneSnapshots.get(zoneId)
  if (!snapshot) {
    return false
  }

  return eventServerTs < snapshot.server_ts
}

export function getSnapshotServerTs(zoneId: number): number | undefined {
  return zoneSnapshots.get(zoneId)?.server_ts
}

export function clearSnapshotRegistry(): void {
  zoneSnapshots.clear()
  snapshotHandlers.clear()
}

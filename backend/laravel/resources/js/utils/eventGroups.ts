import { translateEventKind } from '@/utils/i18n'
import { readNumber, readString, toPayloadRecord } from '@/utils/eventPayload'
import type { ZoneEvent } from '@/types/ZoneEvent'

export interface ZoneEventGroup {
  id: string
  title: string
  subtitle: string | null
  badge: string | null
  events: ZoneEvent[]
  latestOccurredAt: string
  isCorrelated: boolean
}

const RUNTIME_CORRELATED_KINDS = new Set([
  'AE_TASK_STARTED',
  'AE_TASK_COMPLETED',
  'AE_TASK_FAILED',
  'COMMAND_TIMEOUT',
  'CORRECTION_COMPLETE',
  'CORRECTION_DECISION_MADE',
  'CORRECTION_EXHAUSTED',
  'CORRECTION_OBSERVATION_EVALUATED',
  'CORRECTION_SENSOR_MODE_REACTIVATED',
  'EC_DOSING',
  'IRRIGATION_CORRECTION_COMPLETED',
  'IRRIGATION_CORRECTION_STARTED',
  'IRRIGATION_DECISION_EVALUATED',
  'IRRIGATION_DECISION_SNAPSHOT_LOCKED',
  'IRRIGATION_EC_MULTI_DOSE',
  'IRR_STATE_SNAPSHOT',
  'PH_CORRECTED',
])

// Типы, которые объединяются в общую группу по виду (нет task_id / cw_id в payload)
const KIND_BUCKET_KINDS = new Set([
  'IRR_STATE_SNAPSHOT',
])

function parseEventTime(value: string | undefined): number {
  if (!value) return 0
  const ts = Date.parse(value)
  return Number.isFinite(ts) ? ts : 0
}

function formatGroupBadge(count: number): string {
  return `${count} ${count === 1 ? 'событие' : count < 5 ? 'события' : 'событий'}`
}

function describeCorrectionWindow(windowId: string): string {
  const parts = windowId.split(':')
  if (parts.length >= 4 && parts[0] === 'task') {
    return `Окно ${parts[3]}`
  }
  return `Окно ${windowId}`
}

function buildContext(event: ZoneEvent): {
  groupKey: string
  title: string
  subtitle: string | null
  isCorrelated: boolean
} {
  const payload = toPayloadRecord(event.payload)
  const taskId = readNumber(payload, 'task_id')
  const correctionWindowId = readString(payload, 'correction_window_id')
  const workflowPhase = readString(payload, 'workflow_phase')
  const stage = readString(payload, 'stage')
  const snapshotEventId = readNumber(payload, 'snapshot_event_id')
  const causedByEventId = readNumber(payload, 'caused_by_event_id')
  const isRuntimeEvent = RUNTIME_CORRELATED_KINDS.has(event.kind)

  const contextBits = [workflowPhase, stage].filter(Boolean)
  const subtitle = contextBits.length > 0 ? contextBits.join(' / ') : null

  if (correctionWindowId) {
    const windowTitle = taskId !== null
      ? `AE задача #${taskId} · ${describeCorrectionWindow(correctionWindowId)}`
      : describeCorrectionWindow(correctionWindowId)
    return {
      groupKey: `correction_window:${correctionWindowId}`,
      title: windowTitle,
      subtitle,
      isCorrelated: true,
    }
  }

  if (taskId !== null && isRuntimeEvent) {
    const phaseName = readString(payload, 'phase_name')
    const title = phaseName
      ? `AE задача #${taskId} · ${phaseName}`
      : `AE задача #${taskId}`
    return {
      groupKey: `task:${taskId}`,
      title,
      subtitle,
      isCorrelated: true,
    }
  }

  if (snapshotEventId !== null && isRuntimeEvent) {
    return {
      groupKey: `snapshot:${snapshotEventId}`,
      title: `Связанные события (снимок #${snapshotEventId})`,
      subtitle,
      isCorrelated: true,
    }
  }

  if (causedByEventId !== null && isRuntimeEvent) {
    return {
      groupKey: `cause:${causedByEventId}`,
      title: `Связанные события (причина #${causedByEventId})`,
      subtitle,
      isCorrelated: true,
    }
  }

  // Одиночные runtime-события без ключей группируются в общий «ведро» по типу
  if (KIND_BUCKET_KINDS.has(event.kind)) {
    return {
      groupKey: `bucket:${event.kind}`,
      title: translateEventKind(event.kind),
      subtitle: null,
      isCorrelated: false,
    }
  }

  return {
    groupKey: `event:${event.id}`,
    title: translateEventKind(event.kind),
    subtitle: null,
    isCorrelated: false,
  }
}

export function groupZoneEvents(events: ZoneEvent[]): ZoneEventGroup[] {
  const buckets = new Map<string, ZoneEventGroup>()

  events.forEach((event) => {
    const context = buildContext(event)
    const occurredAt = event.occurred_at ?? event.created_at ?? new Date(0).toISOString()
    const existing = buckets.get(context.groupKey)

    if (!existing) {
      buckets.set(context.groupKey, {
        id: context.groupKey,
        title: context.title,
        subtitle: context.subtitle,
        badge: formatGroupBadge(1),
        events: [event],
        latestOccurredAt: occurredAt,
        isCorrelated: context.isCorrelated,
      })
      return
    }

    existing.events.push(event)
    if (parseEventTime(occurredAt) > parseEventTime(existing.latestOccurredAt)) {
      existing.latestOccurredAt = occurredAt
    }
    if (!existing.subtitle && context.subtitle) {
      existing.subtitle = context.subtitle
    }
    existing.badge = formatGroupBadge(existing.events.length)
  })

  return Array.from(buckets.values())
    .map((group) => {
      const sorted = [...group.events].sort((left, right) => {
        const timeDiff = parseEventTime(right.occurred_at) - parseEventTime(left.occurred_at)
        if (timeDiff !== 0) return timeDiff
        return right.id - left.id
      })
      const isBucket = group.id.startsWith('bucket:')
      const events = isBucket ? sorted.slice(0, 3) : sorted
      const total = group.events.length
      const badge = isBucket && total > 3
        ? `последние 3 из ${total}`
        : formatGroupBadge(events.length)
      return { ...group, events, badge }
    })
    .sort((left, right) => parseEventTime(right.latestOccurredAt) - parseEventTime(left.latestOccurredAt))
}

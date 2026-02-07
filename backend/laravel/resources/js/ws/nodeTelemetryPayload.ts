import type { NodeTelemetryData } from '@/composables/useNodeTelemetry'

interface RawTelemetryPayload {
  updates?: unknown
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object') {
    return null
  }
  return value as Record<string, unknown>
}

function toNumber(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }

  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) {
      return parsed
    }

    const timestamp = Date.parse(value)
    if (!Number.isNaN(timestamp)) {
      return timestamp
    }
  }

  return undefined
}

function normalizeTelemetryItem(item: unknown): NodeTelemetryData | null {
  const raw = asRecord(item)
  if (!raw) {
    return null
  }

  const nodeId = toNumber(raw.node_id)
  const metricType = typeof raw.metric_type === 'string' ? raw.metric_type : null
  const value = toNumber(raw.value)
  const timestamp = toNumber(raw.ts)

  if (!nodeId || !metricType || value === undefined || timestamp === undefined) {
    return null
  }

  const channel = typeof raw.channel === 'string' ? raw.channel : null

  return {
    node_id: nodeId,
    channel,
    metric_type: metricType,
    value,
    ts: timestamp,
  }
}

export function parseNodeTelemetryBatch(payload: unknown): NodeTelemetryData[] {
  const rawPayload = asRecord(payload) as RawTelemetryPayload | null
  const updates = Array.isArray(rawPayload?.updates) ? rawPayload?.updates : [payload]

  return updates
    .map((item) => normalizeTelemetryItem(item))
    .filter((item): item is NodeTelemetryData => item !== null)
}

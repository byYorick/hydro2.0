export interface ZoneUpdateTelemetry {
  ph?: number
  ec?: number
  temperature?: number
  humidity?: number
}

export interface ParsedZoneUpdatePayload {
  zoneId?: number
  telemetry?: ZoneUpdateTelemetry
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
    return Number.isFinite(parsed) ? parsed : undefined
  }

  return undefined
}

function normalizeTelemetry(rawTelemetry: unknown): ZoneUpdateTelemetry | undefined {
  const telemetryRecord = asRecord(rawTelemetry)
  if (!telemetryRecord) {
    return undefined
  }

  const normalized: ZoneUpdateTelemetry = {}
  const ph = toNumber(telemetryRecord.ph)
  const ec = toNumber(telemetryRecord.ec)
  const temperature = toNumber(telemetryRecord.temperature)
  const humidity = toNumber(telemetryRecord.humidity)

  if (ph !== undefined) {
    normalized.ph = ph
  }
  if (ec !== undefined) {
    normalized.ec = ec
  }
  if (temperature !== undefined) {
    normalized.temperature = temperature
  }
  if (humidity !== undefined) {
    normalized.humidity = humidity
  }

  return Object.keys(normalized).length > 0 ? normalized : undefined
}

export function parseZoneUpdatePayload(payload: unknown): ParsedZoneUpdatePayload {
  const raw = asRecord(payload)
  if (!raw) {
    return {}
  }

  const zoneId = toNumber(raw.id)
  const telemetry = normalizeTelemetry(raw.telemetry)

  return {
    zoneId,
    telemetry,
  }
}

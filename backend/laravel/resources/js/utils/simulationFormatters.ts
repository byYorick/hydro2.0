export function formatTimestamp(value?: string | null): string {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleTimeString()
}

export function formatDateTime(value?: string | null): string {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString()
}

export function formatPidValue(value?: number | null, decimals = 2): string {
  if (value === null || value === undefined) return '—'
  return Number(value).toFixed(decimals)
}

export function formatSimulationPayload(payload: unknown): string | null {
  if (!payload) return null
  if (typeof payload === 'string') {
    return payload.length > 160 ? `${payload.slice(0, 160)}…` : payload
  }
  try {
    const serialized = JSON.stringify(payload)
    return serialized.length > 160 ? `${serialized.slice(0, 160)}…` : serialized
  } catch {
    return null
  }
}

export function formatReportKey(key: string): string {
  return key.replace(/_/g, ' ')
}

export function formatReportValue(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'number') return String(value)
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

export function simulationLevelClass(level?: string | null): string {
  switch (level) {
    case 'error':
      return 'bg-[color:var(--accent-red)]'
    case 'warning':
      return 'bg-[color:var(--accent-amber)]'
    default:
      return 'bg-[color:var(--accent-green)]'
  }
}

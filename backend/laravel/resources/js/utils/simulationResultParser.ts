export interface SimulationPoint {
  t: number
  ph: number
  ec: number
  temp_air: number
}

export interface SimulationResults {
  duration_hours?: number
  step_minutes?: number
  points: SimulationPoint[]
}

function hasPoints(value: unknown): value is SimulationResults {
  if (!value || typeof value !== 'object') return false
  const payload = value as { points?: unknown }
  return Array.isArray(payload.points)
}

export function normalizeSimulationResult(payload: unknown): SimulationResults | null {
  if (!payload || typeof payload !== 'object') return null

  if (hasPoints(payload)) {
    return payload
  }

  const payloadWithData = payload as { data?: unknown; result?: unknown }

  if (hasPoints(payloadWithData.data)) {
    return payloadWithData.data
  }

  if (hasPoints(payloadWithData.result)) {
    return payloadWithData.result
  }

  const nestedResult = payloadWithData.result as { data?: unknown } | undefined
  if (nestedResult && hasPoints(nestedResult.data)) {
    return nestedResult.data
  }

  return null
}

export type SimulationRuntimeStatus = 'idle' | 'queued' | 'processing' | 'completed' | 'failed'

export interface SimulationInitialState {
  ph: number | null
  ec: number | null
  temp_air: number | null
  temp_water: number | null
  humidity_air: number | null
}

export interface SimulationSubmitForm {
  duration_hours: number
  step_minutes: number
  sim_duration_minutes: number | null
  full_simulation: boolean
  recipe_id: number | null
  initial_state: SimulationInitialState
}

export interface SimulationSubmitDrift {
  ph: number | null
  ec: number | null
  temp_air: number | null
  temp_water: number | null
  humidity_air: number | null
  noise: number | null
}

export interface SimulationPayload {
  duration_hours: number
  step_minutes: number
  sim_duration_minutes?: number
  full_simulation?: boolean
  recipe_id?: number
  initial_state?: Partial<SimulationInitialState>
  node_sim?: {
    drift_per_minute?: Partial<Record<keyof SimulationInitialState, number>>
    drift_noise_per_minute?: number
  }
}

interface ApiResponseEnvelope {
  status?: string
  data?: unknown
}

interface ApiClient {
  post<T>(url: string, data?: unknown): Promise<{ data?: T }>
}

export type SimulationSubmitOutcome =
  | {
      kind: 'queued'
      jobId: string
      status: Exclude<SimulationRuntimeStatus, 'idle'>
      payload: Record<string, unknown>
    }
  | {
      kind: 'completed'
      payload: unknown
    }
  | {
      kind: 'invalid'
      message: string
    }

const KNOWN_RUNTIME_STATUSES: ReadonlySet<SimulationRuntimeStatus> = new Set([
  'idle',
  'queued',
  'processing',
  'completed',
  'failed',
])

function normalizeRuntimeStatus(
  value: unknown,
  fallback: Exclude<SimulationRuntimeStatus, 'idle'> = 'queued'
): Exclude<SimulationRuntimeStatus, 'idle'> {
  if (typeof value !== 'string') return fallback
  if (!KNOWN_RUNTIME_STATUSES.has(value as SimulationRuntimeStatus)) return fallback
  if (value === 'idle') return fallback
  return value as Exclude<SimulationRuntimeStatus, 'idle'>
}

export function buildSimulationPayload(
  form: SimulationSubmitForm,
  drift: SimulationSubmitDrift
): SimulationPayload {
  const payload: SimulationPayload = {
    duration_hours: form.duration_hours,
    step_minutes: form.step_minutes,
  }

  if (form.sim_duration_minutes !== null) {
    payload.sim_duration_minutes = form.sim_duration_minutes
  }

  if (form.full_simulation && form.sim_duration_minutes !== null) {
    payload.full_simulation = true
  }

  if (form.recipe_id !== null) {
    payload.recipe_id = form.recipe_id
  }

  const initialState: Partial<SimulationInitialState> = {}
  if (form.initial_state.ph !== null) initialState.ph = form.initial_state.ph
  if (form.initial_state.ec !== null) initialState.ec = form.initial_state.ec
  if (form.initial_state.temp_air !== null) initialState.temp_air = form.initial_state.temp_air
  if (form.initial_state.temp_water !== null) initialState.temp_water = form.initial_state.temp_water
  if (form.initial_state.humidity_air !== null) initialState.humidity_air = form.initial_state.humidity_air
  if (Object.keys(initialState).length > 0) {
    payload.initial_state = initialState
  }

  const driftPerMinute: Partial<Record<keyof SimulationInitialState, number>> = {}
  if (drift.ph !== null) driftPerMinute.ph = drift.ph
  if (drift.ec !== null) driftPerMinute.ec = drift.ec
  if (drift.temp_air !== null) driftPerMinute.temp_air = drift.temp_air
  if (drift.temp_water !== null) driftPerMinute.temp_water = drift.temp_water
  if (drift.humidity_air !== null) driftPerMinute.humidity_air = drift.humidity_air

  const nodeSimPayload: SimulationPayload['node_sim'] = {}
  if (Object.keys(driftPerMinute).length > 0) {
    nodeSimPayload.drift_per_minute = driftPerMinute
  }
  if (drift.noise !== null) {
    nodeSimPayload.drift_noise_per_minute = drift.noise
  }
  if (Object.keys(nodeSimPayload).length > 0) {
    payload.node_sim = nodeSimPayload
  }

  return payload
}

export function useSimulationSubmit(api: ApiClient) {
  const submitZoneSimulation = async (
    zoneId: number,
    form: SimulationSubmitForm,
    drift: SimulationSubmitDrift
  ): Promise<SimulationSubmitOutcome> => {
    const payload = buildSimulationPayload(form, drift)
    const response = await api.post<ApiResponseEnvelope>(`/zones/${zoneId}/simulate`, payload)
    const responseEnvelope = response.data
    const responseData = responseEnvelope?.data

    if (responseEnvelope?.status !== 'ok' || !responseData || typeof responseData !== 'object') {
      return {
        kind: 'invalid',
        message: 'Неожиданный формат ответа',
      }
    }

    const responseObject = responseData as Record<string, unknown>
    const jobId = responseObject.job_id
    if (typeof jobId === 'string' && jobId.length > 0) {
      return {
        kind: 'queued',
        jobId,
        status: normalizeRuntimeStatus(responseObject.status, 'queued'),
        payload: responseObject,
      }
    }

    return {
      kind: 'completed',
      payload: responseData,
    }
  }

  return {
    submitZoneSimulation,
  }
}

import { nextTick, ref } from 'vue'
import { logger } from '@/utils/logger'

interface ApiClient {
  get<T = any>(url: string, config?: Record<string, unknown>): Promise<{ data?: T }>
}

export interface SimulationEvent {
  id: number
  simulation_id?: number | null
  zone_id?: number | null
  service: string
  stage: string
  status: string
  level?: string | null
  message?: string | null
  payload?: unknown
  occurred_at?: string | null
  created_at?: string | null
}

function compareSimulationEvents(a: SimulationEvent, b: SimulationEvent): number {
  const aTime = a.occurred_at || a.created_at || ''
  const bTime = b.occurred_at || b.created_at || ''
  if (aTime === bTime) {
    return b.id - a.id
  }
  return aTime > bTime ? -1 : 1
}

export function useSimulationEventFeed(api: ApiClient) {
  const simulationDbId = ref<number | null>(null)
  const simulationEvents = ref<SimulationEvent[]>([])
  const simulationEventsLoading = ref(false)
  const simulationEventsError = ref<string | null>(null)
  const simulationEventsLastId = ref(0)
  const simulationEventsListRef = ref<HTMLElement | null>(null)
  const simulationEventsPinnedTop = ref(true)

  let simulationEventsSource: EventSource | null = null
  let simulationEventsReconnectTimer: ReturnType<typeof setTimeout> | null = null
  let simulationEventsReconnectAttempts = 0
  let simulationEventsPollTimer: ReturnType<typeof setInterval> | null = null

  const stopSimulationEventStream = (): void => {
    if (simulationEventsSource) {
      simulationEventsSource.close()
      simulationEventsSource = null
    }
  }

  const clearSimulationEventReconnect = (): void => {
    if (simulationEventsReconnectTimer) {
      clearTimeout(simulationEventsReconnectTimer)
      simulationEventsReconnectTimer = null
    }
  }

  const stopSimulationEventPolling = (): void => {
    if (simulationEventsPollTimer) {
      clearInterval(simulationEventsPollTimer)
      simulationEventsPollTimer = null
    }
  }

  const scrollEventsToTop = (force = false): void => {
    if (!force && !simulationEventsPinnedTop.value) {
      return
    }
    const container = simulationEventsListRef.value
    if (!container) return
    container.scrollTop = 0
  }

  const onSimulationEventsScroll = (): void => {
    const container = simulationEventsListRef.value
    if (!container) return
    simulationEventsPinnedTop.value = container.scrollTop <= 8
  }

  const appendSimulationEvent = (event: SimulationEvent): void => {
    if (simulationEvents.value.some((item) => item.id === event.id)) {
      return
    }
    simulationEvents.value.push(event)
    simulationEvents.value.sort(compareSimulationEvents)
    simulationEventsLastId.value = Math.max(simulationEventsLastId.value, event.id)
    if (simulationEvents.value.length > 200) {
      simulationEvents.value = simulationEvents.value.slice(0, 200)
    }
    nextTick(() => {
      scrollEventsToTop()
    })
  }

  const loadSimulationEvents = async (simulationId: number): Promise<void> => {
    simulationEventsLoading.value = true
    simulationEventsError.value = null
    try {
      const response = await api.get<{ status: string; data?: SimulationEvent[]; meta?: any }>(
        `/simulations/${simulationId}/events`,
        { params: { order: 'desc', limit: 200 } }
      )
      const items = Array.isArray(response.data?.data) ? response.data?.data : []
      simulationEvents.value = items.sort(compareSimulationEvents)
      simulationEventsLastId.value = items.length ? Math.max(...items.map((item) => item.id)) : 0
      await nextTick()
      scrollEventsToTop()
    } catch (err) {
      logger.debug('[ZoneSimulationModal] Failed to load simulation events', err)
      simulationEventsError.value = 'Не удалось загрузить события симуляции'
    } finally {
      simulationEventsLoading.value = false
    }
  }

  const startSimulationEventPolling = (simulationId: number): void => {
    stopSimulationEventPolling()
    simulationEventsPollTimer = setInterval(() => {
      if (!simulationEventsLoading.value) {
        void loadSimulationEvents(simulationId)
      }
    }, 5000)
  }

  const scheduleSimulationEventReconnect = (simulationId: number): void => {
    if (simulationEventsReconnectTimer) return
    const delay = Math.min(30000, 2000 * 2 ** simulationEventsReconnectAttempts)
    simulationEventsReconnectAttempts += 1
    simulationEventsReconnectTimer = setTimeout(() => {
      simulationEventsReconnectTimer = null
      startSimulationEventStream(simulationId)
    }, delay)
  }

  const startSimulationEventStream = (simulationId: number): void => {
    stopSimulationEventStream()
    clearSimulationEventReconnect()
    stopSimulationEventPolling()
    if (typeof window === 'undefined') return
    if (typeof EventSource === 'undefined') {
      startSimulationEventPolling(simulationId)
      return
    }

    const params = new URLSearchParams()
    if (simulationEventsLastId.value > 0) {
      params.set('last_id', String(simulationEventsLastId.value))
    }
    const url = `/api/simulations/${simulationId}/events/stream?${params.toString()}`
    const source = new EventSource(url)
    simulationEventsSource = source

    source.addEventListener('open', () => {
      simulationEventsReconnectAttempts = 0
      stopSimulationEventPolling()
    })

    source.addEventListener('simulation_event', (event) => {
      try {
        const data = JSON.parse((event as MessageEvent).data)
        if (data && typeof data.id === 'number') {
          appendSimulationEvent(data as SimulationEvent)
        }
      } catch (err) {
        logger.debug('[ZoneSimulationModal] Failed to parse simulation event', err)
      }
    })

    source.addEventListener('close', () => {
      stopSimulationEventStream()
      startSimulationEventPolling(simulationId)
      scheduleSimulationEventReconnect(simulationId)
    })

    source.addEventListener('error', () => {
      stopSimulationEventStream()
      startSimulationEventPolling(simulationId)
      scheduleSimulationEventReconnect(simulationId)
    })
  }

  const attachSimulation = (simulationId: number): void => {
    if (simulationDbId.value !== simulationId) {
      simulationDbId.value = simulationId
      simulationEvents.value = []
      simulationEventsError.value = null
      simulationEventsLoading.value = false
      simulationEventsLastId.value = 0
      simulationEventsPinnedTop.value = true
    }

    if (!simulationEvents.value.length && !simulationEventsLoading.value) {
      void loadSimulationEvents(simulationId)
    }
    startSimulationEventStream(simulationId)
  }

  const resetSimulationEvents = (): void => {
    simulationDbId.value = null
    simulationEvents.value = []
    simulationEventsError.value = null
    simulationEventsLoading.value = false
    simulationEventsLastId.value = 0
    simulationEventsPinnedTop.value = true
    stopSimulationEventStream()
    clearSimulationEventReconnect()
    stopSimulationEventPolling()
  }

  return {
    simulationDbId,
    simulationEvents,
    simulationEventsLoading,
    simulationEventsError,
    simulationEventsListRef,
    onSimulationEventsScroll,
    loadSimulationEvents,
    attachSimulation,
    resetSimulationEvents,
  }
}

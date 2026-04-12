import { computed, ref, watch, onMounted } from 'vue'
import { api } from '@/services/api'
import { useToast } from '@/composables/useToast'
import { logger } from '@/utils/logger'
import { translateEventKind } from '@/utils/i18n'
import type { BadgeVariant } from '@/Components/Badge.vue'

export interface CycleEvent {
  id: number | string
  type: string
  details: Record<string, unknown>
  message: string | undefined
  created_at: string | undefined
}

function parseEventPayload(raw: Record<string, unknown>): Record<string, unknown> {
  if (raw.details && typeof raw.details === 'object' && raw.details !== null) {
    return raw.details as Record<string, unknown>
  }
  if (typeof raw.payload_json === 'string' && raw.payload_json.length > 0) {
    try {
      const parsed = JSON.parse(raw.payload_json)
      return parsed && typeof parsed === 'object' ? (parsed as Record<string, unknown>) : {}
    } catch {
      return {}
    }
  }
  return {}
}

export function getEventVariant(type: string): BadgeVariant {
  if (type.includes('HARVESTED') || type.includes('STARTED') || type.includes('RESUMED')) {
    return 'success'
  }
  if (type.includes('ABORTED') || type.includes('CRITICAL')) {
    return 'danger'
  }
  if (type.includes('PAUSED') || type.includes('WARNING')) {
    return 'warning'
  }
  return 'neutral'
}

export function getEventTypeLabel(type: string): string {
  return translateEventKind(type)
}

export function getEventMessage(event: CycleEvent): string {
  if (typeof event.message === 'string' && event.message.trim().length > 0) {
    return event.message
  }

  const details = event.details
  const type = event.type

  if (type === 'CYCLE_HARVESTED') {
    return `Урожай собран${details.batch_label ? ` (партия: ${details.batch_label})` : ''}`
  }
  if (type === 'CYCLE_ABORTED') {
    return `Цикл прерван${details.reason ? `: ${details.reason}` : ''}`
  }
  if (type === 'PHASE_TRANSITION' || type === 'RECIPE_PHASE_CHANGED') {
    return `Фаза ${details.from_phase ?? ''} → ${details.to_phase ?? ''}`
  }
  if (type === 'ZONE_COMMAND') {
    return `Команда: ${details.command_type || 'команда'}`
  }
  if (type === 'ALERT_CREATED') {
    return `Критическое предупреждение: ${details.message || details.code || 'alert'}`
  }

  return translateEventKind(type)
}

export interface UseCycleEventsOptions {
  limit?: number
}

/**
 * Загрузка событий цикла с поддержкой пагинации.
 * @param getCycleId — функция-геттер для zone_id текущего цикла
 * @param getPhaseId — функция-геттер для id текущей фазы (для реагирования на смену фазы)
 * @param options — { limit } для пагинации (по умолчанию 50)
 */
export function useCycleEvents(
  getCycleId: () => number | null | undefined,
  getPhaseId: () => number | null | undefined = () => undefined,
  options: UseCycleEventsOptions = {},
) {
  const { showToast } = useToast()
  const limit = options.limit ?? 50
  const events = ref<CycleEvent[]>([])
  const loading = ref(false)
  const loadingMore = ref(false)
  const hasMore = ref(true)

  function parseItems(response: unknown): Record<string, unknown>[] {
    if (Array.isArray(response)) return response as Record<string, unknown>[]
    if (
      response && typeof response === 'object' && 'data' in response
      && Array.isArray((response as { data?: unknown }).data)
    ) {
      return (response as { data: Record<string, unknown>[] }).data
    }
    return []
  }

  function mapEvents(items: Record<string, unknown>[]): CycleEvent[] {
    return items.map((e) => {
      const parsed = parseEventPayload(e)
      return {
        id: (e.event_id || e.id) as number | string,
        type: e.type as string,
        details: parsed,
        message: typeof e.message === 'string' ? e.message : undefined,
        created_at: e.created_at as string | undefined,
      }
    })
  }

  async function loadEvents(): Promise<void> {
    const zoneId = getCycleId()
    if (!zoneId) {
      events.value = []
      hasMore.value = false
      return
    }

    loading.value = true
    try {
      const response = await api.zones.events(zoneId, { cycle_only: true, limit })
      const items = parseItems(response)
      const mapped = mapEvents(items)
      events.value = mapped.reverse()
      hasMore.value = items.length >= limit
    } catch (err) {
      logger.error('Failed to load cycle events:', err)
      showToast('Ошибка загрузки событий цикла', 'error')
      events.value = []
      hasMore.value = false
    } finally {
      loading.value = false
    }
  }

  async function loadMore(): Promise<void> {
    const zoneId = getCycleId()
    if (!zoneId || !hasMore.value || loadingMore.value) return

    const oldest = events.value[0]
    if (!oldest) return

    loadingMore.value = true
    try {
      const response = await api.zones.events(zoneId, {
        cycle_only: true,
        limit,
        before_id: oldest.id,
      })
      const items = parseItems(response)
      const mapped = mapEvents(items)
      events.value = [...mapped.reverse(), ...events.value]
      hasMore.value = items.length >= limit
    } catch (err) {
      logger.error('Failed to load more cycle events:', err)
      showToast('Ошибка загрузки событий', 'error')
    } finally {
      loadingMore.value = false
    }
  }

  onMounted(() => {
    if (getCycleId()) {
      loadEvents()
    }
  })

  watch(
    () => getCycleId(),
    (newId) => {
      if (newId) {
        loadEvents()
      } else {
        events.value = []
        hasMore.value = false
      }
    },
  )

  watch(
    () => getPhaseId(),
    (newPhaseId, oldPhaseId) => {
      if (newPhaseId && newPhaseId !== oldPhaseId) {
        loadEvents()
      }
    },
  )

  return { events, loading, loadingMore, hasMore: computed(() => hasMore.value), loadEvents, loadMore }
}

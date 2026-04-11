import { ref, watch, onMounted } from 'vue'
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

/**
 * Загрузка событий цикла. Перезагружается при смене cycle_id или phase_id.
 * @param getCycleId — функция-геттер для zone_id текущего цикла
 * @param getPhaseId — функция-геттер для id текущей фазы (для реагирования на смену фазы)
 */
export function useCycleEvents(
  getCycleId: () => number | null | undefined,
  getPhaseId: () => number | null | undefined = () => undefined,
) {
  const { showToast } = useToast()
  const events = ref<CycleEvent[]>([])
  const loading = ref(false)

  async function loadEvents(): Promise<void> {
    const zoneId = getCycleId()
    if (!zoneId) {
      events.value = []
      return
    }

    loading.value = true
    try {
      const response = await api.zones.events(zoneId, { cycle_only: true, limit: 50 }) as Record<string, unknown>[] | { data?: Record<string, unknown>[] }
      const items: Record<string, unknown>[] = Array.isArray(response)
        ? response
        : (Array.isArray((response as { data?: Record<string, unknown>[] })?.data)
          ? ((response as { data: Record<string, unknown>[] }).data)
          : [])

      events.value = items
        .map((e) => {
          const parsed = parseEventPayload(e)
          return {
            id: (e.event_id || e.id) as number | string,
            type: e.type as string,
            details: parsed,
            message: typeof e.message === 'string' ? e.message : undefined,
            created_at: e.created_at as string | undefined,
          }
        })
        .reverse()
    } catch (err) {
      logger.error('Failed to load cycle events:', err)
      showToast('Ошибка загрузки событий цикла', 'error')
      events.value = []
    } finally {
      loading.value = false
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

  return { events, loading, loadEvents }
}

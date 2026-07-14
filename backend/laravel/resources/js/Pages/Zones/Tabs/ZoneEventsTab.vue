<template>
  <div
    class="space-y-2"
    data-testid="zone-events-list"
  >
    <div class="flex flex-wrap items-center gap-1.5 px-1">
      <span class="font-headline text-sm font-bold text-[color:var(--text-primary)]">События</span>
      <Badge
        variant="info"
        size="sm"
      >
        {{ eventsList.length }}
      </Badge>
      <div class="mx-1 h-3.5 w-px bg-[color:var(--border-muted)]"></div>
      <button
        v-for="mode in layoutModes"
        :key="mode.value"
        type="button"
        class="h-5 px-2 rounded text-[10px] font-semibold uppercase tracking-wide border transition-colors"
        :class="layoutMode === mode.value
          ? 'border-[color:var(--accent-cyan)] text-[color:var(--accent-cyan)] bg-[color:var(--bg-elevated)]'
          : 'border-transparent text-[color:var(--text-dim)] hover:border-[color:var(--border-strong)] hover:text-[color:var(--text-muted)]'"
        @click="layoutMode = mode.value"
      >
        {{ mode.label }}
      </button>
    </div>

    <div
      class="grid gap-2"
      :class="layoutMode === 'both'
        ? 'lg:grid-cols-2'
        : 'grid-cols-1'"
    >
      <OperatorStoriesPanel
        v-if="layoutMode === 'both' || layoutMode === 'operator'"
        :stories="operatorStories"
      />
      <EngineerEventsPanel
        v-if="layoutMode === 'both' || layoutMode === 'engineer'"
        v-model:selected-kind="selectedKind"
        v-model:query="query"
        :grouped-events="groupedEvents"
        :filtered-count="filteredEvents.length"
        :can-load-more="canLoadMore"
        :loading-more="loadingMore"
        @export="exportEvents"
        @load-more="loadOlderEvents"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import Badge from '@/Components/Badge.vue'
import OperatorStoriesPanel from '@/Components/Events/OperatorStoriesPanel.vue'
import EngineerEventsPanel from '@/Components/Events/EngineerEventsPanel.vue'
import { api } from '@/services/api'
import { classifyEventKind } from '@/utils/i18n'
import { groupZoneEvents } from '@/utils/eventGroups'
import { buildOperatorStories } from '@/utils/eventOperatorView'
import type { ZoneEvent } from '@/types/ZoneEvent'

interface Props {
  events: ZoneEvent[]
  zoneId: number | null
}

const props = defineProps<Props>()

type KindFilter = 'ALL' | 'ALERT' | 'WARNING' | 'INFO' | 'ACTION'
type LayoutMode = 'both' | 'operator' | 'engineer'

const layoutModes: Array<{ value: LayoutMode; label: string }> = [
  { value: 'both', label: 'Оба' },
  { value: 'operator', label: 'Оператор' },
  { value: 'engineer', label: 'Инженер' },
]

const layoutMode = ref<LayoutMode>('both')
const selectedKind = ref<KindFilter>('ALL')
const query = ref('')
const olderEvents = ref<ZoneEvent[]>([])
const hasMoreBefore = ref(true)
const loadingMore = ref(false)

const queryLower = computed(() => query.value.toLowerCase())

const eventsList = computed(() => {
  const incoming = Array.isArray(props.events) ? props.events : []
  const merged = new Map<number, ZoneEvent>()
  ;[...incoming, ...olderEvents.value].forEach((event) => {
    merged.set(event.id, event)
  })
  return [...merged.values()].sort((left, right) => {
    const timeDiff = Date.parse(right.occurred_at || '') - Date.parse(left.occurred_at || '')
    if (timeDiff !== 0) return timeDiff
    return right.id - left.id
  })
})

watch(
  () => props.events,
  () => {
    // При полной перезагрузке props убираем дубликаты из older, оставляя только id старше props
    const propIds = new Set((props.events || []).map((event) => event.id))
    const minPropId = propIds.size > 0 ? Math.min(...propIds) : null
    if (minPropId === null) {
      olderEvents.value = []
      return
    }
    olderEvents.value = olderEvents.value.filter((event) => event.id < minPropId)
  },
)

const filteredEvents = computed(() => {
  return eventsList.value.filter((event) => {
    const matchesKind =
      selectedKind.value === 'ALL'
        ? true
        : classifyEventKind(event.kind) === selectedKind.value
    const matchesQuery = queryLower.value
      ? event.message?.toLowerCase().includes(queryLower.value)
        || event.kind?.toLowerCase().includes(queryLower.value)
      : true
    return matchesKind && matchesQuery
  })
})

const groupedEvents = computed(() => groupZoneEvents(filteredEvents.value))
const operatorStories = computed(() => buildOperatorStories(eventsList.value))

const oldestEventId = computed(() => {
  if (eventsList.value.length === 0) return null
  return Math.min(...eventsList.value.map((event) => event.id))
})

const canLoadMore = computed(() => Boolean(props.zoneId) && hasMoreBefore.value && oldestEventId.value !== null)

function mapApiEvent(raw: Record<string, unknown>): ZoneEvent | null {
  const idRaw = raw.event_id ?? raw.id
  const id = typeof idRaw === 'number' ? idRaw : Number(idRaw)
  if (!Number.isFinite(id)) return null
  const kind = typeof raw.type === 'string'
    ? raw.type
    : (typeof raw.kind === 'string' ? raw.kind : 'INFO')
  const payload = (raw.payload && typeof raw.payload === 'object' && !Array.isArray(raw.payload))
    ? raw.payload as Record<string, unknown>
    : (raw.details && typeof raw.details === 'object' && !Array.isArray(raw.details))
      ? raw.details as Record<string, unknown>
      : {}
  const occurred = typeof raw.created_at === 'string'
    ? raw.created_at
    : (typeof raw.occurred_at === 'string' ? raw.occurred_at : new Date().toISOString())

  return {
    id,
    kind,
    zone_id: typeof raw.zone_id === 'number' ? raw.zone_id : (props.zoneId ?? undefined),
    message: typeof raw.message === 'string' ? raw.message : '',
    occurred_at: occurred,
    payload,
  }
}

async function loadOlderEvents(): Promise<void> {
  if (!props.zoneId || !oldestEventId.value || loadingMore.value) return
  loadingMore.value = true
  try {
    const page = await api.zones.eventsPage(props.zoneId, {
      before_id: oldestEventId.value,
      limit: 50,
    })
    const mapped = page.data
      .map((row) => mapApiEvent(row))
      .filter((event): event is ZoneEvent => event !== null)
    olderEvents.value = [...olderEvents.value, ...mapped]
    hasMoreBefore.value = page.has_more_before && mapped.length > 0
  } catch {
    hasMoreBefore.value = false
  } finally {
    loadingMore.value = false
  }
}

function exportEvents(): void {
  if (typeof window === 'undefined') return
  const rows: string[] = ['id,kind,message,occurred_at']
  filteredEvents.value.forEach((event) => {
    const escapedMessage = (event.message || '').replace(/"/g, '""')
    rows.push(`${event.id},${event.kind},"${escapedMessage}",${event.occurred_at}`)
  })
  const csv = rows.join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  const fileLabel = props.zoneId ? `zone-${props.zoneId}` : 'zone'
  link.href = url
  link.download = `${fileLabel}-events.csv`
  link.click()
  URL.revokeObjectURL(url)
}
</script>

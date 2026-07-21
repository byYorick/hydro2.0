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
    <div
      v-if="canLoadMore && layoutMode === 'operator'"
      class="flex justify-center px-1"
    >
      <button
        type="button"
        class="h-7 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] px-3 text-[11px] font-semibold text-[color:var(--text-primary)] hover:border-[color:var(--border-strong)] disabled:opacity-50"
        :disabled="loadingMore"
        data-testid="zone-events-operator-load-more"
        @click="loadOlderEvents"
      >
        {{ loadingMore ? 'Загрузка…' : 'Загрузить ещё' }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { usePage } from '@inertiajs/vue3'
import Badge from '@/Components/Badge.vue'
import OperatorStoriesPanel from '@/Components/Events/OperatorStoriesPanel.vue'
import EngineerEventsPanel from '@/Components/Events/EngineerEventsPanel.vue'
import { api } from '@/services/api'
import { classifyEventKind } from '@/utils/i18n'
import { groupZoneEvents } from '@/utils/eventGroups'
import { buildOperatorStories } from '@/utils/eventOperatorView'
import { logger } from '@/utils/logger'
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

const page = usePage()
const layoutMode = ref<LayoutMode>('both')
const selectedKind = ref<KindFilter>('ALL')
const query = ref('')
const olderEvents = ref<ZoneEvent[]>([])
const hasMoreBefore = ref(true)
const loadingMore = ref(false)
/** Avoid re-stomping engineer query after the user clears/edits it. */
const lastAppliedDeepLink = ref<string | null>(null)

function readDeepLinkParams(): { taskId: string | null; executionId: string | null } {
  // Prefer window.location: zone tab switching uses useUrlState → history.replaceState,
  // which does not update Inertia page.url.
  const fromWindow = typeof window !== 'undefined' ? (window.location.search ?? '').replace(/^\?/, '') : ''
  const pageUrl = typeof page.url === 'string' ? page.url : ''
  const fromPage = pageUrl.includes('?') ? pageUrl.slice(pageUrl.indexOf('?') + 1) : ''
  const params = new URLSearchParams(fromWindow || fromPage)
  const taskRaw = params.get('task_id')?.trim() ?? ''
  const executionRaw = params.get('execution_id')?.trim() ?? ''
  return {
    taskId: taskRaw !== '' ? taskRaw : null,
    executionId: executionRaw !== '' ? executionRaw : null,
  }
}

function applyDeepLinkFilters(): void {
  const { taskId, executionId } = readDeepLinkParams()
  const key = taskId
    ? `task:${taskId}`
    : (executionId ? `execution:${executionId}` : '')
  if (!key) {
    // Clear sticky filter when deep-link params disappear (e.g. popstate).
    if (lastAppliedDeepLink.value && query.value === lastAppliedDeepLink.value) {
      query.value = ''
      layoutMode.value = 'both'
    }
    lastAppliedDeepLink.value = null
    return
  }
  if (lastAppliedDeepLink.value === key) {
    return
  }
  lastAppliedDeepLink.value = key
  layoutMode.value = 'engineer'
  query.value = key
}

onMounted(() => {
  applyDeepLinkFilters()
  if (typeof window !== 'undefined') {
    window.addEventListener('popstate', applyDeepLinkFilters)
  }
})

onBeforeUnmount(() => {
  if (typeof window !== 'undefined') {
    window.removeEventListener('popstate', applyDeepLinkFilters)
  }
})

watch(
  () => page.url,
  () => {
    applyDeepLinkFilters()
  },
)

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
      hasMoreBefore.value = true
      return
    }
    olderEvents.value = olderEvents.value.filter((event) => event.id < minPropId)
    hasMoreBefore.value = true
  },
)

function eventMatchesQuery(event: ZoneEvent, needle: string): boolean {
  if (!needle) {
    return true
  }

  const payload = event.payload && typeof event.payload === 'object'
    ? event.payload as Record<string, unknown>
    : {}
  const taskId = payload.task_id != null ? String(payload.task_id) : ''
  const executionId = payload.execution_id != null ? String(payload.execution_id) : ''
  const windowId = typeof payload.correction_window_id === 'string'
    ? payload.correction_window_id.toLowerCase()
    : ''

  // Exact prefix filters first — never use substring includes ("task:2" must not match task 28).
  // Only treat `task:<digits>` as a task filter so correction_window_id values like
  // `task:28:irrigating:...` still fall through to includes().
  if (/^task:\d+$/.test(needle)) {
    const wanted = needle.slice('task:'.length).trim()
    return wanted !== '' && taskId === wanted
  }
  if (/^execution:\d+$/.test(needle)) {
    const wanted = needle.slice('execution:'.length).trim()
    // AE3 zone_events store task_id; scheduler deep-link uses execution_id (= ae_tasks.id).
    return wanted !== '' && (executionId === wanted || taskId === wanted)
  }
  if (needle.startsWith('#') && /^\d+$/.test(needle.slice(1))) {
    return taskId === needle.slice(1)
  }

  if (event.message?.toLowerCase().includes(needle) || event.kind?.toLowerCase().includes(needle)) {
    return true
  }
  if (taskId && (taskId === needle || `#${taskId}` === needle)) {
    return true
  }
  if (executionId && executionId === needle) {
    return true
  }
  if (windowId && windowId.includes(needle)) {
    return true
  }
  return false
}

const filteredEvents = computed(() => {
  return eventsList.value.filter((event) => {
    const matchesKind =
      selectedKind.value === 'ALL'
        ? true
        : classifyEventKind(event.kind) === selectedKind.value
    return matchesKind && eventMatchesQuery(event, queryLower.value)
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
    const params: Record<string, unknown> = {
      before_id: oldestEventId.value,
      limit: 50,
    }
    // Keep deep-link causal filter on the server so load-more can find older task events.
    const deepLinkTaskMatch = query.value.match(/^task:(\d+)$/i)
      ?? query.value.match(/^execution:(\d+)$/i)
    if (deepLinkTaskMatch) {
      params.task_id = Number(deepLinkTaskMatch[1])
    }
    const page = await api.zones.eventsPage(props.zoneId, params)
    const mapped = page.data
      .map((row) => mapApiEvent(row))
      .filter((event): event is ZoneEvent => event !== null)
    olderEvents.value = [...olderEvents.value, ...mapped]
    hasMoreBefore.value = page.has_more_before && mapped.length > 0
  } catch (error) {
    // Keep load-more available after transient failures.
    logger.warn('[ZoneEventsTab] Failed to load older events', { error })
  } finally {
    loadingMore.value = false
  }
}

function csvEscape(value: string): string {
  const normalized = value.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
  return `"${normalized.replace(/"/g, '""')}"`
}

function exportEvents(): void {
  if (typeof window === 'undefined') return
  const rows: string[] = ['id,kind,message,occurred_at']
  filteredEvents.value.forEach((event) => {
    rows.push([
      String(event.id),
      csvEscape(event.kind || ''),
      csvEscape(event.message || ''),
      csvEscape(event.occurred_at || ''),
    ].join(','))
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

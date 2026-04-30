<template>
  <div
    class="space-y-2"
    data-testid="zone-events-list"
  >
    <!-- Компактная шапка: заголовок + пилюли + поиск + CSV в одну строку -->
    <div class="flex flex-wrap items-center gap-1.5 px-1">
      <span class="font-headline text-sm font-bold text-[color:var(--text-primary)]">События</span>
      <Badge
        variant="info"
        size="sm"
      >
        {{ filteredEvents.length }}
      </Badge>
      <div class="mx-1 h-3.5 w-px bg-[color:var(--border-muted)]"></div>
      <button
        v-for="kind in kindOptions"
        :key="kind.value"
        type="button"
        class="h-5 px-2 rounded text-[10px] font-semibold uppercase tracking-wide border transition-colors"
        :class="selectedKind === kind.value
          ? 'border-[color:var(--accent-cyan)] text-[color:var(--accent-cyan)] bg-[color:var(--bg-elevated)]'
          : 'border-transparent text-[color:var(--text-dim)] hover:border-[color:var(--border-strong)] hover:text-[color:var(--text-muted)]'"
        @click="selectedKind = kind.value"
      >
        {{ kind.label }}
      </button>
      <div class="ml-auto flex items-center gap-1.5">
        <input
          :value="query"
          class="input-field h-6 w-32 text-xs px-2"
          placeholder="Поиск..."
          @input="query = ($event.target as HTMLInputElement).value"
        />
        <button
          class="h-6 px-2 text-[11px] rounded-md border border-[color:var(--border-muted)] text-[color:var(--text-dim)] hover:text-[color:var(--text-primary)] hover:bg-[color:var(--bg-elevated)] transition-colors"
          @click="exportEvents"
        >
          CSV
        </button>
      </div>
    </div>

    <!-- Список событий -->
    <section class="surface-card rounded-xl border border-[color:var(--border-muted)] p-2">
      <div
        v-if="filteredEvents.length === 0"
        class="py-6 text-center text-[11px] text-[color:var(--text-dim)]"
      >
        Нет событий по текущим фильтрам
      </div>

      <div
        v-else
        class="max-h-[calc(100vh-260px)] space-y-1.5 overflow-y-auto pr-0.5"
      >
        <div
          v-for="group in groupedEvents"
          :key="group.id"
          class="rounded-lg border"
          :class="group.isCorrelated
            ? 'border-[color:var(--accent-cyan)]/25 bg-[color:var(--accent-cyan)]/3'
            : 'border-[color:var(--border-muted)]'"
        >
          <!-- Заголовок группы (клик сворачивает/разворачивает) -->
          <div
            class="flex flex-wrap items-center justify-between gap-1.5 px-2.5 py-1.5 cursor-pointer select-none hover:bg-[color:var(--bg-elevated)]/40 transition-colors rounded-t-lg"
            :class="isGroupCollapsed(group.id) ? 'rounded-b-lg' : 'border-b border-[color:var(--border-muted)]/70'"
            @click="toggleGroupCollapsed(group.id)"
          >
            <div class="flex min-w-0 items-center gap-1.5">
              <span class="text-[11px] text-[color:var(--text-dim)] shrink-0">
                {{ isGroupCollapsed(group.id) ? '›' : '⌄' }}
              </span>
              <span class="text-[11px] font-semibold text-[color:var(--text-primary)] truncate">
                {{ group.title }}
              </span>
              <span
                v-if="group.badge"
                class="shrink-0 font-mono text-[10px] text-[color:var(--text-dim)]"
              >
                {{ group.badge }}
              </span>
            </div>
            <div class="flex shrink-0 items-center gap-2 text-[10px] text-[color:var(--text-muted)]">
              <span
                v-if="group.subtitle"
                class="hidden truncate sm:inline max-w-[140px]"
              >
                {{ group.subtitle }}
              </span>
              <span>{{ formatGroupTimestamp(group.latestOccurredAt) }}</span>
            </div>
          </div>

          <!-- Строки событий -->
          <div
            v-if="!isGroupCollapsed(group.id)"
            class="divide-y divide-[color:var(--border-muted)]/50"
          >
            <EventRow
              v-for="item in group.events"
              :key="item.id"
              :item="item"
              :expanded="isExpanded(item.id)"
              @toggle="toggleExpanded(item.id)"
            />
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import Badge from '@/Components/Badge.vue'
import EventRow from '@/Components/Events/EventRow.vue'
import { classifyEventKind } from '@/utils/i18n'
import { groupZoneEvents } from '@/utils/eventGroups'
import type { ZoneEvent } from '@/types/ZoneEvent'

interface Props {
  events: ZoneEvent[]
  zoneId: number | null
}

const props = defineProps<Props>()

type KindFilter = 'ALL' | 'ALERT' | 'WARNING' | 'INFO' | 'ACTION'

const kindOptions: Array<{ value: KindFilter; label: string }> = [
  { value: 'ALL', label: 'Все' },
  { value: 'ALERT', label: 'Тревога' },
  { value: 'WARNING', label: 'Предупр.' },
  { value: 'INFO', label: 'Инфо' },
  { value: 'ACTION', label: 'Действие' },
]

const selectedKind = ref<KindFilter>('ALL')
const query = ref('')
const expandedIds = ref<Set<number>>(new Set())
const collapsedGroupIds = ref<Set<string>>(new Set())

const queryLower = computed(() => query.value.toLowerCase())

const filteredEvents = computed(() => {
  const list = Array.isArray(props.events) ? props.events : []
  return list.filter((event) => {
    const matchesKind =
      selectedKind.value === 'ALL'
        ? true
        : classifyEventKind(event.kind) === selectedKind.value
    const matchesQuery = queryLower.value
      ? event.message?.toLowerCase().includes(queryLower.value) ||
        event.kind?.toLowerCase().includes(queryLower.value)
      : true
    return matchesKind && matchesQuery
  })
})

const groupedEvents = computed(() => groupZoneEvents(filteredEvents.value))

function isExpanded(id: number): boolean {
  return expandedIds.value.has(id)
}

function toggleExpanded(id: number): void {
  const next = new Set(expandedIds.value)
  if (next.has(id)) {
    next.delete(id)
  } else {
    next.add(id)
  }
  expandedIds.value = next
}

function isGroupCollapsed(groupId: string): boolean {
  return collapsedGroupIds.value.has(groupId)
}

function toggleGroupCollapsed(groupId: string): void {
  const next = new Set(collapsedGroupIds.value)
  if (next.has(groupId)) {
    next.delete(groupId)
  } else {
    next.add(groupId)
  }
  collapsedGroupIds.value = next
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

function formatGroupTimestamp(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('ru-RU')
}
</script>

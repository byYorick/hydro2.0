<template>
  <section
    class="surface-card rounded-xl border border-[color:var(--border-muted)] p-2"
    data-testid="zone-events-engineer"
  >
    <div class="flex flex-wrap items-center gap-1.5 px-1 pb-1.5">
      <span class="text-xs font-semibold text-[color:var(--text-primary)]">Инженер</span>
      <Badge
        variant="neutral"
        size="sm"
      >
        {{ filteredCount }}
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
        @click="$emit('update:selectedKind', kind.value)"
      >
        {{ kind.label }}
      </button>
      <div class="ml-auto flex items-center gap-1.5">
        <input
          :value="query"
          class="input-field h-6 w-28 text-xs px-2"
          placeholder="Поиск..."
          @input="$emit('update:query', ($event.target as HTMLInputElement).value)"
        />
        <button
          type="button"
          class="h-6 px-2 text-[11px] rounded-md border border-[color:var(--border-muted)] text-[color:var(--text-dim)] hover:text-[color:var(--text-primary)] hover:bg-[color:var(--bg-elevated)] transition-colors"
          @click="$emit('export')"
        >
          CSV
        </button>
      </div>
    </div>

    <div
      v-if="groupedEvents.length === 0"
      class="py-6 text-center text-[11px] text-[color:var(--text-dim)]"
    >
      Нет событий по текущим фильтрам
    </div>

    <div
      v-else
      class="max-h-[calc(100vh-300px)] space-y-1.5 overflow-y-auto pr-0.5"
    >
      <div
        v-for="group in groupedEvents"
        :key="group.id"
        class="rounded-lg border"
        :class="group.isCorrelated
          ? 'border-[color:var(--accent-cyan)]/25 bg-[color:var(--accent-cyan)]/3'
          : 'border-[color:var(--border-muted)]'"
      >
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
          <span class="shrink-0 text-[10px] text-[color:var(--text-muted)]">
            {{ formatGroupTimestamp(group.latestOccurredAt) }}
          </span>
        </div>

        <div
          v-if="!isGroupCollapsed(group.id)"
          class="divide-y divide-[color:var(--border-muted)]/50"
        >
          <template
            v-for="item in feedItemsForGroup(group)"
            :key="itemKey(item)"
          >
            <EventRow
              v-if="item.type === 'event'"
              :item="item.event"
              :expanded="isExpanded(item.event.id)"
              @toggle="toggleExpanded(item.event.id)"
            />
            <button
              v-else
              type="button"
              class="flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-[11px] text-[color:var(--text-muted)] hover:bg-[color:var(--bg-elevated)]/40"
              @click="toggleCollapsedReveal(item.kind + ':' + item.latestOccurredAt)"
            >
              <span class="font-mono text-[10px] text-[color:var(--text-dim)]">{{ item.label }}</span>
              <span class="ml-auto text-[10px] text-[color:var(--text-dim)]">
                {{ revealedCollapses.has(item.kind + ':' + item.latestOccurredAt) ? 'скрыть' : 'показать' }}
              </span>
            </button>
            <template v-if="item.type === 'collapsed' && revealedCollapses.has(item.kind + ':' + item.latestOccurredAt)">
              <EventRow
                v-for="event in item.events"
                :key="event.id"
                :item="event"
                :expanded="isExpanded(event.id)"
                @toggle="toggleExpanded(event.id)"
              />
            </template>
          </template>
        </div>
      </div>
    </div>

    <div
      v-if="canLoadMore"
      class="pt-2 px-1"
    >
      <button
        type="button"
        class="h-7 w-full rounded-md border border-[color:var(--border-muted)] text-[11px] text-[color:var(--text-muted)] hover:text-[color:var(--text-primary)] hover:bg-[color:var(--bg-elevated)] transition-colors disabled:opacity-50"
        :disabled="loadingMore"
        @click="$emit('load-more')"
      >
        {{ loadingMore ? 'Загрузка…' : 'Загрузить ещё' }}
      </button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import Badge from '@/Components/Badge.vue'
import EventRow from '@/Components/Events/EventRow.vue'
import { collapseNoisyEvents, type CollapsedFeedItem } from '@/utils/eventOperatorView'
import type { ZoneEventGroup } from '@/utils/eventGroups'

type KindFilter = 'ALL' | 'ALERT' | 'WARNING' | 'INFO' | 'ACTION'

defineProps<{
  groupedEvents: ZoneEventGroup[]
  filteredCount: number
  selectedKind: KindFilter
  query: string
  canLoadMore: boolean
  loadingMore: boolean
}>()

defineEmits<{
  'update:selectedKind': [KindFilter]
  'update:query': [string]
  export: []
  'load-more': []
}>()

const kindOptions: Array<{ value: KindFilter; label: string }> = [
  { value: 'ALL', label: 'Все' },
  { value: 'ALERT', label: 'Тревога' },
  { value: 'WARNING', label: 'Предупр.' },
  { value: 'INFO', label: 'Инфо' },
  { value: 'ACTION', label: 'Действие' },
]

const expandedIds = ref<Set<number>>(new Set())
const collapsedGroupIds = ref<Set<string>>(new Set())
const revealedCollapses = ref<Set<string>>(new Set())

function isExpanded(id: number): boolean {
  return expandedIds.value.has(id)
}

function toggleExpanded(id: number): void {
  const next = new Set(expandedIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedIds.value = next
}

function isGroupCollapsed(groupId: string): boolean {
  return collapsedGroupIds.value.has(groupId)
}

function toggleGroupCollapsed(groupId: string): void {
  const next = new Set(collapsedGroupIds.value)
  if (next.has(groupId)) next.delete(groupId)
  else next.add(groupId)
  collapsedGroupIds.value = next
}

function toggleCollapsedReveal(key: string): void {
  const next = new Set(revealedCollapses.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  revealedCollapses.value = next
}

function feedItemsForGroup(group: ZoneEventGroup): CollapsedFeedItem[] {
  return collapseNoisyEvents(group.events)
}

function itemKey(item: CollapsedFeedItem): string {
  if (item.type === 'event') return `e-${item.event.id}`
  return `c-${item.kind}-${item.latestOccurredAt}-${item.count}`
}

function formatGroupTimestamp(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('ru-RU')
}
</script>

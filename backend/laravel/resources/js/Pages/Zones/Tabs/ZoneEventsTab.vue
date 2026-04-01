<template>
  <div class="space-y-4">
    <EventFilterBar
      v-model="selectedKind"
      :query="query"
      @update:query="query = $event"
      @export="exportEvents"
    />

    <section class="surface-card border border-[color:var(--border-muted)] rounded-2xl p-4">
      <div
        v-if="filteredEvents.length === 0"
        class="py-6 text-center text-sm text-[color:var(--text-dim)]"
      >
        Нет событий по текущим фильтрам
      </div>
      <div
        v-else
        class="h-[520px]"
      >
        <VirtualList
          v-if="useVirtual"
          :items="filteredEvents"
          :item-size="64"
          class="h-full"
          key-field="id"
        >
          <template #default="{ item }">
            <EventRow
              :item="item"
              :expanded="isExpanded(item.id)"
              @toggle="toggleExpanded(item.id)"
            />
          </template>
        </VirtualList>
        <div
          v-else
          class="max-h-[520px] space-y-0 overflow-y-auto divide-y divide-[color:var(--border-muted)]"
        >
          <EventRow
            v-for="item in filteredEvents"
            :key="item.id"
            :item="item"
            :expanded="isExpanded(item.id)"
            @toggle="toggleExpanded(item.id)"
          />
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import VirtualList from '@/Components/VirtualList.vue'
import EventFilterBar from '@/Components/Events/EventFilterBar.vue'
import EventRow from '@/Components/Events/EventRow.vue'
import { classifyEventKind } from '@/utils/i18n'
import type { ZoneEvent } from '@/types/ZoneEvent'

interface Props {
  events: ZoneEvent[]
  zoneId: number | null
}

const props = defineProps<Props>()

type KindFilter = 'ALL' | 'ALERT' | 'WARNING' | 'INFO' | 'ACTION'

const selectedKind = ref<KindFilter>('ALL')
const query = ref('')
const expandedIds = ref<Set<number>>(new Set())

const queryLower = computed(() => query.value.toLowerCase())

const filteredEvents = computed(() => {
  const list = Array.isArray(props.events) ? props.events : []
  return list.filter((event) => {
    const matchesKind = selectedKind.value === 'ALL'
      ? true
      : classifyEventKind(event.kind) === selectedKind.value
    const matchesQuery = queryLower.value
      ? (event.message?.toLowerCase().includes(queryLower.value) || event.kind?.toLowerCase().includes(queryLower.value))
      : true
    return matchesKind && matchesQuery
  })
})

const useVirtual = computed(() => filteredEvents.value.length > 200)

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

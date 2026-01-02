<template>
  <div class="space-y-4">
    <section class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4">
      <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
        <div class="flex flex-wrap items-center gap-2">
          <span class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">Фильтр</span>
          <button
            v-for="kind in kindOptions"
            :key="kind.value"
            type="button"
            class="h-9 px-3 rounded-full border text-xs font-semibold transition-colors"
            :class="selectedKind === kind.value
              ? 'border-[color:var(--accent-cyan)] text-[color:var(--accent-cyan)] bg-[color:var(--bg-elevated)]'
              : 'border-[color:var(--border-muted)] text-[color:var(--text-dim)] hover:border-[color:var(--border-strong)]'"
            @click="selectedKind = kind.value"
          >
            {{ kind.label }}
          </button>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <input
            v-model="query"
            class="input-field h-9 w-full sm:w-64"
            placeholder="Поиск по событию..."
          />
          <Button size="sm" variant="secondary" @click="exportEvents">Экспорт CSV</Button>
        </div>
      </div>
    </section>

    <section class="surface-card border border-[color:var(--border-muted)] rounded-2xl p-4">
      <div v-if="filteredEvents.length === 0" class="text-sm text-[color:var(--text-dim)] text-center py-6">
        Нет событий по текущим фильтрам
      </div>
      <div v-else class="h-[520px]">
        <VirtualList
          v-if="useVirtual"
          :items="filteredEvents"
          :item-size="64"
          class="h-full"
          key-field="id"
        >
          <template #default="{ item }">
            <div class="text-sm text-[color:var(--text-muted)] flex items-start gap-2 py-2 border-b border-[color:var(--border-muted)]">
              <Badge :variant="getEventVariant(item.kind)" class="text-xs shrink-0">
                {{ translateEventKind(item.kind) }}
              </Badge>
              <div class="flex-1 min-w-0">
                <div class="text-xs text-[color:var(--text-dim)]">
                  {{ new Date(item.occurred_at).toLocaleString('ru-RU') }}
                </div>
                <div class="text-sm">{{ item.message }}</div>
              </div>
            </div>
          </template>
        </VirtualList>
        <div v-else class="space-y-1 max-h-[520px] overflow-y-auto">
          <div
            v-for="item in filteredEvents"
            :key="item.id"
            class="text-sm text-[color:var(--text-muted)] flex items-start gap-2 py-2 border-b border-[color:var(--border-muted)]"
          >
            <Badge :variant="getEventVariant(item.kind)" class="text-xs shrink-0">
              {{ translateEventKind(item.kind) }}
            </Badge>
            <div class="flex-1 min-w-0">
              <div class="text-xs text-[color:var(--text-dim)]">
                {{ new Date(item.occurred_at).toLocaleString('ru-RU') }}
              </div>
              <div class="text-sm">{{ item.message }}</div>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import VirtualList from '@/Components/VirtualList.vue'
import { translateEventKind } from '@/utils/i18n'
import type { ZoneEvent } from '@/types/ZoneEvent'

interface Props {
  events: ZoneEvent[]
  zoneId: number | null
}

const props = defineProps<Props>()

const selectedKind = ref<'ALL' | 'ALERT' | 'WARNING' | 'INFO' | 'ACTION'>('ALL')
const query = ref('')

const kindOptions: Array<{ value: 'ALL' | 'ALERT' | 'WARNING' | 'INFO' | 'ACTION', label: string }> = [
  { value: 'ALL', label: 'Все' },
  { value: 'ALERT', label: 'Alert' },
  { value: 'WARNING', label: 'Warning' },
  { value: 'INFO', label: 'Info' },
  { value: 'ACTION', label: 'Action' },
]

const queryLower = computed(() => query.value.toLowerCase())

const filteredEvents = computed(() => {
  const list = Array.isArray(props.events) ? props.events : []
  return list.filter((event) => {
    const matchesKind = selectedKind.value === 'ALL' ? true : event.kind === selectedKind.value
    const matchesQuery = queryLower.value
      ? event.message?.toLowerCase().includes(queryLower.value)
      : true
    return matchesKind && matchesQuery
  })
})

const useVirtual = computed(() => filteredEvents.value.length > 200)

function getEventVariant(kind: string): 'danger' | 'warning' | 'info' | 'neutral' {
  if (kind === 'ALERT') return 'danger'
  if (kind === 'WARNING') return 'warning'
  if (kind === 'INFO') return 'info'
  return 'neutral'
}

const exportEvents = (): void => {
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

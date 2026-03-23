<template>
  <div class="space-y-4">
    <section class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4">
      <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
        <div class="flex flex-wrap items-center gap-2">
          <span class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">Фильтр</span>
          <button
            v-for="status in statusOptions"
            :key="status.value"
            type="button"
            class="h-9 px-3 rounded-full border text-xs font-semibold transition-colors"
            :class="selectedStatus === status.value
              ? 'border-[color:var(--accent-cyan)] text-[color:var(--accent-cyan)] bg-[color:var(--bg-elevated)]'
              : 'border-[color:var(--border-muted)] text-[color:var(--text-dim)] hover:border-[color:var(--border-strong)]'"
            @click="selectedStatus = status.value"
          >
            {{ status.label }}
          </button>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <input
            v-model="query"
            class="input-field h-9 w-full sm:w-72"
            placeholder="Поиск по типу, сообщению, details..."
          />
        </div>
      </div>
    </section>

    <section class="surface-card border border-[color:var(--border-muted)] rounded-2xl p-4">
      <div
        v-if="filteredAlerts.length === 0"
        class="text-sm text-[color:var(--text-dim)] text-center py-6"
      >
        Алерты по текущим фильтрам не найдены
      </div>

      <div
        v-else
        class="h-[520px]"
      >
        <VirtualList
          v-if="useVirtual"
          :items="filteredAlerts"
          :item-size="72"
          class="h-full"
          key-field="id"
        >
          <template #default="{ item }">
            <div class="text-sm text-[color:var(--text-muted)] flex items-start gap-2 py-2 border-b border-[color:var(--border-muted)]">
              <Badge
                :variant="alertStatusVariant(item.status)"
                class="text-xs shrink-0"
              >
                {{ translateStatus(item.status) }}
              </Badge>
              <div class="flex-1 min-w-0">
                <div class="flex flex-wrap items-center gap-2 text-xs text-[color:var(--text-dim)]">
                  <span>{{ formatDate(item.created_at) }}</span>
                  <span v-if="getAlertTitle(item)">{{ getAlertTitle(item) }}</span>
                </div>
                <div class="text-sm">
                  {{ getAlertMessage(item) || 'Без сообщения' }}
                </div>
              </div>
            </div>
          </template>
        </VirtualList>

        <div
          v-else
          class="space-y-1 max-h-[520px] overflow-y-auto"
        >
          <div
            v-for="item in filteredAlerts"
            :key="item.id"
            class="text-sm text-[color:var(--text-muted)] flex items-start gap-2 py-2 border-b border-[color:var(--border-muted)]"
          >
            <Badge
              :variant="alertStatusVariant(item.status)"
              class="text-xs shrink-0"
            >
              {{ translateStatus(item.status) }}
            </Badge>
            <div class="flex-1 min-w-0">
              <div class="flex flex-wrap items-center gap-2 text-xs text-[color:var(--text-dim)]">
                <span>{{ formatDate(item.created_at) }}</span>
                <span v-if="getAlertTitle(item)">{{ getAlertTitle(item) }}</span>
              </div>
              <div class="text-sm">
                {{ getAlertMessage(item) || 'Без сообщения' }}
              </div>
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
import VirtualList from '@/Components/VirtualList.vue'
import { translateStatus } from '@/utils/i18n'
import type { Alert } from '@/types/Alert'

interface Props {
  alerts: Alert[]
  zoneId: number | null
}

const props = defineProps<Props>()

const selectedStatus = ref<'ALL' | 'ACTIVE' | 'RESOLVED'>('ALL')
const query = ref('')

const statusOptions: Array<{ value: 'ALL' | 'ACTIVE' | 'RESOLVED', label: string }> = [
  { value: 'ALL', label: 'Все' },
  { value: 'ACTIVE', label: 'Активные' },
  { value: 'RESOLVED', label: 'Решённые' },
]

const queryLower = computed(() => query.value.toLowerCase())

const statusNormalized = (status: string | undefined): 'ACTIVE' | 'RESOLVED' | 'OTHER' => {
  const normalized = String(status || '').toUpperCase()
  if (normalized === 'ACTIVE') return 'ACTIVE'
  if (normalized === 'RESOLVED') return 'RESOLVED'
  return 'OTHER'
}

const detailsToString = (details: Alert['details']): string => {
  if (!details || typeof details !== 'object') return ''
  try {
    return JSON.stringify(details)
  } catch {
    return ''
  }
}

const getAlertMessage = (alert: Alert): string => {
  if (typeof alert.message === 'string' && alert.message.trim() !== '') return alert.message
  if (alert.details && typeof alert.details === 'object') {
    const details = alert.details as Record<string, unknown>
    const detailMessage = details.message ?? details.reason ?? details.error ?? details.error_message ?? details.description
    if (typeof detailMessage === 'string' && detailMessage.trim() !== '') return detailMessage
  }
  return ''
}

const getAlertTitle = (alert: Alert): string => {
  if (typeof alert.title === 'string' && alert.title.trim() !== '') return alert.title
  if (alert.details && typeof alert.details === 'object') {
    const details = alert.details as Record<string, unknown>
    if (typeof details.title === 'string' && details.title.trim() !== '') {
      return details.title
    }
  }
  return typeof alert.type === 'string' ? alert.type : ''
}

const filteredAlerts = computed(() => {
  const list = Array.isArray(props.alerts) ? props.alerts : []

  return list.filter((alert) => {
    const normalizedStatus = statusNormalized(alert.status)
    const matchesStatus = selectedStatus.value === 'ALL' ? true : normalizedStatus === selectedStatus.value
    const searchSource = `${alert.type || ''} ${getAlertMessage(alert)} ${detailsToString(alert.details)}`.toLowerCase()
    const matchesQuery = queryLower.value ? searchSource.includes(queryLower.value) : true
    return matchesStatus && matchesQuery
  })
})

const useVirtual = computed(() => filteredAlerts.value.length > 200)

const alertStatusVariant = (status: Alert['status']): 'danger' | 'success' | 'warning' => {
  const normalized = statusNormalized(status)
  if (normalized === 'ACTIVE') return 'danger'
  if (normalized === 'RESOLVED') return 'success'
  return 'warning'
}

const formatDate = (value: string): string => {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString('ru-RU')
}
</script>

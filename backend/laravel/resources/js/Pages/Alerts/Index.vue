<template>
  <AppLayout>
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-lg font-semibold">Алерты</h1>
    </div>
    <div class="mb-3 flex flex-col sm:flex-row sm:flex-wrap items-stretch sm:items-center gap-2">
      <div class="flex items-center gap-2 flex-1 sm:flex-none">
        <label class="text-sm text-[color:var(--text-muted)] shrink-0">Фильтр:</label>
        <select v-model="onlyActive" data-testid="alerts-filter-active" class="input-select flex-1 sm:w-auto sm:min-w-[140px]">
          <option :value="true">Только активные</option>
          <option :value="false">Все</option>
        </select>
      </div>
      <div class="flex items-center gap-2 flex-1 sm:flex-none">
        <label class="text-sm text-[color:var(--text-muted)] shrink-0">Зона:</label>
        <input v-model="zoneQuery" data-testid="alerts-filter-zone" placeholder="Зона..." class="input-field flex-1 sm:w-56" />
      </div>
    </div>

    <div class="rounded-xl border border-[color:var(--border-muted)] overflow-hidden max-h-[720px] flex flex-col">
      <div class="overflow-auto flex-1">
        <table class="w-full border-collapse" data-testid="alerts-table">
          <thead class="bg-[color:var(--bg-elevated)] text-[color:var(--text-muted)] text-sm sticky top-0 z-10">
            <tr>
              <th class="text-left px-3 py-2 font-semibold border-b border-[color:var(--border-muted)]">Тип</th>
              <th class="text-left px-3 py-2 font-semibold border-b border-[color:var(--border-muted)]">Зона</th>
              <th class="text-left px-3 py-2 font-semibold border-b border-[color:var(--border-muted)]">Время</th>
              <th class="text-left px-3 py-2 font-semibold border-b border-[color:var(--border-muted)]">Статус</th>
              <th class="text-left px-3 py-2 font-semibold border-b border-[color:var(--border-muted)]">Действия</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(a, index) in paginatedAlerts"
              :key="a.id"
              :data-testid="`alert-row-${a.id}`"
              :class="index % 2 === 0 ? 'bg-[color:var(--bg-surface-strong)]' : 'bg-[color:var(--bg-surface)]'"
              class="text-sm border-b border-[color:var(--border-muted)] hover:bg-[color:var(--bg-elevated)] transition-colors"
            >
              <td class="px-3 py-2 text-xs text-[color:var(--text-muted)]">{{ a.type }}</td>
              <td class="px-3 py-2 text-xs text-[color:var(--text-muted)]">
                <span class="truncate block">{{ a.zone?.name || `Zone #${a.zone_id}` || '-' }}</span>
              </td>
              <td class="px-3 py-2 text-xs text-[color:var(--text-muted)]">{{ a.created_at ? new Date(a.created_at).toLocaleString('ru-RU') : '-' }}</td>
              <td class="px-3 py-2 text-xs text-[color:var(--text-muted)]">{{ translateStatus(a.status) }}</td>
              <td class="px-3 py-2">
                <Button size="sm" variant="secondary" :data-testid="`alert-resolve-btn-${a.id}`" @click="onResolve(a)" :disabled="a.status === 'resolved'">Подтвердить</Button>
              </td>
            </tr>
            <tr v-if="!paginatedAlerts.length">
              <td colspan="5" class="px-3 py-6 text-sm text-[color:var(--text-dim)] text-center">Нет алертов по текущим фильтрам</td>
            </tr>
          </tbody>
        </table>
      </div>
      <Pagination
        v-model:current-page="currentPage"
        v-model:per-page="perPage"
        :total="filtered.length"
      />
    </div>

    <Modal :open="confirm.open" title="Подтвердить алерт" @close="confirm.open=false">
      <div class="text-sm text-[color:var(--text-muted)]">Вы уверены, что алерт будет помечен как решённый?</div>
      <template #footer>
        <Button size="sm" variant="secondary" @click="confirm.open=false">Отмена</Button>
        <Button size="sm" @click="doResolve">Подтвердить</Button>
      </template>
    </Modal>
  </AppLayout>
</template>

<script setup lang="ts">
import { reactive, ref, watch, computed, onMounted, onUnmounted } from 'vue'
import AppLayout from '@/Layouts/AppLayout.vue'
import Button from '@/Components/Button.vue'
import Modal from '@/Components/Modal.vue'
import Pagination from '@/Components/Pagination.vue'
import { usePage } from '@inertiajs/vue3'
import { subscribeAlerts } from '@/ws/subscriptions'
import { translateStatus } from '@/utils/i18n'
import { logger } from '@/utils/logger'
import { useApi } from '@/composables/useApi'
import { useFilteredList } from '@/composables/useFilteredList'
import type { Alert } from '@/types'

interface PageProps {
  alerts?: Alert[]
}

const page = usePage<PageProps>()
const alerts = ref<Alert[]>(Array.isArray(page.props.alerts) ? [...page.props.alerts] : [])

// Синхронизируем локальный список с props без перезагрузок страницы
watch(
  () => page.props.alerts,
  (newAlerts) => {
    alerts.value = Array.isArray(newAlerts) ? [...newAlerts] : []
  },
  { deep: true }
)

const upsertAlert = (alert: Alert): void => {
  if (!alert || !('id' in alert)) return
  const idx = alerts.value.findIndex(a => a.id === alert.id)
  if (idx >= 0) {
    alerts.value[idx] = { ...alerts.value[idx], ...alert }
  } else {
    alerts.value.unshift(alert)
  }
}

const markResolved = (id: number): void => {
  const idx = alerts.value.findIndex(a => a.id === id)
  if (idx >= 0) {
    alerts.value[idx] = {
      ...alerts.value[idx],
      status: 'resolved',
      resolved_at: new Date().toISOString(),
    }
  }
}

// Инициализация API без Toast (используем стандартную обработку ошибок)
const { api } = useApi()

const headers = ['Тип', 'Зона', 'Время', 'Статус', 'Действия']
const onlyActive = ref<boolean>(true)
const zoneQuery = ref<string>('')
const currentPage = ref<number>(1)
const perPage = ref<number>(25)

const filtered = useFilteredList(alerts, (alert) => {
  const activeOk = onlyActive.value ? alert.status !== 'resolved' && alert.status !== 'RESOLVED' : true
  const zoneName = alert.zone?.name || `Zone #${alert.zone_id}` || ''
  const zoneOk = zoneQuery.value ? zoneName.toLowerCase().includes(zoneQuery.value.toLowerCase()) : true
  return activeOk && zoneOk
})

const paginatedAlerts = computed(() => {
  const total = filtered.value.length
  if (total === 0) return []
  
  // Защита от некорректных значений
  const maxPage = Math.ceil(total / perPage.value) || 1
  const validPage = Math.min(currentPage.value, maxPage)
  if (validPage !== currentPage.value) {
    currentPage.value = validPage
  }
  
  const start = (validPage - 1) * perPage.value
  const end = start + perPage.value
  return filtered.value.slice(start, end)
})

const confirm = reactive<{ open: boolean; alertId: number | null }>({ open: false, alertId: null })
const onResolve = (a: Alert): void => {
  confirm.open = true
  confirm.alertId = a.id
}
const doResolve = (): void => {
  const id = confirm.alertId
  if (!id) return
  api.patch(`/api/alerts/${id}/ack`, {}).then((res) => {
    // Обновляем локальный список без перезагрузки страницы
    const updated = (res?.data as { data?: Alert })?.data
    if (updated) {
      upsertAlert(updated)
    } else {
      markResolved(id)
    }
    confirm.open = false
  }).catch((err) => {
    logger.error('Failed to resolve alert:', err)
    confirm.open = false
  })
}

// subscribe realtime
let unsubscribeAlerts: (() => void) | null = null

onMounted(() => {
  unsubscribeAlerts = subscribeAlerts((e) => {
    if (e?.alert) {
      upsertAlert(e.alert as Alert)
    }
  })
})

onUnmounted(() => {
  unsubscribeAlerts?.()
  unsubscribeAlerts = null
})

// Сбрасываем на первую страницу при изменении фильтров
watch([onlyActive, zoneQuery], () => {
  currentPage.value = 1
})

</script>

<style scoped>
table {
  table-layout: auto;
}

th, td {
  white-space: nowrap;
}

th:first-child,
td:first-child {
  min-width: 120px;
}

th:nth-child(2),
td:nth-child(2) {
  min-width: 150px;
  max-width: 250px;
}

th:nth-child(3),
td:nth-child(3) {
  min-width: 180px;
}

th:nth-child(4),
td:nth-child(4) {
  min-width: 100px;
}

th:last-child,
td:last-child {
  min-width: 140px;
  text-align: center;
}
</style>

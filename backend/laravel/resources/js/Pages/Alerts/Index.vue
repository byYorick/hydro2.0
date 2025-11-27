<template>
  <AppLayout>
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-lg font-semibold">Алерты</h1>
    </div>
    <div class="mb-3 flex flex-col sm:flex-row sm:flex-wrap items-stretch sm:items-center gap-2">
      <div class="flex items-center gap-2 flex-1 sm:flex-none">
        <label class="text-sm text-neutral-300 shrink-0">Фильтр:</label>
        <select v-model="onlyActive" class="h-9 flex-1 sm:w-auto sm:min-w-[140px] rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm">
          <option :value="true">Только активные</option>
          <option :value="false">Все</option>
        </select>
      </div>
      <div class="flex items-center gap-2 flex-1 sm:flex-none">
        <label class="text-sm text-neutral-300 shrink-0">Зона:</label>
        <input v-model="zoneQuery" placeholder="Зона..." class="h-9 flex-1 sm:w-56 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm" />
      </div>
    </div>

    <div class="rounded-xl border border-neutral-800 overflow-hidden max-h-[720px] flex flex-col">
      <!-- Заголовок таблицы -->
      <div class="flex-shrink-0 grid grid-cols-5 gap-0 bg-neutral-900 text-neutral-300 text-sm border-b border-neutral-800">
        <div v-for="(h, i) in headers" :key="i" class="px-3 py-2 text-left font-medium">
          {{ h }}
        </div>
      </div>
      <!-- Виртуализированный список -->
      <div class="flex-1 overflow-hidden">
        <RecycleScroller
          :items="filtered"
          :item-size="rowHeight"
          key-field="id"
          v-slot="{ item: a, index }"
          class="virtual-table-body h-full"
        >
          <div 
            :class="index % 2 === 0 ? 'bg-neutral-950' : 'bg-neutral-925'" 
            class="grid grid-cols-5 gap-0 text-sm border-b border-neutral-900"
            style="height:44px"
          >
            <div class="px-3 py-2 flex items-center">{{ a.type }}</div>
            <div class="px-3 py-2 flex items-center">{{ a.zone?.name || `Zone #${a.zone_id}` || '-' }}</div>
            <div class="px-3 py-2 flex items-center">{{ a.created_at ? new Date(a.created_at).toLocaleString('ru-RU') : '-' }}</div>
            <div class="px-3 py-2 flex items-center">{{ translateStatus(a.status) }}</div>
            <div class="px-3 py-2 flex items-center">
              <Button size="sm" variant="secondary" @click="onResolve(a)" :disabled="a.status === 'resolved'">Подтвердить</Button>
            </div>
          </div>
        </RecycleScroller>
        <div v-if="!filtered.length" class="text-sm text-neutral-400 px-3 py-6">Нет алертов по текущим фильтрам</div>
      </div>
    </div>

    <Modal :open="confirm.open" title="Подтвердить алерт" @close="confirm.open=false">
      <div class="text-sm">Вы уверены, что алерт будет помечен как решённый?</div>
      <template #footer>
        <Button size="sm" variant="secondary" @click="confirm.open=false">Отмена</Button>
        <Button size="sm" @click="doResolve">Подтвердить</Button>
      </template>
    </Modal>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, reactive, ref, onMounted, onUnmounted } from 'vue'
import AppLayout from '@/Layouts/AppLayout.vue'
import Button from '@/Components/Button.vue'
import Modal from '@/Components/Modal.vue'
import { usePage, router } from '@inertiajs/vue3'
import { subscribeAlerts } from '@/bootstrap'
import { translateStatus } from '@/utils/i18n'
import { logger } from '@/utils/logger'
import { useApi } from '@/composables/useApi'
import type { Alert } from '@/types'

interface PageProps {
  alerts?: Alert[]
}

const page = usePage<PageProps>()
const alerts = computed(() => (page.props.alerts || []) as Alert[])

// Инициализация API без Toast (используем стандартную обработку ошибок)
const { api } = useApi()

const headers = ['Тип', 'Зона', 'Время', 'Статус', 'Действия']
const onlyActive = ref<boolean>(true)
const zoneQuery = ref<string>('')

const filtered = computed(() =>
  alerts.value.filter(a => {
    const activeOk = onlyActive.value ? a.status !== 'resolved' && a.status !== 'RESOLVED' : true
    const zoneName = a.zone?.name || `Zone #${a.zone_id}` || ''
    const zoneOk = zoneQuery.value ? zoneName.toLowerCase().includes(zoneQuery.value.toLowerCase()) : true
    return activeOk && zoneOk
  })
)
const confirm = reactive<{ open: boolean; alertId: number | null }>({ open: false, alertId: null })
const onResolve = (a: Alert): void => {
  confirm.open = true
  confirm.alertId = a.id
}
const doResolve = (): void => {
  const id = confirm.alertId
  if (!id) return
  api.patch(`/api/alerts/${id}/ack`, {}).then(() => {
    router.reload({ only: ['alerts'] })
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
      router.reload({ only: ['alerts'] })
    }
  })
})

onUnmounted(() => {
  unsubscribeAlerts?.()
  unsubscribeAlerts = null
})

// Виртуализация через RecycleScroller
const rowHeight = 44
</script>


<template>
  <AppLayout>
    <h1 class="text-lg font-semibold mb-4">Alerts</h1>
    <div class="mb-3 flex flex-wrap items-center gap-2">
      <label class="text-sm text-neutral-300">Фильтр:</label>
      <select v-model="onlyActive" class="h-9 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm">
        <option :value="true">Только активные</option>
        <option :value="false">Все</option>
      </select>
      <label class="ml-4 text-sm text-neutral-300">Зона:</label>
      <input v-model="zoneQuery" placeholder="Zone..." class="h-9 w-48 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm" />
    </div>

    <div class="rounded-xl border border-neutral-800 overflow-hidden max-h-[700px]" @scroll.passive="onScroll">
      <table class="min-w-full text-sm">
        <thead class="bg-neutral-900 text-neutral-300">
          <tr>
            <th v-for="(h, i) in headers" :key="i" class="px-3 py-2 text-left font-medium border-b border-neutral-800">
              {{ h }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="a in windowed" :key="a.id" class="odd:bg-neutral-950 even:bg-neutral-925" style="height:44px">
            <td class="px-3 py-2 border-b border-neutral-900">{{ a.type }}</td>
            <td class="px-3 py-2 border-b border-neutral-900">{{ a.zone?.name || `Zone #${a.zone_id}` || '-' }}</td>
            <td class="px-3 py-2 border-b border-neutral-900">{{ a.created_at ? new Date(a.created_at).toLocaleString('ru-RU') : '-' }}</td>
            <td class="px-3 py-2 border-b border-neutral-900">{{ a.status === 'resolved' ? 'RESOLVED' : 'ACTIVE' }}</td>
            <td class="px-3 py-2 border-b border-neutral-900">
              <div class="flex gap-2">
                <Button size="sm" variant="secondary" @click="onResolve(a)" :disabled="a.status === 'resolved'">Подтвердить</Button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
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

<script setup>
import { computed, reactive, ref, onMounted } from 'vue'
import AppLayout from '@/Layouts/AppLayout.vue'
import Button from '@/Components/Button.vue'
import Modal from '@/Components/Modal.vue'
import axios from 'axios'
import { usePage, router } from '@inertiajs/vue3'
import { subscribeAlerts } from '@/bootstrap'

const page = usePage()
const alerts = computed(() => page.props.alerts || [])

const headers = ['Type', 'Zone', 'Time', 'Status', 'Actions']
const onlyActive = ref(true)
const zoneQuery = ref('')

const filtered = computed(() =>
  alerts.value.filter(a => {
    const activeOk = onlyActive.value ? a.status !== 'resolved' && a.status !== 'RESOLVED' : true
    const zoneName = a.zone?.name || `Zone #${a.zone_id}` || ''
    const zoneOk = zoneQuery.value ? zoneName.toLowerCase().includes(zoneQuery.value.toLowerCase()) : true
    return activeOk && zoneOk
  })
)
const confirm = reactive({ open: false, alertId: null })
const onResolve = (a) => {
  confirm.open = true
  confirm.alertId = a.id
}
const doResolve = () => {
  const id = confirm.alertId
  axios.patch(`/api/alerts/${id}/ack`, {}, {
    headers: {
      'Accept': 'application/json',
      'X-Requested-With': 'XMLHttpRequest',
    },
  }).then(() => {
    router.reload({ only: ['alerts'] })
    confirm.open = false
  }).catch((err) => {
    console.error('Failed to resolve alert:', err)
    confirm.open = false
  })
}

// subscribe realtime
onMounted(() => {
  subscribeAlerts((e) => {
    if (e?.alert) {
      router.reload({ only: ['alerts'] })
    }
  })
})

// Простейшая виртуализация: окно по индексу
const rowHeight = 44
const visibleCount = 15
const start = ref(0)
function onScroll(ev) {
  const top = ev.target.scrollTop || 0
  start.value = Math.max(0, Math.floor(top / rowHeight) - 2)
}
const windowed = computed(() => filtered.value.slice(start.value, start.value + visibleCount))
</script>


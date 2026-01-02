<template>
  <AppLayout>
    <h1 class="text-lg font-semibold mb-4">Admin · Zones</h1>
    <Card class="mb-4">
      <div class="text-sm font-semibold mb-2">Create Zone</div>
      <form class="grid grid-cols-1 md:grid-cols-4 gap-2" @submit.prevent="onCreate">
        <input v-model="form.name" placeholder="Name" class="input-field" />
        <input v-model="form.description" placeholder="Description" class="input-field" />
        <select v-model="form.status" class="input-select">
          <option value="RUNNING">RUNNING</option>
          <option value="PAUSED">PAUSED</option>
          <option value="WARNING">WARNING</option>
          <option value="ALARM">ALARM</option>
        </select>
        <select v-model="form.greenhouse_id" class="input-select">
          <option :value="null">Выберите теплицу</option>
          <option v-for="gh in greenhouses" :key="gh.id" :value="gh.id">{{ gh.name }}</option>
        </select>
        <div class="md:col-span-4">
          <Button size="sm" type="submit">Create</Button>
        </div>
      </form>
    </Card>

    <Card>
      <div class="text-sm font-semibold mb-2">Zones</div>
      <ul class="text-sm text-[color:var(--text-muted)] space-y-1">
        <li v-for="z in zones" :key="(z as Zone).id">
          {{ (z as Zone).name }} — {{ (z as Zone).status }}
          <span v-if="(z as Zone).description"> — {{ (z as Zone).description }}</span>
          <span v-if="(z as Zone).greenhouse"> — {{ (z as Zone).greenhouse!.name }}</span>
        </li>
      </ul>
    </Card>
  </AppLayout>
</template>

<script setup lang="ts">
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import { reactive, ref, onMounted, computed } from 'vue'
import { logger } from '@/utils/logger'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { usePageProps } from '@/composables/usePageProps'
import { extractData } from '@/utils/apiHelpers'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import { useZonesStore } from '@/stores/zones'
import type { Greenhouse, Zone } from '@/types'

interface PageProps {
  zones?: Zone[]
  [key: string]: any
}

const { zones: zonesProp } = usePageProps<PageProps>(['zones'])
const zonesStore = useZonesStore()

// Используем store для получения зон, с fallback на props
const zones = computed(() => {
  const storeZones = zonesStore.allZones as Zone[]
  return storeZones.length > 0 ? storeZones : (zonesProp?.value || [])
})
const { showToast } = useToast()
const { api } = useApi(showToast)
const greenhouses = ref<Greenhouse[]>([])
const form = reactive<{ name: string; description: string; status: string; greenhouse_id: number | null }>({ 
  name: '', 
  description: '', 
  status: 'RUNNING', 
  greenhouse_id: null 
})

onMounted(async () => {
  // Инициализируем store из props
  if (zonesProp?.value) {
    zonesStore.initFromProps({ zones: zonesProp.value as Zone[] })
  }
  
  // Загружаем теплицы
  try {
    const response = await api.get<{ data?: Greenhouse[] } | Greenhouse[]>('/greenhouses')
    const data = extractData<Greenhouse[]>(response.data) || []
    greenhouses.value = Array.isArray(data) ? data : []
  } catch (err) {
    // Ошибка уже обработана в useApi через showToast
    logger.error('[Admin/Zones] Failed to load greenhouses:', err)
  }
})

async function onCreate(): Promise<void> {
  try {
    const response = await api.post<{ data?: Zone } | Zone>('/zones', form)
    const newZone = extractData<Zone>(response.data) || response.data as Zone
    
    // Добавляем новую зону в store вместо reload
    if (newZone?.id) {
      zonesStore.upsert(newZone)
      logger.debug('[Admin/Zones] Zone added to store after creation', { zoneId: newZone.id })
    }
    
    showToast('Зона успешно создана', 'success', TOAST_TIMEOUT.NORMAL)
    form.name = ''
    form.description = ''
    form.greenhouse_id = null
  } catch (err) {
    // Ошибка уже обработана в useApi через showToast
    logger.error('[Admin/Zones] Failed to create zone:', err)
  }
}
</script>

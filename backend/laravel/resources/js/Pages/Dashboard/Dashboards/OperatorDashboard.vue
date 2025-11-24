<template>
  <div class="space-y-6">
    <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
      <h1 class="text-lg font-semibold">Панель оператора</h1>
      <div class="flex flex-wrap gap-2">
        <Link href="/zones" class="flex-1 sm:flex-none min-w-[120px]">
          <Button size="sm" variant="outline" class="w-full sm:w-auto">Все зоны</Button>
        </Link>
      </div>
    </div>

    <!-- Активные зоны -->
    <div class="space-y-4">
      <h2 class="text-md font-semibold">Активные зоны</h2>
      <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        <Card
          v-for="zone in activeZones"
          :key="zone.id"
          class="hover:border-neutral-700 transition-colors"
        >
          <div class="flex items-start justify-between mb-3">
            <div>
              <div class="text-sm font-semibold">{{ zone.name }}</div>
              <div v-if="zone.greenhouse" class="text-xs text-neutral-400 mt-1">
                {{ zone.greenhouse.name }}
              </div>
            </div>
            <Badge :variant="zone.status === 'RUNNING' ? 'success' : 'warning'">
              {{ translateStatus(zone.status) }}
            </Badge>
          </div>
          
          <!-- Метрики -->
          <div class="grid grid-cols-2 gap-2 mb-3 text-xs">
            <div v-if="zone.telemetry?.ph !== null && zone.telemetry?.ph !== undefined && typeof zone.telemetry.ph === 'number'">
              <span class="text-neutral-400">pH:</span>
              <span class="ml-1 font-medium">{{ zone.telemetry.ph.toFixed(2) }}</span>
            </div>
            <div v-if="zone.telemetry?.ec !== null && zone.telemetry?.ec !== undefined && typeof zone.telemetry.ec === 'number'">
              <span class="text-neutral-400">EC:</span>
              <span class="ml-1 font-medium">{{ zone.telemetry.ec.toFixed(2) }}</span>
            </div>
            <div v-if="zone.telemetry?.temperature !== null && zone.telemetry?.temperature !== undefined">
              <span class="text-neutral-400">Темп:</span>
              <span class="ml-1 font-medium">{{ zone.telemetry.temperature.toFixed(1) }}°C</span>
            </div>
            <div v-if="zone.telemetry?.humidity !== null && zone.telemetry?.humidity !== undefined">
              <span class="text-neutral-400">Влаж:</span>
              <span class="ml-1 font-medium">{{ zone.telemetry.humidity.toFixed(0) }}%</span>
            </div>
          </div>
          
          <!-- Быстрые действия -->
          <div class="flex gap-2 mt-3">
            <Link :href="`/zones/${zone.id}`">
              <Button size="sm" variant="secondary">Открыть</Button>
            </Link>
            <Button
              size="sm"
              variant="outline"
              @click="irrigateZone(zone.id)"
            >
              Полить
            </Button>
          </div>
        </Card>
      </div>
    </div>

    <!-- Требуют внимания -->
    <div v-if="zonesNeedingAttention.length > 0" class="space-y-4">
      <h2 class="text-md font-semibold">Требуют внимания</h2>
      <Card class="border-amber-800 bg-amber-950/10">
        <div class="space-y-3">
          <div
            v-for="zone in zonesNeedingAttention"
            :key="zone.id"
            class="flex items-center justify-between p-3 bg-neutral-900 rounded-lg"
          >
            <div>
              <div class="text-sm font-semibold">{{ zone.name }}</div>
              <div class="text-xs text-amber-400 mt-1">
                {{ zone.issues?.join(', ') || 'Требует внимания' }}
              </div>
            </div>
            <div class="flex gap-2">
              <Link :href="`/zones/${zone.id}`">
                <Button size="sm" variant="secondary">Открыть</Button>
              </Link>
              <Button
                size="sm"
                variant="outline"
                @click="resolveIssues(zone.id)"
              >
                Исправить
              </Button>
            </div>
          </div>
        </div>
      </Card>
    </div>

    <!-- Активные алерты -->
    <div class="space-y-4">
      <div class="flex items-center justify-between">
        <h2 class="text-md font-semibold">Активные алерты</h2>
        <Link href="/alerts">
          <Button size="sm" variant="outline">Все алерты</Button>
        </Link>
      </div>
      <Card>
        <div v-if="activeAlerts.length > 0" class="space-y-2">
          <div
            v-for="alert in activeAlerts"
            :key="alert.id"
            class="flex items-center justify-between p-3 bg-neutral-900 rounded-lg hover:bg-neutral-800 transition-colors"
          >
            <div>
              <div class="text-sm font-semibold">{{ alert.type }}</div>
              <div class="text-xs text-neutral-400 mt-1">
                Зона: {{ alert.zone?.name || `ID ${alert.zone_id}` }}
              </div>
              <div class="text-xs text-neutral-500 mt-1">
                {{ formatTime(alert.created_at) }}
              </div>
            </div>
            <Button
              size="sm"
              variant="primary"
              @click="resolveAlert(alert.id)"
            >
              Разрешить
            </Button>
          </div>
        </div>
        <div v-else class="text-sm text-neutral-400 text-center py-4">
          Нет активных алертов
        </div>
      </Card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Link } from '@inertiajs/vue3'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import Badge from '@/Components/Badge.vue'
import { translateStatus } from '@/utils/i18n'
import { formatTime } from '@/utils/formatTime'
import { useApi } from '@/composables/useApi'
import type { Zone, Alert, Device } from '@/types'

interface Props {
  dashboard: {
    zones?: Zone[]
    activeAlerts?: Alert[]
  }
}

const props = defineProps<Props>()

const { api } = useApi()

const activeZones = computed(() => {
  return (props.dashboard.zones || []).filter(z => z.status === 'RUNNING').slice(0, 9)
})

const zonesNeedingAttention = computed(() => {
  return (props.dashboard.zones || []).filter(z => 
    z.status === 'WARNING' || 
    z.status === 'ALARM' ||
    (z.alertsCount && z.alertsCount > 0)
  )
})

const activeAlerts = computed(() => {
  return (props.dashboard.activeAlerts || []).slice(0, 5)
})

async function irrigateZone(zoneId: number) {
  try {
    await api.post(`/api/zones/${zoneId}/commands`, {
      type: 'FORCE_IRRIGATION',
      params: { duration_sec: 10 }
    })
    // TODO: Показать Toast уведомление
  } catch (error) {
    console.error('Failed to irrigate zone:', error)
  }
}

async function resolveAlert(alertId: number) {
  try {
    await api.post(`/api/alerts/${alertId}/resolve`)
    // TODO: Показать Toast уведомление и обновить список
  } catch (error) {
    console.error('Failed to resolve alert:', error)
  }
}

function resolveIssues(zoneId: number) {
  // TODO: Реализовать разрешение проблем зоны
  console.log('Resolve issues for zone:', zoneId)
}
</script>


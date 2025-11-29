<template>
  <div class="space-y-6">
    <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h1 class="text-lg font-semibold">Панель оператора</h1>
        <p class="text-sm text-neutral-400 max-w-2xl">
          Контролируйте теплицы, следите за зонами и быстро реагируйте на аномалии из единого интерфейса.
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <Link href="/logs">
          <Button size="sm" variant="secondary">Служебные логи</Button>
        </Link>
        <Link href="/zones">
          <Button size="sm" variant="outline">Все зоны</Button>
        </Link>
      </div>
    </div>

    <div class="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
      <GreenhouseStatusCard
        v-for="gh in enrichedGreenhouses"
        :key="gh.id"
        :greenhouse="gh"
        :problematic-zones="zonesByGreenhouse[gh.id] || []"
      />
    </div>

    <div class="grid gap-4 lg:grid-cols-2">
      <Card class="space-y-4">
        <div class="flex items-center justify-between">
          <div>
            <h2 class="text-base font-semibold">Активные зоны</h2>
            <p class="text-xs text-neutral-500">Состояние зон с текущим циклом</p>
          </div>
          <span class="text-xs text-neutral-500">Всего {{ activeZones.length }}</span>
        </div>
        <div class="space-y-2">
          <div
            v-for="zone in activeZones.slice(0, 4)"
            :key="zone.id"
            class="surface-strong rounded-2xl border border-neutral-800 p-3 flex items-center justify-between gap-3"
          >
            <div>
              <div class="text-sm font-semibold">{{ zone.name }}</div>
              <div class="text-xs text-neutral-400">{{ zone.greenhouse?.name }}</div>
              <div class="text-xs text-neutral-500 mt-1 flex gap-3">
                <span v-if="zone.telemetry?.ph !== undefined">pH {{ zone.telemetry.ph?.toFixed(2) ?? '-' }}</span>
                <span v-if="zone.telemetry?.ec !== undefined">EC {{ zone.telemetry.ec?.toFixed(2) ?? '-' }}</span>
              </div>
            </div>
            <div class="flex flex-col items-end gap-2">
              <Badge :variant="zone.status === 'RUNNING' ? 'success' : 'warning'">{{ translateStatus(zone.status) }}</Badge>
              <div class="flex gap-2">
                <Link :href="`/zones/${zone.id}`">
                  <Button size="sm" variant="outline">Открыть</Button>
                </Link>
                <Button size="sm" variant="ghost" @click="irrigateZone(zone.id)">💧</Button>
              </div>
            </div>
          </div>
        </div>
        <div v-if="activeZones.length > 4" class="text-xs text-neutral-500 text-right">
          + ещё {{ activeZones.length - 4 }} активных зон
        </div>
      </Card>

      <Card class="space-y-4">
        <div class="flex items-center justify-between">
          <div>
            <h2 class="text-base font-semibold">Активные алерты</h2>
            <p class="text-xs text-neutral-500">События требуют вашего внимания</p>
          </div>
          <Link href="/alerts">
            <Button size="sm" variant="outline">Все алерты</Button>
          </Link>
        </div>
        <div class="space-y-2">
          <div
            v-for="alert in activeAlerts"
            :key="alert.id"
            class="surface-strong rounded-2xl border border-neutral-800 p-3 flex items-center justify-between gap-2"
          >
            <div>
              <div class="text-sm font-semibold">{{ alert.type }}</div>
              <div class="text-xs text-neutral-400 mt-1">
                {{ alert.zone?.name || `Зона #${alert.zone_id}` }}
              </div>
              <div class="text-xs text-neutral-500 mt-1">{{ formatTime(alert.created_at) }}</div>
            </div>
            <div class="flex flex-col gap-2">
              <Button size="sm" variant="primary" @click="resolveAlert(alert.id)">Разрешить</Button>
            </div>
          </div>
        </div>
        <div v-if="!activeAlerts.length" class="text-xs text-neutral-500 text-center py-4">
          Нет активных алертов
        </div>
      </Card>
    </div>

    <div v-if="zonesNeedingAttention.length > 0" class="space-y-4">
      <div class="flex items-center justify-between">
        <h2 class="text-base font-semibold">Требуют внимания</h2>
        <Button size="sm" variant="secondary" @click="resolveIssues(zonesNeedingAttention[0]?.id)">Следующая</Button>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Card v-for="zone in zonesNeedingAttention" :key="zone.id" class="border-amber-800 bg-amber-950/10">
          <div class="flex items-start justify-between">
            <div>
              <div class="text-sm font-semibold">{{ zone.name }}</div>
              <div class="text-xs text-neutral-400">{{ zone.greenhouse?.name }}</div>
            </div>
            <Badge :variant="zone.status === 'ALARM' ? 'danger' : 'warning'">{{ zone.status }}</Badge>
          </div>
          <p class="text-xs text-neutral-400 mt-2">
            {{ zone.description || 'Описание отсутствует' }}
          </p>
          <div class="text-xs text-red-300 mt-2">Алертов: {{ zone.alerts_count ?? 0 }}</div>
        </Card>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Link } from '@inertiajs/vue3'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import Badge from '@/Components/Badge.vue'
import GreenhouseStatusCard from '@/Components/GreenhouseStatusCard.vue'
import { translateStatus } from '@/utils/i18n'
import { formatTime } from '@/utils/formatTime'
import { useApi } from '@/composables/useApi'
import { useFilteredList } from '@/composables/useFilteredList'
import type { Zone, Alert } from '@/types'

interface DashboardProps {
  dashboard: {
    zones?: Zone[]
    activeAlerts?: Alert[]
    greenhouses?: Array<Record<string, any>>
    problematicZones?: Array<Zone & { greenhouse?: { id: number; name: string } }>
  }
}

const props = defineProps<DashboardProps>()

const { api } = useApi()

const enrichedGreenhouses = computed(() => {
  return (props.dashboard.greenhouses || []).map((gh) => ({
    ...gh,
    zone_status_summary: gh.zone_status_summary ?? gh.zoneStatusSummary ?? {},
    node_status_summary: gh.node_status_summary ?? gh.nodeStatusSummary ?? {},
  }))
})

const zonesByGreenhouse = computed(() => {
  return (props.dashboard.problematicZones || []).reduce((acc, zone) => {
    const ghId = zone.greenhouse_id ?? zone.greenhouse?.id ?? 'global'
    if (!acc[ghId]) {
      acc[ghId] = []
    }
    acc[ghId].push(zone)
    return acc
  }, {} as Record<number | string, Zone[]>)
})

const activeZones = computed(() => {
  return (props.dashboard.zones || []).filter((z) => z.status === 'RUNNING')
})

const zonesNeedingAttention = computed(() => {
  return (props.dashboard.zones || []).filter((zone) =>
    zone.status === 'WARNING' ||
    zone.status === 'ALARM' ||
    (zone.alertsCount && zone.alertsCount > 0)
  )
})

const activeAlerts = computed(() => {
  return (props.dashboard.activeAlerts || []).slice(0, 6)
})

async function irrigateZone(zoneId: number) {
  try {
    await api.post(`/api/zones/${zoneId}/commands`, {
      type: 'FORCE_IRRIGATION',
      params: { duration_sec: 10 }
    })
    // TODO: Показать уведомление
  } catch (error) {
    logger.error('Failed to irrigate zone:', { error })
  }
}

async function resolveAlert(alertId: number) {
  try {
    await api.post(`/api/alerts/${alertId}/resolve`)
    // TODO: Обновить список и показать уведомление
  } catch (error) {
    logger.error('Failed to resolve alert:', { error })
  }
}

function resolveIssues(zoneId?: number) {
  if (!zoneId) return
  logger.info('Resolve issues for zone:', { zoneId })
}
</script>

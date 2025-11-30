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
        <Button size="sm" variant="primary" @click="showCreateModal = true">Новая теплица</Button>
        <Link href="/logs">
          <Button size="sm" variant="secondary">Служебные логи</Button>
        </Link>
        <Link href="/zones">
          <Button size="sm" variant="outline">Все зоны</Button>
        </Link>
      </div>
    </div>

    <div class="grid gap-4 grid-cols-1 md:grid-cols-2">
      <GreenhouseStatusCard
        v-for="gh in enrichedGreenhouses"
        :key="gh.id"
        :greenhouse="gh"
        :problematic-zones="zonesByGreenhouse[gh.id] || []"
      />
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

    <!-- Мастер настройки -->
    <SetupWizardModal
      :show="showCreateModal"
      @close="showCreateModal = false"
      @created="handleGreenhouseCreated"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Link } from '@inertiajs/vue3'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import Badge from '@/Components/Badge.vue'
import GreenhouseStatusCard from '@/Components/GreenhouseStatusCard.vue'
import SetupWizardModal from '@/Components/SetupWizardModal.vue'
import { translateStatus } from '@/utils/i18n'
import { logger } from '@/utils/logger'
import type { Zone } from '@/types'

interface DashboardProps {
  dashboard: {
    zones?: Zone[]
    greenhouses?: Array<Record<string, any>>
    problematicZones?: Array<Zone & { greenhouse?: { id: number; name: string } }>
  }
}

const props = defineProps<DashboardProps>()

const showCreateModal = ref(false)

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

const zonesNeedingAttention = computed(() => {
  return (props.dashboard.zones || []).filter((zone) =>
    zone.status === 'WARNING' ||
    zone.status === 'ALARM' ||
    (zone.alertsCount && zone.alertsCount > 0)
  )
})

function resolveIssues(zoneId?: number) {
  if (!zoneId) return
  logger.info('Resolve issues for zone:', { zoneId })
}

function handleGreenhouseCreated(greenhouse: any) {
  logger.info('Greenhouse created from modal:', greenhouse)
  // Модальное окно уже обновит страницу через router.reload()
}
</script>

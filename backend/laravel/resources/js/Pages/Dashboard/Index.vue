<template>
  <AppLayout>
    <template #default>
      <h1 class="text-lg font-semibold mb-4">Dashboard</h1>
      
      <!-- Основные статистики -->
      <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 mb-6">
        <Card>
          <div class="text-neutral-400 text-sm mb-1">Теплицы</div>
          <div class="text-3xl font-bold">{{ dashboard.greenhousesCount }}</div>
        </Card>
        <Card>
          <div class="text-neutral-400 text-sm mb-1">Зоны</div>
          <div class="text-3xl font-bold">{{ dashboard.zonesCount }}</div>
          <div v-if="zonesStatusSummary" class="text-xs text-neutral-500 mt-1">
            <span v-if="zonesStatusSummary.RUNNING">RUNNING: {{ zonesStatusSummary.RUNNING }}</span>
            <span v-if="zonesStatusSummary.PAUSED" class="ml-2">PAUSED: {{ zonesStatusSummary.PAUSED }}</span>
            <span v-if="zonesStatusSummary.ALARM" class="ml-2 text-red-400">ALARM: {{ zonesStatusSummary.ALARM }}</span>
            <span v-if="zonesStatusSummary.WARNING" class="ml-2 text-amber-400">WARNING: {{ zonesStatusSummary.WARNING }}</span>
          </div>
        </Card>
        <Card>
          <div class="text-neutral-400 text-sm mb-1">Устройства</div>
          <div class="text-3xl font-bold">{{ dashboard.devicesCount }}</div>
          <div v-if="nodesStatusSummary" class="text-xs text-neutral-500 mt-1">
            <span v-if="nodesStatusSummary.online" class="text-emerald-400">ONLINE: {{ nodesStatusSummary.online }}</span>
            <span v-if="nodesStatusSummary.offline" class="ml-2 text-red-400">OFFLINE: {{ nodesStatusSummary.offline }}</span>
          </div>
        </Card>
        <Card>
          <div class="text-neutral-400 text-sm mb-1">Активные алерты</div>
          <div class="text-3xl font-bold" :class="dashboard.alertsCount > 0 ? 'text-red-400' : 'text-emerald-400'">
            {{ dashboard.alertsCount }}
          </div>
        </Card>
      </div>

      <!-- Теплицы -->
      <div v-if="hasGreenhouses" class="mb-6">
        <h2 class="text-md font-semibold mb-3">Теплицы</h2>
        <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          <Card v-for="gh in dashboard.greenhouses" :key="gh.id" class="hover:border-neutral-700 transition-colors">
            <div class="flex items-start justify-between">
              <div>
                <div class="text-sm font-semibold">{{ gh.name }}</div>
                <div class="text-xs text-neutral-400 mt-1">
                  <span v-if="gh.type">{{ gh.type }}</span>
                  <span v-if="gh.uid" class="ml-2">UID: {{ gh.uid }}</span>
                </div>
              </div>
            </div>
            <div class="mt-3 text-xs text-neutral-400">
              <div>Зон: {{ gh.zones_count || 0 }}</div>
              <div class="text-emerald-400">Запущено: {{ gh.zones_running || 0 }}</div>
            </div>
          </Card>
        </div>
      </div>

      <!-- Проблемные зоны -->
      <div v-if="hasProblematicZones" class="mb-6">
        <h2 class="text-md font-semibold mb-3">Проблемные зоны</h2>
        <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          <Card v-for="zone in dashboard.problematicZones" :key="zone.id" class="hover:border-neutral-700 transition-colors">
            <div class="flex items-start justify-between mb-2">
              <div>
                <div class="text-sm font-semibold">{{ zone.name }}</div>
                <div v-if="zone.greenhouse" class="text-xs text-neutral-400 mt-1">
                  {{ zone.greenhouse.name }}
                </div>
              </div>
              <Badge :variant="zone.status === 'ALARM' ? 'danger' : 'warning'">
                {{ zone.status }}
              </Badge>
            </div>
            <div v-if="zone.description" class="text-xs text-neutral-400 mb-2">{{ zone.description }}</div>
            <div v-if="zone.alerts_count > 0" class="text-xs text-red-400">
              Активных алертов: {{ zone.alerts_count }}
            </div>
            <div class="mt-3">
              <Link :href="`/zones/${zone.id}`">
                <Button size="sm" variant="secondary">Подробнее</Button>
              </Link>
            </div>
          </Card>
        </div>
      </div>
      <div v-else class="mb-6">
        <Card>
          <div class="text-sm text-neutral-400">Нет проблемных зон</div>
        </Card>
      </div>
    </template>
    <template #context>
      <div class="h-full flex flex-col">
        <div class="text-neutral-300 font-medium mb-3">Последние алерты</div>
        <div v-if="hasAlerts" class="space-y-2 flex-1 overflow-y-auto">
          <div v-for="a in dashboard.latestAlerts" :key="a.id" class="rounded-lg border border-neutral-800 bg-neutral-925 p-3">
            <div class="flex items-start justify-between mb-1">
              <Badge :variant="a.status === 'active' ? 'danger' : 'neutral'" class="text-xs">
                {{ a.status }}
              </Badge>
              <span class="text-xs text-neutral-500">{{ formatTime(a.created_at) }}</span>
            </div>
            <div class="text-xs text-neutral-400 mb-1">{{ a.type }}</div>
            <div v-if="a.zone" class="text-xs text-neutral-500 mb-1">
              Зона: <Link :href="`/zones/${a.zone.id}`" class="text-sky-400 hover:underline">{{ a.zone.name }}</Link>
            </div>
            <div v-else-if="a.zone_id" class="text-xs text-neutral-500 mb-1">
              Зона ID: {{ a.zone_id }}
            </div>
            <div v-if="a.details && a.details.message" class="text-sm text-neutral-300 mt-1">
              {{ a.details.message }}
            </div>
          </div>
        </div>
        <div v-else class="text-neutral-500 text-sm">Нет алертов</div>
      </div>
    </template>
  </AppLayout>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { Link } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'

const props = defineProps({
  dashboard: {
    type: Object,
    required: true
  }
})

const zonesStatusSummary = computed(() => props.dashboard.zonesByStatus || {})
const nodesStatusSummary = computed(() => props.dashboard.nodesByStatus || {})
const hasAlerts = computed(() => {
  const alerts = props.dashboard.latestAlerts
  return alerts && Array.isArray(alerts) && alerts.length > 0
})
const hasGreenhouses = computed(() => {
  const gh = props.dashboard.greenhouses
  return gh && Array.isArray(gh) && gh.length > 0
})
const hasProblematicZones = computed(() => {
  const zones = props.dashboard.problematicZones
  return zones && Array.isArray(zones) && zones.length > 0
})

// Debug: проверка данных
onMounted(() => {
  console.log('Dashboard data:', props.dashboard)
  console.log('Latest alerts:', props.dashboard.latestAlerts)
  console.log('Alerts count:', props.dashboard.latestAlerts?.length)
  console.log('Has alerts:', hasAlerts.value)
  console.log('Greenhouses:', props.dashboard.greenhouses)
  console.log('Has greenhouses:', hasGreenhouses.value)
  console.log('Problematic zones:', props.dashboard.problematicZones)
  console.log('Has problematic zones:', hasProblematicZones.value)
})

function formatTime(dateString) {
  if (!dateString) return ''
  const date = new Date(dateString)
  const now = new Date()
  const diffMs = now - date
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)
  
  if (diffMins < 1) return 'только что'
  if (diffMins < 60) return `${diffMins} мин назад`
  if (diffHours < 24) return `${diffHours} ч назад`
  if (diffDays < 7) return `${diffDays} дн назад`
  return date.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}
</script>


<template>
  <div class="space-y-6">
    <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
      <h1 class="text-lg font-semibold">Панель наблюдателя</h1>
    </div>

    <!-- Общий обзор системы -->
    <Card class="bg-[color:var(--bg-elevated)] border-[color:var(--border-muted)]">
      <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        <div>
          <div class="text-[color:var(--text-muted)] text-sm mb-1">Система</div>
          <div class="text-2xl font-bold text-[color:var(--accent-green)]">✅ Онлайн</div>
        </div>
        <div data-testid="dashboard-zones-count">
          <div class="text-[color:var(--text-muted)] text-sm mb-1">Зоны</div>
          <div class="text-2xl font-bold">{{ totalZonesCount }}</div>
          <div class="text-xs text-[color:var(--text-muted)] mt-1">
            {{ activeZonesCount }} активных
          </div>
        </div>
        <div>
          <div class="text-[color:var(--text-muted)] text-sm mb-1">Устройства</div>
          <div class="text-2xl font-bold">{{ totalDevicesCount }}</div>
          <div class="text-xs text-[color:var(--text-muted)] mt-1">
            <span class="text-[color:var(--accent-green)]">{{ onlineDevicesCount }} онлайн</span>
            <span v-if="offlineDevicesCount > 0" class="text-[color:var(--accent-red)] ml-2">
              {{ offlineDevicesCount }} офлайн
            </span>
          </div>
        </div>
        <div data-testid="dashboard-alerts-count">
          <div class="text-[color:var(--text-muted)] text-sm mb-1">Активные алерты</div>
          <div class="text-2xl font-bold" :class="activeAlertsCount > 0 ? 'text-[color:var(--accent-red)]' : 'text-[color:var(--accent-green)]'">
            {{ activeAlertsCount }}
          </div>
        </div>
      </div>
    </Card>

    <!-- Все зоны -->
    <div class="space-y-4">
      <h2 class="text-md font-semibold">Все зоны</h2>
      <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        <Card
          v-for="zone in allZones"
          :key="zone.id"
          class="hover:border-[color:var(--border-strong)] transition-colors"
        >
          <div class="flex items-start justify-between mb-3">
            <div>
              <div class="text-sm font-semibold">{{ zone.name }}</div>
              <div v-if="zone.greenhouse" class="text-xs text-[color:var(--text-muted)] mt-1">
                {{ zone.greenhouse.name }}
              </div>
            </div>
            <Badge :variant="getStatusVariant(zone.status)">
              {{ translateStatus(zone.status) }}
            </Badge>
          </div>
          
          <!-- Метрики -->
          <div class="grid grid-cols-2 gap-2 text-xs mb-3">
            <div v-if="zone.telemetry?.ph !== null && zone.telemetry?.ph !== undefined && typeof zone.telemetry.ph === 'number'">
              <span class="text-[color:var(--text-muted)]">pH:</span>
              <span class="ml-1 font-medium">{{ zone.telemetry.ph.toFixed(2) }}</span>
            </div>
            <div v-if="zone.telemetry?.ec !== null && zone.telemetry?.ec !== undefined && typeof zone.telemetry.ec === 'number'">
              <span class="text-[color:var(--text-muted)]">EC:</span>
              <span class="ml-1 font-medium">{{ zone.telemetry.ec.toFixed(2) }}</span>
            </div>
            <div v-if="zone.telemetry?.temperature !== null && zone.telemetry?.temperature !== undefined">
              <span class="text-[color:var(--text-muted)]">Темп:</span>
              <span class="ml-1 font-medium">{{ zone.telemetry.temperature.toFixed(1) }}°C</span>
            </div>
            <div v-if="zone.telemetry?.humidity !== null && zone.telemetry?.humidity !== undefined">
              <span class="text-[color:var(--text-muted)]">Влаж:</span>
              <span class="ml-1 font-medium">{{ zone.telemetry.humidity.toFixed(0) }}%</span>
            </div>
          </div>
          
          <Link :href="`/zones/${zone.id}`">
            <Button size="sm" variant="secondary" class="w-full">Просмотр</Button>
          </Link>
        </Card>
      </div>
    </div>

    <!-- Активные алерты -->
    <div v-if="activeAlerts.length > 0" class="space-y-4">
      <h2 class="text-md font-semibold">Активные алерты</h2>
      <Card>
        <div class="space-y-2">
          <div
            v-for="alert in activeAlerts"
            :key="alert.id"
            class="p-3 bg-[color:var(--bg-elevated)] rounded-lg border border-[color:var(--badge-danger-border)]"
          >
            <div class="text-sm font-semibold text-[color:var(--accent-red)]">{{ alert.type }}</div>
            <div class="text-xs text-[color:var(--text-muted)] mt-1">
              Зона: {{ alert.zone?.name || `ID ${alert.zone_id}` }}
            </div>
            <div class="text-xs text-[color:var(--text-dim)] mt-1">
              {{ formatTime(alert.created_at) }}
            </div>
          </div>
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
import type { Zone, Alert, Device } from '@/types'

interface Props {
  dashboard: {
    zones?: Zone[]
    devices?: Device[]
    activeAlerts?: Alert[]
    zonesByStatus?: Record<string, number>
    nodesByStatus?: Record<string, number>
  }
}

const props = defineProps<Props>()

const totalZonesCount = computed(() => props.dashboard.zones?.length || 0)
const activeZonesCount = computed(() => props.dashboard.zonesByStatus?.RUNNING || 0)
const totalDevicesCount = computed(() => props.dashboard.devices?.length || 0)
const onlineDevicesCount = computed(() => props.dashboard.nodesByStatus?.online || 0)
const offlineDevicesCount = computed(() => props.dashboard.nodesByStatus?.offline || 0)
const activeAlertsCount = computed(() => props.dashboard.activeAlerts?.length || 0)

const allZones = computed(() => props.dashboard.zones || [])
const activeAlerts = computed(() => props.dashboard.activeAlerts || [])

function getStatusVariant(status: string): 'success' | 'warning' | 'danger' | 'info' | 'neutral' {
  switch (status) {
    case 'RUNNING':
      return 'success'
    case 'WARNING':
      return 'warning'
    case 'ALARM':
      return 'danger'
    case 'PAUSED':
      return 'info'
    default:
      return 'neutral'
  }
}
</script>

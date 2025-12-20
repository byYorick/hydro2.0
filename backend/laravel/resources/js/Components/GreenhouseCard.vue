<template>
  <Card class="bg-[color:var(--bg-surface-strong)]">
    <div class="space-y-6">
      <!-- Заголовок -->
      <div class="flex items-start justify-between">
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2 mb-2">
            <h2 class="text-xl font-semibold truncate">{{ greenhouse.name }}</h2>
            <Badge v-if="greenhouse.type" variant="neutral" class="shrink-0">
              {{ greenhouse.type }}
            </Badge>
          </div>
          <p v-if="greenhouse.description" class="text-sm text-[color:var(--text-muted)]">
            {{ greenhouse.description }}
          </p>
        </div>
      </div>

      <!-- Метрики теплицы -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div class="bg-[color:var(--bg-elevated)] rounded-lg p-3">
          <div class="text-xs text-[color:var(--text-muted)] mb-1">Зоны</div>
          <div class="text-2xl font-bold text-[color:var(--text-primary)]">{{ zones.length }}</div>
        </div>
        <div class="bg-[color:var(--bg-elevated)] rounded-lg p-3">
          <div class="text-xs text-[color:var(--text-muted)] mb-1">Активные циклы</div>
          <div class="text-2xl font-bold text-[color:var(--accent-green)]">{{ activeCyclesCount }}</div>
        </div>
        <div class="bg-[color:var(--bg-elevated)] rounded-lg p-3">
          <div class="text-xs text-[color:var(--text-muted)] mb-1">Узлы онлайн</div>
          <div class="text-2xl font-bold text-[color:var(--accent-cyan)]">{{ nodesOnlineTotal }}</div>
        </div>
        <div class="bg-[color:var(--bg-elevated)] rounded-lg p-3">
          <div class="text-xs text-[color:var(--text-muted)] mb-1">Алерты</div>
          <div class="text-2xl font-bold" :class="alertsTotal > 0 ? 'text-[color:var(--accent-red)]' : 'text-[color:var(--text-dim)]'">
            {{ alertsTotal }}
          </div>
        </div>
      </div>

      <!-- Зоны -->
      <div class="space-y-3">
        <div class="flex items-center justify-between">
          <h3 class="text-sm font-semibold text-[color:var(--text-primary)]">Зоны</h3>
          <span class="text-xs text-[color:var(--text-muted)]">{{ zones.length }} зон</span>
        </div>
        
        <div v-if="zones.length > 0" class="grid gap-3 md:grid-cols-2">
          <ZoneCycleCard
            v-for="zone in zones"
            :key="zone.id"
            :zone="zone"
          />
        </div>
        <div v-else class="text-sm text-[color:var(--text-muted)] py-8 text-center">
          Нет зон в этой теплице
        </div>
      </div>
    </div>
  </Card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Card from './Card.vue'
import Badge from './Badge.vue'
import ZoneCycleCard from './ZoneCycleCard.vue'

interface ZoneData {
  id: number
  name: string
  status: string
  cycle_progress?: number | null
  alerts_count?: number
  nodes_online?: number
}

interface Props {
  greenhouse: {
    id: number
    name: string
    description?: string | null
    type?: string | null
  }
  zones: ZoneData[]
}

const props = defineProps<Props>()

const activeCyclesCount = computed(() => {
  return props.zones.filter(zone => zone.cycle_progress !== null && zone.cycle_progress !== undefined).length
})

const nodesOnlineTotal = computed(() => {
  return props.zones.reduce((sum, zone) => sum + (zone.nodes_online || 0), 0)
})

const alertsTotal = computed(() => {
  return props.zones.reduce((sum, zone) => sum + (zone.alerts_count || 0), 0)
})
</script>

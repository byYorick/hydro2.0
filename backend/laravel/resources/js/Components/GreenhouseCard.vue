<template>
  <Card class="bg-gradient-to-br from-neutral-900 to-neutral-925">
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
          <p v-if="greenhouse.description" class="text-sm text-neutral-400">
            {{ greenhouse.description }}
          </p>
        </div>
      </div>

      <!-- Метрики теплицы -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div class="bg-neutral-800/50 rounded-lg p-3">
          <div class="text-xs text-neutral-400 mb-1">Зоны</div>
          <div class="text-2xl font-bold text-neutral-100">{{ zones.length }}</div>
        </div>
        <div class="bg-neutral-800/50 rounded-lg p-3">
          <div class="text-xs text-neutral-400 mb-1">Активные циклы</div>
          <div class="text-2xl font-bold text-emerald-400">{{ activeCyclesCount }}</div>
        </div>
        <div class="bg-neutral-800/50 rounded-lg p-3">
          <div class="text-xs text-neutral-400 mb-1">Узлы онлайн</div>
          <div class="text-2xl font-bold text-sky-400">{{ nodesOnlineTotal }}</div>
        </div>
        <div class="bg-neutral-800/50 rounded-lg p-3">
          <div class="text-xs text-neutral-400 mb-1">Алерты</div>
          <div class="text-2xl font-bold" :class="alertsTotal > 0 ? 'text-red-400' : 'text-neutral-400'">
            {{ alertsTotal }}
          </div>
        </div>
      </div>

      <!-- Зоны -->
      <div class="space-y-3">
        <div class="flex items-center justify-between">
          <h3 class="text-sm font-semibold text-neutral-200">Зоны</h3>
          <span class="text-xs text-neutral-400">{{ zones.length }} зон</span>
        </div>
        
        <div v-if="zones.length > 0" class="grid gap-3 md:grid-cols-2">
          <ZoneCycleCard
            v-for="zone in zones"
            :key="zone.id"
            :zone="zone"
          />
        </div>
        <div v-else class="text-sm text-neutral-400 py-8 text-center">
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

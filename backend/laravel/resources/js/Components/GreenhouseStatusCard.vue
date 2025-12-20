<template>
  <Card class="flex flex-col gap-4 surface-card-hover transition-all duration-200">
    <div class="flex justify-between gap-4 items-start min-w-0">
      <div class="min-w-0 flex-1">
        <div class="text-xs uppercase text-[color:var(--text-dim)] tracking-[0.2em]">{{ greenhouse.type || 'Теплица' }}</div>
        <h3 class="text-lg font-semibold text-[color:var(--text-primary)] truncate">{{ greenhouse.name }}</h3>
        <p v-if="greenhouse.description" class="text-xs text-[color:var(--text-dim)] mt-1 max-h-10 overflow-hidden">
          {{ greenhouse.description }}
        </p>
      </div>
      <div class="text-right text-xs text-[color:var(--text-muted)] flex-shrink-0">
        <div>Зон: <span class="font-semibold text-[color:var(--text-primary)]">{{ greenhouse.zones_count || 0 }}</span></div>
        <div class="mt-1">Активных: <span class="font-semibold text-[color:var(--accent-green)]">{{ greenhouse.zones_running || 0 }}</span></div>
      </div>
    </div>

    <div class="grid grid-cols-2 gap-2 md:grid-cols-4 text-xs text-[color:var(--text-muted)]">
      <div v-for="status in zoneStatusList" :key="status.key" class="surface-strong p-3 rounded-xl border border-[color:var(--border-muted)] min-w-0 overflow-hidden">
        <div class="flex items-center justify-between gap-2 min-w-0">
          <div class="min-w-0 flex-1 overflow-hidden">
            <Badge :variant="status.badge" size="xs" class="max-w-full overflow-hidden">{{ status.label }}</Badge>
          </div>
          <span class="text-sm font-semibold text-[color:var(--text-primary)] flex-shrink-0 whitespace-nowrap">{{ status.value }}</span>
        </div>
      </div>
    </div>

    <div class="grid grid-cols-2 gap-2 text-xs">
      <div class="surface-strong p-3 rounded-xl border border-[color:var(--border-muted)]">
        <div class="text-[color:var(--text-muted)] text-[0.65rem] uppercase tracking-[0.2em] mb-2">Узлы</div>
        <div class="flex items-center justify-between">
          <span>Онлайн</span>
          <span class="font-semibold text-[color:var(--accent-green)]">{{ nodeSummary.online }}</span>
        </div>
        <div class="flex items-center justify-between mt-1">
          <span>Офлайн</span>
          <span class="font-semibold text-[color:var(--accent-red)]">{{ nodeSummary.offline }}</span>
        </div>
      </div>
      <div class="surface-strong p-3 rounded-xl border border-[color:var(--border-muted)]">
        <div class="text-[color:var(--text-muted)] text-[0.65rem] uppercase tracking-[0.2em] mb-2">Оповещения</div>
        <div class="text-2xl font-bold text-[color:var(--accent-amber)] text-right">{{ greenhouse.alerts_count ?? 0 }}</div>
        <div class="text-xs text-[color:var(--text-dim)] text-right">активных</div>
      </div>
    </div>

    <div v-if="highlightZones.length" class="space-y-2">
      <div class="text-xs uppercase tracking-[0.2em] text-[color:var(--text-dim)]">Зоны, требующие внимания</div>
      <div class="space-y-1">
        <div
          v-for="zone in highlightZones"
          :key="zone.id"
          class="flex items-center justify-between gap-2 p-3 rounded-xl border border-[color:var(--border-muted)] surface-strong min-w-0 overflow-hidden"
        >
          <div class="min-w-0 flex-1">
            <div class="text-sm font-semibold truncate">{{ zone.name }}</div>
            <div class="text-xs text-[color:var(--text-dim)] truncate">{{ zone.description || 'Без описания' }}</div>
          </div>
          <Badge :variant="zone.status === 'ALARM' ? 'danger' : 'warning'" size="xs" class="flex-shrink-0">
            {{ zone.status }}
          </Badge>
        </div>
      </div>
    </div>

    <div class="flex flex-wrap gap-2 mt-2">
      <Link :href="`/greenhouses/${greenhouse.id}`" class="flex-1 min-w-[140px]">
        <Button size="sm" variant="outline" class="w-full">Открыть теплицу</Button>
      </Link>
      <Link href="/zones" class="flex-1 min-w-[140px]">
        <Button size="sm" variant="ghost" class="w-full">Зоны</Button>
      </Link>
    </div>
  </Card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Card from '@/Components/Card.vue'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import { Link } from '@inertiajs/vue3'

interface Props {
  greenhouse: {
    id: number
    name: string
    type?: string
    description?: string | null
    zones_count?: number
    zones_running?: number
    alerts_count?: number
    zone_status_summary?: Record<string, number>
    node_status_summary?: Record<string, number>
  }
  problematicZones?: Array<{ id: number; name: string; description?: string | null; status?: string }>
}

const props = defineProps<Props>()

const nodeSummary = computed(() => {
  const summary = props.greenhouse.node_status_summary || {}
  return {
    online: summary.online ?? 0,
    offline: summary.offline ?? 0,
  }
})

const zoneStatusList = computed(() => {
  const statusOrder = [
    { key: 'RUNNING', label: 'Запущено', badge: 'success' },
    { key: 'PAUSED', label: 'Пауза', badge: 'info' },
    { key: 'WARNING', label: 'Предупрежд.', badge: 'warning' },
    { key: 'ALARM', label: 'Тревога', badge: 'danger' },
  ]
  const summary = props.greenhouse.zone_status_summary || {}
  return statusOrder.map((item) => ({
    ...item,
    value: summary[item.key] ?? 0,
  }))
})

const highlightZones = computed(() => props.problematicZones || [])
</script>

<style scoped>
/* Обработка переполнения для Badge в статусах зон */
.surface-strong > div > div:first-child {
  max-width: 100%;
}

.surface-strong .inline-flex {
  display: inline-flex;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>

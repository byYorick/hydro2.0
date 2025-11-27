<template>
  <AppLayout>
    <div class="space-y-6">
      <header class="space-y-4">
        <div class="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <p class="text-xs uppercase tracking-[0.4em] text-neutral-500">
              {{ greenhouse.type || 'Теплица' }}
            </p>
            <h1 class="text-2xl font-semibold text-neutral-100">{{ greenhouse.name }}</h1>
            <p class="text-sm text-neutral-400 max-w-2xl mt-1">
              {{ greenhouse.description || 'Информационная панель по текущему состоянию теплицы и прикрепленным зонам.' }}
            </p>
          </div>
          <div class="flex items-center gap-3">
            <Link href="/zones">
              <Button size="sm" variant="outline">Все зоны</Button>
            </Link>
            <Button size="sm" variant="ghost" disabled>
              Синхронизация {{ greenhouse.timezone || 'UTC' }}
            </Button>
          </div>
        </div>
        <div class="grid gap-3 xs:grid-cols-2 md:grid-cols-4">
          <MetricCard label="Зоны" :value="zones.length" color="#38bdf8" status="success" subtitle="Общее количество зон" />
          <MetricCard label="Активные циклы" :value="activeCyclesCount" color="#4ade80" status="info" subtitle="С привязанными рецептами" />
          <MetricCard label="Узлы онлайн" :value="nodeSummary.online" color="#22d3ee" status="success" subtitle="Работает" />
          <MetricCard label="Оповещения" :value="activeAlerts" color="#f87171" status="danger" subtitle="Активных" />
        </div>
      </header>

      <section class="space-y-4">
        <div class="flex items-center justify-between">
          <div>
            <h2 class="text-base font-semibold">Зоны теплицы</h2>
            <p class="text-xs text-neutral-500">Панель наблюдения и управления.</p>
          </div>
          <span class="text-xs text-neutral-500">{{ zones.length }} зон</span>
        </div>
        <div class="grid gap-3 md:grid-cols-2">
          <ZoneCard
            v-for="zone in zones"
            :key="zone.id"
            :zone="zone"
            :telemetry="zone.telemetry"
          />
        </div>
      </section>

      <section class="space-y-4">
        <div class="flex items-center justify-between">
          <div>
            <h2 class="text-base font-semibold">Циклы</h2>
            <p class="text-xs text-neutral-500">Отслеживание фаз и прогресса рецептов.</p>
          </div>
          <span class="text-xs text-neutral-500">{{ cycles.length }} активных</span>
        </div>
        <div class="grid gap-3 md:grid-cols-2">
          <Card v-for="cycle in cycles" :key="cycle.zone_id" class="space-y-3">
            <div class="flex items-center justify-between">
              <div>
                <div class="text-sm font-semibold">{{ cycle.zone?.name }}</div>
                <div class="text-xs text-neutral-400">{{ cycle.recipe?.name }}</div>
              </div>
              <Badge :variant="cycle.progress >= 85 ? 'success' : cycle.progress >= 45 ? 'warning' : 'info'">
                {{ cycle.statusLabel }}
              </Badge>
            </div>
            <div class="text-xs text-neutral-400">
              Фаза {{ cycle.phaseIndex }} · Прогресс {{ cycle.progress.toFixed(1) }}%
            </div>
            <div class="h-2 rounded-full bg-neutral-900 overflow-hidden">
              <div
                class="h-full rounded-full bg-gradient-to-r from-emerald-500 to-sky-500 transition-all"
                :style="{ width: `${Math.min(Math.max(cycle.progress, 0), 100)}%` }"
              />
            </div>
          </Card>
        </div>
        <div v-if="cycles.length === 0" class="text-xs text-neutral-500">Нет активных циклов</div>
      </section>

      <section class="space-y-4">
        <div class="flex items-center justify-between">
          <div>
            <h2 class="text-base font-semibold">Узлы</h2>
            <p class="text-xs text-neutral-500">Состояние оборудования.</p>
          </div>
          <span class="text-xs text-neutral-500">{{ nodes.length }} устройств</span>
        </div>
        <div class="grid gap-3 md:grid-cols-2">
          <Card v-for="node in nodes" :key="node.id" class="space-y-2">
            <div class="flex items-center justify-between">
              <div>
                <div class="text-sm font-semibold">{{ node.name || node.uid }}</div>
                <div class="text-xs text-neutral-400">{{ node.zone?.name }}</div>
              </div>
              <Badge :variant="node.status === 'online' ? 'success' : 'danger'">
                {{ node.status }}
              </Badge>
            </div>
            <div class="text-xs text-neutral-400">Ф/В: {{ node.fw_version || '—' }}</div>
            <div class="text-xs text-neutral-400">Жизненный цикл: {{ node.lifecycle_state || 'Неизвестно' }}</div>
            <div class="text-xs text-neutral-400">Последний отклик: {{ formatTime(node.last_seen_at) }}</div>
          </Card>
        </div>
      </section>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Link } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import Badge from '@/Components/Badge.vue'
import MetricCard from '@/Components/MetricCard.vue'
import ZoneCard from '@/Pages/Zones/ZoneCard.vue'
import { formatTime } from '@/utils/formatTime'
import type { Zone } from '@/types'
import type { Device } from '@/types'
import type { ZoneTelemetry } from '@/types'

interface Props {
  greenhouse: {
    id: number
    name: string
    description?: string | null
    type?: string | null
    timezone?: string | null
  }
  zones: Array<Zone & {
    telemetry?: ZoneTelemetry | null
    alerts_count?: number
    nodes_online?: number
    nodes_offline?: number
    nodes_total?: number
  }>
  nodes: Array<Device & {
    last_seen_at?: string
  }>
  nodeSummary: {
    online: number
    offline: number
    total?: number
  }
  activeAlerts: number
}

const props = defineProps<Props>()

const cycles = computed(() => {
  return props.zones
    .filter((zone) => zone.recipe_instance && zone.recipe_instance.recipe)
    .map((zone) => ({
      zone_id: zone.id,
      zone,
      recipe: zone.recipe_instance?.recipe,
      phaseIndex: (zone.recipe_instance?.current_phase_index ?? 0) + 1,
      statusLabel: zone.recipe_instance?.phase_progress && zone.recipe_instance.phase_progress >= 85
        ? 'Старт' : zone.recipe_instance?.phase_progress && zone.recipe_instance.phase_progress >= 45
        ? 'В процессе' : 'Начало',
      progress: zone.recipe_instance?.phase_progress ?? 0,
    }))
})

const activeCyclesCount = computed(() => cycles.value.length)

const nodes = computed(() => props.nodes)
const zones = computed(() => props.zones)
const nodeSummary = computed(() => props.nodeSummary)

const activeAlerts = computed(() => props.activeAlerts ?? 0)
</script>
